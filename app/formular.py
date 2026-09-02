"""Prüfen und Umwandeln von Formulareingaben.

Steht als eigenes Modul da, weil dieselben Regeln später auch beim Erzeugen
von Inhalten und im Scheduler gebraucht werden. Jede Funktion liefert
entweder einen sauberen Wert oder wirft `Ungueltig` mit einem Satz, der so
in der Oberfläche stehen kann.
"""

from datetime import time
from urllib.parse import urlparse


class Ungueltig(ValueError):
    """Die Eingabe stimmt nicht. Der Text ist für Carsten, nicht fürs Log."""


def text(wert: str | None, feld: str, *, max_laenge: int, pflicht: bool = True) -> str:
    geputzt = (wert or "").strip()
    if not geputzt:
        if pflicht:
            raise Ungueltig(f"{feld} fehlt.")
        return ""
    if len(geputzt) > max_laenge:
        raise Ungueltig(f"{feld} ist zu lang, höchstens {max_laenge} Zeichen.")
    return geputzt


def ziel_adresse(wert: str | None) -> str:
    """Der Link, zu dem am Ende alles führt.

    Streng geprüft, und zwar aus einem praktischen Grund: eine Adresse ohne
    Schema landet später ungeprüft in einem Pin. Pinterest lehnt sie ab oder,
    schlimmer, nimmt sie an und der Pin führt ins Leere. Beides fällt erst
    Tage später auf, wenn niemand mehr weiß, woran es lag.
    """
    geputzt = text(wert, "Der Ziel-Link", max_laenge=2000)
    zerlegt = urlparse(geputzt)
    if zerlegt.scheme not in ("http", "https"):
        raise Ungueltig(
            "Der Ziel-Link muss mit http:// oder https:// anfangen."
        )
    if not zerlegt.netloc:
        raise Ungueltig("Im Ziel-Link fehlt die Adresse, z. B. pinario.de.")
    return geputzt


def aus_auswahl(wert: str | None, erlaubt, feld: str) -> str:
    geputzt = (wert or "").strip()
    if geputzt not in erlaubt:
        raise Ungueltig(f"{feld} hat einen unbekannten Wert.")
    return geputzt


def ganze_zahl(wert: str | None, feld: str, *, min_wert: int, max_wert: int) -> int:
    geputzt = (wert or "").strip()
    try:
        zahl = int(geputzt)
    except ValueError:
        raise Ungueltig(f"{feld} muss eine Zahl sein.") from None
    if not min_wert <= zahl <= max_wert:
        raise Ungueltig(f"{feld} muss zwischen {min_wert} und {max_wert} liegen.")
    return zahl


def uhrzeit(wert: str | None, feld: str) -> time:
    geputzt = (wert or "").strip()
    try:
        stunde, _, minute = geputzt.partition(":")
        return time(int(stunde), int(minute))
    except ValueError:
        raise Ungueltig(f"{feld} muss eine Uhrzeit sein, z. B. 09:00.") from None


def zeitfenster(von: str | None, bis: str | None) -> list[str]:
    """Das Fenster, in dem an einem Tag gepostet werden darf.

    Gemeint ist immer deutsche Zeit, auch wenn der Server auf UTC läuft. Die
    Umrechnung macht später `zeit.py`; hier stehen nur die beiden Uhrzeiten
    als Text, damit sie in `settings` lesbar bleiben.
    """
    a = uhrzeit(von, "Der Beginn des Zeitfensters")
    b = uhrzeit(bis, "Das Ende des Zeitfensters")
    if a >= b:
        raise Ungueltig("Das Zeitfenster muss vorne anfangen und hinten aufhören.")
    return [a.strftime("%H:%M"), b.strftime("%H:%M")]


def kennungen(wert: str | None, *, max_stueck: int = 20) -> list[str]:
    """Board- oder Standort-Kennungen, eine je Zeile oder per Komma getrennt.

    Von Hand einzutragen ist ein Zwischenschritt: sobald ein Konto verbunden
    ist, holt der Adapter die Liste selbst und daraus wird eine Auswahl.
    """
    roh = (wert or "").replace(",", "\n").splitlines()
    gesehen: list[str] = []
    for eintrag in roh:
        eintrag = eintrag.strip()
        if not eintrag or eintrag in gesehen:
            continue
        if len(eintrag) > 255:
            raise Ungueltig("Eine der Kennungen ist zu lang.")
        gesehen.append(eintrag)
    if len(gesehen) > max_stueck:
        raise Ungueltig(f"Höchstens {max_stueck} Kennungen.")
    return gesehen
