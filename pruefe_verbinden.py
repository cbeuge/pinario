"""Prueft den Verbinden-Weg gegen die echte Anwendung.

    venv\\Scripts\\python.exe pruefe_verbinden.py

**Dieses Skript darf nur gegen eine Datenbank laufen, in der niemand
arbeitet.** Es legt Kampagnen an, verbindet und trennt Konten, laedt Dateien
hoch und raeumt hinterher auf. Am 05.09.2026 ist es auf dem Server gelaufen
und hat dabei vier echte Kampagnen mitgenommen, unwiederbringlich, weil
pinario keine Sicherung hat. Seitdem bricht `_nur_lokal` vorher ab: bei
gesetztem PRODUKTION in der Umgebung und wenn fremde Kampagnen dastehen.

Anders als die uebrigen Pruefskripte **braucht dieses die lokale
Datenbank**: gemessen wird genau das, was zwischen Browser, Sitzung und
Tabelle passiert, und das laesst sich nicht trocken nachbauen. Angefasst
wird dabei nichts Bleibendes: die Pinterest-Zugangsdaten werden vorher
gesichert und am Ende wieder hergestellt, angelegte Konten verschwinden.

**Nichts davon wird vorausgesetzt.** Weder dass lokal Zugangsdaten stehen
noch dass keine stehen — das Skript sichert, was da ist, und schreibt genau
das zurueck. Ein Pruefskript, das einen gepflegten Wert einfach entfernt,
ist teurer als der Fehler, den es finden soll.

Angemeldet wird ueber die Sitzung und nicht ueber das Formular. Nicht aus
Bequemlichkeit: die Anmeldung nimmt den ersten Nutzer der Tabelle, ein
zweiter mit eigenem Passwort kaeme also gar nicht durch — und das Passwort
des echten Nutzers hat in einem Pruefskript nichts zu suchen.

Dafuer wird Flask-Logins Sitzungsschutz hier abgeschaltet. Er vergleicht bei
jeder Anfrage einen Abdruck aus IP und Browserkennung mit dem, der beim
Anmelden entstand; eine von aussen gesetzte Sitzung bringt diesen Abdruck
nicht mit und wird deshalb nach der ersten Anfrage stillschweigend geleert.
**Im Betrieb bleibt der Schutz an** — abgeschaltet ist er nur in dieser
Datei.

Und noch eine Falle, die dasselbe Symptom macht: **Flask-Login merkt sich
den angemeldeten Nutzer in `g`**, und alle Anfragen innerhalb eines
`app_context` teilen sich dieses `g`. Eine einzige Anfrage ohne Anmeldung
legt dort den anonymen Nutzer ab, und ab da gilt jede weitere Anfrage als
abgemeldet — die Anwendung ist dabei voellig in Ordnung. Deshalb geht hier
jeder Aufruf durch `Browser`, der den Eintrag vorher wegraeumt.

Warum es dieses Skript gibt: der `zustand` ist die einzige Stelle, an der
diese Anwendung eine fremde Eingabe gegen etwas Eigenes prueft. Faellt die
Pruefung aus, kann jemand einem angemeldeten Nutzer einen Rueckruf mit
*seinem* Code unterschieben, und von da an gingen alle Pins auf ein fremdes
Board. Das ist kein Fehler, den man im Betrieb bemerkt.

Der Adapter wird untergeschoben. Was er selbst tut, steht in
`pruefe_pinterest.py`.
"""

import re
import sys
from datetime import timedelta

from flask import g
from sqlalchemy import delete, func, select

from app import create_app
from app.config import Config
from app.extensions import db
from app.kanaele import BEKANNT, KanalFehler, anmelde_urspruenge
from app.kanaele.basis import Kanal
from app.models import Account, Campaign, CampaignChannel, Channel, ContentItem, User
from app.zeit import jetzt, nach_berlin

ADRESSE = "https://pinario.example"


class TestConfig(Config):
    PRODUKTION = False
    OEFFENTLICHE_ADRESSE = ADRESSE
    WTF_CSRF_ENABLED = False


class Adapter(Kanal):
    """Steht anstelle des echten Pinterest-Adapters.

    **Erbt von `Kanal` und baut die Eigenschaften nicht nach.** Vorher stand
    hier eine Handvoll Klassenattribute, und bei jeder neuen Eigenschaft am
    Kanal fehlte eine davon -- der Fehler sah dann aus wie ein Fehler in der
    Anwendung. Was hier ueberschrieben wird, sind nur die Methoden, die ins
    Netz gehen wuerden.
    """

    def __init__(self):
        super().__init__(
            key="pinterest",
            name="Pinterest",
            unterstuetzt_ablagen=True,
            ablage_bezeichnung="Board",
            ablage_mehrzahl="Boards",
            # Muss dastehen wie beim echten Adapter: daraus baut sich die
            # form-action der CSP, siehe unten.
            anmelde_ursprung="https://www.pinterest.com",
            # Nur Bild, wie der echte. Ohne das nimmt der Upload alles an
            # und die Pruefung "ein Video wird abgelehnt" misst nichts.
            typen=("image",),
            max_beschreibung=800,
        )
        self.zustaende = []
        self.codes = []
        self.wirft = None
        # Was `fehlende_rechte` melden soll, und ob die Abfrage selbst
        # scheitert. Beides wird von aussen gesetzt.
        self.fehlt = []
        self.rechte_wirft = None
        self.antwort = {
            "zugang": "zugang-1",
            "erneuerung": "erneuern-1",
            "laeuft_ab": jetzt() + timedelta(days=30),
            "kontoname": "pinario",
        }

    def anmelde_adresse(self, zustand):
        # Wie der echte Adapter: ohne App-ID gibt es keine Anmeldung. Ohne
        # diese Zeile misst die Pruefung "kein Verbinden ohne Zugangsdaten"
        # nur den Testaufbau.
        from app.einstellungen import kanal_wert

        if not kanal_wert("pinterest", "app_id"):
            raise KanalFehler("Für Pinterest ist keine App-ID hinterlegt.")
        self.zustaende.append(zustand)
        return f"https://www.pinterest.com/oauth/?state={zustand}"

    def zugang_holen(self, code):
        self.codes.append(code)
        if self.wirft:
            raise self.wirft
        return dict(self.antwort)

    def fehlende_rechte(self, zugang):
        if self.rechte_wirft:
            raise self.rechte_wirft
        return list(self.fehlt)

    def ablagen(self, zugang):
        from app.kanaele.basis import Ablage

        return [Ablage(id="7", name="Ferienwohnung")]


ergebnisse = []


def pruefe(name, bedingung):
    ergebnisse.append((name, bool(bedingung)))


class Browser:
    """Testclient, der den zwischengespeicherten Nutzer vorher wegraeumt.

    Siehe den Kopf dieser Datei: ohne das faerbt eine Anfrage ohne Anmeldung
    auf alle folgenden ab.
    """

    def __init__(self, client):
        self._client = client

    def _frisch(self):
        g.pop("_login_user", None)

    def get(self, *args, **kwargs):
        self._frisch()
        return self._client.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        self._frisch()
        return self._client.post(*args, **kwargs)

    def session_transaction(self):
        return self._client.session_transaction()


