"""Varianten erzeugen lassen: Texte und Bilder über Gemini.

Zwei Dinge sind hier wichtiger als der API-Aufruf selbst.

**Erstens: was in der Anfrage fehlt, denkt sich das Modell aus.** Preise,
Zahlen, Garantien, Ortsangaben — wenn sie im Ergebnis stehen dürfen, müssen
sie in der Anfrage stehen. Deshalb baut `anfrage_bauen` den Text aus genau
den Angaben, die es wirklich gibt (Kampagnenname, Ziel-Link, Briefing,
Grenzen des Kanals), und verbietet ausdrücklich alles darüber hinaus. Ein
erfundener Preis in einem Pin ist Werbung mit einer falschen Angabe, und
zwar unter Carstens Namen.

**Zweitens: der Anfragetext wird mitgespeichert** (`content_items.prompt`).
Die Anwendung existiert, um zu messen, welche Variante zieht. Ohne die
Anfrage daneben ist das Ergebnis eine Zahl ohne Frage.

`anfrage_bauen` und `variante_pruefen` laufen trocken, ohne Netz und ohne
Schlüssel. Genau deshalb sind sie eigene Funktionen: so lässt sich das
Nachdenken prüfen, ohne für jede Prüfung Gemini zu bezahlen. Siehe
`pruefe_ki.py`.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path

from flask import current_app

# Höchstlängen der Anwendung, unabhängig vom Kanal. Der Kanal darf strenger
# sein, nie großzügiger: `title` ist in der Datenbank 255 Zeichen lang.
MAX_TITEL = 120
MIN_VARIANTEN = 1
MAX_VARIANTEN = 8

# Bildformat der erzeugten Dateien. PNG, weil Gemini es so liefert und eine
# zweite Umwandlung nur Qualität kostet.
BILD_ENDUNG = ".png"


class KIFehler(RuntimeError):
    """Gemini war nicht erreichbar, hat abgelehnt oder Unbrauchbares
    geliefert. Der Text ist für Carsten und landet in der Oberfläche."""


@dataclass
class Variante:
    """Ein Vorschlag, so wie er in `content_items` landet."""

    titel: str
    beschreibung: str


# --- Die Anfrage -------------------------------------------------------


def anfrage_bauen(
    *,
    kampagne_name: str,
    ziel_url: str,
    briefing: str | None,
    kanal_name: str,
    max_beschreibung: int,
    anzahl: int,
    affiliate_erlaubt: bool,
    link_im_text: bool = False,
    link_klickbar: bool = True,
) -> str:
    """Baut den Anfragetext. Ohne Netz, damit er sich prüfen lässt.

    Jede Angabe, die im Ergebnis stehen darf, steht hier drin. Alles andere
    ist ausdrücklich verboten — ein Modell, dem eine Angabe fehlt, füllt die
    Lücke, statt nachzufragen.
    """
    briefing = (briefing or "").strip()

    zeilen = [
        f"Du schreibst {anzahl} Vorschläge für einen Beitrag auf {kanal_name}.",
        "",
        "Das ist bekannt, und mehr ist nicht bekannt:",
        f"- Kampagne: {kampagne_name}",
        f"- Ziel-Link: {ziel_url}",
    ]

    if briefing:
        zeilen += ["- Beschreibung des Angebots, wörtlich vom Betreiber:", ""]
        zeilen += [f"  {teil}" for teil in briefing.splitlines()]
    else:
        # Kein Briefing heißt: der Anfrage fehlt fast alles. Das gehört in
        # die Anfrage selbst, sonst füllt das Modell die Lücke mit
        # Plausiblem statt mit Wahrem.
        zeilen += [
            "- Eine Beschreibung des Angebots gibt es nicht.",
            "  Bleib deshalb ganz allgemein und nenne keine Einzelheiten,",
            "  die du nur aus dem Namen oder der Adresse ableiten könntest.",
        ]

    zeilen += [
        "",
        "Regeln:",
        f"- Titel höchstens {MAX_TITEL} Zeichen, Beschreibung höchstens "
        f"{max_beschreibung} Zeichen.",
        "- Deutsch, geduzt, natürliche Sprache. Keine Werbefloskeln, keine",
        "  Ausrufezeichen-Ketten, keine Emoji-Reihen, höchstens ein Emoji.",
        "- **Erfinde nichts.** Keine Preise, Prozentangaben, Zahlen, Fristen,",
        "  Garantien, Auszeichnungen, Bewertungen, Nutzerzahlen, Ortsangaben",
        "  oder Namen, die oben nicht stehen. Lieber allgemeiner formulieren",
        "  als eine Angabe hinzuerfinden.",
        "- Keine Behauptungen über Ergebnisse, die niemand zusichern kann.",
        "- Die Vorschläge müssen sich deutlich unterscheiden, nicht nur in",
        "  einzelnen Wörtern. Verschiedene Blickwinkel, nicht dieselbe Aussage",
        "  in neuer Reihenfolge.",
    ]

    # Wohin der Ziel-Link gehört, entscheidet die Plattform und nicht diese
    # Datei: ein Pin hat ein eigenes Feld dafür, eine Bildunterschrift nicht.
    # Stünde hier pauschal "nicht in den Text", führte jeder Beitrag auf
    # Facebook und Instagram ins Leere.
    if not link_im_text:
        zeilen += [
            "- Den Ziel-Link nicht in den Text schreiben, der wird getrennt "
            "gesetzt.",
        ]
    elif link_klickbar:
        zeilen += [
            "- Der Ziel-Link gehört ans Ende des Textes, genau so wie er oben",
            "  steht. Es gibt hier kein eigenes Feld dafür.",
        ]
    else:
        # Instagram. Der Link steht dort als Text da und lässt sich nicht
        # anklicken; ein "hier klicken" wäre eine Anweisung ins Nichts.
        zeilen += [
            "- Auf dieser Plattform sind Links im Text **nicht anklickbar**.",
            "  Schreib den Ziel-Link trotzdem ans Ende, genau so wie er oben",
            "  steht, damit man ihn abtippen oder kopieren kann. Fordere aber",
            "  nicht zum Klicken oder Antippen auf und verweise nicht auf",
            "  einen Link in der Biografie, den es vielleicht gar nicht gibt.",
        ]

    if not affiliate_erlaubt:
        # Google Business Profile. Die Regel steht am Kanal, nicht als
        # Sonderfall in einer Maske, und wird von dort durchgereicht.
        zeilen += [
            "- Dieser Kanal ist ein Unternehmensprofil: schreib über das",
            "  eigene Angebot, nicht über fremde Produkte, und mach keine",
            "  Werbung für Partnerprogramme.",
        ]

    return "\n".join(zeilen)


# --- Was zurückkommt ---------------------------------------------------


SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "titel": {"type": "STRING"},
            "beschreibung": {"type": "STRING"},
        },
        "required": ["titel", "beschreibung"],
    },
}


def variante_pruefen(roh: dict, *, max_beschreibung: int) -> Variante:
    """Prüft und kürzt einen einzelnen Vorschlag.

    Ein Modell hält sich an Längenangaben meistens, aber nicht immer, und
    „meistens" heißt hier: der Pin wird irgendwann abgeschnitten oder die
    API lehnt ab. Also wird gemessen statt geglaubt.
    """
    if not isinstance(roh, dict):
        raise KIFehler("Gemini hat etwas geliefert, das kein Vorschlag ist.")

    titel = str(roh.get("titel") or "").strip()
    beschreibung = str(roh.get("beschreibung") or "").strip()

    if not titel or not beschreibung:
        raise KIFehler("Ein Vorschlag kam ohne Titel oder ohne Beschreibung.")

    return Variante(
        titel=_kuerzen(titel, MAX_TITEL),
        beschreibung=_kuerzen(beschreibung, max_beschreibung),
    )


def _kuerzen(wert: str, grenze: int) -> str:
    """Kürzt an der letzten Wortgrenze davor, nicht mitten im Wort."""
    if len(wert) <= grenze:
        return wert
    schnitt = wert[:grenze]
    luecke = schnitt.rfind(" ")
    if luecke > grenze * 0.6:
        schnitt = schnitt[:luecke]
    return schnitt.rstrip(" ,;:-") + "…"


# --- Der Aufruf --------------------------------------------------------


def _klient():
    """Erst hier importieren, nicht oben im Modul.

    `google-genai` zieht httpx und pydantic mit. Die Anwendung soll auch
    dann starten, wenn an dieser Stelle etwas fehlt — ohne Schlüssel ist
    Erzeugen ohnehin abgeschaltet, und ein Importfehler beim Start würde die
    ganze Seite kosten statt nur diese eine Funktion.
    """
    from .einstellungen import gemini_api_key

    schluessel = gemini_api_key()
    if not schluessel:
        raise KIFehler(
            "Es ist kein Gemini-Schlüssel hinterlegt. Einzutragen unter "
            "Einstellungen; Varianten lassen sich auch ohne ihn von Hand anlegen."
        )
    try:
        from google import genai
    except ImportError as fehler:  # pragma: no cover
        raise KIFehler(f"google-genai ist nicht installiert: {fehler}") from fehler
    return genai.Client(api_key=schluessel)


def _uebersetze(fehler: Exception) -> KIFehler:
    """Macht aus einem API-Fehler einen Satz, der weiterhilft."""
    text = str(fehler)
    if "429" in text or "RESOURCE_EXHAUSTED" in text:
        # Ein 429 mit "limit: 0" ist kein Ansturm, sondern ein Schlüssel
        # ohne hinterlegte Zahlungsweise. Der Unterschied hat schon einmal
        # einen halben Abend gekostet.
        if "limit: 0" in text or '"limit":0' in text or "limit\": 0" in text:
            return KIFehler(
                "Gemini lehnt mit Kontingent 0 ab. Das heißt nicht „zu viele "
                "Anfragen\", sondern dass für diesen Schlüssel keine "
                "Zahlungsweise hinterlegt ist."
            )
        return KIFehler("Gemini ist gerade am Limit. In ein paar Minuten noch einmal.")
    if "401" in text or "403" in text or "API_KEY" in text.upper():
        return KIFehler("Gemini weist den Schlüssel ab. Steht der richtige in der .env?")
    return KIFehler(f"Gemini hat nicht geantwortet: {text}")


def texte_erzeugen(anfrage: str, *, anzahl: int, max_beschreibung: int) -> list[Variante]:
    """Holt `anzahl` Vorschläge. Wirft KIFehler, statt Halbes zu liefern."""
    if not MIN_VARIANTEN <= anzahl <= MAX_VARIANTEN:
        raise KIFehler(
            f"Zwischen {MIN_VARIANTEN} und {MAX_VARIANTEN} Varianten auf einmal."
        )

    klient = _klient()
    modell = current_app.config["GEMINI_MODELL_TEXT"]

    try:
        from google.genai import types

        antwort = klient.models.generate_content(
            model=modell,
            contents=anfrage,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SCHEMA,
                # Etwas Streuung, sonst kommen bei „mehrere Varianten" fast
                # identische Sätze zurück und die Messreihe misst nichts.
                temperature=1.0,
            ),
        )
    except Exception as fehler:  # noqa: BLE001 — die API wirft Verschiedenes
        raise _uebersetze(fehler) from fehler

    roh = (getattr(antwort, "text", "") or "").strip()
    if not roh:
        raise KIFehler(
            "Gemini hat nichts geliefert. Das passiert, wenn die Anfrage an "
            "einem Sicherheitsfilter hängenbleibt."
        )

    try:
        geladen = json.loads(roh)
    except ValueError as fehler:
        raise KIFehler("Gemini hat kein gültiges JSON geliefert.") from fehler

    if not isinstance(geladen, list) or not geladen:
        raise KIFehler("Gemini hat keine Liste von Vorschlägen geliefert.")

    varianten = [
        variante_pruefen(eintrag, max_beschreibung=max_beschreibung)
        for eintrag in geladen[:anzahl]
    ]
    current_app.logger.info(
        "Gemini: %s Variante(n) über %s erzeugt", len(varianten), modell
    )
    return varianten


def verbindung_pruefen() -> str:
    """Ein kurzer echter Aufruf, damit ein Schlüssel nicht erst beim ersten
    Schwung Varianten auffällt.

    Bewusst mit dem Textmodell und einer Antwort von wenigen Zeichen: es geht
    darum, ob Schlüssel und Modellname stimmen, nicht darum, etwas zu
    erzeugen. Liefert den Namen des Modells, das geantwortet hat.
    """
    klient = _klient()
    modell = current_app.config["GEMINI_MODELL_TEXT"]
    try:
        antwort = klient.models.generate_content(
            model=modell, contents="Antworte nur mit dem Wort: ok"
        )
    except Exception as fehler:  # noqa: BLE001
        raise _uebersetze(fehler) from fehler

    if not (getattr(antwort, "text", "") or "").strip():
        raise KIFehler(f"{modell} hat geantwortet, aber ohne Inhalt.")
    return modell


def bild_anfrage_bauen(
    *,
    titel: str,
    beschreibung: str,
    briefing: str | None,
    format: str = "1:1",
) -> str:
    """Die Anfrage für das Bild — und **nur** für das Bild.

    Der Grund, warum es diese Funktion gibt, hat am 04.09.2026 einen halben
    Tag gekostet: vorher ging die komplette Text-Anfrage an das Bildmodell,
    also "Du schreibst 3 Vorschläge für einen Beitrag auf Facebook, Titel
    höchstens 100 Zeichen, Deutsch, geduzt…". Ein Bildmodell kann damit
    nichts anfangen. Es antwortete mit `finish_reason=NO_IMAGE` und
    lieferte **jedes Mal** nichts — nachgemessen mit demselben Briefing gegen
    beide Fassungen: alte Anfrage 0 Bilder, reine Bildbeschreibung sofort
    eines.

    Ein Bildmodell will beschrieben bekommen, was zu sehen ist. Sonst nichts.

    Drei Regeln stehen fest darin:

    * **Keine Schrift im Bild.** Bildmodelle setzen gern Wörter hinein, und
      sie schreiben sie falsch. Ein Pin mit einem Tippfehler im Bild ist
      unbrauchbar, und auffallen würde er erst draußen.
    * **Keine Menschen.** Zum einen postet pinario keine erfundenen Fotos von
      Personen, zum anderen laufen Anfragen mit Personenbeschreibung in
      Filter — und dann steht wieder ein Text ohne Bild da.
    * **Keine Logos und keine Marken**, aus demselben Grund.
    """
    briefing = (briefing or "").strip()

    zeilen = [
        "Erzeuge ein Bild für einen Social-Media-Beitrag.",
        "",
        "Der Beitrag sagt sinngemäß:",
        f"{(titel or '').strip()}",
    ]
    if (beschreibung or "").strip():
        zeilen.append((beschreibung or "").strip())

    if briefing:
        # Nur als Hintergrund, nicht als Anweisung: sonst versucht das
        # Modell, das Briefing bildlich nachzuerzählen.
        zeilen += [
            "",
            "Worum es geht, als Hintergrund für die Bildidee:",
            briefing,
        ]

    zeilen += [
        "",
        "So soll das Bild sein:",
        "- Ein einziges, ruhiges Motiv, das zum Thema passt. Gegenstände,",
        "  Räume, Materialien, Licht — kein Wimmelbild.",
        "- Fotografisch und natürlich, kein Stockfoto-Look, keine grellen",
        "  Farben, keine Collage.",
        f"- Seitenverhältnis {format}, das Motiv passt in dieses Format.",
        "",
        "Was auf keinen Fall hineingehört:",
        "- **Keine Schrift, keine Buchstaben, keine Zahlen im Bild.**",
        "- **Keine Menschen**, auch nicht angeschnitten, von hinten oder",
        "  verschwommen. Keine Hände.",
        "- Keine Logos, Markenzeichen oder erfundenen Produktverpackungen.",
        "- Keine Diagramme und keine Bildschirminhalte, die Zahlen zeigen.",
    ]
    return chr(10).join(zeilen)


def bild_erzeugen(anfrage: str, format: str = "1:1") -> bytes:
    """Ein Bild zum Beitrag. Liefert die Rohdaten, speichert nichts.

    `format` ist das Seitenverhältnis und kommt vom Kanal: ein Pin steht
    hochkant, ein Facebook-Beitrag quer. Ohne die Angabe liefert Gemini
    quadratisch, und das sieht überall etwas daneben aus.
    """
    klient = _klient()
    modell = current_app.config["GEMINI_MODELL_BILD"]

    try:
        from google.genai import types

        antwort = klient.models.generate_content(
            model=modell,
            contents=anfrage,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(aspect_ratio=format),
            ),
        )
    except Exception as fehler:  # noqa: BLE001
        raise _uebersetze(fehler) from fehler

    for teil in _bildteile(antwort):
        daten = getattr(teil, "data", None)
        if daten:
            return daten

    # Der Grund steht in `finish_reason` und gehört in die Meldung. Ohne ihn
    # sieht jedes leere Ergebnis gleich aus, und man rät zwischen Filter,
    # falscher Anfrage und einem Modell, das gerade nichts liefert.
    grund = ""
    for kandidat in getattr(antwort, "candidates", None) or []:
        wert = getattr(kandidat, "finish_reason", None)
        if wert is not None:
            grund = str(getattr(wert, "name", wert))
            break

    if grund == "NO_IMAGE":
        raise KIFehler(
            "Gemini hat kein Bild geliefert (NO_IMAGE). Das Modell konnte mit "
            "der Anfrage nichts anfangen — meist beschreibt sie kein Motiv, "
            "sondern eine Aufgabe."
        )
    if grund in ("SAFETY", "PROHIBITED_CONTENT", "IMAGE_SAFETY"):
        raise KIFehler(
            f"Gemini hat das Bild abgelehnt ({grund}). Die Anfrage läuft in "
            "einen Filter, meist wegen beschriebener Personen oder einer "
            "Marke."
        )
    raise KIFehler(
        "Gemini hat kein Bild geliefert"
        + (f" ({grund})." if grund else ".")
    )


def _bildteile(antwort):
    """Geht die Antwort nach eingebetteten Bildern durch.

    Defensiv, weil die Struktur bei fehlgeschlagenen Antworten teilweise
    leer ist und ein Attributfehler hier nur den echten Grund verdecken
    würde.
    """
    for kandidat in getattr(antwort, "candidates", None) or []:
        inhalt = getattr(kandidat, "content", None)
        for teil in getattr(inhalt, "parts", None) or []:
            eingebettet = getattr(teil, "inline_data", None)
            if eingebettet is not None:
                yield eingebettet


# --- Ablegen -----------------------------------------------------------


def bild_ablegen(daten: bytes) -> str:
    """Speichert ein erzeugtes Bild und liefert den Pfad relativ zu uploads.

    Der Dateiname wird gewürfelt und nicht aus dem Titel gebaut. Pinterest
    holt Bilder über eine öffentlich erreichbare Adresse; ein Name, der den
    Kampagnennamen verrät, stünde damit im Netz.
    """
    ordner: Path = current_app.config["UPLOAD_ORDNER"]
    unterordner = "erzeugt"
    (ordner / unterordner).mkdir(parents=True, exist_ok=True)

    name = f"{uuid.uuid4().hex}{BILD_ENDUNG}"
    (ordner / unterordner / name).write_bytes(daten)
    return f"{unterordner}/{name}"


def datei_ablegen(daten: bytes, endung: str) -> str:
    """Legt eine hochgeladene Datei ab, wie ein erzeugtes Bild.

    Eigener Unterordner, damit man Selbstgemachtes von Erzeugtem
    unterscheiden kann, ohne in die Datenbank zu sehen. Der Name wird aus
    demselben Grund gewürfelt wie oben: die Dateien liegen unter einer
    öffentlich erreichbaren Adresse, damit die Plattformen sie abholen
    können, und ein sprechender Name stünde damit im Netz.
    """
    ordner: Path = current_app.config["UPLOAD_ORDNER"]
    unterordner = "hochgeladen"
    (ordner / unterordner).mkdir(parents=True, exist_ok=True)

    name = f"{uuid.uuid4().hex}.{endung.lstrip('.')}"
    (ordner / unterordner / name).write_bytes(daten)
    return f"{unterordner}/{name}"


def variantengruppe() -> str:
    """Kennung für einen Schwung Varianten, die gegeneinander gemessen werden."""
    return secrets.token_hex(8)

