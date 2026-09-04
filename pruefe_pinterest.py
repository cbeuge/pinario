"""Prueft den Pinterest-Adapter gegen untergeschobene Antworten.

    venv\\Scripts\\python.exe pruefe_pinterest.py

Warum es dieses Skript gibt: gegen die echte API ist der Adapter noch nie
gelaufen, und bis die App bei Pinterest steht, kann er das auch nicht. Was
sich trotzdem messen laesst, ist alles, was nicht die Wirklichkeit von
Pinterest betrifft — und genau dort sitzen die teuren Fehler:

* Die Rueckruf-Adresse muss beim Anmelden und beim Eintauschen des Codes
  **zeichengenau dieselbe** sein. Weicht sie ab, kommt `invalid_grant`
  zurueck und sagt nicht, woran es lag.
* Beim Erneuern schickt Pinterest kein neues Erneuerungs-Token mit. Wer das
  alte dabei ueberschreibt, verliert den Zugang dauerhaft — und merkt es
  erst 30 Tage spaeter.
* Ein abgelehnter Aufruf muss einen lesbaren Grund hinterlassen. Der steht
  in `posted_items.fehler` und ist spaeter die einzige Spur.

Laeuft trocken: ohne Netz, ohne Schluessel, ohne Datenbank. `requests` und
die Einstellungen werden untergeschoben.
"""

import sys
from datetime import datetime, timedelta

from app import create_app
from app.config import Config
from app.kanaele import KanalFehler
from app.kanaele import pinterest as modul
from app.kanaele.pinterest import Pinterest

ADRESSE = "https://pinario.example"
BOARD = "888"
ZUGANG = "zugang-abc"


class Antwort:
    """Das Wenige, das der Adapter von einer Antwort liest."""

    def __init__(self, status=200, daten=None, text=""):
        self.status_code = status
        self._daten = daten
        self.text = text

    def json(self):
        if self._daten is None:
            raise ValueError("kein JSON")
        return self._daten


class Netz:
    """Untergeschobenes `requests`. Merkt sich, was rausgegangen waere."""

    class RequestException(Exception):
        pass

    def __init__(self):
        self.aufrufe = []
        self.antworten = []
        self.wirft = None

    def stelle(self, *antworten):
        self.antworten = list(antworten)

    def _naechste(self, art, url, kwargs):
        self.aufrufe.append({"art": art, "url": url, **kwargs})
        if self.wirft:
            raise self.wirft
        if not self.antworten:
            raise AssertionError(f"keine Antwort hinterlegt für {url}")
        return self.antworten.pop(0)

    def get(self, url, **kwargs):
        return self._naechste("get", url, kwargs)

    def post(self, url, **kwargs):
        return self._naechste("post", url, kwargs)


class TestConfig(Config):
    PRODUKTION = False
    OEFFENTLICHE_ADRESSE = ADRESSE
    # Der Adapter fragt nie die Datenbank, weil `kanal_wert` unten ersetzt
    # wird. Die Adresse hier steht trotzdem, damit `create_app` durchlaeuft.
    SQLALCHEMY_DATABASE_URI = "postgresql+psycopg://niemand@localhost/niemand"


ergebnisse = []


def pruefe(name: str, bedingung: bool) -> None:
    ergebnisse.append((name, bool(bedingung)))


def wirft(name: str, aufruf, *, enthaelt: str = "") -> None:
    """Prueft, dass ein Aufruf einen lesbaren KanalFehler wirft."""
    try:
        aufruf()
    except KanalFehler as fehler:
        pruefe(name, not enthaelt or enthaelt.lower() in str(fehler).lower())
        return
    except Exception as fehler:  # noqa: BLE001
        pruefe(f"{name} (falscher Fehlertyp: {type(fehler).__name__})", False)
        return
    pruefe(f"{name} (kein Fehler geworfen)", False)


