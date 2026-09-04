"""Prueft den Threads-Adapter gegen untergeschobene Antworten.

    venv\\Scripts\\python.exe pruefe_threads.py

Threads gehoert Meta, ist aber keine Erweiterung der Graph API: eigener
Host, eigener Anmeldeweg, eigene Rechte, eigene App, eigenes Verfahren fuers
Erneuern. Genau deshalb wird hier eigens nachgemessen und nicht darauf
vertraut, dass "das ja wie Instagram laeuft".

Vier Stellen, an denen es teuer wird:

* **Der Anmeldeweg geht ueber threads.net, nicht ueber facebook.com**, und
  die Token-Adressen liegen ohne Versionsnummer daneben. Wer eine davon
  verwechselt, bekommt einen 404, der wie ein falscher Pfad aussieht.
* **Das erste Token gilt eine Stunde.** Wer es speichert statt es zu
  tauschen, hat einen Kanal, der nach dem Mittagessen tot ist.
* **Erneuert wird das Zugangs-Token selbst**, ein eigenes
  Erneuerungs-Token gibt es nicht. Und ein Token, das 60 Tage nicht
  aufgefrischt wurde, ist endgueltig hin.
* **Es gibt keine Ablagen.** Ein Wert in `ablage_id` ist hier ein
  Missverstaendnis und kein Ziel; er darf den Beitrag nicht umlenken.

Laeuft trocken: ohne Netz, ohne Schluessel, ohne Datenbank.
"""

import sys
from datetime import datetime, timedelta

from app import create_app
from app.config import Config
from app.kanaele import KanalFehler
from app.kanaele import threads as modul
from app.kanaele.threads import Threads

ADRESSE = "https://pinario.example"
ZUGANG = "th-lang-1"
KONTO = "9911"


class Antwort:
    def __init__(self, status=200, daten=None, text=""):
        self.status_code = status
        self._daten = daten
        self.text = text

    def json(self):
        if self._daten is None:
            raise ValueError("kein JSON")
        return self._daten


class Netz:
    """Untergeschobenes `requests`, Antworten nach dem Ende der Adresse.

    Wie bei `pruefe_meta.py`: verglichen wird auf das Ende und nicht auf ein
    enthaltenes Stueck, sonst faengt "/threads" auch "/threads_publish" ab.
    """

    class RequestException(Exception):
        pass

    def __init__(self):
        self.aufrufe = []
        self.antworten = {}
        self.wirft = None

    def stelle(self, teil, *antworten):
        self.antworten[teil] = list(antworten)

    def _naechste(self, art, url, kwargs):
        self.aufrufe.append({"art": art, "url": url, **kwargs})
        if self.wirft:
            raise self.wirft
        for teil, liste in self.antworten.items():
            if url.endswith(teil) and liste:
                return liste.pop(0) if len(liste) > 1 else liste[0]
        raise AssertionError(f"keine Antwort hinterlegt für {url}")

    def get(self, url, **kwargs):
        return self._naechste("get", url, kwargs)

    def post(self, url, **kwargs):
        return self._naechste("post", url, kwargs)


class TestConfig(Config):
    PRODUKTION = False
    OEFFENTLICHE_ADRESSE = ADRESSE
    SQLALCHEMY_DATABASE_URI = "postgresql+psycopg://niemand@localhost/niemand"


ergebnisse = []


def pruefe(name, bedingung):
    ergebnisse.append((name, bool(bedingung)))


def wirft(name, aufruf, *, enthaelt=""):
    try:
        aufruf()
    except KanalFehler as fehler:
        pruefe(name, not enthaelt or enthaelt.lower() in str(fehler).lower())
        return
    except Exception as fehler:  # noqa: BLE001
        pruefe(f"{name} (falscher Fehlertyp: {type(fehler).__name__})", False)
        return
    pruefe(f"{name} (kein Fehler geworfen)", False)


def _letzter(netz, teil):
    for aufruf in reversed(netz.aufrufe):
        if aufruf["url"].endswith(teil):
            return aufruf
    raise AssertionError(f"kein Aufruf auf {teil}")


def _posten(kanal, **abweichung):
    felder = {
        "titel": "Gästemappe",
        "beschreibung": "Kurz erklärt.",
        "ziel_url": "https://welcometap.de",
        "datei": "erzeugt/abc.png",
        "ablage_id": None,
    }
    felder.update(abweichung)
    return kanal.veroeffentlichen(ZUGANG, **felder)


