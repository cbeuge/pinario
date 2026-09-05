"""Prueft die beiden Meta-Adapter gegen untergeschobene Antworten.

    venv\\Scripts\\python.exe pruefe_meta.py

Gegen die echte API ist noch nichts gelaufen, dafuer fehlt die App. Was sich
trotzdem messen laesst, ist alles, was nicht Metas Wirklichkeit betrifft —
und dort sitzen die teuren Fehler:

* **Gepostet wird mit dem Seiten-Token, nicht mit dem Nutzer-Token.** Wer
  das verwechselt, bekommt einen Rechtefehler, der nach einem fehlenden
  Recht aussieht und keines ist.
* **Instagram postet zweistufig**, und zwischen Container und
  Veroeffentlichen muss Meta das Bild verarbeitet haben. Ein sofortiges
  media_publish scheitert sonst an einem Container, der noch nicht fertig
  ist.
* **Das kurzlebige Token gilt eine Stunde.** Wer es speichert statt es
  gegen ein langlebiges zu tauschen, hat einen Kanal, der nach dem
  Mittagessen tot ist.
* **Der Ziel-Link hat kein eigenes Feld.** Er muss in den Text, und er darf
  dabei nicht abgeschnitten werden: ein halber Link sieht aus, als fuehre er
  irgendwohin.

Laeuft trocken: ohne Netz, ohne Schluessel, ohne Datenbank.
"""

import sys
from datetime import datetime, timedelta

from app import create_app
from app.config import Config
from app.kanaele import KanalFehler
from app.kanaele import meta as modul
from app.kanaele.meta import Facebook, Instagram
from app.kanaele.pinterest import Pinterest

