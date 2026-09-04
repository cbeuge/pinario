"""Prueft, was an Gemini geht und was von dort zurueckkommt.

    venv\\Scripts\\python.exe pruefe_ki.py

Warum es dieses Skript gibt: der teuerste Fehler bei einer KI-Anfrage ist
nicht der abgestuerzte Aufruf, sondern die Luecke. Was in der Anfrage fehlt,
denkt sich das Modell aus, und ein erfundener Preis in einem Pin ist Werbung
mit einer falschen Angabe unter Carstens Namen. Also wird nachgemessen, dass
wirklich jede Angabe in der Anfrage steht und dass das Erfinden ausdruecklich
verboten ist.

Der zweite Teil prueft, was zurueckkommt: ein Modell haelt sich an
Laengenangaben meistens, und "meistens" heisst hier, dass der Pin irgendwann
abgeschnitten wird oder die API ablehnt.

Laeuft trocken: ohne Netz, ohne Schluessel, ohne Datenbank.
"""

import sys

from app.ki import MAX_TITEL, KIFehler, anfrage_bauen, variante_pruefen

BRIEFING = "Digitale Gästemappe für Ferienwohnungen.\nKeine Preise nennen."

STANDARD = {
    "kampagne_name": "welcometap",
    "ziel_url": "https://welcometap.de",
    "briefing": BRIEFING,
    "kanal_name": "Pinterest",
    "max_beschreibung": 800,
    "anzahl": 3,
    "affiliate_erlaubt": True,
}


def _anfrage(**abweichung) -> str:
    return anfrage_bauen(**{**STANDARD, **abweichung})


# (Beschreibung, Abweichung vom Standard, was drinstehen muss)
ENTHALTEN = [
    ("Kampagnenname", {}, ["welcometap"]),
    ("Ziel-Link", {}, ["https://welcometap.de"]),
    ("Kanalname", {}, ["Pinterest"]),
    ("Anzahl", {"anzahl": 5}, ["5 Vorschläge"]),
    ("Grenze der Beschreibung", {"max_beschreibung": 800}, ["800"]),
    ("Grenze des Titels", {}, [str(MAX_TITEL)]),
    ("Briefing, erste Zeile", {}, ["Digitale Gästemappe für Ferienwohnungen."]),
    ("Briefing, zweite Zeile", {}, ["Keine Preise nennen."]),
    ("Verbot: erfinden", {}, ["Erfinde nichts"]),
    ("Verbot: Preise", {}, ["Preise"]),
    ("Verbot: Garantien", {}, ["Garantien"]),
    ("Verbot: Zahlen", {}, ["Zahlen"]),
    ("Ziel-Link nicht in den Text", {}, ["nicht in den Text"]),
    ("Varianten muessen sich unterscheiden", {}, ["deutlich unterscheiden"]),
    ("Ohne Briefing steht die Luecke drin",
     {"briefing": None},
     ["gibt es nicht", "ganz allgemein"]),
    ("Ohne Briefing: keine Ableitung aus dem Namen",
     {"briefing": ""},
     ["nur aus dem Namen"]),
    ("Kein Affiliate: Zusatzregel",
     {"affiliate_erlaubt": False},
     ["Unternehmensprofil", "Partnerprogramme"]),
    # Wohin der Ziel-Link gehoert, entscheidet die Plattform. Ein Pin hat
    # ein eigenes Feld dafuer, eine Bildunterschrift nicht — stuende hier
    # pauschal "nicht in den Text", fuehrte jeder Beitrag auf Facebook und
    # Instagram ins Leere.
    ("Kanal mit eigenem Link-Feld: raus aus dem Text",
     {}, ["nicht in den Text"]),
    ("Kanal ohne Link-Feld: rein in den Text",
     {"link_im_text": True}, ["ans Ende des Textes"]),
    ("Instagram: der Link ist dort nicht anklickbar",
     {"link_im_text": True, "link_klickbar": False},
     ["nicht anklickbar", "abtippen oder kopieren"]),
    ("Instagram: kein Verweis auf den Link in der Biografie",
     {"link_im_text": True, "link_klickbar": False},
     ["Biografie"]),
]