def _bereit(netz):
    """Der Normalfall: Konto da, Container fertig, Beitrag geht raus."""
    netz.antworten.clear()
    netz.stelle("/me", Antwort(daten={"id": KONTO, "username": "pinario"}))
    netz.stelle("/threads_publish", Antwort(daten={"id": "th-post-1"}))
    netz.stelle("/threads", Antwort(daten={"id": "container-1"}))
    netz.stelle("/container-1", Antwort(daten={"status": "FINISHED"}))


def main() -> int:  # noqa: C901
    app = create_app(TestConfig)
    netz = Netz()
    modul.requests = netz
    kanal = Threads()
    kanal._zugangsdaten = lambda: ("app-1", "geheim")  # noqa: SLF001

    with app.test_request_context():
        # --- Was der Kanal ueberhaupt ist -----------------------------

        pruefe("Threads kennt keine Ablagen", not kanal.unterstuetzt_ablagen)
        pruefe("Threads nimmt kein Video", "video" not in kanal.typen)
        pruefe("Der Link gehoert in den Text", kanal.link_im_text)
        # Der Unterschied zu Instagram, und er ist wichtig.
        pruefe("Und ist dort anklickbar", kanal.link_klickbar)
        pruefe("Die Textgrenze ist 500", kanal.max_beschreibung == 500)

        # --- Anmelde-Adresse ------------------------------------------

        import app.einstellungen as e

        e.kanal_wert = lambda k, f: {"app_id": "app-1", "app_secret": "g"}.get(f, "")

        adresse = kanal.anmelde_adresse("zustand-1")
        # Der erste teure Fall, siehe Kopf.
        pruefe("Anmeldung geht zu threads.net, nicht zu facebook.com",
               adresse.startswith("https://threads.net/oauth/authorize")
               and "facebook.com" not in adresse)
        pruefe("Anmeldung traegt die App-ID", "client_id=app-1" in adresse)
        pruefe("Anmeldung traegt den Zustand", "state=zustand-1" in adresse)
        pruefe("Anmeldung traegt die Rueckruf-Adresse",
               "pinario.example%2Fkanaele%2Fthreads%2Frueckruf" in adresse)
        pruefe("Anmeldung fragt threads_basic", "threads_basic" in adresse)
        pruefe("Anmeldung fragt threads_content_publish",
               "threads_content_publish" in adresse)

        e.kanal_wert = lambda k, f: ""
        wirft("Ohne App-ID keine Anmeldung",
              lambda: kanal.anmelde_adresse("x"),
              enthaelt="App-ID")
        e.kanal_wert = lambda k, f: {"app_id": "app-1", "app_secret": "g"}.get(f, "")

        # --- Code eintauschen -----------------------------------------

        netz.aufrufe.clear()
        netz.stelle("/oauth/access_token",
                    Antwort(daten={"access_token": "th-kurz", "user_id": KONTO}))
        netz.stelle("/access_token",
                    Antwort(daten={"access_token": ZUGANG, "expires_in": 5184000}))
        netz.stelle("/me", Antwort(daten={"id": KONTO, "username": "pinario"}))

        felder = kanal.zugang_holen("code-1")
        erster = _letzter(netz, "/oauth/access_token")
        zweiter = _letzter(netz, "/access_token")

        pruefe("Der Code geht an die Token-Adresse",
               erster["data"].get("code") == "code-1")
        pruefe("Mit der Rueckruf-Adresse",
               erster["data"].get("redirect_uri")
               == f"{ADRESSE}/kanaele/threads/rueckruf")
        pruefe("Und dem richtigen Grant-Typ",
               erster["data"].get("grant_type") == "authorization_code")
        # Der zweite teure Fall, siehe Kopf.
        pruefe("Das kurzlebige Token wird sofort getauscht",
               zweiter["params"].get("grant_type") == "th_exchange_token"
               and zweiter["params"].get("access_token") == "th-kurz")
        pruefe("Beim Tausch geht das Secret mit",
               zweiter["params"].get("client_secret") == "geheim")
        pruefe("Gespeichert wird das langlebige", felder["zugang"] == ZUGANG)
        pruefe("Threads kennt kein eigenes Erneuerungs-Token",
               felder["erneuerung"] == ZUGANG)
        pruefe("Ablauf liegt rund 60 Tage voraus",
               timedelta(days=59)
               < felder["laeuft_ab"] - datetime.now(felder["laeuft_ab"].tzinfo)
               < timedelta(days=61))
        pruefe("Der Kontoname kommt mit dem @ davor",
               felder["kontoname"] == "@pinario")
        pruefe("Jeder Aufruf hat eine Frist", erster["timeout"] > 0)

        netz.stelle("/oauth/access_token", Antwort(daten={"user_id": KONTO}))
        wirft("Eine Antwort ohne Token wird abgelehnt",
              lambda: kanal.zugang_holen("code"),
              enthaelt="keinen Zugang")

        netz.stelle("/oauth/access_token", Antwort(status=400, daten={
            "error": {"message": "Invalid platform app", "code": 1}
        }))
        wirft("Ein abgelehnter Tausch nennt den Grund",
              lambda: kanal.zugang_holen("code"),
              enthaelt="Invalid platform app")

        netz.wirft = Netz.RequestException("Netz weg")
        wirft("Netzfehler wird zum KanalFehler",
              lambda: kanal.zugang_holen("code"),
              enthaelt="nicht erreichbar")
        netz.wirft = None

        # --- Erneuern -------------------------------------------------

        netz.antworten.clear()
        netz.stelle("/refresh_access_token",
                    Antwort(daten={"access_token": "th-neu", "expires_in": 5184000}))
        felder = kanal.zugang_erneuern(ZUGANG)
        auffrischen = _letzter(netz, "/refresh_access_token")

        pruefe("Erneuert wird ueber refresh_access_token",
               auffrischen["params"].get("grant_type") == "th_refresh_token")
        pruefe("Dabei geht das alte Zugangs-Token mit, kein anderes",
               auffrischen["params"].get("access_token") == ZUGANG)
        pruefe("Beim Erneuern braucht es kein Secret",
               "client_secret" not in auffrischen["params"])
        pruefe("Das neue Token kommt zurueck", felder["zugang"] == "th-neu")
        pruefe("Und steht wieder in beiden Feldern",
               felder["erneuerung"] == "th-neu")

        wirft("Ohne Token gar kein Aufruf",
              lambda: kanal.zugang_erneuern(""),
              enthaelt="neu verbunden")

        netz.stelle("/refresh_access_token", Antwort(status=400, daten={
            "error": {"message": "The access token could not be refreshed."}
        }))
        wirft("Ein abgelehntes Erneuern nennt den Grund",
              lambda: kanal.zugang_erneuern(ZUGANG),
              enthaelt="could not be refreshed")

        # --- Posten ---------------------------------------------------

        _bereit(netz)
        netz.aufrufe.clear()
        antwort = _posten(kanal)
        container = _letzter(netz, "/threads")
        veroeffentlichen = _letzter(netz, "/threads_publish")

        pruefe("Der Container geht an die eigene Konto-Kennung",
               container["url"].endswith(f"/{KONTO}/threads"))
        pruefe("Als Bild-Beitrag", container["data"]["media_type"] == "IMAGE")
        pruefe("Mit der oeffentlichen Bildadresse",
               container["data"]["image_url"]
               == f"{ADRESSE}/medien/erzeugt/abc.png")
        pruefe("Der Titel steht mit im Text",
               "Gästemappe" in container["data"]["text"])
        pruefe("Der Ziel-Link steht im Text",
               "https://welcometap.de" in container["data"]["text"])
        pruefe("Veroeffentlicht wird mit der Container-Kennung",
               veroeffentlichen["data"]["creation_id"] == "container-1")
        pruefe("Der Status wird vorher abgefragt",
               any(a["url"].endswith("/container-1") for a in netz.aufrufe))
        pruefe("Zurueck kommt die Beitrags-Kennung",
               antwort.plattform_id == "th-post-1")
        # Der vierte teure Fall, siehe Kopf.
        pruefe("Ohne Ablagen bleibt das Ziel leer",
               antwort.ablage_id is None)

        _bereit(netz)
        netz.aufrufe.clear()
        # Mit einem gesetzten Wert pruefen, nicht mit None: sonst besteht
        # die Pruefung auch dann, wenn der Adapter ihn brav durchreicht.
        antwort = _posten(kanal, ablage_id="sollte-egal-sein")
        pruefe("Ein Wert in ablage_id lenkt den Beitrag nicht um",
               _letzter(netz, "/threads")["url"].endswith(f"/{KONTO}/threads"))
        pruefe("Und landet auch nicht in der Veroeffentlichung",
               antwort.ablage_id is None)

        wirft("Ohne Bild gar kein Aufruf",
              lambda: _posten(kanal, datei=None),
              enthaelt="Bild")

        _bereit(netz)
        netz.stelle("/threads", Antwort(daten={}))
        wirft("Ohne Container wird nicht veroeffentlicht",
              lambda: _posten(kanal),
              enthaelt="keinen Container")

        _bereit(netz)
        netz.stelle("/container-1", Antwort(daten={
            "status": "ERROR", "error_message": "Bild nicht erreichbar",
        }))
        vorher = len([a for a in netz.aufrufe
                      if a["url"].endswith("/threads_publish")])
        wirft("Ein kaputter Container wird nicht veroeffentlicht",
              lambda: _posten(kanal),
              enthaelt="Bild nicht erreichbar")
        pruefe("Und danach geht nichts mehr raus",
               len([a for a in netz.aufrufe
                    if a["url"].endswith("/threads_publish")]) == vorher)

        _bereit(netz)
        netz.stelle("/container-1", Antwort(daten={"status": "IN_PROGRESS"}))
        modul.CONTAINER_VERSUCHE = 2
        modul.CONTAINER_PAUSE = 0
        wirft("Ein Container, der nie fertig wird, laeuft in die Grenze",
              lambda: _posten(kanal),
              enthaelt="nicht rechtzeitig")

        _bereit(netz)
        netz.stelle("/threads_publish", Antwort(daten={}))
        wirft("Ohne Kennung gilt der Beitrag nicht als raus",
              lambda: _posten(kanal),
              enthaelt="keine Kennung")

        _bereit(netz)
        netz.stelle("/me", Antwort(daten={"username": "ohne-kennung"}))
        wirft("Ohne Konto-Kennung gar kein Beitrag",
              lambda: _posten(kanal),
              enthaelt="keine Konto-Kennung")

        # --- Der Ziel-Link im Text ------------------------------------

        text = modul._text_mit_link("Kurz.", "https://welcometap.de", 500)
        pruefe("Der Link haengt hinten dran",
               text.endswith("https://welcometap.de"))
        pruefe("Ein Link, der schon dasteht, kommt nicht zweimal",
               modul._text_mit_link(
                   "Mehr auf https://welcometap.de", "https://welcometap.de", 500
               ).count("https://welcometap.de") == 1)
        eng = modul._text_mit_link("x" * 600, "https://welcometap.de", 60)
        pruefe("Bei Platzmangel wird der Text gekuerzt, nicht der Link",
               eng.endswith("https://welcometap.de") and len(eng) <= 60)
        wirft("Ein Link, der allein zu lang ist, wird gemeldet",
              lambda: modul._text_mit_link("x", "https://" + "y" * 80, 20),
              enthaelt="länger als die Plattform")

        # Threads schneidet bei 500 ab, und der Adapter muss das vorher tun.
        _bereit(netz)
        netz.aufrufe.clear()
        _posten(kanal, titel="", beschreibung="y" * 900)
        pruefe("Der Text wird auf die Grenze gekuerzt",
               len(_letzter(netz, "/threads")["data"]["text"]) <= 500)

        # --- Zahlen ---------------------------------------------------

        netz.antworten.clear()
        netz.stelle("/insights", Antwort(daten={"data": [
            {"name": "views", "total_value": {"value": 412}},
        ]}))
        zahlen = kanal.zahlen(ZUGANG, "th-1")
        pruefe("Aufrufe kommen aus total_value", zahlen.impressions == 412)
        pruefe("Threads kennt keine Klicks und laesst es bei Null",
               zahlen.clicks == 0)
        pruefe("Und keine Speicherungen", zahlen.saves == 0)

        netz.stelle("/insights", Antwort(daten={"data": [
            {"name": "views", "values": [{"value": 5}, {"value": 77}]},
        ]}))
        pruefe("Auch die Schreibweise mit values wird gelesen, letzter Wert",
               kanal.zahlen(ZUGANG, "th-1").impressions == 77)

        netz.stelle("/insights", Antwort(daten={"data": []}))
        pruefe("Fehlende Kennzahlen sind Null, kein Absturz",
               kanal.zahlen(ZUGANG, "th-1").impressions == 0)

        netz.stelle("/insights", Antwort(daten={"data": [
            {"name": "views", "total_value": {"value": "viele"}},
        ]}))
        pruefe("Eine unlesbare Kennzahl wird zu Null",
               kanal.zahlen(ZUGANG, "th-1").impressions == 0)

    for name, gut in ergebnisse:
        if not gut:
            print(f"  FEHLER  {name}")

    fehler = [n for n, gut in ergebnisse if not gut]
    print()
    if fehler:
        print(f"{len(fehler)} von {len(ergebnisse)} Prüfungen fehlgeschlagen.")
        return 1
    print(f"Alle {len(ergebnisse)} Prüfungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
