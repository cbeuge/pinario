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
    # Steht der Link im Profil, ist "Link in der Bio" dort das Uebliche --
    # eine nackte Adresse in der Bildunterschrift kann man nicht antippen.
    # Die Angabe kommt vom Nutzer: ob der Link dort steht, weiss nur, wer
    # das Profil pflegt.
    ("Link in der Bio: die Adresse bleibt aus dem Text",
     {"link_im_text": True, "link_klickbar": False, "link_in_bio": True},
     ["nicht** in den Text"]),
    ("Link in der Bio: der Text verweist aufs Profil",
     {"link_im_text": True, "link_klickbar": False, "link_in_bio": True},
     ["Link in der Biografie", "ohne die Adresse zu nennen"]),
    # Der Text zu einer hochgeladenen Datei. Ohne diese Zeilen sieht das
    # Modell das Bild zwar, haelt es aber fuer Beiwerk und schreibt am Motiv
    # vorbei -- der Beitrag beschreibt dann etwas anderes als das Bild
    # daneben zeigt.
    ("Zur Vorlage: das Bild wird ausdruecklich genannt",
     {"zu_vorlage": True}, ["Oben steht das Bild"]),
    ("Zur Vorlage: was zu sehen ist, gehoert in den Text",
     {"zu_vorlage": True}, ["was darauf zu sehen ist"]),
    ("Zur Vorlage: nichts hineinerfinden",
     {"zu_vorlage": True}, ["Erfinde nichts hinein"]),
    # Ohne Untergrenze schreibt das Modell so kurz wie moeglich -- auf
    # Instagram kamen 280 Zeichen heraus, wo 500 der Anfang waeren. Das Wort
    # "hoechstens" zieht fuer sich genommen in diese Richtung.
    ("Mindestlaenge: sie steht in der Anfrage",
     {"min_beschreibung": 500}, ["mindestens 500", "hoechstens".replace("oe", "ö")]),
    ("Mindestlaenge: sie ist keine Zielmarke",
     {"min_beschreibung": 500}, ["nutze den Platz"]),
    ("Absaetze: ausdruecklich mit Leerzeile",
     {"absaetze": True}, ["Leerzeile", "Kein durchgehender Block"]),
    ("Absaetze: der erste Absatz steht fuer sich",
     {"absaetze": True}, ["fuer sich stehen".replace("ue", "ü")]),
]