def _token(client) -> str:
    """Holt den CSRF-Token aus einer Seite, so wie ein Browser das tut.

    Bewusst nicht aus der Sitzung: Flask-Login vergleicht bei jeder Anfrage
    einen Abdruck aus IP und Browserkennung, und wer die Sitzung von außen
    öffnet, schreibt dabei einen anderen hinein. Die Folge wäre eine
    Anmeldung, die mitten im Skript still verlorengeht — und dann misst man
    stundenlang, warum ein Knopf angeblich nichts tut.
    """
    seite = client.get("/einstellungen").data.decode()
    treffer = re.search(r'name="csrf_token" value="([^"]+)"', seite)
    if not treffer:
        raise AssertionError("Kein CSRF-Token auf der Seite. Nicht angemeldet?")
    return treffer.group(1)


def _anmelden(app, client, nutzer):
    """Meldet über die Sitzung an, siehe den Kopf dieser Datei."""
    app.login_manager.session_protection = None
    with client.session_transaction() as sitzung:
        sitzung["_user_id"] = nutzer.get_id()
        sitzung["_fresh"] = True


def main() -> int:  # noqa: C901
    app = create_app(TestConfig)
    adapter = Adapter()
    echt = BEKANNT["pinterest"]
    BEKANNT["pinterest"] = adapter

    with app.app_context():
        _nur_lokal()

        kanal_zeile = db.session.scalar(
            select(Channel).where(Channel.key == "pinterest")
        )
        if kanal_zeile is None:
            print("Kanal 'pinterest' fehlt in der Datenbank. "
                  "Erst `flask kanaele-abgleichen` laufen lassen.")
            return 1

        nutzer = db.session.scalars(select(User).order_by(User.id)).first()
        if nutzer is None:
            print("Kein Nutzer in der Datenbank. "
                  "Erst `flask passwort` laufen lassen.")
            return 1

        # Ein bestehendes Konto wuerde die Messung verfaelschen. Lokal gibt
        # es keins — aber das anzunehmen ist genau der Fehler, der sonst
        # still durchgeht.
        vorher = db.session.scalars(
            select(Account).where(Account.channel_id == kanal_zeile.id)
        ).all()
        if vorher:
            print(f"Für Pinterest ist lokal ein Konto verbunden "
                  f"({len(vorher)}). Erst trennen, dann noch einmal.")
            return 1

        # Was an Zugangsdaten dasteht, kommt am Ende genau so zurueck.
        from app import einstellungen
        from app.kanaele import ZUGANGSFELDER

        vorherige_daten = {
            feld.name: einstellungen.hole(
                einstellungen.kanal_name("pinterest", feld.name)
            )
            for feld in ZUGANGSFELDER["pinterest"]
        }

        try:
            _messen(app, adapter, kanal_zeile, nutzer)
        finally:
            # **Hier und nicht am Ende von `_messen`.** Bricht die Messung
            # mittendrin ab -- bei einem Gegentest zum Beispiel --, bleiben
            # sonst Kampagnen, Varianten und Dateien liegen. Genau das ist
            # am 04.09.2026 passiert: fuenf Wegwerf-Kampagnen und zehn
            # verwaiste Bilder, die niemand mehr zuordnen konnte.
            _aufraeumen(app, kanal_zeile)
            einstellungen.kanal_entferne("pinterest")
            for name, wert in vorherige_daten.items():
                if wert:
                    einstellungen.setze(
                        einstellungen.kanal_name("pinterest", name), wert
                    )
            db.session.commit()
            BEKANNT["pinterest"] = echt

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


def _nur_lokal() -> None:
    """Bricht ab, wenn das hier gegen eine Produktivdatenbank liefe.

    **Am 05.09.2026 ist genau das passiert.** Dieses Skript legt Kampagnen
    an, verbindet und trennt Konten, laedt Dateien hoch und raeumt hinterher
    auf. Auf dem Server ausgefuehrt hat es Carstens vier Kampagnen
    mitgenommen -- unwiederbringlich, weil pinario keine Sicherung hat.

    Zwei Gurte, weil einer nicht reicht:

    **1. `PRODUKTION` aus der Umgebung.** Nicht aus der Konfiguration: die
    `TestConfig` dieses Skripts setzt sie auf False, und damit waere die
    Pruefung genau dort blind, wo sie greifen muss. Der Wert kommt aus der
    `.env` und steht auf dem Server auf 1.

    **2. Fremde Kampagnen in der Datenbank.** Alles, was dieses Skript
    anlegt, heisst "Prüfung ...". Steht etwas anderes darin, ist es eine
    Datenbank, in der jemand arbeitet, und dann wird hier nichts angefasst.
    Das schuetzt auch lokal, wo `PRODUKTION` leer ist.
    """
    import os

    from app.models import Campaign

    if os.environ.get("PRODUKTION", "").strip().lower() in {
        "1", "true", "ja", "yes", "on"
    }:
        raise SystemExit(
            "Abbruch: PRODUKTION ist gesetzt. Dieses Skript legt Daten an "
            "und loescht sie wieder; gegen eine Produktivdatenbank darf es "
            "nie laufen. Es gehoert auf den Entwicklungsrechner."
        )

    fremde = [
        k.name
        for k in db.session.scalars(select(Campaign))
        if not k.name.startswith("Prüfung ")
    ]
    if fremde:
        raise SystemExit(
            "Abbruch: in dieser Datenbank stehen Kampagnen, die nicht von "
            "diesem Skript sind: " + ", ".join(fremde[:5]) + ". "
            "Das Skript legt Daten an und loescht sie wieder; es laeuft nur "
            "gegen eine Datenbank, in der niemand arbeitet."
        )


def _aufraeumen(app, kanal_zeile) -> None:
    """Raeumt weg, was die Messung angelegt hat -- auch nach einem Abbruch.

    Erkannt wird es am Namen: alle Wegwerf-Kampagnen dieses Skripts heissen
    "Prüfung ...". Eine echte Kampagne heisst nie so, und der Filter ist
    deutlich sicherer als eine Liste von Kennungen, die bei einem Abbruch
    mitten im Lauf unvollstaendig waere.
    """
    import os

    wurzel = app.config["UPLOAD_ORDNER"]
    db.session.rollback()

    for kampagne in db.session.scalars(
        select(Campaign).where(Campaign.name.like("Prüfung %"))
    ):
        for verbindung in list(kampagne.kanaele):
            for eintrag in db.session.scalars(
                select(ContentItem).where(
                    ContentItem.campaign_channel_id == verbindung.id
                )
            ):
                if eintrag.file_path:
                    try:
                        os.remove(
                            os.path.join(wurzel, *eintrag.file_path.split("/"))
                        )
                    except OSError:
                        pass
                db.session.delete(eintrag)
            db.session.delete(verbindung)
        db.session.delete(kampagne)

    for konto in db.session.scalars(
        select(Account).where(Account.channel_id == kanal_zeile.id)
    ):
        db.session.delete(konto)
    db.session.commit()


