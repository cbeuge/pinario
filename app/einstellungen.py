"""Werte, die sich im Betrieb ändern, an einer Stelle.

Die `.env` bleibt für alles, was zum Aufsetzen gehört und sich danach nicht
mehr rührt: Datenbank, SECRET_KEY, Tresor-Schlüssel. Was sich im Betrieb
ändert, gehört hierher — sonst hieße jeder Wechsel: anmelden per ssh, Datei
bearbeiten, Dienst neu starten.

**Geheime Werte liegen verschlüsselt in der Datenbank**, mit demselben
Tresor wie die OAuth-Token. Welche geheim sind, entscheidet allein `GEHEIM`
weiter unten. Ein Schlüssel im Klartext stünde sonst in jeder Sicherung.

**Die Einstellung schlägt die `.env`.** Wer einen Wert hier setzt, will
genau den; die `.env` ist ab dann nur noch der Rückfall für den Fall, dass
in der Datenbank nichts steht. Andersherum wäre die Oberfläche eine Maske,
die etwas anzeigt, das nicht gilt.
"""

from sqlalchemy import select

from .extensions import db
from .models import Einstellung
from .tresor import TresorFehler, aufschliessen, einschliessen

GEMINI_SCHLUESSEL = "gemini_api_key"

# Was verschlüsselt abgelegt wird. Eine Menge und keine Spalte am Modell:
# so lässt sich die Frage an genau einer Stelle beantworten, statt an jeder
# Schreibstelle noch einmal.
GEHEIM = frozenset({GEMINI_SCHLUESSEL})


def hole(name: str) -> str:
    """Der gespeicherte Wert, oder "" wenn nichts gesetzt ist."""
    eintrag = db.session.get(Einstellung, name)
    if eintrag is None or not eintrag.wert:
        return ""
    if name not in GEHEIM:
        return eintrag.wert
    try:
        return aufschliessen(eintrag.wert)
    except TresorFehler:
        # Der Tresor-Schlüssel wurde gewechselt. Nicht durchreichen: der
        # Aufrufer will hier einen Wert oder keinen, und ein unlesbarer Wert
        # ist keiner. Sichtbar wird es trotzdem, weil `lesbar` es prüft.
        return ""


def lesbar(name: str) -> bool:
    """Ob ein gespeicherter geheimer Wert sich noch entschlüsseln lässt.

    Trennt die beiden Fälle, die sonst gleich aussehen: nichts gespeichert,
    oder gespeichert und nach einem Wechsel des TRESOR_SCHLUESSEL unlesbar.
    """
    eintrag = db.session.get(Einstellung, name)
    if eintrag is None or not eintrag.wert:
        return True
    if name not in GEHEIM:
        return True
    try:
        aufschliessen(eintrag.wert)
    except TresorFehler:
        return False
    return True


def gesetzt(name: str) -> bool:
    eintrag = db.session.get(Einstellung, name)
    return eintrag is not None and bool(eintrag.wert)


def setze(name: str, wert: str) -> None:
    eintrag = db.session.get(Einstellung, name)
    if eintrag is None:
        eintrag = Einstellung(schluessel=name)
        db.session.add(eintrag)
    eintrag.wert = einschliessen(wert) if name in GEHEIM else wert
    db.session.commit()


def entferne(name: str) -> None:
    eintrag = db.session.get(Einstellung, name)
    if eintrag is not None:
        db.session.delete(eintrag)
        db.session.commit()


def alle() -> dict[str, str]:
    """Nur für Prüfskripte und die Kommandozeile, nicht für die Oberfläche."""
    return {
        eintrag.schluessel: eintrag.wert
        for eintrag in db.session.scalars(select(Einstellung))
    }


# --- Der Gemini-Schlüssel ----------------------------------------------


def gemini_api_key() -> str:
    """Erst die Einstellung, dann die `.env`.

    Die Reihenfolge ist die eigentliche Aussage: was in der Oberfläche steht,
    gilt. Die `.env` bleibt als Rückfall, damit ein frisch aufgesetzter
    Server nicht erst durch die Maske muss.
    """
    from flask import current_app

    return hole(GEMINI_SCHLUESSEL) or current_app.config.get("GEMINI_API_KEY", "")


def gemini_herkunft() -> str:
    """Woher der Schlüssel gerade kommt: "einstellung", "env" oder "".

    Steht in der Oberfläche, weil sonst niemand versteht, warum das
    Erzeugen läuft, obwohl das Feld leer aussieht.
    """
    from flask import current_app

    if hole(GEMINI_SCHLUESSEL):
        return "einstellung"
    if current_app.config.get("GEMINI_API_KEY", ""):
        return "env"
    return ""


def verdeckt(wert: str) -> str:
    """Zeigt genug zum Wiedererkennen und zu wenig zum Benutzen."""
    if not wert:
        return ""
    if len(wert) <= 8:
        return "…" * 4
    return f"{wert[:4]}…{wert[-4:]}"