# (Beschreibung, Abweichung, was NICHT drinstehen darf)
FEHLEN = [
    ("Affiliate erlaubt: keine Zusatzregel", {}, ["Unternehmensprofil"]),
    ("Kanal ohne Link-Feld: nicht auch noch das Gegenteil",
     {"link_im_text": True}, ["nicht in den Text"]),
    ("Anklickbarer Link: kein Hinweis aufs Abtippen",
     {"link_im_text": True}, ["nicht anklickbar"]),
    ("Ohne Vorlage kein Hinweis auf ein Bild", {}, ["Oben steht das Bild"]),
    ("Mit Briefing: kein Luecken-Hinweis", {}, ["gibt es nicht"]),
    # Der teure Fall: beides zugleich waere ein Text, der auf die Bio
    # verweist und die Adresse trotzdem darunter schreibt.
    ("Link in der Bio: kein Abtippen-Hinweis daneben",
     {"link_im_text": True, "link_klickbar": False, "link_in_bio": True},
     ["abtippen oder kopieren", "ans Ende des Textes"]),
    # Und ohne das Haekchen bleibt es beim alten Verhalten. Ein "Link in
    # der Bio", den es nicht gibt, schickt jeden Leser ins Leere.
    ("Ohne das Haekchen kein Verweis aufs Profil",
     {"link_im_text": True, "link_klickbar": False},
     ["Verweise am Ende stattdessen"]),
    ("Ohne Mindestlaenge steht dort keine", {}, ["mindestens"]),
    ("Ohne Absatz-Vorgabe steht dort nichts davon", {}, ["Leerzeile"]),
    # Eine Untergrenze ueber der Obergrenze waere eine Anfrage, die sich
    # selbst widerspricht. Pinterest hat 800 Zeichen -- eine Vorgabe von
    # 900 darf nicht durchschlagen.
    ("Untergrenze ueber der Obergrenze wird verworfen",
     {"min_beschreibung": 900, "max_beschreibung": 800}, ["mindestens"]),
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


# --- Der Ziel-Link ------------------------------------------------------

# Niemand tippt https:// freiwillig. Abgelehnt wird nur, was gar keine
# Adresse ist -- was die Pruefung wirklich verhindern soll, ist eine
# unvollstaendige Adresse *im Pin*, und die entsteht so gerade nicht mehr.
ZIEL_FAELLE = [
    ("Ohne Schema wird https ergaenzt", "pinario.de", "https://pinario.de"),
    ("Auch mit Pfad", "pinario.de/start", "https://pinario.de/start"),
    ("Mit www", "www.pinario.de", "https://www.pinario.de"),
    ("https bleibt https", "https://pinario.de", "https://pinario.de"),
    ("http bleibt http", "http://pinario.de", "http://pinario.de"),
    ("Leerraum faellt weg", "  pinario.de  ", "https://pinario.de"),
]

ZIEL_ABGELEHNT = [
    ("javascript: wird nicht stillschweigend umgeschrieben",
     "javascript:alert(1)"),
    ("Ein fremdes Schema auch nicht", "ftp://x.de"),
    ("Ohne Endung ist es ein Tippfehler", "pinario"),
    ("Leer bleibt leer", ""),
]


def _pruefe_ziel() -> int:
    from app.formular import Ungueltig, ziel_adresse

    fehler = 0
    print()
    print("Der Ziel-Link")
    for name, roh, erwartet in ZIEL_FAELLE:
        try:
            ist = ziel_adresse(roh)
        except Ungueltig as f:
            fehler += 1
            print(f"  FEHLER  {name}: abgelehnt ({f})")
            continue
        if ist == erwartet:
            print(f"  ok      {name}")
        else:
            fehler += 1
            print(f"  FEHLER  {name}: {ist} statt {erwartet}")

    for name, roh in ZIEL_ABGELEHNT:
        try:
            ist = ziel_adresse(roh)
        except Ungueltig:
            print(f"  ok      {name}")
        else:
            fehler += 1
            print(f"  FEHLER  {name}: durchgelassen als {ist}")
    return fehler


# --- Der MIME-Typ des Bildes --------------------------------------------

# Geht an Gemini mit. Aus den ersten Bytes abgeleitet und nicht aus dem
# Dateinamen: dem Modell etwas Falsches anzusagen ist schlimmer, als es
# raten zu lassen.
MIME_FAELLE = [
    ("JPG", bytes([0xFF, 0xD8, 0xFF]) + b"x" * 20, "image/jpeg"),
    ("PNG", bytes([0x89]) + b"PNG" + b"x" * 20, "image/png"),
    ("GIF", b"GIF89a" + b"x" * 20, "image/gif"),
    ("WEBP", b"RIFF" + b"x" * 20, "image/webp"),
    ("Unbekanntes faellt auf PNG", b"egal", "image/png"),
]


def _pruefe_mime() -> int:
    from app.ki import _mime

    fehler = 0
    print()
    print("Der MIME-Typ des Bildes")
    for name, daten, erwartet in MIME_FAELLE:
        ist = _mime(daten)
        if ist == erwartet:
            print(f"  ok      {name}")
        else:
            fehler += 1
            print(f"  FEHLER  {name}: {ist} statt {erwartet}")
    return fehler


# --- Die Anfrage fuers Bild ---------------------------------------------

# Am 04.09.2026 ging hier die komplette Text-Anfrage an das Bildmodell:
# "Du schreibst 3 Vorschlaege fuer einen Beitrag auf Facebook, Titel
# hoechstens 100 Zeichen, Deutsch, geduzt...". Ein Bildmodell kann damit
# nichts anfangen, es antwortete mit NO_IMAGE und lieferte **jedes Mal**
# nichts. Gemessen mit demselben Briefing gegen beide Fassungen: alte
# Anfrage 0 Bilder, reine Bildbeschreibung sofort eines.
BILD_STANDARD = {
    "titel": "Behalte den Ueberblick",
    "beschreibung": "Alle Ausgaben an einem Ort.",
    "briefing": "Finanzueberblick ohne Bankanbindung.",
    "format": "2:3",
}

BILD_ENTHALTEN = [
    # Menschen sind eine Entscheidung an der Kampagne, kein Naturgesetz.
    # **Gesteuert allein ueber die Anfrage**: das SDK kennt zwar einen
    # Parameter `person_generation`, die Gemini Developer API lehnt ihn aber
    # ab -- und zwar jede Bilderzeugung, auch die ohne Menschen. Am
    # 05.09.2026 gegen die echte API gemessen, bevor es ausgerollt wurde.
    ("Mit Erlaubnis: Menschen duerfen aufs Bild",
     {"menschen": True}, ["Menschen dürfen im Bild sein"]),
    ("Mit Erlaubnis: aber keine erkennbaren echten Personen",
     {"menschen": True}, ["Keine erkennbaren echten Personen"]),
    ("Mit Erlaubnis: keine Kinder",
     {"menschen": True}, ["Keine Kinder"]),
    ("Ohne Erlaubnis: das Verbot steht drin",
     {}, ["**Keine Menschen**"]),
    ("Der Titel des Beitrags steht drin", {}, ["Behalte den Ueberblick"]),
    ("Die Beschreibung auch", {}, ["Alle Ausgaben an einem Ort."]),
    ("Das Briefing als Hintergrund", {}, ["Finanzueberblick ohne Bankanbindung."]),
    ("Das Seitenverhaeltnis des Kanals", {"format": "16:9"}, ["16:9"]),
    ("Verbot: Schrift im Bild", {}, ["Keine Schrift"]),
    ("Verbot: Menschen", {}, ["Keine Menschen"]),
    ("Verbot: Logos und Marken", {}, ["Logos"]),
    ("Es wird ausdruecklich ein Bild verlangt", {}, ["Erzeuge ein Bild"]),
    ("Ohne Briefing geht es trotzdem",
     {"briefing": None}, ["Behalte den Ueberblick"]),
]

# Was auf keinen Fall drinstehen darf: alles, was nach einer Textaufgabe
# klingt. Genau daran ist die alte Fassung gescheitert.
BILD_FEHLEN = [
    ("Mit Erlaubnis steht das Verbot NICHT mehr drin",
     {"menschen": True}, ["**Keine Menschen**"]),
    ("Ohne Erlaubnis keine Regeln fuer Menschen im Bild",
     {}, ["Menschen dürfen im Bild sein"]),
    ("Keine Anweisung zum Texteschreiben", {}, ["Du schreibst"]),
    ("Keine Zeichengrenzen fuer Texte", {}, ["hoechstens", "Zeichen."]),
    ("Kein Ziel-Link im Bildauftrag", {}, ["Ziel-Link"]),
    ("Keine Regeln zur Sprache", {}, ["geduzt"]),
    ("Ohne Briefing kein leerer Hintergrund-Block",
     {"briefing": None}, ["Hintergrund fuer die Bildidee"]),
]


def _pruefe_bildanfragen() -> int:
    from app.ki import bild_anfrage_bauen

    fehler = 0
    print()
    print("Die Anfrage fuers Bild")
    for name, abweichung, teile in BILD_ENTHALTEN:
        text = bild_anfrage_bauen(**{**BILD_STANDARD, **abweichung})
        fehlt = [t for t in teile if t not in text]
        if fehlt:
            fehler += 1
            print(f"  FEHLER  {name} (fehlt: {fehlt})")
        else:
            print(f"  ok      {name}")

    for name, abweichung, teile in BILD_FEHLEN:
        text = bild_anfrage_bauen(**{**BILD_STANDARD, **abweichung})
        drin = [t for t in teile if t in text]
        if drin:
            fehler += 1
            print(f"  FEHLER  {name} (steht drin: {drin})")
        else:
            print(f"  ok      {name}")

    return fehler


def main() -> int:
    fehler = (
        _pruefe_anfragen() + _pruefe_antworten() + _pruefe_bildanfragen()
        + _pruefe_mime() + _pruefe_ziel()
    )

    print()
    if fehler:
        print(f"{fehler} Prüfung(en) fehlgeschlagen.")
        return 1

    gesamt = (
        len(ENTHALTEN) + len(FEHLEN) + len(_antwort_faelle())
        + len(BILD_ENTHALTEN) + len(BILD_FEHLEN) + len(MIME_FAELLE)
        + len(ZIEL_FAELLE) + len(ZIEL_ABGELEHNT)
    )
    print(f"Alle {gesamt} Prüfungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