# (Beschreibung, Abweichung, was NICHT drinstehen darf)
FEHLEN = [
    ("Affiliate erlaubt: keine Zusatzregel", {}, ["Unternehmensprofil"]),
    ("Kanal ohne Link-Feld: nicht auch noch das Gegenteil",
     {"link_im_text": True}, ["nicht in den Text"]),
    ("Anklickbarer Link: kein Hinweis aufs Abtippen",
     {"link_im_text": True}, ["nicht anklickbar"]),
    ("Mit Briefing: kein Luecken-Hinweis", {}, ["gibt es nicht"]),
]


def _pruefe_anfragen() -> int:
    fehler = 0

    print("Was in der Anfrage stehen muss")
    for name, abweichung, teile in ENTHALTEN:
        text = _anfrage(**abweichung)
        fehlend = [teil for teil in teile if teil not in text]
        if fehlend:
            fehler += 1
            print(f"  FEHLER  {name} -> fehlt: {fehlend}")
        else:
            print(f"  ok      {name}")

    print()
    print("Was in der Anfrage nicht stehen darf")
    for name, abweichung, teile in FEHLEN:
        text = _anfrage(**abweichung)
        drin = [teil for teil in teile if teil in text]
        if drin:
            fehler += 1
            print(f"  FEHLER  {name} -> steht drin: {drin}")
        else:
            print(f"  ok      {name}")

    return fehler


def _antwort_faelle():
    """Was zurueckkommt, wird gemessen statt geglaubt."""
    faelle = []

    def fall(name, pruefung):
        faelle.append((name, pruefung))

    fall(
        "Kurzer Vorschlag bleibt unveraendert",
        lambda: variante_pruefen(
            {"titel": "Kurz", "beschreibung": "Auch kurz."}, max_beschreibung=800
        ).beschreibung == "Auch kurz.",
    )
    fall(
        "Zu lange Beschreibung wird gekuerzt",
        lambda: len(
            variante_pruefen(
                {"titel": "T", "beschreibung": "wort " * 400},
                max_beschreibung=100,
            ).beschreibung
        ) <= 101,
    )
    fall(
        "Gekuerzt wird an der Wortgrenze",
        lambda: not variante_pruefen(
            {"titel": "T", "beschreibung": "aaa bbb ccc ddd eee fff ggg hhh"},
            max_beschreibung=20,
        ).beschreibung.rstrip("…").endswith(" "),
    )
    fall(
        "Zu langer Titel wird gekuerzt",
        lambda: len(
            variante_pruefen(
                {"titel": "x" * 500, "beschreibung": "gut"}, max_beschreibung=800
            ).titel
        ) <= MAX_TITEL + 1,
    )
    fall(
        "Leerraum faellt weg",
        lambda: variante_pruefen(
            {"titel": "  Titel  ", "beschreibung": "  Text  "}, max_beschreibung=800
        ).titel == "Titel",
    )
    fall(
        "Fehlender Titel wird abgelehnt",
        lambda: _wirft({"titel": "", "beschreibung": "da"}),
    )
    fall(
        "Fehlende Beschreibung wird abgelehnt",
        lambda: _wirft({"titel": "da", "beschreibung": "   "}),
    )
    fall(
        "Kein Objekt wird abgelehnt",
        lambda: _wirft(["Liste statt Objekt"]),
    )
    fall(
        "Fehlende Schluessel werden abgelehnt",
        lambda: _wirft({}),
    )

    return faelle


def _pruefe_antworten() -> int:
    fehler = 0
    print()
    print("Was zurueckkommt")
    for name, pruefung in _antwort_faelle():
        try:
            bestanden = pruefung()
        except Exception as ausnahme:  # noqa: BLE001
            bestanden = False
            name = f"{name} (Ausnahme: {ausnahme})"
        if bestanden:
            print(f"  ok      {name}")
        else:
            fehler += 1
            print(f"  FEHLER  {name}")

    return fehler


def _wirft(roh) -> bool:
    try:
        variante_pruefen(roh, max_beschreibung=800)
    except KIFehler:
        return True
    return False


def main() -> int:
    fehler = _pruefe_anfragen() + _pruefe_antworten()

    print()
    if fehler:
        print(f"{fehler} Prüfung(en) fehlgeschlagen.")
        return 1

    gesamt = len(ENTHALTEN) + len(FEHLEN) + len(_antwort_faelle())
    print(f"Alle {gesamt} Prüfungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
