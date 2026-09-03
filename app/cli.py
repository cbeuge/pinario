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
