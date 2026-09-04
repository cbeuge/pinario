"""Prueft den Verbinden-Weg gegen die echte Anwendung.

    venv\\Scripts\\python.exe pruefe_verbinden.py

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
from sqlalchemy import select

from app import create_app
from app.config import Config
from app.extensions import db
from app.kanaele import BEKANNT, KanalFehler
from app.models import Account, Channel, User
from app.zeit import jetzt

ADRESSE = "https://pinario.example"


class TestConfig(Config):
    PRODUKTION = False
    OEFFENTLICHE_ADRESSE = ADRESSE
    WTF_CSRF_ENABLED = False


class Adapter:
    """Steht anstelle des echten Pinterest-Adapters."""

    key = "pinterest"
    name = "Pinterest"
    unterstuetzt_ablagen = True
    ablage_bezeichnung = "Board"
    ablage_mehrzahl = "Boards"

    def __init__(self):
        self.zustaende = []
        self.codes = []
        self.wirft = None
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
            einstellungen.kanal_entferne("pinterest")
            for name, wert in vorherige_daten.items():
                if wert:
                    einstellungen.setze(
                        einstellungen.kanal_name("pinterest", name), wert
                    )
            for eintrag in db.session.scalars(
                select(Account).where(Account.channel_id == kanal_zeile.id)
            ):
                db.session.delete(eintrag)
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
    seite = client.get("/einstellungen").data.decode()
    pruefe("Ohne Zugangsdaten steht 'Zugangsdaten fehlen'",
           "Zugangsdaten fehlen" in seite)
    pruefe("Ohne Zugangsdaten kein Verbinden-Knopf",
           "Konto verbinden" not in seite)

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
    pruefe("Mit Zugangsdaten steht 'nicht verbunden'", "nicht verbunden" in seite)
    pruefe("Mit Zugangsdaten steht der Verbinden-Knopf da",
           "Konto verbinden" in seite)
    pruefe("Die Rueckruf-Adresse steht zum Abschreiben da",
           f"{ADRESSE}/kanaele/pinterest/rueckruf" in seite)
    pruefe("Das Secret steht nicht im Klartext auf der Seite",
           "geheim" not in seite)

    # --- CSRF ----------------------------------------------------------

    antwort = client.post("/kanaele/pinterest/verbinden", data={})
    pruefe("Verbinden ohne CSRF-Token wird abgewiesen", antwort.status_code == 400)

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

    seite = client.get("/einstellungen").data.decode()
    pruefe("Der Zustand steht jetzt auf 'verbunden'", "verbunden" in seite)
    pruefe("Trennen steht da", "Trennen" in seite)

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

    # --- Boards --------------------------------------------------------

    antwort = client.get("/kanaele/pinterest/ablagen")
    pruefe("Boards werden gezeigt", b"Ferienwohnung" in antwort.data)
    pruefe("Die Kennung steht zum Abschreiben da", b">7<" in antwort.data)

    # --- Zeitplan sieht das Konto -------------------------------------

    seite = client.get("/zeitplan").data.decode()
    pruefe("Zeitplan meldet keinen fehlenden Zugang mehr",
           "Kein Konto verbunden" not in seite)

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
           "Kein Konto verbunden" in seite)

    # --- Ein Kanal ohne Adapter ---------------------------------------

    antwort = client.post(
        "/kanaele/instagram/verbinden", data={"csrf_token": _token(client)}
    )
    pruefe("Ein Kanal ohne Adapter gibt 404", antwort.status_code == 404)


if __name__ == "__main__":
    sys.exit(main())
