"""Befehle für die Kommandozeile, aufrufbar mit `flask <name>`."""

import pathlib
import re

import click
from flask import Flask
from sqlalchemy import select

from .auth import MIN_PASSWORTLAENGE, passwort_setzen
from .extensions import db
from .kanaele import ALLE
from .models import Channel, User


# Was ein Terminal beim Einfuegen mitschickt, ohne dass man es sieht.
# "Bracketed Paste": der eingefuegte Text wird in ESC[200~ und ESC[201~
# eingefasst, damit ein Programm Eingetipptes von Eingefuegtem
# unterscheiden kann. Bei einem versteckten Eingabefeld sieht man davon
# nichts, und die Sequenz landet mitten im Wert.
_EINFUEGE_MARKER = re.compile(r"\x1b\[20[01]~")


def _token_saeubern(roh: str) -> tuple[str, int]:
    """Macht aus einer Eingabe ein Token und zählt, was weg musste.

    Der Grund ist ein Fehler, der eine halbe Stunde kostet: ein Token mit
    Einfüge-Markern darin ergibt einen syntaktisch kaputten
    `Authorization`-Kopf. Pinterest antwortet darauf nicht mit "Token
    ungültig", sondern mit einer HTML-Fehlerseite seines CDN und einem 400 —
    und die sagt über die eigentliche Ursache gar nichts.

    Geprüft wird über `isprintable`, nicht über eine Liste verbotener
    Zeichen: ein Token besteht aus druckbaren Zeichen ohne Leerraum, und was
    das nicht ist, gehört nicht hinein. Eine Verbotsliste vergisst immer
    eins.
    """
    # Leerraum aussen zaehlt nicht mit: ein Zeilenende gehoert zur Eingabe
    # und ist kein Grund fuer eine Warnung. Gemeldet wird nur, was mitten im
    # Wert stand und dort nichts verloren hat.
    roh = (roh or "").strip()
    ohne_marker = _EINFUEGE_MARKER.sub("", roh)
    sauber = "".join(
        zeichen
        for zeichen in ohne_marker
        if zeichen.isprintable() and not zeichen.isspace()
    )
    return sauber, len(roh) - len(sauber)


