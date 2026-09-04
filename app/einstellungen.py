"""Werte, die sich im Betrieb ändern, an einer Stelle.

Die `.env` bleibt für alles, was zum Aufsetzen gehört und sich danach nicht
mehr rührt: Datenbank, SECRET_KEY, Tresor-Schlüssel. Was sich im Betrieb
ändert, gehört hierher — sonst hieße jeder Wechsel: anmelden per ssh, Datei
bearbeiten, Dienst neu starten.

**Geheime Werte liegen verschlüsselt in der Datenbank**, mit demselben
Tresor wie die OAuth-Token. Welche geheim sind, leitet `ist_geheim` aus dem
Verzeichnis der Kanäle ab statt aus einer zweiten Liste von Hand. Ein
Schlüssel im Klartext stünde sonst in jeder Sicherung.

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


def kanal_name(kanal_key: str, feld: str) -> str:
    """Der Einstellungs-Schlüssel für ein Zugangsfeld eines Kanals."""
    return f"kanal_{kanal_key}_{feld}"


def _geheime() -> frozenset[str]:
    """Was verschlüsselt abgelegt wird.

    Wird aus dem Verzeichnis der Kanäle abgeleitet und nicht von Hand
    gepflegt: eine zweite Liste würde beim nächsten Kanal vergessen, und das
    Ergebnis wäre ein Secret im Klartext in jeder Sicherung. Der Import
    steht in der Funktion, weil die Adapter umgekehrt dieses Modul brauchen.
    """
    from .kanaele import ZUGANGSFELDER

    namen = {GEMINI_SCHLUESSEL}
    for schluessel, felder in ZUGANGSFELDER.items():
        namen.update(
            kanal_name(schluessel, feld.name) for feld in felder if feld.geheim
        )
    return frozenset(namen)


def ist_geheim(name: str) -> bool:
    return name in _geheime()


def hole(name: str) -> str:
    """Der gespeicherte Wert, oder "" wenn nichts gesetzt ist."""
    eintrag = db.session.get(Einstellung, name)
    if eintrag is None or not eintrag.wert:
        return ""
    if not ist_geheim(name):
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
    if not ist_geheim(name):
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
    eintrag.wert = einschliessen(wert) if ist_geheim(name) else wert
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


# --- Zugangsdaten der Kanäle -------------------------------------------

# Wo derselbe Wert früher in der .env stand. Nur diese beiden Kanäle haben
# dort je einen Platz gehabt; für die anderen gibt es nichts zum Zurückfallen
# und die Einstellung ist der einzige Ort.
_ENV_RUECKFALL = {
    ("pinterest", "app_id"): "PINTEREST_APP_ID",
    ("pinterest", "app_secret"): "PINTEREST_APP_SECRET",
    ("google_business", "client_id"): "GOOGLE_CLIENT_ID",
    ("google_business", "client_secret"): "GOOGLE_CLIENT_SECRET",
}


def kanal_wert(kanal_key: str, feld: str) -> str:
    """Ein Zugangsfeld eines Kanals. Erst die Einstellung, dann die `.env`.

    Adapter holen ihre Zugangsdaten hierüber und nie direkt aus der
    Konfiguration. Sonst läge ein Wert in der Maske, der nicht benutzt wird.
    """
    from flask import current_app

    wert = hole(kanal_name(kanal_key, feld))
    if wert:
        return wert
    aus_env = _ENV_RUECKFALL.get((kanal_key, feld))
    return current_app.config.get(aus_env, "") if aus_env else ""


def kanal_herkunft(kanal_key: str, feld: str) -> str:
    """"einstellung", "env" oder "" — dieselbe Frage wie bei Gemini."""
    from flask import current_app

    if hole(kanal_name(kanal_key, feld)):
        return "einstellung"
    aus_env = _ENV_RUECKFALL.get((kanal_key, feld))
    if aus_env and current_app.config.get(aus_env, ""):
        return "env"
    return ""


def kanal_vollstaendig(kanal_key: str) -> bool:
    """Ob für diesen Kanal alle Zugangsfelder belegt sind.

    Alle, nicht eines: eine App-ID ohne Secret ist genauso wenig ein Zugang
    wie gar nichts, sieht in einer Übersicht aber nach halb erledigt aus.
    """
    from .kanaele import ZUGANGSFELDER

    felder = [f for f in ZUGANGSFELDER.get(kanal_key, ()) if f.pflicht]
    return bool(felder) and all(kanal_wert(kanal_key, f.name) for f in felder)


def kanal_entferne(kanal_key: str) -> None:
    """Alle Zugangsfelder eines Kanals auf einmal."""
    from .kanaele import ZUGANGSFELDER

    for feld in ZUGANGSFELDER.get(kanal_key, ()):
        entferne(kanal_name(kanal_key, feld.name))
