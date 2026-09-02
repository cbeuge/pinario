"""Zeitzone an einer einzigen Stelle.

Der Server läuft auf UTC, geplant wird in deutscher Zeit. Wer einen Pin für
"morgen 9 Uhr" einplant, meint 9 Uhr in Deutschland. Deshalb darf "heute"
und "jetzt" nirgends aus der Prozess-Zeitzone abgeleitet werden.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
UTC = ZoneInfo("UTC")


def jetzt() -> datetime:
    """Aktueller Zeitpunkt mit Berliner Zeitzone."""
    return datetime.now(BERLIN)


def heute() -> date:
    """Heutiges Datum aus Berliner Sicht, nicht aus Sicht des Servers."""
    return jetzt().date()


def nach_berlin(zeitpunkt: datetime) -> datetime:
    """Rechnet einen Zeitpunkt nach Berlin um.

    Ein Zeitpunkt ohne Zonenangabe wird als UTC gelesen, weil genau so die
    Werte aus den Kanal-APIs und aus der Datenbank kommen.
    """
    if zeitpunkt.tzinfo is None:
        zeitpunkt = zeitpunkt.replace(tzinfo=UTC)
    return zeitpunkt.astimezone(BERLIN)


def berliner_zeitpunkt(tag: date, uhrzeit: time) -> datetime:
    """Datum und Uhrzeit als deutscher Zeitpunkt.

    Gebraucht beim Einplanen: das Zeitfenster einer Kampagne steht als
    "09:00" bis "21:00" in den Einstellungen und meint deutsche Zeit.
    """
    return datetime.combine(tag, uhrzeit, tzinfo=BERLIN)


def formatiere_uhrzeit(zeitpunkt: datetime | None) -> str:
    if zeitpunkt is None:
        return "-"
    return nach_berlin(zeitpunkt).strftime("%H:%M")


def formatiere_datum(wert: date | datetime | None) -> str:
    if wert is None:
        return "-"
    if isinstance(wert, datetime):
        wert = nach_berlin(wert).date()
    wochentage = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    return f"{wochentage[wert.weekday()]}, {wert.strftime('%d.%m.%Y')}"