def befehle_registrieren(app: Flask) -> None:
    @app.cli.command("passwort")
    @click.option("--benutzer", default="carsten", show_default=True)
    @click.password_option("--passwort", prompt=True, confirmation_prompt=True)
    def passwort_befehl(benutzer: str, passwort: str) -> None:
        """Legt den Nutzer an oder setzt sein Passwort neu.

        Ein Passwortwechsel beendet alle noch offenen Anmeldungen.
        """
        if len(passwort) < MIN_PASSWORTLAENGE:
            raise click.ClickException(
                f"Mindestens {MIN_PASSWORTLAENGE} Zeichen. Das ist der "
                "einzige Schutz vor der Tür."
            )

        nutzer = db.session.scalar(select(User).where(User.benutzername == benutzer))
        if nutzer is None:
            nutzer = User(benutzername=benutzer, passwort_hash="")
            db.session.add(nutzer)
            hinweis = f"Nutzer '{benutzer}' angelegt."
        else:
            hinweis = (
                f"Passwort von '{benutzer}' geändert, alte Anmeldungen sind beendet."
            )

        passwort_setzen(nutzer, passwort)
        db.session.commit()
        click.echo(hinweis)

    @app.cli.command("zeitplan")
    @click.option(
        "--trocken", is_flag=True,
        help="Nur sagen, was passieren würde. Fasst nichts an.",
    )
    @click.option(
        "--nur-planen", is_flag=True,
        help="Termine vergeben, aber nichts posten.",
    )
    def zeitplan_befehl(trocken: bool, nur_planen: bool) -> None:
        """Aufräumen, einplanen, posten.

        Das ist der Befehl, den der systemd-Timer alle fünf Minuten ruft.
        Von Hand vor allem mit --trocken interessant: dann steht da, was
        beim nächsten echten Lauf rausginge, ohne dass etwas rausgeht.
        """
        from .zeitplan import einplanen, lauf, zurueckholen

        if nur_planen:
            zurueck = zurueckholen()
            vergeben = einplanen()
            click.echo(f"{zurueck} zurückgeholt, {vergeben} Termin(e) vergeben.")
            return

        bericht = lauf(trocken=trocken)
        if trocken:
            click.echo(f"Trocken: {bericht['gepostet']} Beitrag/Beiträge wären dran.")
        else:
            click.echo(
                f"{bericht['zurueckgeholt']} zurückgeholt, "
                f"{bericht['eingeplant']} eingeplant, "
                f"{bericht['gepostet']} gepostet, "
                f"{bericht['gescheitert']} gescheitert."
            )
        if bericht["uebersprungen"]:
            # Kein Fehler, aber der häufigste Grund dafür, dass nichts
            # passiert. Muss dastehen, sonst sucht man im Code. Die beiden
            # Ursachen stehen getrennt da, weil sie Verschiedenes verlangen:
            # verbinden, oder herausfinden, warum das Erneuern scheitert.
            click.echo(f"{bericht['uebersprungen']} übersprungen.")
            if bericht["kein_konto"]:
                kanaele = ", ".join(sorted(set(bericht["kein_konto"])))
                click.echo(f"  Kein Konto verbunden: {kanaele}.")
            if bericht["zugang_abgelaufen"]:
                kanaele = ", ".join(sorted(set(bericht["zugang_abgelaufen"])))
                click.echo(
                    f"  Zugang abgelaufen und nicht erneuerbar: {kanaele}. "
                    "Konto neu verbinden."
                )

    @app.cli.command("token-eintragen")
    @click.argument("kanal_key")
    @click.option(
        "--datei", type=click.Path(exists=True, dir_okay=False),
        help="Das Token aus einer Datei lesen statt es einzutippen. Der "
             "zuverlässigste Weg über ssh, siehe die Anmerkung zum Einfügen.",
    )
    @click.password_option(
        "--token", prompt=False, confirmation_prompt=False,
        help="Wird abgefragt statt als Argument genommen, damit es nicht in "
             "der Verlaufsdatei der Shell landet.",
    )
    def token_eintragen(kanal_key: str, datei: str | None, token: str) -> None:
        """Trägt ein von Hand erzeugtes Zugriffstoken als Konto ein.

        Für den Fall, dass eine Plattform ein Token zum Ausprobieren
        ausgibt, bevor die App freigeschaltet ist. Bei Pinterest ist das
        eins mit **Leserechten**: Konto und Boards abfragen geht damit,
        einen Pin schreiben nicht.

        Der normale Weg ist und bleibt OAuth über `/einstellungen`. Ein so
        eingetragenes Token hat kein Erneuerungs-Token und keinen bekannten
        Ablauf; es steht deshalb ohne `expires_at` da, damit der Zeitplan
        nicht versucht, etwas zu erneuern, was sich nicht erneuern lässt.
        """
        from .kanaele import BEKANNT, KanalFehler, kanal
        from .models import Account

        if datei:
            token = pathlib.Path(datei).read_text(encoding="utf-8")
        elif not token:
            token = click.prompt("Zugriffstoken", hide_input=True, default="")

        token, entfernt = _token_saeubern(token)
        if not token:
            raise click.ClickException("Kein Token eingegeben.")
        if entfernt:
            # Muss dastehen. Wer nicht weiß, dass etwas entfernt wurde,
            # sucht den Fehler später im Token statt im Terminal.
            click.echo(
                f"Hinweis: {entfernt} unsichtbare(s) Zeichen entfernt. Beim "
                "Einfügen schickt das Terminal Steuerzeichen mit, die sonst "
                "im Kopf der Anfrage landen."
            )
        click.echo(f"Token: {len(token)} Zeichen, beginnt mit {token[:5]}…")
        if kanal_key not in BEKANNT:
            raise click.ClickException(
                f"Für '{kanal_key}' gibt es keinen Adapter. Bekannt: "
                + ", ".join(sorted(BEKANNT))
            )

        zeile = db.session.scalar(select(Channel).where(Channel.key == kanal_key))
        if zeile is None:
            raise click.ClickException(
                f"'{kanal_key}' steht nicht in der Tabelle channels."
            )

        adapter = kanal(kanal_key)
        # Erst fragen, dann speichern: ein Token, das die Plattform nicht
        # annimmt, soll gar nicht erst in der Datenbank landen. Sonst steht
        # dort ein Konto, das der Zeitplan für verbunden hält.
        try:
            name = adapter._kontoname(token)  # noqa: SLF001
        except KanalFehler as fehler:
            raise click.ClickException(str(fehler)) from fehler

        konto = db.session.scalars(
            select(Account)
            .where(Account.channel_id == zeile.id)
            .order_by(Account.id)
        ).first()
        if konto is None:
            konto = Account(channel_id=zeile.id, access_token="")
            db.session.add(konto)

        konto.zugang = token
        konto.erneuerung = ""
        konto.expires_at = None
        konto.account_name = name or None
        db.session.commit()

        click.echo(f"{zeile.name} verbunden als {name or 'ohne Namen'}.")
        click.echo(
            "Achtung: ein von Hand erzeugtes Token laeuft irgendwann ab und "
            "laesst sich nicht erneuern. Sobald die App freigeschaltet ist, "
            "ueber /einstellungen richtig verbinden."
        )
        if datei:
            click.echo(
                f"Die Datei {datei} enthaelt jetzt ein gueltiges Token. "
                "Loeschen."
            )

    @app.cli.command("kanaele-abgleichen")
    def kanaele_abgleichen() -> None:
        """Trägt fehlende Kanäle in `channels` nach.

        Wiederholbar: vorhandene Zeilen bleiben, wie sie sind. Die Migration
        macht dasselbe beim ersten Aufsetzen; dieser Befehl ist für den Fall,
        dass später ein Kanal dazukommt.
        """
        vorhanden = {
            k for k in db.session.scalars(select(Channel.key)).all()
        }
        neu = 0
        for key, name in ALLE:
            if key not in vorhanden:
                db.session.add(Channel(key=key, name=name))
                neu += 1
        db.session.commit()
        click.echo(f"{neu} Kanal/Kanäle ergänzt, {len(vorhanden)} waren schon da.")
