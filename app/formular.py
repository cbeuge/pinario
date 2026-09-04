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

    # **Fehlt das Schema, wird https:// ergänzt** statt abzulehnen. Niemand
    # tippt es freiwillig, und die Ablehnung war eine Hürde ohne Gewinn: was
    # die Prüfung wirklich verhindern soll, ist eine Adresse, die *ohne*
    # Schema in einem Pin landet — und genau das passiert jetzt nicht mehr,
    # weil hier eine vollständige herauskommt.
    #
    # Nur wenn schon ein anderes Schema dasteht (`ftp:`, `javascript:`),
    # wird abgelehnt. Das ist der Fall, den man nicht stillschweigend
    # überschreiben darf.
    if "://" not in geputzt:
        if ":" in geputzt.split("/")[0]:
            raise Ungueltig(
                "Der Ziel-Link muss mit http:// oder https:// anfangen."
            )
        geputzt = "https://" + geputzt.lstrip("/")

    zerlegt = urlparse(geputzt)
    if zerlegt.scheme not in ("http", "https"):
        raise Ungueltig(
            "Der Ziel-Link muss mit http:// oder https:// anfangen."
        )
    if not zerlegt.netloc:
        raise Ungueltig("Im Ziel-Link fehlt die Adresse, z. B. pinario.de.")
    # Ohne Punkt ist es kein Name, sondern ein Tippfehler. Ein Pin, der auf
    # "welcometap" zeigt, führt nirgendwohin und fällt erst spät auf.
    if "." not in zerlegt.netloc:
        raise Ungueltig(
            "Im Ziel-Link fehlt die Endung, z. B. pinario.de statt pinario."
        )
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


def wochentage(werte: list[str] | None) -> list[int]:
    """Die angehakten Wochentage, Montag ist 0.

    **Keine Auswahl heißt: alle Tage**, und zwar ausdrücklich als volle
    Liste und nicht als leere. Eine leere Liste sähe in der Datenbank aus
    wie "nie posten", und ein Kanal, der stillschweigend aufhört, ist der
    teuerste Fehler, den dieses Formular machen könnte.
    """
    gewaehlt = []
    for wert in werte or []:
        try:
            zahl = int(wert)
        except (TypeError, ValueError):
            raise Ungueltig("Ein Wochentag ist keine Zahl.") from None
        if not 0 <= zahl <= 6:
            raise Ungueltig("Ein Wochentag liegt außerhalb der Woche.")
        if zahl not in gewaehlt:
            gewaehlt.append(zahl)
    return sorted(gewaehlt) or list(range(7))


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


# --- Hochgeladene Dateien ----------------------------------------------

# Was angenommen wird, und woran man es erkennt. Die Endung allein reicht
# nicht: sie steht im Dateinamen und den bestimmt der Absender. Geprüft wird
# deshalb der Anfang der Datei — die ersten Bytes, an denen ein Format sich
# ausweist.
#
# Der Grund ist nicht Sicherheit im engeren Sinn: die Dateien werden nie
# ausgeführt, sie gehen an Pinterest und Meta. Aber eine kaputte oder
# falsch benannte Datei fällt sonst erst dort auf, Tage später, als
# gescheiterter Beitrag mit einer Fehlermeldung von der Plattform.
BILD_ARTEN = {
    b"\xff\xd8\xff": ("jpg", "image"),
    b"\x89PNG\r\n\x1a\n": ("png", "image"),
    b"GIF87a": ("gif", "image"),
    b"GIF89a": ("gif", "image"),
}
# Bei MP4 und Konsorten steht die Kennung nicht ganz vorn, sondern nach vier
# Bytes Längenangabe. Deshalb wird sie getrennt geprüft.
VIDEO_KENNUNG = b"ftyp"

# Grenzen, damit nicht versehentlich ein Rohschnitt hochgeht. Die Plattformen
# nehmen mehr, aber alles darüber ist bei pinario ein Versehen.
MAX_BILD = 20 * 1024 * 1024
MAX_VIDEO = 200 * 1024 * 1024


def datei_pruefen(datei) -> tuple[bytes, str, str]:
    """Liest eine hochgeladene Datei und sagt, was sie ist.

    Liefert Inhalt, Endung und Typ ("image" oder "video"). Wirft `Ungueltig`
    mit einem Satz, der weiterhilft — die Meldung landet direkt vor dem
    Nutzer und "ungültige Datei" wäre dort wertlos.
    """
    if datei is None or not getattr(datei, "filename", ""):
        raise Ungueltig("Es wurde keine Datei ausgewählt.")

    inhalt = datei.read()
    if not inhalt:
        raise Ungueltig("Die Datei ist leer.")

    for kennung, (endung, typ) in BILD_ARTEN.items():
        if inhalt.startswith(kennung):
            if len(inhalt) > MAX_BILD:
                raise Ungueltig(
                    f"Das Bild ist größer als {MAX_BILD // 1024 // 1024} MB."
                )
            return inhalt, endung, typ

    # MP4, MOV und Verwandte: die Kennung steht ab Byte 4.
    if inhalt[4:8] == VIDEO_KENNUNG:
        if len(inhalt) > MAX_VIDEO:
            raise Ungueltig(
                f"Das Video ist größer als {MAX_VIDEO // 1024 // 1024} MB."
            )
        return inhalt, "mp4", "video"

    raise Ungueltig(
        "Das ist weder ein Bild (JPG, PNG, GIF) noch ein Video (MP4, MOV). "
        "Erkannt wird das am Inhalt der Datei, nicht an ihrer Endung — eine "
        "umbenannte Datei hilft also nicht."
    )