def _kasten(seite: str, kanal_key: str) -> str:
    """Nur der Abschnitt der Seite, der zu diesem Kanal gehört.

    Die Einstellungen-Seite zeigt **alle** Kanäle. Wer auf der ganzen Seite
    nach "Konto verbinden" sucht, misst mit, ob ein anderer Kanal
    Zugangsdaten hat — lokal steht dort nichts und die Prüfung besteht, auf
    dem Server steht dort etwas und sie schlägt fehl. Genau so passiert am
    04.09.2026.
    """
    marke = f'/kanaele/{kanal_key}/'
    teile = seite.split('<section class="kanalkasten')
    for teil in teile:
        if marke in teil:
            return teil
    return ""


def _ohne_konto(seite: str) -> str:
    """Die Kanaele, die die Zeitplan-Seite als unverbunden meldet."""
    treffer = re.search(r"Kein Konto verbunden: ([^.]*)\.", seite)
    return treffer.group(1) if treffer else ""


def _konto(kanal_id):
    return db.session.scalars(
        select(Account).where(Account.channel_id == kanal_id).order_by(Account.id)
    ).first()


def _messen(app, adapter, kanal_zeile, nutzer):  # noqa: C901
    from app import einstellungen

    # --- Ohne Anmeldung geht nichts -----------------------------------

    # Bewusst ohne `with`: ein Testclient als Kontextmanager laesst den
    # Anfrage-Kontext stehen, bis der Block endet, und die naechste Anmeldung
    # landet dann im falschen. Das Ergebnis ist ein Skript, das eine
    # funktionierende Anwendung als kaputt meldet.
    gast = Browser(app.test_client())
    for pfad in (
        "/kanaele/pinterest/rueckruf?code=x&state=y",
        "/kanaele/pinterest/ablagen",
    ):
        antwort = gast.get(pfad)
        # Die Anmeldung liegt auf "/", die Startseite ist zugleich das
        # Passwortfeld.
        pruefe(f"Ohne Anmeldung kein Zugriff auf {pfad.split('?')[0]}",
               antwort.status_code in (301, 302)
               and antwort.headers.get("Location", "").startswith("/?next="))

    client = Browser(app.test_client())
    _anmelden(app, client, nutzer)
    pruefe("Angemeldet", b"Einstellungen" in client.get("/einstellungen").data)

    # --- Ohne Zugangsdaten kein Knopf ---------------------------------

    einstellungen.kanal_entferne("pinterest")
    kasten = _kasten(client.get("/einstellungen").data.decode(), "pinterest")
    pruefe("Ohne Zugangsdaten steht 'Zugangsdaten fehlen'",
           "Zugangsdaten fehlen" in kasten)
    pruefe("Ohne Zugangsdaten kein Verbinden-Knopf",
           "Konto verbinden" not in kasten)

    antwort = client.post(
        "/kanaele/pinterest/verbinden", data={"csrf_token": _token(client)}
    )
    pruefe("Verbinden ohne Zugangsdaten fuehrt zurueck, nicht zu Pinterest",
           antwort.status_code in (301, 302)
           and "pinterest.com" not in antwort.headers.get("Location", ""))

    # --- Mit Zugangsdaten ---------------------------------------------

    einstellungen.setze(einstellungen.kanal_name("pinterest", "app_id"), "app-1")
    einstellungen.setze(
        einstellungen.kanal_name("pinterest", "app_secret"), "geheim"
    )
    seite = client.get("/einstellungen").data.decode()
    kasten = _kasten(seite, "pinterest")
    pruefe("Mit Zugangsdaten steht 'nicht verbunden'", "nicht verbunden" in kasten)
    pruefe("Mit Zugangsdaten steht der Verbinden-Knopf da",
           "Konto verbinden" in kasten)
    pruefe("Die Rueckruf-Adresse steht zum Abschreiben da",
           f"{ADRESSE}/kanaele/pinterest/rueckruf" in kasten)
    pruefe("Das Secret steht nicht im Klartext auf der Seite",
           "geheim" not in seite)

    # --- CSRF ----------------------------------------------------------

    antwort = client.post("/kanaele/pinterest/verbinden", data={})
    pruefe("Verbinden ohne CSRF-Token wird abgewiesen", antwort.status_code == 400)

    # --- Die CSP muss die Weiterleitung durchlassen -------------------
    #
    # Am 04.09.2026 der teuerste Fehler des Tages: `form-action 'self'`
    # verbietet nicht nur, ein Formular woandershin zu schicken, sondern
    # auch die **Weiterleitung**, die auf einen Formular-POST folgt. Der
    # Browser verwirft sie stillschweigend -- keine Meldung auf der Seite,
    # keine Zeile im Server-Log, der Knopf tut einfach nichts. Nachgestellt
    # mit zwei Seiten, die sich nur in der CSP unterscheiden: mit der alten
    # blieb die Seite stehen, mit der neuen kam die Weiterleitung an.
    antwort = client.get("/einstellungen")
    csp = antwort.headers.get("Content-Security-Policy", "")
    regel = ""
    for teil in csp.split(";"):
        if teil.strip().startswith("form-action"):
            regel = teil.strip()

    pruefe("Die CSP hat eine form-action-Regel", bool(regel))
    pruefe("Eigene Formulare gehen weiter", "'self'" in regel)
    for ursprung in anmelde_urspruenge():
        pruefe(f"Weiterleitung zu {ursprung} ist erlaubt", ursprung in regel)
    pruefe("Und nicht einfach alles",
           "*" not in regel and "https:" not in regel.replace("https://", ""))

    # --- Hinweg --------------------------------------------------------

    antwort = client.post(
        "/kanaele/pinterest/verbinden", data={"csrf_token": _token(client)}
    )
    ziel = antwort.headers.get("Location", "")
    pruefe("Verbinden leitet zu Pinterest", "pinterest.com/oauth" in ziel)
    pruefe("Der Adapter hat einen Zustand bekommen", bool(adapter.zustaende))
    zustand = adapter.zustaende[-1]
    pruefe("Der Zustand ist lang genug zum Raten", len(zustand) >= 32)

    with client.session_transaction() as sitzung:
        pruefe("Der Zustand liegt in der Sitzung",
               sitzung.get("verbinden_zustand") == zustand)
        pruefe("Der Kanal liegt daneben",
               sitzung.get("verbinden_kanal") == "pinterest")

    # --- Rueckweg: die Faelle, die schiefgehen muessen -----------------

    antwort = client.get(f"/kanaele/pinterest/rueckruf?code=c&state={zustand}x")
    pruefe("Falscher Zustand wird abgewiesen", _konto(kanal_zeile.id) is None)
    pruefe("Falscher Zustand fuehrt zurueck zu den Einstellungen",
           "einstellungen" in antwort.headers.get("Location", ""))

    # Nach einem Fehlversuch ist der Zustand verbraucht. Das ist Absicht:
    # ein Wert, der nach dem ersten Versuch noch gilt, laesst sich beliebig
    # oft ausprobieren.
    antwort = client.get(f"/kanaele/pinterest/rueckruf?code=c&state={zustand}")
    pruefe("Der Zustand gilt nur einmal", _konto(kanal_zeile.id) is None)

    client.post("/kanaele/pinterest/verbinden", data={"csrf_token": _token(client)})
    zustand = adapter.zustaende[-1]
    client.get(f"/kanaele/pinterest/rueckruf?state={zustand}")
    pruefe("Rueckruf ohne Code legt nichts an", _konto(kanal_zeile.id) is None)

    client.post("/kanaele/pinterest/verbinden", data={"csrf_token": _token(client)})
    zustand = adapter.zustaende[-1]
    client.get(
        f"/kanaele/pinterest/rueckruf?error=access_denied&state={zustand}"
    )
    pruefe("Abbruch bei Pinterest legt nichts an", _konto(kanal_zeile.id) is None)

    client.post("/kanaele/pinterest/verbinden", data={"csrf_token": _token(client)})
    zustand = adapter.zustaende[-1]
    adapter.wirft = KanalFehler("Pinterest: Authentication failed.")
    antwort = client.get(
        f"/kanaele/pinterest/rueckruf?code=c&state={zustand}",
        follow_redirects=True,
    )
    pruefe("Ein abgelehnter Tausch legt nichts an", _konto(kanal_zeile.id) is None)
    pruefe("Der Grund steht auf der Seite",
           b"Authentication failed" in antwort.data)
    adapter.wirft = None

    # --- Rueckweg: der Fall, der klappen muss -------------------------

    client.post("/kanaele/pinterest/verbinden", data={"csrf_token": _token(client)})
    zustand = adapter.zustaende[-1]
    antwort = client.get(
        f"/kanaele/pinterest/rueckruf?code=code-echt&state={zustand}",
        follow_redirects=True,
    )
    konto = _konto(kanal_zeile.id)
    pruefe("Das Konto steht in der Datenbank", konto is not None)
    pruefe("Der Code ist beim Adapter angekommen",
           adapter.codes[-1] == "code-echt")
    pruefe("Der Kontoname steht dran", konto and konto.account_name == "pinario")
    pruefe("Der Zugang laesst sich wieder lesen",
           konto and konto.zugang == "zugang-1")
    pruefe("Die Erneuerung laesst sich wieder lesen",
           konto and konto.erneuerung == "erneuern-1")
    pruefe("Der Zugang steht verschluesselt in der Spalte",
           konto and "zugang-1" not in konto.access_token)
    pruefe("Der Ablauf steht dran", konto and konto.expires_at is not None)
    pruefe("Die Seite sagt, wer verbunden ist", b"pinario" in antwort.data)

    kasten = _kasten(client.get("/einstellungen").data.decode(), "pinterest")
    pruefe("Der Zustand steht jetzt auf 'verbunden'", "verbunden" in kasten)
    pruefe("Trennen steht da", "Trennen" in kasten)

    # --- Kein zweites Konto daneben -----------------------------------

    adapter.antwort = dict(adapter.antwort, zugang="zugang-2", kontoname="anders")
    client.post("/kanaele/pinterest/verbinden", data={"csrf_token": _token(client)})
    zustand = adapter.zustaende[-1]
    client.get(f"/kanaele/pinterest/rueckruf?code=c2&state={zustand}")

    konten = db.session.scalars(
        select(Account).where(Account.channel_id == kanal_zeile.id)
    ).all()
    pruefe("Neu verbinden legt kein zweites Konto an", len(konten) == 1)
    pruefe("Neu verbinden ueberschreibt den Zugang",
           konten and konten[0].zugang == "zugang-2")
    pruefe("Neu verbinden zieht den Kontonamen nach",
           konten and konten[0].account_name == "anders")

    # --- Fehlende Rechte fallen beim Verbinden auf ---------------------
    #
    # Am 05.09.2026 war Facebook verbunden, zeigte alle vier Seiten und
    # durfte auf keine posten. Gemerkt hat das erst der Zeitplan, Stunden
    # spaeter und als gescheiterter Beitrag. Ab hier faellt es sofort auf.

    adapter.fehlt = ["pages_manage_posts"]
    client.post("/kanaele/pinterest/verbinden", data={"csrf_token": _token(client)})
    zustand = adapter.zustaende[-1]
    antwort = client.get(
        f"/kanaele/pinterest/rueckruf?code=c3&state={zustand}",
        follow_redirects=True,
    )
    pruefe("Fehlende Rechte stehen gleich nach dem Verbinden da",
           b"pages_manage_posts" in antwort.data)
    pruefe("Und dazu, dass Nachtragen allein nicht reicht",
           "neu verbinden".encode() in antwort.data)
    pruefe("Das Konto wird trotzdem gespeichert",
           _konto(kanal_zeile.id) is not None)

    antwort = client.post(
        "/kanaele/pinterest/rechte",
        data={"csrf_token": _token(client)},
        follow_redirects=True,
    )
    pruefe("Der Knopf meldet dieselben fehlenden Rechte",
           b"pages_manage_posts" in antwort.data)

    adapter.fehlt = []
    antwort = client.post(
        "/kanaele/pinterest/rechte",
        data={"csrf_token": _token(client)},
        follow_redirects=True,
    )
    pruefe("Sind alle Rechte da, sagt der Knopf das auch",
           "alle Rechte erteilt".encode() in antwort.data)
    pruefe("Und meldet dann keine fehlenden",
           b"pages_manage_posts" not in antwort.data)

    # Scheitert die Abfrage, darf sie weder das Verbinden umwerfen noch
    # eine Warnung erfinden, die sie nicht belegen kann.
    adapter.rechte_wirft = KanalFehler("Rechte-Abfrage kaputt")
    client.post("/kanaele/pinterest/verbinden", data={"csrf_token": _token(client)})
    zustand = adapter.zustaende[-1]
    antwort = client.get(
        f"/kanaele/pinterest/rueckruf?code=c4&state={zustand}",
        follow_redirects=True,
    )
    # Der Statuscode muss mitgeprueft werden. Ohne ihn misst das hier
    # nichts: bei einem 500er steht das Konto genauso in der Datenbank
    # (gespeichert wird vorher) und die Warnung fehlt genauso -- beide
    # Bedingungen waeren also auch dann erfuellt, wenn der Rueckruf
    # abstuerzt. Genau das ist beim Gegentest herausgekommen.
    pruefe("Eine kaputte Rechte-Abfrage ergibt trotzdem eine Seite",
           antwort.status_code == 200)
    pruefe("Und landet auf den Einstellungen, nicht im Fehler",
           b"Zugangsdaten" in antwort.data)
    pruefe("Eine kaputte Rechte-Abfrage laesst das Verbinden stehen",
           _konto(kanal_zeile.id) is not None)
    pruefe("Das Verbinden gilt als geglueckt",
           b"verbunden" in antwort.data)
    pruefe("Und warnt nicht ins Blaue",
           "fehlen Rechte".encode() not in antwort.data)
    adapter.rechte_wirft = None

    # --- Boards --------------------------------------------------------

    antwort = client.get("/kanaele/pinterest/ablagen")
    pruefe("Boards werden gezeigt", b"Ferienwohnung" in antwort.data)
    pruefe("Die Kennung steht zum Abschreiben da", b">7<" in antwort.data)

    # --- Zeitplan sieht das Konto -------------------------------------
    #
    # Der Zeitplan meldet nur Kanaele, die eine Kampagne auch benutzt. Fuer
    # diesen Abschnitt braucht es also eine -- ohne sie misst man, dass die
    # Meldung schweigt, und haelt das faelschlich fuer den Erfolg.
    zeitplan_kampagne = Campaign(
        name="Prüfung Zeitplan", target_url="https://example.de", status="draft"
    )
    db.session.add(zeitplan_kampagne)
    db.session.commit()
    zeitplan_verbindung = CampaignChannel(
        campaign_id=zeitplan_kampagne.id, channel_id=kanal_zeile.id,
        content_source="ai_generated", settings={},
    )
    db.session.add(zeitplan_verbindung)
    db.session.commit()

    # Nicht auf den ganzen Satz pruefen: es sind mehrere Kanaele aktiv, und
    # ein Test, der das nicht trennt, misst die Zahl der Kanaele statt das
    # Verhalten.
    seite = client.get("/zeitplan").data.decode()
    pruefe("Zeitplan zaehlt Pinterest nicht mehr als unverbunden",
           "Pinterest" not in _ohne_konto(seite))

    konten[0].expires_at = jetzt() - timedelta(days=1)
    db.session.commit()
    seite = client.get("/zeitplan").data.decode()
    pruefe("Zeitplan zeigt einen abgelaufenen Zugang",
           "Zugang abgelaufen" in seite)

    # --- Trennen -------------------------------------------------------

    antwort = client.post(
        "/kanaele/pinterest/trennen",
        data={"csrf_token": _token(client)},
        follow_redirects=True,
    )
    pruefe("Trennen entfernt das Konto", _konto(kanal_zeile.id) is None)
    pruefe("Trennen sagt, dass Eingeplantes stehen bleibt",
           "bleiben stehen".encode() in antwort.data)

    seite = client.get("/zeitplan").data.decode()
    pruefe("Zeitplan meldet den Kanal wieder als nicht verbunden",
           "Pinterest" in _ohne_konto(seite))

    db.session.delete(zeitplan_verbindung)
    db.session.delete(zeitplan_kampagne)
    db.session.commit()

    # --- Die Ablagen an der Kampagne ----------------------------------
    #
    # Kennungen abzutippen war ein Zwischenschritt, solange kein Konto
    # verbunden war. Jetzt kommt die Liste vom Adapter und wird angehakt.
    # Der teure Fehler dabei waere `get` statt `getlist`: dann kaeme nur
    # das erste Haekchen an, und wer drei Seiten anhakt, bespielt eine.

    client.post("/kanaele/pinterest/verbinden", data={"csrf_token": _token(client)})
    client.get(f"/kanaele/pinterest/rueckruf?code=c&state={adapter.zustaende[-1]}")

    kampagne = Campaign(name="Prüfung Ablagen", target_url="https://example.de",
                        status="draft")
    db.session.add(kampagne)
    db.session.commit()

    seite = client.get(f"/kampagnen/{kampagne.id}").data.decode()
    pruefe("Die Ablagen des Kontos stehen zur Auswahl", "Ferienwohnung" in seite)
    pruefe("Als Ankreuzfeld, nicht als Textfeld",
           'name="board_ids" value="7"' in seite)
    pruefe("Und die Verarbeitung weiss davon",
           'name="ablagen_gewaehlt"' in seite)

    client.post(
        f"/kampagnen/{kampagne.id}/kanal/{kanal_zeile.id}",
        data={
            "csrf_token": _token(client),
            "content_source": "ai_generated",
            "posts_per_day": "3",
            "zeit_von": "09:00",
            "zeit_bis": "21:00",
            "ablagen_gewaehlt": "ja",
            "board_ids": ["7", "8"],
        },
    )
    verbindung = db.session.scalar(
        select(CampaignChannel).where(CampaignChannel.campaign_id == kampagne.id)
    )
    pruefe("Beide Haken kommen an, nicht nur der erste",
           verbindung is not None
           and (verbindung.settings or {}).get("board_ids") == ["7", "8"])

    seite = client.get(f"/kampagnen/{kampagne.id}").data.decode()
    pruefe("Ein Kanal mit Ziel steht auf 'läuft'", "läuft" in seite)

    client.post(
        f"/kampagnen/{kampagne.id}/kanal/{kanal_zeile.id}",
        data={
            "csrf_token": _token(client),
            "content_source": "ai_generated",
            "posts_per_day": "3",
            "zeit_von": "09:00",
            "zeit_bis": "21:00",
            "ablagen_gewaehlt": "ja",
        },
    )
    db.session.refresh(verbindung)
    pruefe("Ohne Haken bleibt die Auswahl leer",
           (verbindung.settings or {}).get("board_ids") == [])
    seite = client.get(f"/kampagnen/{kampagne.id}").data.decode()
    # Der Zustand, in dem man am ehesten glaubt, es liefe.
    pruefe("Ein Kanal ohne Ziel steht NICHT auf 'läuft'",
           "Board fehlt" in seite)

    db.session.delete(verbindung)
    db.session.delete(kampagne)
    db.session.commit()
    client.post("/kanaele/pinterest/trennen", data={"csrf_token": _token(client)})

    # --- Eine eigene Datei hochladen ----------------------------------
    #
    # Der Weg fuer Material, das nicht hier entsteht. Zwei Dinge muessen
    # sitzen: das Format wird am **Inhalt** erkannt und nicht am Namen, und
    # ein Kanal darf nichts angenommen bekommen, was er nicht posten kann --
    # sonst liegt die Datei da, die Variante sieht fertig aus, und der
    # Zeitplan ueberspringt sie stillschweigend.

    import io

    kampagne = Campaign(name="Prüfung Upload", target_url="https://example.de",
                        status="draft")
    db.session.add(kampagne)
    db.session.commit()
    verbindung = CampaignChannel(
        campaign_id=kampagne.id, channel_id=kanal_zeile.id,
        content_source="upload", settings={},
    )
    db.session.add(verbindung)
    db.session.commit()

    import os

    def _hochladen(name, inhalt, **felder):
        daten = {"csrf_token": _token(client),
                 "datei": (io.BytesIO(inhalt), name)}
        daten.update(felder)
        return client.post(
            f"/kanal/{verbindung.id}/varianten/hochladen",
            data=daten, content_type="multipart/form-data",
            follow_redirects=True,
        )

    def _anzahl():
        return db.session.scalar(
            select(func.count(ContentItem.id))
            .where(ContentItem.campaign_channel_id == verbindung.id)
        ) or 0

    # Die ersten Bytes eines JPG. Das Format wird am Inhalt erkannt.
    JPG = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"x" * 200

    vorher = _anzahl()
    antwort = _hochladen("foto.jpg", JPG, titel="Mein Bild")
    pruefe("Ein Bild wird angenommen", _anzahl() == vorher + 1)
    eintrag = db.session.scalars(
        select(ContentItem)
        .where(ContentItem.campaign_channel_id == verbindung.id)
        .order_by(ContentItem.id.desc())
    ).first()
    pruefe("Es steht als Bild drin", eintrag is not None and eintrag.type == "image")
    pruefe("Und als selbst hochgeladen, nicht als erzeugt",
           eintrag is not None and eintrag.quelle == "upload")
    pruefe("Der Titel kommt mit", eintrag is not None and eintrag.title == "Mein Bild")
    pruefe("Es liegt unter hochgeladen/",
           eintrag is not None and (eintrag.file_path or "").startswith("hochgeladen/"))
    pruefe("Der Dateiname verraet den Titel nicht",
           eintrag is not None and "Mein" not in (eintrag.file_path or ""))
    pruefe("Neu ist immer draft, nicht freigegeben",
           eintrag is not None and eintrag.status == "draft")

    # Der teure Fall: eine umbenannte Datei.
    vorher = _anzahl()
    antwort = antwort = _hochladen("sieht_aus_wie.jpg", b"PK" + bytes([3, 4]) + b"x" * 200)
    pruefe("Eine umbenannte Datei wird abgelehnt", _anzahl() == vorher)
    pruefe("Und die Meldung sagt warum",
           "weder ein Bild".encode() in antwort.data)

    vorher = _anzahl()
    _hochladen("leer.jpg", b"")
    pruefe("Eine leere Datei wird abgelehnt", _anzahl() == vorher)

    # Der zweite teure Fall: ein Kanal, der das gar nicht posten kann.
    vorher = _anzahl()
    antwort = _hochladen(
        "clip.mp4", bytes([0, 0, 0, 0x20]) + b"ftypisom" + b"x" * 200
    )
    pruefe("Ein Video wird abgelehnt, solange der Kanal keins postet",
           _anzahl() == vorher)
    pruefe("Und die Meldung nennt, was der Kanal annimmt",
           "Angenommen wird".encode() in antwort.data)

    # --- Der Ziel-Link im Formular ------------------------------------
    #
    # Am 05.09.2026 gemeldet: "chaosbeenden.de" wurde abgelehnt, obwohl die
    # Pruefung es ergaenzt. Der Grund lag im HTML: `type="url"` laesst der
    # **Browser** gar nicht erst abschicken, und die serverseitige Ergaenzung
    # kommt nie zum Zug. Geprueft wird deshalb beides -- die Funktion und das
    # Feld.

    seite = client.get("/kampagnen/neu").data.decode()
    pruefe("Das Ziel-Link-Feld ist kein url-Feld",
           'type="url"' not in seite)
    pruefe("Sondern ein Textfeld mit url-Tastatur",
           'inputmode="url"' in seite)

    antwort = client.post(
        "/kampagnen/neu",
        data={
            "csrf_token": _token(client),
            "name": "Prüfung Ziel-Link",
            "target_url": "chaosbeenden.de",
            "status": "draft",
        },
        follow_redirects=True,
    )
    ohne_schema = db.session.scalar(
        select(Campaign).where(Campaign.name == "Prüfung Ziel-Link")
    )
    pruefe("Eine Adresse ohne https wird angenommen", ohne_schema is not None)
    pruefe("Und mit https gespeichert",
           ohne_schema is not None
           and ohne_schema.target_url == "https://chaosbeenden.de")
    # Menschen sind aus, solange niemand sie anhakt.
    pruefe("Menschen im Bild sind standardmaessig aus",
           ohne_schema is not None and not ohne_schema.menschen_erlaubt)

    client.post(
        f"/kampagnen/{ohne_schema.id}/bearbeiten",
        data={
            "csrf_token": _token(client),
            "name": "Prüfung Ziel-Link",
            "target_url": "chaosbeenden.de",
            "status": "draft",
            "menschen": "ja",
        },
    )
    db.session.refresh(ohne_schema)
    pruefe("Menschen lassen sich an der Kampagne einschalten",
           ohne_schema.menschen_erlaubt)

    db.session.delete(ohne_schema)
    db.session.commit()

    # --- Textvorschlaege zur hochgeladenen Datei ----------------------
    #
    # Der Kern von Carstens Rueckmeldung am 04.09.2026: hochgeladen wurde,
    # aber der KI-Schritt fehlte -- und "Erzeugen" daneben ignorierte die
    # eigene Datei komplett. Jetzt entstehen mehrere Texte **zu derselben
    # Datei**, damit die Auswertung spaeter den Text misst und nicht das
    # Bild.

    import app.ki as ki_modul

    echte_texte = ki_modul.texte_erzeugen
    gesehen = {}

    def _texte(anfrage, *, anzahl, max_beschreibung, bild=None):
        gesehen["anfrage"] = anfrage
        gesehen["bild"] = bild
        return [
            ki_modul.Variante(titel=f"Titel {i}", beschreibung=f"Text {i}")
            for i in range(anzahl)
        ]

    ki_modul.texte_erzeugen = _texte
    try:
        vorher = _anzahl()
        antwort = _hochladen("mit_text.jpg", JPG, anzahl="3")
        neue = db.session.scalars(
            select(ContentItem)
            .where(ContentItem.campaign_channel_id == verbindung.id)
            .order_by(ContentItem.id.desc())
            .limit(3)
        ).all()

        pruefe("Drei Textvorschlaege entstehen", _anzahl() == vorher + 3)
        pruefe("Alle mit demselben Bild",
               len({e.file_path for e in neue}) == 1)
        pruefe("Und in derselben Gruppe",
               len({e.variant_group for e in neue}) == 1)
        pruefe("Die Texte unterscheiden sich",
               len({e.title for e in neue}) == 3)
        # Der eigentliche Fehler von vorher: die Datei wurde uebergangen.
        pruefe("Das Bild geht wirklich an das Modell", gesehen["bild"] == JPG)
        pruefe("Und die Anfrage sagt, dass es dasteht",
               "Oben steht das Bild" in gesehen["anfrage"])
        pruefe("Die Anfrage wird mitgespeichert",
               all(e.prompt for e in neue))

        vorher = _anzahl()
        gesehen.clear()
        _hochladen("ohne_text.jpg", JPG, anzahl="0")
        pruefe("Null Vorschlaege legen nur die Datei ab",
               _anzahl() == vorher + 1)
        pruefe("Und rufen das Modell gar nicht erst auf", not gesehen)

        # Scheitert der Text, darf die Datei nicht verloren gehen.
        def _wirft(anfrage, **_):
            raise ki_modul.KIFehler("Gemini hat nichts geliefert.")

        ki_modul.texte_erzeugen = _wirft
        vorher = _anzahl()
        antwort = _hochladen("trotzdem.jpg", JPG, anzahl="2")
        pruefe("Ein gescheiterter Text kostet die Datei nicht",
               _anzahl() == vorher + 1)
        pruefe("Und die Meldung sagt, was los ist",
               "Text ist gescheitert".encode() in antwort.data)
    finally:
        ki_modul.texte_erzeugen = echte_texte

    # --- Nach dem Einschalten geht es zu den Varianten ----------------
    #
    # Ein frisch eingeschalteter Kanal hat nichts zu posten; der naechste
    # Schritt ist immer derselbe.

    from app.models import ContentItem as CI

    zweite = Campaign(name="Prüfung Ablauf", target_url="https://example.de",
                      status="draft")
    db.session.add(zweite)
    db.session.commit()
    antwort = client.post(
        f"/kampagnen/{zweite.id}/kanal/{kanal_zeile.id}",
        data={
            "csrf_token": _token(client),
            "content_source": "ai_generated",
            "posts_per_day": "2",
            "zeit_von": "09:00",
            "zeit_bis": "21:00",
            "ablagen_gewaehlt": "ja",
            "board_ids": ["7"],
        },
    )
    pruefe("Einschalten fuehrt weiter zu den Varianten",
           "/varianten" in antwort.headers.get("Location", ""))

    neue_verbindung = db.session.scalar(
        select(CampaignChannel).where(CampaignChannel.campaign_id == zweite.id)
    )
    seite = client.get(f"/kanal/{neue_verbindung.id}/varianten").data.decode()
    # Vorher stand hier immer eine feste 3, egal was am Kanal eingestellt war.
    pruefe("Die Anzahl kommt aus den Kanal-Einstellungen",
           'name="anzahl" min="1" max="8"' in seite and 'value="2"' in seite)

    antwort = client.post(
        f"/kampagnen/{zweite.id}/kanal/{kanal_zeile.id}",
        data={
            "csrf_token": _token(client),
            "content_source": "ai_generated",
            "posts_per_day": "2",
            "zeit_von": "09:00",
            "zeit_bis": "21:00",
            "ablagen_gewaehlt": "ja",
            "board_ids": ["7"],
        },
    )
    pruefe("Beim blossen Aendern bleibt man auf der Kampagne",
           "/varianten" not in antwort.headers.get("Location", ""))

    # --- Ein geaenderter Takt vergibt die Termine neu -----------------
    #
    # Am 05.09.2026 gemeldet: das Zeitfenster verschoben, und der Beitrag
    # blieb auf der alten Uhrzeit stehen. `einplanen` fasst absichtlich nur
    # an, was noch keinen Termin hat -- fuer geaenderte Einstellungen hiess
    # das aber, dass sich nichts ruehrt.

    zweite.status = "active"
    db.session.commit()
    takt = CI(
        campaign_channel_id=neue_verbindung.id, variant_group="takt",
        type="image", quelle="upload", title="Mit Termin",
        description="x", file_path="hochgeladen/x.jpg", status="ready",
    )
    db.session.add(takt)
    db.session.commit()

    def _speichern(**abweichung):
        daten = {
            "csrf_token": _token(client),
            "content_source": "ai_generated",
            "posts_per_day": "2",
            "zeit_von": "09:00",
            "zeit_bis": "21:00",
            "ablagen_gewaehlt": "ja",
            "board_ids": ["7"],
        }
        daten.update(abweichung)
        return client.post(
            f"/kampagnen/{zweite.id}/kanal/{kanal_zeile.id}",
            data=daten, follow_redirects=True,
        )

    _speichern()
    db.session.refresh(takt)
    pruefe("Eine freigegebene Variante bekommt einen Termin",
           takt.geplant_fuer is not None)
    vorher = takt.geplant_fuer

    antwort = _speichern(zeit_von="15:30", zeit_bis="16:00")
    db.session.refresh(takt)
    pruefe("Ein geaendertes Zeitfenster verschiebt den Termin",
           takt.geplant_fuer is not None and takt.geplant_fuer != vorher)
    pruefe("Und die Meldung sagt es",
           "neu vergeben".encode() in antwort.data)

    vorher = takt.geplant_fuer
    antwort = _speichern(zeit_von="15:30", zeit_bis="16:00", board_ids=["7", "8"])
    db.session.refresh(takt)
    # Wer bloss eine Seite dazuwaehlt, soll seine Termine behalten.
    pruefe("Eine andere Seite laesst den Termin in Ruhe",
           takt.geplant_fuer == vorher)
    pruefe("Und meldet auch nichts",
           "neu vergeben".encode() not in antwort.data)

    db.session.delete(takt)
    db.session.commit()
    zweite.status = "draft"
    db.session.commit()

    # --- Der Zeitplan sagt, warum nichts ansteht ----------------------
    #
    # Am 05.09.2026 gemeldet: eine freigegebene Variante war im Zeitplan
    # nirgends zu sehen, und daneben stand "Kein Konto verbunden", obwohl
    # Facebook verbunden war. Beides Anzeigefehler, beide fuehren genau in
    # die falsche Richtung.

    wartende = CI(
        campaign_channel_id=neue_verbindung.id, variant_group="wartet",
        type="image", quelle="upload", title="Wartet auf active",
        description="x", file_path="hochgeladen/x.jpg", status="ready",
    )
    db.session.add(wartende)
    db.session.commit()

    seite = client.get("/zeitplan").data.decode()
    pruefe("Eine freigegebene Variante ohne Termin steht auf dem Zeitplan",
           "Wartet auf active" in seite)
    pruefe("Und dazu, woran es liegt",
           "Kampagne steht auf draft" in seite)

    zweite.status = "active"
    db.session.commit()
    seite = client.get("/zeitplan").data.decode()
    pruefe("Bei aktiver Kampagne steht dort der naechste Lauf",
           "naechsten Lauf".replace("ae", "ä") in seite)
    zweite.status = "draft"
    db.session.commit()

    # Der zweite Teil: gemeldet wird nur, was auch gebraucht wird.
    ohne = _ohne_konto(client.get("/zeitplan").data.decode())
    pruefe("Pinterest steht dort, weil die Kampagne ihn benutzt",
           "Pinterest" in ohne)
    pruefe("Instagram nicht, den benutzt keine Kampagne",
           "Instagram" not in ohne)
    pruefe("Threads auch nicht", "Threads" not in ohne)

    db.session.delete(wartende)
    db.session.commit()

    # --- Eine gescheiterte Variante noch einmal ansetzen ---------------
    #
    # Am 05.09.2026 gescheitert, weil bei Meta zwei Rechte fehlten. Nach dem
    # Nachtragen war die Variante trotzdem nicht mehr einzuplanen: sie stand
    # auf `failed` und behielt ihren Termin in der Vergangenheit.
    # `einplanen` fasst nur an, was **keinen** Termin hat, `posten` nimmt nur
    # `ready` -- sie waere fuer immer liegengeblieben.

    from app.models import PostedItem as PI

    zweite.status = "active"
    db.session.commit()
    kaputt = CI(
        campaign_channel_id=neue_verbindung.id, variant_group="kaputt",
        type="image", quelle="upload", title="Ging schief",
        description="x", file_path="hochgeladen/x.jpg", status="failed",
        geplant_fuer=jetzt() - timedelta(hours=2),
    )
    db.session.add(kaputt)
    db.session.commit()
    db.session.add(PI(
        content_item_id=kaputt.id,
        campaign_channel_id=neue_verbindung.id,
        status="failed",
        fehler="Meta: (#200) The permission(s) pages_manage_posts are not available.",
    ))
    db.session.commit()

    seite = client.get(f"/kanal/{neue_verbindung.id}/varianten").data.decode()
    pruefe("Der Grund steht an der gescheiterten Variante",
           "pages_manage_posts" in seite)
    pruefe("Und ein Knopf, der es noch einmal versucht",
           'value="nochmal"' in seite)

    alter_termin = kaputt.geplant_fuer
    antwort = client.post(
        f"/kanal/{neue_verbindung.id}/varianten/{kaputt.id}",
        data={"csrf_token": _token(client), "aktion": "nochmal"},
        follow_redirects=True,
    )
    db.session.refresh(kaputt)
    pruefe("Erneut versuchen setzt sie zurueck auf freigegeben",
           kaputt.status == "ready")
    pruefe("Und vergibt gleich einen neuen Termin",
           kaputt.geplant_fuer is not None)
    pruefe("Der neue Termin liegt in der Zukunft",
           kaputt.geplant_fuer is not None
           and nach_berlin(kaputt.geplant_fuer) > jetzt())
    pruefe("Nicht der alte aus der Vergangenheit",
           kaputt.geplant_fuer != alter_termin)
    pruefe("Die Meldung nennt den neuen Termin",
           "neu angesetzt".encode() in antwort.data)

    # Der Fehlversuch bleibt stehen. Er ist passiert, und die Auswertung
    # soll ihn zaehlen -- ein Kanal, an dem jeder zweite Beitrag scheitert,
    # sieht sonst so gut aus wie einer, an dem alles klappt.
    pruefe("Der alte Fehlversuch bleibt in der Auswertung stehen",
           db.session.scalar(
               select(func.count(PI.id)).where(PI.content_item_id == kaputt.id)
           ) == 1)

    # Nur der gescheiterte Fall. Sonst waere das ein zweiter Weg, eine
    # laufende oder schon geposteten Variante umzubiegen.
    for zustand in ("ready", "draft", "posted"):
        kaputt.status = zustand
        db.session.commit()
        antwort = client.post(
            f"/kanal/{neue_verbindung.id}/varianten/{kaputt.id}",
            data={"csrf_token": _token(client), "aktion": "nochmal"},
            follow_redirects=True,
        )
        db.session.refresh(kaputt)
        pruefe(f"Aus '{zustand}' laesst sich nichts neu ansetzen",
               kaputt.status == zustand)

    db.session.execute(
        delete(PI).where(PI.content_item_id == kaputt.id)
    )
    db.session.delete(kaputt)
    db.session.commit()
    zweite.status = "draft"
    db.session.commit()

    # --- Status von der Uebersicht aus --------------------------------

    seite = client.get("/uebersicht").data.decode()
    pruefe("Die Uebersicht zeigt, wo eine Kampagne laeuft",
           "Läuft auf" in seite and "Pinterest" in seite)
    pruefe("Und der Status ist dort waehlbar",
           f'/kampagnen/{zweite.id}/status' in seite)

    client.post(
        f"/kampagnen/{zweite.id}/status",
        data={"csrf_token": _token(client), "status": "active"},
    )
    db.session.refresh(zweite)
    pruefe("Der Status laesst sich dort umstellen", zweite.status == "active")
    pruefe("Name und Ziel-Link bleiben dabei stehen",
           zweite.name == "Prüfung Ablauf"
           and zweite.target_url == "https://example.de")

    client.post(
        f"/kampagnen/{zweite.id}/status",
        data={"csrf_token": _token(client), "status": "erfunden"},
    )
    db.session.refresh(zweite)
    pruefe("Ein unbekannter Status wird abgewiesen", zweite.status == "active")

    db.session.delete(neue_verbindung)
    db.session.delete(zweite)
    db.session.commit()

    # Beim Loeschen einer Variante muss auch die Datei verschwinden, sonst
    # fuellt sich der Ordner mit Bildern, die zu nichts mehr gehoeren.
    vorher = _anzahl()
    _hochladen("weg.jpg", JPG)
    eintrag = db.session.scalars(
        select(ContentItem)
        .where(ContentItem.campaign_channel_id == verbindung.id)
        .order_by(ContentItem.id.desc())
    ).first()
    pfad = os.path.join(app.config["UPLOAD_ORDNER"], *eintrag.file_path.split("/"))
    pruefe("Die hochgeladene Datei liegt wirklich da", os.path.exists(pfad))
    client.post(
        f"/kanal/{verbindung.id}/varianten/{eintrag.id}",
        data={"csrf_token": _token(client), "aktion": "loeschen"},
    )
    pruefe("Loeschen entfernt die Variante", _anzahl() == vorher)
    pruefe("Und die Datei dazu", not os.path.exists(pfad))

    # Auch die Dateien wegräumen, nicht nur die Zeilen. Ein Prüfskript, das
    # bei jedem Lauf ein paar Bytes im Upload-Ordner liegen lässt, füllt ihn
    # über Monate mit Müll, den niemand zuordnen kann.
    wurzel = app.config["UPLOAD_ORDNER"]
    for e in db.session.scalars(
        select(ContentItem).where(ContentItem.campaign_channel_id == verbindung.id)
    ):
        if e.file_path:
            try:
                os.remove(os.path.join(wurzel, *e.file_path.split("/")))
            except OSError:
                pass
        db.session.delete(e)
    db.session.delete(verbindung)
    db.session.delete(kampagne)
    db.session.commit()

    # --- Ein Kanal ohne Adapter ---------------------------------------

    # X ist der letzte ohne Adapter. Instagram und Facebook standen hier
    # bis zum 04.09.2026 und haben jetzt einen.
    antwort = client.post(
        "/kanaele/x/verbinden", data={"csrf_token": _token(client)}
    )
    pruefe("Ein Kanal ohne Adapter gibt 404", antwort.status_code == 404)


if __name__ == "__main__":
    sys.exit(main())
