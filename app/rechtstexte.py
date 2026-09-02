"""Rechtstexte aus LegalHub (legal.carstenbeuge.de), wie bei den anderen Marken.

Der Ablauf ist derselbe wie in bestellone, xtranu und startklar.tools: ein
Cache jünger als 24 Stunden wird genommen, sonst wird frisch geholt; schlägt
der Abruf fehl, gilt der letzte bekannte Stand. **Impressum und Datenschutz
dürfen nie leer sein**, auch nicht wenn LegalHub gerade neu startet.

Der Domain-Slug muss in LegalHub `pinariode` heißen, analog zu `bestellonede`
und `startklartools`. Solange er dort nicht angelegt ist, liefert die API 404,
diese Funktion gibt None zurück und die Seite zeigt einen Platzhalter statt
einer kaputten Seite.

Nie eine zweite Fassung der Texte im Projekt ablegen. Sonst laufen zwei
Fassungen auseinander, und die falsche steht online.
"""

import logging
import re
from pathlib import Path

import requests
from flask import current_app

from .rechtstext_saeubern import saeubern
from .zeit import jetzt

BASIS = "https://legal.carstenbeuge.de/api/v1/legal"
DOMAIN_SLUG = "pinariode"
MAX_ALTER = 24 * 60 * 60          # Sekunden
ZEITGRENZE = 5                    # Sekunden, damit die Seite nicht hängt

KATEGORIEN = {
    "impressum": "Impressum",
    "datenschutz": "Datenschutz",
}

log = logging.getLogger(__name__)

# Quill schreibt jede leere Zeile als <p><br></p>. In den echten Texten
# stehen davon bis zu drei hintereinander, und auf der Seite reißt das
# Löcher zwischen die Abschnitte. Den Abstand macht hier die CSS, nicht der
# Redakteur.
#
# Bewusst getrennt vom Säubern: das eine ist Sicherheit und darf nichts
# durchlassen, das hier ist Darstellung und darf nichts wegwerfen, was Text
# ist. Deshalb nur Absätze, die außer einem <br> nichts enthalten —
# <p>a<br>b</p> bleibt unangetastet.
_LEERE_ABSAETZE = re.compile(r"<p>\s*(?:<br\s*/?>\s*)+</p>", re.IGNORECASE)


def _leerzeilen_entfernen(html: str) -> str:
    return _LEERE_ABSAETZE.sub("", html)


def _datei(kategorie: str) -> Path:
    ordner = Path(current_app.config["CACHE_ORDNER"]) / "legal"
    return ordner / f"{DOMAIN_SLUG}_{kategorie}.html"


def _aus_cache(datei: Path) -> tuple[str, float] | None:
    try:
        return datei.read_text(encoding="utf-8"), jetzt().timestamp() - datei.stat().st_mtime
    except OSError:
        return None


def _abrufen(kategorie: str) -> str | None:
    try:
        antwort = requests.get(
            f"{BASIS}/{DOMAIN_SLUG}/{kategorie}", timeout=ZEITGRENZE
        )
    except requests.RequestException as fehler:
        log.warning("LegalHub nicht erreichbar (%s): %s", kategorie, fehler)
        return None
    if antwort.status_code == 404:
        # Kein Fehler, sondern der normale Zustand, solange der Slug in
        # LegalHub noch nicht angelegt ist. Deshalb nur eine Info-Zeile.
        log.info("LegalHub kennt '%s/%s' noch nicht", DOMAIN_SLUG, kategorie)
        return None
    if not antwort.ok:
        log.warning("LegalHub antwortet mit %s (%s)", antwort.status_code, kategorie)
        return None
    try:
        inhalt = (antwort.json().get("inhalt") or "").strip()
    except ValueError:
        log.warning("LegalHub liefert kein JSON (%s)", kategorie)
        return None
    return inhalt or None


def rechtstext(kategorie: str) -> str | None:
    """Gesäubertes HTML des Textes, oder None wenn es ihn nirgends gibt."""
    if kategorie not in KATEGORIEN:
        raise ValueError(f"Unbekannte Kategorie: {kategorie}")

    datei = _datei(kategorie)
    zwischenstand = _aus_cache(datei)
    if zwischenstand and zwischenstand[1] < MAX_ALTER:
        return _aufbereiten(zwischenstand[0])

    frisch = _abrufen(kategorie)
    if frisch:
        try:
            datei.parent.mkdir(parents=True, exist_ok=True)
            datei.write_text(frisch, encoding="utf-8")
        except OSError as fehler:
            # Nicht schreiben zu können ist ärgerlich, aber kein Grund, die
            # Seite leer zu lassen.
            log.warning("Cache nicht schreibbar (%s): %s", datei, fehler)
        return _aufbereiten(frisch)

    # Gesäubert wird beim Ausliefern, nicht vor dem Schreiben in den Cache.
    # So wird ein Eintrag, der schon vor einer Änderung an dieser Datei dort
    # lag, beim nächsten Ausliefern mit erfasst.
    return _aufbereiten(zwischenstand[0]) if zwischenstand else None


def _aufbereiten(html: str) -> str:
    """Erst sicher machen, dann hübsch. In dieser Reihenfolge, damit die
    Darstellungsregel nie auf ungeprüftem HTML arbeitet."""
    return _leerzeilen_entfernen(saeubern(html))
