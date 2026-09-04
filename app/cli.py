"""Befehle für die Kommandozeile, aufrufbar mit `flask <name>`."""

import click
from flask import Flask
from sqlalchemy import select

from .auth import MIN_PASSWORTLAENGE, passwort_setzen
from .extensions import db
from .kanaele import ALLE
from .models import Channel, User


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