def main() -> int:  # noqa: C901
    app = create_app(TestConfig)
    adapter = Pinterest()
    netz = Netz()
    modul.requests = netz

    # Zugangsdaten kommen sonst aus der Datenbank.
    modul._zugangsdaten = lambda: ("app-1", "geheim")

    with app.test_request_context():
        # --- Was der Kanal ueberhaupt annimmt -------------------------

        pruefe("Video steht nicht in den Typen", "video" not in adapter.typen)
        pruefe("Bild steht in den Typen", "image" in adapter.typen)
        pruefe("Kanal kennt Ablagen", adapter.unterstuetzt_ablagen)

        # --- Anmelde-Adresse ------------------------------------------

        modul_kanal_wert = {"app_id": "app-1", "app_secret": "geheim"}
        import app.einstellungen as e

        e.kanal_wert = lambda k, f: modul_kanal_wert.get(f, "")

        adresse = adapter.anmelde_adresse("zustand-123")
        pruefe("Anmeldung geht zu Pinterest",
               adresse.startswith("https://www.pinterest.com/oauth/"))
        pruefe("Anmeldung traegt die App-ID", "client_id=app-1" in adresse)
        pruefe("Anmeldung traegt den Zustand", "state=zustand-123" in adresse)
        pruefe("Anmeldung traegt die Rueckruf-Adresse",
               "pinario.example%2Fkanaele%2Fpinterest%2Frueckruf" in adresse)
        for bereich in ("boards%3Aread", "pins%3Awrite"):
            pruefe(f"Anmeldung traegt {bereich}", bereich in adresse)

        modul_kanal_wert["app_id"] = ""
        wirft("Ohne App-ID keine Anmeldung",
              lambda: adapter.anmelde_adresse("x"),
              enthaelt="App-ID")
        modul_kanal_wert["app_id"] = "app-1"

        # --- Code eintauschen -----------------------------------------

        netz.stelle(
            Antwort(daten={
                "access_token": ZUGANG,
                "refresh_token": "erneuern-1",
                "expires_in": 2592000,
            }),
            Antwort(daten={"username": "pinario", "id": "1"}),
        )
        felder = adapter.zugang_holen("code-xyz")
        token_aufruf = netz.aufrufe[0]

        pruefe("Token wird geholt",
               token_aufruf["url"].endswith("/oauth/token"))
        pruefe("App weist sich per Basic-Auth aus",
               token_aufruf["headers"]["Authorization"].startswith("Basic "))
        pruefe("Das Secret steht nicht im Rumpf",
               "geheim" not in str(token_aufruf["data"]))
        pruefe("Code geht mit", token_aufruf["data"]["code"] == "code-xyz")
        pruefe("Grant-Typ stimmt",
               token_aufruf["data"]["grant_type"] == "authorization_code")
        # Der wichtigste Fall dieses Skripts, siehe Kopf.
        pruefe("Rueckruf-Adresse beim Eintauschen ist dieselbe wie beim Anmelden",
               token_aufruf["data"]["redirect_uri"]
               == f"{ADRESSE}/kanaele/pinterest/rueckruf")
        pruefe("Jeder Aufruf hat eine Frist", token_aufruf["timeout"] > 0)

        pruefe("Zugang kommt zurueck", felder["zugang"] == ZUGANG)
        pruefe("Erneuerung kommt zurueck", felder["erneuerung"] == "erneuern-1")
        pruefe("Kontoname kommt aus /user_account",
               felder["kontoname"] == "pinario")
        pruefe("Ablauf wird ausgerechnet",
               isinstance(felder["laeuft_ab"], datetime))
        pruefe("Ablauf liegt rund 30 Tage voraus",
               timedelta(days=29)
               < felder["laeuft_ab"] - datetime.now(felder["laeuft_ab"].tzinfo)
               < timedelta(days=31))
        pruefe("Kontoname wird mit Bearer geholt",
               netz.aufrufe[1]["headers"]["Authorization"] == f"Bearer {ZUGANG}")

        netz.stelle(Antwort(daten={"refresh_token": "nur-das"}))
        wirft("Antwort ohne Zugang wird abgelehnt",
              lambda: adapter.zugang_holen("code"),
              enthaelt="keinen Zugang")

        netz.stelle(Antwort(status=401, daten={
            "code": 2, "message": "Authentication failed."
        }))
        wirft("Abgelehnter Tausch nennt den Grund",
              lambda: adapter.zugang_holen("code"),
              enthaelt="Authentication failed")

        netz.stelle(Antwort(status=500, text="<html>Bad Gateway</html>"))
        wirft("Antwort ohne JSON nennt trotzdem den Status",
              lambda: adapter.zugang_holen("code"),
              enthaelt="500")

        netz.wirft = Netz.RequestException("Verbindung abgebrochen")
        wirft("Netzfehler wird zum KanalFehler",
              lambda: adapter.zugang_holen("code"),
              enthaelt="nicht erreichbar")
        netz.wirft = None

        # --- Erneuern -------------------------------------------------

        netz.stelle(Antwort(daten={"access_token": "neu", "expires_in": 100}))
        felder = adapter.zugang_erneuern("erneuern-1")
        pruefe("Erneuern schickt das alte Token",
               netz.aufrufe[-1]["data"]["refresh_token"] == "erneuern-1")
        pruefe("Erneuern nutzt den richtigen Grant-Typ",
               netz.aufrufe[-1]["data"]["grant_type"] == "refresh_token")
        pruefe("Neuer Zugang kommt zurueck", felder["zugang"] == "neu")
        # Der zweite teure Fall, siehe Kopf.
        pruefe("Ohne neues Erneuerungs-Token bleibt das alte stehen",
               felder["erneuerung"] == "erneuern-1")

        netz.stelle(Antwort(daten={
            "access_token": "neu", "refresh_token": "erneuern-2"
        }))
        felder = adapter.zugang_erneuern("erneuern-1")
        pruefe("Ein neues Erneuerungs-Token wird uebernommen",
               felder["erneuerung"] == "erneuern-2")

        netz.stelle(Antwort(daten={"access_token": "neu"}))
        felder = adapter.zugang_erneuern("erneuern-1")
        pruefe("Ohne expires_in bleibt der Ablauf leer",
               felder["laeuft_ab"] is None)

        wirft("Ohne Erneuerungs-Token gar kein Aufruf",
              lambda: adapter.zugang_erneuern(""),
              enthaelt="neu verbunden")

        # --- Boards ---------------------------------------------------

        netz.stelle(
            Antwort(daten={
                "items": [{"id": "1", "name": "Ferienwohnung"}],
                "bookmark": "weiter",
            }),
            Antwort(daten={
                "items": [{"id": "2", "name": "Werkzeuge"}],
                "bookmark": None,
            }),
        )
        boards = adapter.ablagen(ZUGANG)
        pruefe("Boards ueber alle Seiten", len(boards) == 2)
        pruefe("Zweite Seite wird mit Lesezeichen geholt",
               netz.aufrufe[-1]["params"].get("bookmark") == "weiter")
        pruefe("Board traegt Kennung und Namen",
               boards[0].id == "1" and boards[0].name == "Ferienwohnung")

        netz.stelle(Antwort(daten={"items": [{"name": "ohne Kennung"}]}))
        pruefe("Board ohne Kennung faellt raus", adapter.ablagen(ZUGANG) == [])

        netz.stelle(Antwort(daten={}))
        pruefe("Antwort ohne items ergibt eine leere Liste",
               adapter.ablagen(ZUGANG) == [])

        # --- Pin schreiben --------------------------------------------

        netz.stelle(Antwort(daten={
            "id": "pin-1",
            "board_id": BOARD,
            "created_at": "2026-09-04T10:00:00-00:00",
        }))
        antwort = adapter.veroeffentlichen(
            ZUGANG,
            titel="Digitale Gästemappe",
            beschreibung="Kurz erklärt.",
            ziel_url="https://welcometap.de",
            datei="erzeugt/abc123.png",
            ablage_id=BOARD,
        )
        pin = netz.aufrufe[-1]["json"]
        pruefe("Pin geht an /pins", netz.aufrufe[-1]["url"].endswith("/pins"))
        pruefe("Pin traegt das Board", pin["board_id"] == BOARD)
        pruefe("Pin traegt den Ziel-Link", pin["link"] == "https://welcometap.de")
        pruefe("Bild kommt als oeffentliche Adresse",
               pin["media_source"] == {
                   "source_type": "image_url",
                   "url": f"{ADRESSE}/medien/erzeugt/abc123.png",
               })
        pruefe("Kennung kommt zurueck", antwort.plattform_id == "pin-1")
        pruefe("Board kommt zurueck", antwort.ablage_id == BOARD)
        pruefe("Zeitpunkt wird gelesen",
               isinstance(antwort.zeitpunkt, datetime))

        netz.stelle(Antwort(daten={"id": "pin-2"}))
        adapter.veroeffentlichen(
            ZUGANG,
            titel="x" * 200,
            beschreibung="y" * 2000,
            ziel_url="https://welcometap.de",
            datei="a.png",
            ablage_id=BOARD,
        )
        pin = netz.aufrufe[-1]["json"]
        pruefe("Titel wird gekuerzt", len(pin["title"]) == modul.MAX_TITEL)
        pruefe("Beschreibung wird gekuerzt",
               len(pin["description"]) == adapter.max_beschreibung)

        netz.stelle(Antwort(daten={"id": "pin-3", "created_at": "kein Datum"}))
        antwort = adapter.veroeffentlichen(
            ZUGANG, titel="t", beschreibung="b",
            ziel_url="https://x.de", datei="a.png", ablage_id=BOARD,
        )
        pruefe("Unlesbarer Zeitpunkt laesst den Pin trotzdem gelten",
               antwort.plattform_id == "pin-3" and antwort.zeitpunkt is None)

        netz.stelle(Antwort(daten={"board_id": BOARD}))
        wirft("Pin ohne Kennung wird abgelehnt",
              lambda: adapter.veroeffentlichen(
                  ZUGANG, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei="a.png", ablage_id=BOARD),
              enthaelt="keine Kennung")

        wirft("Ohne Board gar kein Aufruf",
              lambda: adapter.veroeffentlichen(
                  ZUGANG, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei="a.png", ablage_id=None),
              enthaelt="Board")

        wirft("Ohne Bild gar kein Aufruf",
              lambda: adapter.veroeffentlichen(
                  ZUGANG, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei=None, ablage_id=BOARD),
              enthaelt="Bild")

        netz.stelle(Antwort(status=403, daten={
            "code": 7, "message": "You do not have permission."
        }))
        wirft("Abgelehnter Pin nennt den Grund",
              lambda: adapter.veroeffentlichen(
                  ZUGANG, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei="a.png", ablage_id=BOARD),
              enthaelt="permission")

        # --- Zahlen ---------------------------------------------------

        netz.stelle(Antwort(daten={"all": {"summary_metrics": {
            "IMPRESSION": 120, "PIN_CLICK": 9, "SAVE": 4,
        }}}))
        zahlen = adapter.zahlen(ZUGANG, "pin-1")
        parameter = netz.aufrufe[-1]["params"]
        pruefe("Zahlen kommen an", (zahlen.impressions, zahlen.clicks,
                                    zahlen.saves) == (120, 9, 4))
        pruefe("Beide Daten gehen mit",
               "start_date" in parameter and "end_date" in parameter)
        pruefe("Zeitraum ist 90 Tage lang",
               (datetime.fromisoformat(parameter["end_date"])
                - datetime.fromisoformat(parameter["start_date"])).days
               == modul.ZEITRAUM_TAGE)
        pruefe("Alle drei Kennzahlen werden angefragt",
               parameter["metric_types"] == "IMPRESSION,PIN_CLICK,SAVE")

        netz.stelle(Antwort(daten={"summary_metrics": {"IMPRESSION": 5}}))
        pruefe("Kennzahlen auch ohne den Block 'all'",
               adapter.zahlen(ZUGANG, "p").impressions == 5)

        netz.stelle(Antwort(daten={"all": {}}))
        zahlen = adapter.zahlen(ZUGANG, "p")
        pruefe("Fehlende Kennzahlen sind Null, kein Absturz",
               (zahlen.impressions, zahlen.clicks, zahlen.saves) == (0, 0, 0))

        netz.stelle(Antwort(daten={"all": {"summary_metrics": {
            "IMPRESSION": "keine Zahl"
        }}}))
        pruefe("Unlesbare Kennzahl wird zu Null",
               adapter.zahlen(ZUGANG, "p").impressions == 0)

    fehler = [name for name, gut in ergebnisse if not gut]
    for name, gut in ergebnisse:
        if not gut:
            print(f"  FEHLER  {name}")

    print()
    if fehler:
        print(f"{len(fehler)} von {len(ergebnisse)} Prüfungen fehlgeschlagen.")
        return 1
    print(f"Alle {len(ergebnisse)} Prüfungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