ADRESSE = "https://pinario.example"
NUTZER_TOKEN = "nutzer-token"
SEITEN_TOKEN = "seiten-token-abc"
SEITE = "111"
IG_KONTO = "222"


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
    """Untergeschobenes `requests`.

    Antworten werden nach Pfad hinterlegt, nicht der Reihe nach: die
    Adapter fragen die Seitenliste je nach Weg unterschiedlich oft ab, und
    eine feste Reihenfolge wuerde hier nur das Skript pruefen.

    Verglichen wird auf das **Ende** der Adresse und nicht auf ein
    enthaltenes Stueck. Sonst faengt "/media" auch "/media_publish" ab, und
    dann misst man den Container gegen die Antwort des Veroeffentlichens —
    ein Fehler, der wie ein Fehler im Adapter aussieht.
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
    """Der letzte Aufruf, dessen Adresse auf `teil` endet."""
    for aufruf in reversed(netz.aufrufe):
        if aufruf["url"].endswith(teil):
            return aufruf
    raise AssertionError(f"kein Aufruf auf {teil}")


SEITEN_ANTWORT = Antwort(daten={
    "data": [
        {
            "id": SEITE,
            "name": "Ferienhaus Peggy",
            "access_token": SEITEN_TOKEN,
            "instagram_business_account": {"id": IG_KONTO, "username": "peggy"},
        },
        {"id": "999", "name": "Ohne Instagram", "access_token": "tok-999"},
    ],
})


def main() -> int:  # noqa: C901
    app = create_app(TestConfig)
    netz = Netz()
    modul.requests = netz
    facebook = Facebook()
    instagram = Instagram()

    for kanal in (facebook, instagram):
        kanal._zugangsdaten = lambda: ("app-1", "geheim")  # noqa: SLF001

    with app.test_request_context():
        # --- Was die Kanaele ueberhaupt annehmen ----------------------

        pruefe("Facebook nimmt Video", "video" in facebook.typen)
        pruefe("Instagram nimmt kein Video", "video" not in instagram.typen)
        pruefe("Facebook: Link gehoert in den Text", facebook.link_im_text)
        pruefe("Facebook: Link ist dort anklickbar", facebook.link_klickbar)
        pruefe("Instagram: Link gehoert in den Text", instagram.link_im_text)
        # Der Punkt, der Instagram von allen anderen unterscheidet.
        pruefe("Instagram: Link ist NICHT anklickbar",
               not instagram.link_klickbar)
        pruefe("Facebook nennt seine Ablagen Seiten",
               facebook.ablage_mehrzahl == "Seiten")
        pruefe("Instagram will laengere Texte als 280 Zeichen",
               instagram.min_beschreibung >= 500)
        pruefe("Und die Untergrenze liegt unter der Obergrenze",
               instagram.min_beschreibung < instagram.max_beschreibung)
        pruefe("Instagram will Absaetze", instagram.absaetze)
        pruefe("Facebook will ebenfalls laengere Texte",
               facebook.min_beschreibung >= 400)
        pruefe("Aber weniger als Instagram: dort wird bewusst gelesen",
               facebook.min_beschreibung < instagram.min_beschreibung)
        pruefe("Auch Facebook will Absaetze", facebook.absaetze)
        pruefe("Beide Untergrenzen liegen unter ihrer Obergrenze",
               facebook.min_beschreibung < facebook.max_beschreibung
               and instagram.min_beschreibung < instagram.max_beschreibung)
        pruefe("Pinterest bleibt unveraendert: dort zaehlt der Pin, nicht der Text",
               Pinterest().min_beschreibung == 0 and not Pinterest().absaetze)
        pruefe("Instagram nennt seine Ablagen Konten",
               instagram.ablage_mehrzahl == "Konten")

        # --- Anmelde-Adresse ------------------------------------------

        import app.einstellungen as e

        e.kanal_wert = lambda k, f: {"app_id": "app-1", "app_secret": "g"}.get(f, "")

        adresse = facebook.anmelde_adresse("zustand-1")
        pruefe("Anmeldung geht zu Facebook",
               adresse.startswith("https://www.facebook.com/"))
        pruefe("Anmeldung nennt die Version", modul.VERSION in adresse)
        pruefe("Anmeldung traegt den Zustand", "state=zustand-1" in adresse)
        pruefe("Anmeldung traegt die Rueckruf-Adresse",
               "pinario.example%2Fkanaele%2Ffacebook%2Frueckruf" in adresse)
        pruefe("Facebook fragt pages_manage_posts",
               "pages_manage_posts" in adresse)
        pruefe("Facebook fragt NICHT nach Instagram-Rechten",
               "instagram_content_publish" not in adresse)

        adresse = instagram.anmelde_adresse("zustand-2")
        pruefe("Instagram fragt instagram_content_publish",
               "instagram_content_publish" in adresse)
        pruefe("Instagram fragt NICHT nach dem Recht, Seiten zu beschreiben",
               "pages_manage_posts" not in adresse)
        pruefe("Instagram braucht trotzdem die Seitenliste",
               "pages_show_list" in adresse)
        pruefe("Rueckruf-Adresse je Kanal verschieden",
               "%2Fkanaele%2Finstagram%2Frueckruf" in adresse)

        # --- Der Business-Anmeldeweg ----------------------------------
        #
        # Am 04.09.2026 hing genau hier alles fest: "Facebook Login for
        # Business" nimmt kein `scope`, sondern die `config_id` einer
        # Konfiguration. Ruft man ihn trotzdem mit `scope` auf, kommt der
        # Nutzer nicht zurueck -- ohne Fehler, der bei uns ankaeme.

        e.kanal_wert = lambda k, f: {
            "app_id": "app-1", "app_secret": "g", "config_id": "conf-9"
        }.get(f, "")
        adresse = facebook.anmelde_adresse("zustand-3")
        pruefe("Mit Konfigurations-ID geht sie mit",
               "config_id=conf-9" in adresse)
        pruefe("Und dann steht KEIN scope mehr drin", "scope=" not in adresse)
        # Ohne das nimmt der Business-Dialog seinen eigenen Standard und
        # liefert ein Token statt eines Codes zurueck.
        pruefe("Der Antworttyp wird ausdruecklich erzwungen",
               "override_default_response_type=true" in adresse)
        pruefe("Die Rueckruf-Adresse bleibt dieselbe",
               "%2Fkanaele%2Ffacebook%2Frueckruf" in adresse)

        e.kanal_wert = lambda k, f: {"app_id": "app-1", "app_secret": "g"}.get(f, "")
        adresse = facebook.anmelde_adresse("zustand-4")
        pruefe("Ohne Konfigurations-ID bleibt es beim klassischen Weg",
               "scope=" in adresse and "config_id" not in adresse)
        pruefe("Und ohne den Zwang beim Antworttyp",
               "override_default_response_type" not in adresse)

        # --- Code eintauschen -----------------------------------------

        netz.aufrufe.clear()
        netz.stelle(
            "/oauth/access_token",
            Antwort(daten={"access_token": "kurz-1", "expires_in": 3600}),
            Antwort(daten={"access_token": "lang-1", "expires_in": 5184000}),
        )
        netz.stelle("/me", Antwort(daten={"name": "Carsten"}))
        felder = facebook.zugang_holen("code-1")

        aufrufe = [a for a in netz.aufrufe
                   if a["url"].endswith("/oauth/access_token")]
        pruefe("Zwei Token-Aufrufe: tauschen und verlaengern",
               len(aufrufe) == 2)
        pruefe("Der erste tauscht den Code",
               aufrufe[0]["params"].get("code") == "code-1")
        pruefe("Der erste schickt die Rueckruf-Adresse mit",
               aufrufe[0]["params"].get("redirect_uri")
               == f"{ADRESSE}/kanaele/facebook/rueckruf")
        # Der wichtigste Fall dieses Skripts, siehe Kopf.
        pruefe("Der zweite verlaengert das kurzlebige Token",
               aufrufe[1]["params"].get("grant_type") == "fb_exchange_token"
               and aufrufe[1]["params"].get("fb_exchange_token") == "kurz-1")
        pruefe("Gespeichert wird das langlebige, nicht das kurze",
               felder["zugang"] == "lang-1")
        pruefe("Meta kennt kein Erneuerungs-Token, es steht dasselbe drin",
               felder["erneuerung"] == "lang-1")
        pruefe("Ablauf liegt rund 60 Tage voraus",
               timedelta(days=59)
               < felder["laeuft_ab"] - datetime.now(felder["laeuft_ab"].tzinfo)
               < timedelta(days=61))
        pruefe("Kontoname kommt aus /me", felder["kontoname"] == "Carsten")
        pruefe("Jeder Aufruf hat eine Frist", aufrufe[0]["timeout"] > 0)

        netz.stelle("/oauth/access_token",
                    Antwort(daten={"access_token": "lang-2"}))
        felder = facebook.zugang_erneuern("lang-1")
        pruefe("Erneuern schickt das alte Token",
               _letzter(netz, "/oauth/access_token")["params"]
               .get("fb_exchange_token") == "lang-1")
        pruefe("Ohne expires_in bleibt der Ablauf leer",
               felder["laeuft_ab"] is None)
        wirft("Ohne Token gar kein Aufruf",
              lambda: facebook.zugang_erneuern(""),
              enthaelt="neu verbunden")

        netz.stelle("/oauth/access_token", Antwort(status=400, daten={
            "error": {
                "message": "Invalid verification code format.",
                "code": 100, "error_subcode": 36007,
            }
        }))
        wirft("Ein abgelehnter Tausch nennt den Grund",
              lambda: facebook.zugang_holen("code"),
              enthaelt="Invalid verification code")
        netz.stelle("/oauth/access_token", Antwort(status=400, daten={
            "error": {"message": "technisch", "error_user_msg": "Fuer Menschen"}
        }))
        wirft("Metas Text fuer Menschen wird bevorzugt",
              lambda: facebook.zugang_holen("code"),
              enthaelt="Fuer Menschen")

        netz.wirft = Netz.RequestException("Verbindung weg")
        wirft("Netzfehler wird zum KanalFehler",
              lambda: facebook.zugang_erneuern("lang-1"),
              enthaelt="nicht erreichbar")
        netz.wirft = None

        # --- Seiten und Konten ----------------------------------------

        netz.antworten.clear()
        netz.aufrufe.clear()
        netz.stelle("/me/accounts", SEITEN_ANTWORT)

        seiten = facebook.ablagen(NUTZER_TOKEN)
        pruefe("Facebook findet beide Seiten", len(seiten) == 2)
        pruefe("Seite traegt Kennung und Namen",
               seiten[0].id == SEITE and seiten[0].name == "Ferienhaus Peggy")

        konten = instagram.ablagen(NUTZER_TOKEN)
        pruefe("Instagram findet nur die Seite mit verknuepftem Konto",
               len(konten) == 1)
        pruefe("Konto traegt die Instagram-Kennung, nicht die der Seite",
               konten[0].id == IG_KONTO)
        pruefe("Konto zeigt den Benutzernamen", "@peggy" in konten[0].name)
        pruefe("Und dazu die Seite, an der es haengt",
               "Ferienhaus Peggy" in konten[0].name)

        netz.stelle("/me/accounts", Antwort(daten={"data": []}))
        pruefe("Kein verknuepftes Konto ergibt eine leere Liste",
               instagram.ablagen(NUTZER_TOKEN) == [])

        netz.stelle("/me/accounts", Antwort(daten={}))
        pruefe("Antwort ohne data ergibt eine leere Liste",
               facebook.ablagen(NUTZER_TOKEN) == [])

        # --- Welche Rechte wirklich erteilt sind -----------------------
        #
        # Am 05.09.2026 sah Facebook verbunden aus, zeigte vier Seiten und
        # konnte auf keine posten: `pages_show_list` war erteilt, die beiden
        # Schreib-Rechte nicht. Aufgefallen ist es erst am ersten faelligen
        # Beitrag. Was hier geprueft wird, ist genau dieser Fall.

        netz.antworten.clear()
        netz.aufrufe.clear()
        netz.stelle("/me/permissions", Antwort(daten={"data": [
            {"permission": "pages_show_list", "status": "granted"},
            {"permission": "business_management", "status": "granted"},
            {"permission": "pages_manage_posts", "status": "declined"},
        ]}))
        fehlt = facebook.fehlende_rechte(NUTZER_TOKEN)
        pruefe("Ein abgelehntes Recht faellt auf",
               "pages_manage_posts" in fehlt)
        pruefe("Ein gar nicht genanntes Recht faellt auch auf",
               "pages_read_engagement" in fehlt)
        pruefe("Erteilte Rechte stehen nicht in der Liste",
               "pages_show_list" not in fehlt)
        pruefe("Gefragt wird das Konto, nicht die eigene Anfrage",
               _letzter(netz, "/me/permissions")["art"] == "get")

        netz.stelle("/me/permissions", Antwort(daten={"data": [
            {"permission": recht, "status": "granted"}
            for recht in facebook.bereiche
        ]}))
        pruefe("Sind alle da, meldet die Pruefung nichts",
               facebook.fehlende_rechte(NUTZER_TOKEN) == [])

        # Instagram braucht andere Rechte als Facebook. Wuerde die Pruefung
        # eine feste Liste nehmen statt der des Kanals, faende sie hier
        # entweder nichts oder das Falsche.
        netz.stelle("/me/permissions", Antwort(daten={"data": [
            {"permission": "pages_show_list", "status": "granted"},
        ]}))
        pruefe("Instagram misst an seinen eigenen Rechten",
               "instagram_content_publish"
               in instagram.fehlende_rechte(NUTZER_TOKEN))

        # Scheitert die Abfrage selbst, ist das kein Grund, ein gegluecktes
        # Verbinden mit einer Warnung zu belasten, die nichts belegt.
        netz.stelle("/me/permissions", Antwort(status=400, daten={
            "error": {"message": "Unsupported get request", "code": 100},
        }))
        pruefe("Eine gescheiterte Abfrage meldet nichts statt zu raten",
               facebook.fehlende_rechte(NUTZER_TOKEN) == [])

        netz.wirft = Netz.RequestException("kein Netz")
        pruefe("Und ein Netzfehler wirft hier nicht durch",
               facebook.fehlende_rechte(NUTZER_TOKEN) == [])
        netz.wirft = None

        # --- Facebook posten ------------------------------------------

        netz.antworten.clear()
        netz.aufrufe.clear()
        netz.stelle("/me/accounts", SEITEN_ANTWORT)
        netz.stelle("/photos", Antwort(daten={
            "id": "foto-1", "post_id": f"{SEITE}_555",
        }))

        antwort = facebook.veroeffentlichen(
            NUTZER_TOKEN,
            titel="Digitale Gästemappe",
            beschreibung="Kurz erklärt.",
            ziel_url="https://welcometap.de",
            datei="erzeugt/abc.png",
            ablage_id=SEITE,
        )
        beitrag = _letzter(netz, "/photos")
        # Der zweitwichtigste Fall dieses Skripts, siehe Kopf.
        pruefe("Gepostet wird mit dem SEITEN-Token",
               beitrag["data"]["access_token"] == SEITEN_TOKEN)
        pruefe("Nicht mit dem Nutzer-Token",
               beitrag["data"]["access_token"] != NUTZER_TOKEN)
        pruefe("Bild kommt als oeffentliche Adresse",
               beitrag["data"]["url"] == f"{ADRESSE}/medien/erzeugt/abc.png")
        pruefe("Der Titel steht mit im Text",
               "Digitale Gästemappe" in beitrag["data"]["caption"])
        pruefe("Der Ziel-Link steht im Text, es gibt kein Feld dafuer",
               "https://welcometap.de" in beitrag["data"]["caption"])
        pruefe("Zurueck kommt die Beitrags-Kennung, nicht die des Fotos",
               antwort.plattform_id == f"{SEITE}_555")

        netz.stelle("/photos", Antwort(daten={"id": "nur-foto"}))
        antwort = facebook.veroeffentlichen(
            NUTZER_TOKEN, titel="", beschreibung="b",
            ziel_url="https://x.de", datei="a.png", ablage_id=SEITE,
        )
        pruefe("Ohne post_id wird die Foto-Kennung genommen",
               antwort.plattform_id == "nur-foto")

        wirft("Ohne Seite gar kein Aufruf",
              lambda: facebook.veroeffentlichen(
                  NUTZER_TOKEN, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei="a.png", ablage_id=None),
              enthaelt="Seite")
        wirft("Ohne Bild gar kein Aufruf",
              lambda: facebook.veroeffentlichen(
                  NUTZER_TOKEN, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei=None, ablage_id=SEITE),
              enthaelt="Bild")
        wirft("Eine fremde Seite wird abgelehnt",
              lambda: facebook.veroeffentlichen(
                  NUTZER_TOKEN, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei="a.png", ablage_id="fremd"),
              enthaelt="gehört nicht zu diesem Konto")

        netz.stelle("/me/accounts", Antwort(daten={
            "data": [{"id": SEITE, "name": "Ohne Token"}]
        }))
        wirft("Eine Seite ohne Seiten-Token wird erklaert",
              lambda: facebook.veroeffentlichen(
                  NUTZER_TOKEN, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei="a.png", ablage_id=SEITE),
              enthaelt="pages_show_list")

        netz.stelle("/me/accounts", SEITEN_ANTWORT)
        netz.stelle("/photos", Antwort(status=403, daten={
            "error": {"message": "(#200) Permissions error", "code": 200}
        }))
        wirft("Ein abgelehnter Beitrag nennt den Grund",
              lambda: facebook.veroeffentlichen(
                  NUTZER_TOKEN, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei="a.png", ablage_id=SEITE),
              enthaelt="Permissions error")

        # --- Facebook: ein Video --------------------------------------
        #
        # Facebook holt die Datei ueber `file_url` selbst ab, genau wie ein
        # Foto. Der dreistufige Upload in Stuecken waere erst ueber 1 GB
        # noetig. Zwei Dinge muessen dabei sitzen: der Beitrag geht an
        # /videos und nicht an /photos, und der **Titel hat ein eigenes
        # Feld** -- ein Video ist darin anders als ein Foto.

        netz.antworten.clear()
        netz.aufrufe.clear()
        netz.stelle("/me/accounts", SEITEN_ANTWORT)
        netz.stelle("/videos", Antwort(daten={"id": "vid-1"}))
        netz.stelle("/vid-1", Antwort(daten={
            "status": {"video_status": "ready"}, "post_id": f"{SEITE}_777",
        }))

        antwort = facebook.veroeffentlichen(
            NUTZER_TOKEN,
            titel="Gästemappe erklärt",
            beschreibung="In 30 Sekunden.",
            ziel_url="https://welcometap.de",
            datei="hochgeladen/clip.mp4",
            ablage_id=SEITE,
            typ="video",
        )
        beitrag = _letzter(netz, "/videos")

        pruefe("Ein Video geht an /videos, nicht an /photos",
               beitrag["url"].endswith(f"/{SEITE}/videos"))
        pruefe("Facebook holt die Datei selbst ab",
               beitrag["data"]["file_url"]
               == f"{ADRESSE}/medien/hochgeladen/clip.mp4")
        pruefe("Auch das Video geht mit dem Seiten-Token raus",
               beitrag["data"]["access_token"] == SEITEN_TOKEN)
        # Der Unterschied zum Foto.
        pruefe("Der Titel hat beim Video ein eigenes Feld",
               beitrag["data"].get("title") == "Gästemappe erklärt")
        pruefe("Und steht deshalb NICHT im Text",
               "Gästemappe erklärt" not in beitrag["data"]["description"])
        pruefe("Der Ziel-Link steht im Text",
               "https://welcometap.de" in beitrag["data"]["description"])
        pruefe("Der Status wird abgefragt, bevor der Beitrag als raus gilt",
               any(a["url"].endswith("/vid-1") for a in netz.aufrufe))
        # Fuer die Zahlen ist der Beitrag die richtige Kennung, nicht das
        # Video.
        pruefe("Zurueck kommt die Beitrags-Kennung, nicht die des Videos",
               antwort.plattform_id == f"{SEITE}_777")

        netz.stelle("/vid-1", Antwort(daten={
            "status": {"video_status": "error",
                       "processing_phase": {"errors": "Format nicht lesbar"}},
        }))
        wirft("Ein Video, das Facebook nicht verarbeiten kann, gilt nicht als raus",
              lambda: facebook.veroeffentlichen(
                  NUTZER_TOKEN, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei="a.mp4", ablage_id=SEITE,
                  typ="video"),
              enthaelt="Format nicht lesbar")

        netz.stelle("/vid-1", Antwort(daten={"status": {"video_status": "ready"}}))
        antwort = facebook.veroeffentlichen(
            NUTZER_TOKEN, titel="", beschreibung="b",
            ziel_url="https://x.de", datei="a.mp4", ablage_id=SEITE, typ="video",
        )
        pruefe("Ohne post_id bleibt die Video-Kennung stehen",
               antwort.plattform_id == "vid-1")
        pruefe("Ohne Titel geht kein leeres Titelfeld mit",
               "title" not in _letzter(netz, "/videos")["data"])

        netz.stelle("/videos", Antwort(daten={}))
        wirft("Ein Video ohne Kennung wird abgelehnt",
              lambda: facebook.veroeffentlichen(
                  NUTZER_TOKEN, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei="a.mp4", ablage_id=SEITE,
                  typ="video"),
              enthaelt="keine Kennung")

        # Ohne `typ` bleibt es beim Foto -- sonst waere jeder bestehende
        # Aufruf plötzlich ein Video.
        netz.stelle("/photos", Antwort(daten={"post_id": f"{SEITE}_1"}))
        facebook.veroeffentlichen(
            NUTZER_TOKEN, titel="t", beschreibung="b",
            ziel_url="https://x.de", datei="a.png", ablage_id=SEITE,
        )
        pruefe("Ohne Typ-Angabe geht es weiter an /photos",
               _letzter(netz, "/photos")["url"].endswith("/photos"))

        # --- Instagram posten -----------------------------------------

        netz.antworten.clear()
        netz.aufrufe.clear()
        netz.stelle("/me/accounts", SEITEN_ANTWORT)
        netz.stelle("/media_publish", Antwort(daten={"id": "ig-post-1"}))
        netz.stelle("/media", Antwort(daten={"id": "container-1"}))
        netz.stelle("/container-1", Antwort(daten={"status_code": "FINISHED"}))

        antwort = instagram.veroeffentlichen(
            NUTZER_TOKEN,
            titel="Gästemappe",
            beschreibung="Kurz erklärt.",
            ziel_url="https://welcometap.de",
            datei="erzeugt/abc.png",
            ablage_id=IG_KONTO,
        )
        container = _letzter(netz, "/media")
        veroeffentlichen = _letzter(netz, "/media_publish")

        pruefe("Instagram legt erst einen Container an",
               container["data"]["image_url"]
               == f"{ADRESSE}/medien/erzeugt/abc.png")
        pruefe("Auch Instagram postet mit dem Seiten-Token",
               container["data"]["access_token"] == SEITEN_TOKEN)
        pruefe("Der Ziel-Link steht in der Bildunterschrift",
               "https://welcometap.de" in container["data"]["caption"])
        pruefe("Veroeffentlicht wird mit der Container-Kennung",
               veroeffentlichen["data"]["creation_id"] == "container-1")
        pruefe("Der Status wird vorher abgefragt",
               any(a["url"].endswith("/container-1") for a in netz.aufrufe))
        pruefe("Zurueck kommt die Beitrags-Kennung",
               antwort.plattform_id == "ig-post-1")
        pruefe("Und das Konto", antwort.ablage_id == IG_KONTO)

        netz.stelle("/container-1", Antwort(daten={
            "status_code": "ERROR", "status": "Bild zu klein",
        }))
        wirft("Ein kaputter Container wird nicht veroeffentlicht",
              lambda: instagram.veroeffentlichen(
                  NUTZER_TOKEN, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei="a.png", ablage_id=IG_KONTO),
              enthaelt="Bild zu klein")

        vorher = len([a for a in netz.aufrufe if a["url"].endswith("/media_publish")])
        try:
            instagram.veroeffentlichen(
                NUTZER_TOKEN, titel="t", beschreibung="b",
                ziel_url="https://x.de", datei="a.png", ablage_id=IG_KONTO)
        except KanalFehler:
            pass
        pruefe("Nach einem Fehler geht nichts mehr raus",
               len([a for a in netz.aufrufe
                    if a["url"].endswith("/media_publish")]) == vorher)

        netz.stelle("/container-1", Antwort(daten={"id": "container-1"}))
        modul.CONTAINER_VERSUCHE = 2
        modul.CONTAINER_PAUSE = 0
        wirft("Ein Container, der nie fertig wird, laeuft in die Grenze",
              lambda: instagram.veroeffentlichen(
                  NUTZER_TOKEN, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei="a.png", ablage_id=IG_KONTO),
              enthaelt="nicht rechtzeitig")

        netz.stelle("/media", Antwort(daten={}))
        wirft("Ohne Container wird nicht veroeffentlicht",
              lambda: instagram.veroeffentlichen(
                  NUTZER_TOKEN, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei="a.png", ablage_id=IG_KONTO),
              enthaelt="keinen Container")

        wirft("Ein Konto ohne Seite wird erklaert",
              lambda: instagram.veroeffentlichen(
                  NUTZER_TOKEN, titel="t", beschreibung="b",
                  ziel_url="https://x.de", datei="a.png", ablage_id="fremd"),
              enthaelt="Professional-Konto")

        # --- Der Ziel-Link im Text ------------------------------------

        lang = modul._text_mit_link("Kurz.", "https://welcometap.de", 2200)
        pruefe("Der Link haengt hinten dran", lang.endswith("https://welcometap.de"))
        pruefe("Der Text bleibt davor stehen", lang.startswith("Kurz."))

        schon_drin = modul._text_mit_link(
            "Schau auf https://welcometap.de vorbei.", "https://welcometap.de", 2200
        )
        pruefe("Ein Link, der schon im Text steht, kommt nicht zweimal",
               schon_drin.count("https://welcometap.de") == 1)

        # Der teuerste Fall: lieber den Text kuerzen als den Link.
        eng = modul._text_mit_link("x" * 100, "https://welcometap.de", 40)
        pruefe("Bei Platzmangel wird der Text gekuerzt, nicht der Link",
               eng.endswith("https://welcometap.de") and len(eng) <= 40)

        wirft("Ein Link, der allein zu lang ist, wird gemeldet",
              lambda: modul._text_mit_link("x", "https://" + "y" * 100, 20),
              enthaelt="länger als die Plattform")

        ohne = modul._text_mit_link("Nur Text.", "", 100)
        pruefe("Ohne Ziel-Link bleibt der Text, wie er ist", ohne == "Nur Text.")

        # --- Zahlen ---------------------------------------------------

        netz.antworten.clear()
        netz.stelle("/insights", Antwort(daten={"data": [
            {"name": "post_impressions", "values": [{"value": 340}]},
            {"name": "post_clicks", "values": [{"value": 12}]},
        ]}))
        zahlen = facebook.zahlen(NUTZER_TOKEN, "1_2")
        pruefe("Facebook-Zahlen kommen an",
               (zahlen.impressions, zahlen.clicks) == (340, 12))
        pruefe("Facebook kennt kein Saves und laesst es bei Null",
               zahlen.saves == 0)

        netz.stelle("/insights", Antwort(daten={"data": [
            {"name": "views", "values": [{"value": 90}]},
            {"name": "saved", "values": [{"value": 7}]},
        ]}))
        zahlen = instagram.zahlen(NUTZER_TOKEN, "ig-1")
        pruefe("Instagram nimmt views als Aufrufe", zahlen.impressions == 90)
        pruefe("Und saved als Speicherungen", zahlen.saves == 7)
        pruefe("Instagram kennt keine Klicks und laesst es bei Null",
               zahlen.clicks == 0)

        netz.stelle("/insights", Antwort(daten={"data": [
            {"name": "impressions", "values": [{"value": 55}]},
        ]}))
        pruefe("Der alte Name impressions wird auch gelesen",
               instagram.zahlen(NUTZER_TOKEN, "ig-1").impressions == 55)

        netz.stelle("/insights", Antwort(daten={"data": [
            {"name": "reach", "values": [{"value": 31}]},
        ]}))
        pruefe("Und reach als letzter Rueckfall",
               instagram.zahlen(NUTZER_TOKEN, "ig-1").impressions == 31)

        netz.stelle("/insights", Antwort(daten={"data": []}))
        zahlen = instagram.zahlen(NUTZER_TOKEN, "ig-1")
        pruefe("Fehlende Kennzahlen sind Null, kein Absturz",
               (zahlen.impressions, zahlen.clicks, zahlen.saves) == (0, 0, 0))

        netz.stelle("/insights", Antwort(daten={"data": [
            {"name": "views", "values": [{"value": "viele"}]},
            {"name": "saved"},
        ]}))
        zahlen = instagram.zahlen(NUTZER_TOKEN, "ig-1")
        pruefe("Unlesbare Kennzahlen werden zu Null",
               (zahlen.impressions, zahlen.saves) == (0, 0))

        netz.stelle("/insights", Antwort(daten={"data": [
            {"name": "views", "values": [{"value": 1}, {"value": 9}]},
        ]}))
        pruefe("Von mehreren Werten gilt der letzte",
               instagram.zahlen(NUTZER_TOKEN, "ig-1").impressions == 9)

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
