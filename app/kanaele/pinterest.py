"""Pinterest, API v5.

Stand 04.09.2026: vollständig gebaut. Verbinden, Boards lesen, Pins
schreiben und Zahlen holen stehen als echte Aufrufe da. **Gegen die echte
API ist trotzdem noch nichts gelaufen** — dafür fehlt die App unter
developers.pinterest.com. Geprüft ist der Adapter gegen untergeschobene
Antworten (`pruefe_pinterest.py`); das belegt den Ablauf und nicht die
Wirklichkeit. Was hier steht, wird beim ersten echten Verbinden
gegengeprüft.

Vier Punkte, die dabei erfahrungsgemäß Zeit kosten:

**1. Trial-Modus.** Eine neue App darf nur auf das Konto, dem sie gehört.
Für mehr ist eine Freigabe nötig. Für pinario reicht Trial, weil nur eigene
Konten bedient werden.

**2. Die Rückruf-Adresse muss zeichengenau stimmen**, und zwar dreimal
gleich: im Entwicklerbereich von Pinterest, beim Anmelden und noch einmal
beim Eintauschen des Codes. Deshalb kommt sie aus `rueckruf_adresse` und
wird nirgends von Hand zusammengesetzt. Ein fehlendes oder zusätzliches
`www` genügt für ein `invalid_grant`, und das sagt nicht, was falsch ist.

**3. Bilder werden nicht hochgeladen, sondern geholt.** Pinterest lädt sie
über eine öffentlich erreichbare Adresse; genau dafür liefert nginx
`/medien` ohne Anmeldung aus. Vom Entwicklungsrechner aus geht das nicht,
weil er von außen nicht erreichbar ist. Der Weg ist deshalb im Prüfskript
abgedeckt und nicht im Feldversuch.

**4. Video geht hier absichtlich nicht.** Ein Pin mit Video braucht den
dreistufigen Medien-Upload (anmelden, zu S3 schieben, auf die Verarbeitung
warten), und die Anwendung erzeugt bisher gar keine Videos. Stünde `video`
trotzdem in `typen`, würde der Zeitplan ein hochgeladenes Video einplanen
und der Adapter es beim Posten ablehnen — also ein gescheiterter Versuch,
der nie hätte stattfinden dürfen. Kommt zurück, sobald es Videos gibt.
"""

import base64
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

import requests
from flask import current_app

from .basis import Ablage, Kanal, KanalFehler, Veroeffentlichung, Zahlen

API = "https://api.pinterest.com/v5"
ANMELDUNG = "https://www.pinterest.com/oauth/"

# Nur was gebraucht wird: Boards lesen, Pins schreiben, Zahlen lesen.
BEREICHE = (
    "boards:read",
    "pins:read",
    "pins:write",
    "user_accounts:read",
)

# Kein Aufruf darf den Zeitplan aufhalten. Der Timer läuft alle fünf
# Minuten, und systemd startet den nächsten Lauf nicht, solange der vorige
# hängt — ohne Frist hielte ein einziger stummer Aufruf alles an.
GEDULD = 30

# Wie weit die Auswertung zurückschaut. Pinterest verlangt beide Daten und
# liefert ohne sie gar nichts.
ZEITRAUM_TAGE = 90

# Pinterest schneidet den Titel eines Pins hier ab.
MAX_TITEL = 100


def _rueckruf() -> str:
    """Die Rückruf-Adresse dieses Kanals.

    Import in der Funktion, weil `kanaele/__init__.py` umgekehrt diese Datei
    lädt — oben im Modul wäre das ein Kreis. Dasselbe gilt für
    `einstellungen`, das seinerseits das Verzeichnis der Kanäle liest.
    """
    from . import rueckruf_adresse

    return rueckruf_adresse("pinterest")


def _zugangsdaten() -> tuple[str, str]:
    """App-ID und Secret aus den Einstellungen."""
    from ..einstellungen import kanal_wert

    app_id = kanal_wert("pinterest", "app_id")
    app_secret = kanal_wert("pinterest", "app_secret")
    if not app_id or not app_secret:
        raise KanalFehler(
            "Für Pinterest fehlen die Zugangsdaten der App. Einzutragen unter "
            "Einstellungen; die App wird unter developers.pinterest.com "
            "angelegt."
        )
    return app_id, app_secret


def _fehlertext(antwort) -> str:
    """Was Pinterest zur Ablehnung sagt, in einem Satz.

    Landet als Text in `posted_items.fehler` und wird auf `/zeitplan`
    gelesen. Ein roher JSON-Block wäre dort unlesbar, ein bloßes "hat nicht
    geklappt" wertlos.
    """
    try:
        daten = antwort.json()
    except ValueError:
        auszug = (antwort.text or "").strip()[:200]
        return f"Pinterest antwortete mit {antwort.status_code}: {auszug or 'nichts'}"

    if isinstance(daten, dict):
        meldung = daten.get("message") or daten.get("error_description") or ""
        code = daten.get("code")
        if meldung:
            zusatz = f" (Code {code})" if code is not None else ""
            return f"Pinterest: {meldung}{zusatz}"
    return f"Pinterest antwortete mit {antwort.status_code}."


def _auswerten(antwort) -> dict:
    if antwort.status_code >= 400:
        raise KanalFehler(_fehlertext(antwort))
    try:
        daten = antwort.json()
    except ValueError as fehler:
        raise KanalFehler("Pinterest antwortete nicht mit JSON.") from fehler
    return daten if isinstance(daten, dict) else {}


def _hole(pfad: str, zugang: str, **parameter) -> dict:
    try:
        antwort = requests.get(
            API + pfad,
            headers={"Authorization": f"Bearer {zugang}"},
            params=parameter or None,
            timeout=GEDULD,
        )
    except requests.RequestException as fehler:
        raise KanalFehler(f"Pinterest war nicht erreichbar: {fehler}") from fehler
    return _auswerten(antwort)


def _schicke(pfad: str, zugang: str, daten: dict) -> dict:
    try:
        antwort = requests.post(
            API + pfad,
            headers={"Authorization": f"Bearer {zugang}"},
            json=daten,
            timeout=GEDULD,
        )
    except requests.RequestException as fehler:
        raise KanalFehler(f"Pinterest war nicht erreichbar: {fehler}") from fehler
    return _auswerten(antwort)


def _token(felder: dict) -> dict:
    """Ruft den Token-Endpunkt auf und übersetzt die Antwort für `accounts`.

    Die App weist sich über Basic-Auth aus und nicht über Felder im Rumpf:
    Pinterest nimmt beides an, aber nur der Kopf hält das Secret aus den
    Protokollen der Zwischenstationen heraus.
    """
    from ..zeit import UTC

    app_id, app_secret = _zugangsdaten()
    ausweis = base64.b64encode(f"{app_id}:{app_secret}".encode()).decode()

    try:
        antwort = requests.post(
            API + "/oauth/token",
            headers={
                "Authorization": f"Basic {ausweis}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=felder,
            timeout=GEDULD,
        )
    except requests.RequestException as fehler:
        raise KanalFehler(f"Pinterest war nicht erreichbar: {fehler}") from fehler

    daten = _auswerten(antwort)
    zugang = daten.get("access_token") or ""
    if not zugang:
        raise KanalFehler("Pinterest hat keinen Zugang geliefert.")

    # `expires_in` sind Sekunden ab jetzt. Gerechnet wird in UTC, weil die
    # Spalte in UTC steht — mit Berliner Zeit läge der Ablauf im Sommer zwei
    # Stunden daneben, und zwar in die gefährliche Richtung.
    sekunden = daten.get("expires_in")
    laeuft_ab = None
    if isinstance(sekunden, (int, float)) and sekunden > 0:
        laeuft_ab = datetime.now(tz=UTC) + timedelta(seconds=int(sekunden))

    return {
        "zugang": zugang,
        "erneuerung": daten.get("refresh_token") or "",
        "laeuft_ab": laeuft_ab,
    }


class Pinterest(Kanal):
    def __init__(self) -> None:
        super().__init__(
            key="pinterest",
            name="Pinterest",
            unterstuetzt_ablagen=True,
            ablage_bezeichnung="Board",
            ablage_mehrzahl="Boards",
            anmelde_ursprung="https://www.pinterest.com",
            # Nur Bild, siehe Punkt 4 im Kopf dieser Datei.
            typen=("image",),
            # Pinterest schneidet die Beschreibung eines Pins hier ab.
            max_beschreibung=800,
            # Pins stehen hochkant. Pinterest empfiehlt 2:3.
            bild_format="2:3",
        )

    # --- Verbinden -----------------------------------------------------

    def anmelde_adresse(self, zustand: str) -> str:
        from ..einstellungen import kanal_wert

        app_id = kanal_wert("pinterest", "app_id")
        if not app_id:
            raise KanalFehler(
                "Für Pinterest ist keine App-ID hinterlegt. Einzutragen unter "
                "Einstellungen; die App wird unter developers.pinterest.com "
                "angelegt."
            )
        return ANMELDUNG + "?" + urlencode({
            "client_id": app_id,
            "redirect_uri": _rueckruf(),
            "response_type": "code",
            "scope": ",".join(BEREICHE),
            "state": zustand,
        })

    def zugang_holen(self, code: str) -> dict:
        felder = _token({
            "grant_type": "authorization_code",
            "code": code,
            # Muss dieselbe sein wie beim Anmelden, sonst `invalid_grant`.
            "redirect_uri": _rueckruf(),
        })
        felder["kontoname"] = self._kontoname(felder["zugang"])
        return felder

    def zugang_erneuern(self, erneuerung: str) -> dict:
        if not erneuerung:
            raise KanalFehler(
                "Für Pinterest ist kein Erneuerungs-Token hinterlegt. Das "
                "Konto muss neu verbunden werden."
            )
        felder = _token({
            "grant_type": "refresh_token",
            "refresh_token": erneuerung,
        })
        # Beim Erneuern schickt Pinterest normalerweise kein neues
        # Erneuerungs-Token mit. Das alte bleibt gültig und muss stehen
        # bleiben: stünde hier "", wäre der Zugang nach dem ersten Erneuern
        # dauerhaft verloren und das Konto müsste neu verbunden werden.
        if not felder["erneuerung"]:
            felder["erneuerung"] = erneuerung
        return felder

    def _kontoname(self, zugang: str) -> str:
        """Der Benutzername, damit in der Oberfläche steht, wer verbunden ist.

        Ein Konto ohne Namen ist bei mehreren Zugängen nicht auseinander-
        zuhalten, und beim Trennen will man wissen, was man trennt.
        """
        daten = _hole("/user_account", zugang)
        return str(daten.get("username") or "")

    # --- Betrieb -------------------------------------------------------

    def ablagen(self, zugang: str) -> list[Ablage]:
        """Alle Boards des verbundenen Kontos.

        Über alle Seiten, nicht nur die erste: wer dreißig Boards hat, sucht
        seins sonst vergeblich in der Auswahl und trägt die Kennung wieder
        von Hand ein.
        """
        gefunden: list[Ablage] = []
        lesezeichen = None
        # Harte Grenze gegen eine Antwort, die immer dasselbe Lesezeichen
        # zurückgibt. Zehn Seiten sind 2500 Boards; wer mehr hat, hat ein
        # anderes Problem.
        for _ in range(10):
            parameter = {"page_size": 250}
            if lesezeichen:
                parameter["bookmark"] = lesezeichen
            daten = _hole("/boards", zugang, **parameter)
            for eintrag in daten.get("items") or []:
                kennung = str(eintrag.get("id") or "")
                if kennung:
                    gefunden.append(
                        Ablage(id=kennung, name=str(eintrag.get("name") or kennung))
                    )
            lesezeichen = daten.get("bookmark")
            if not lesezeichen:
                break
        return gefunden

    def veroeffentlichen(
        self,
        zugang: str,
        *,
        titel: str,
        beschreibung: str,
        ziel_url: str,
        datei: str | None,
        ablage_id: str | None,
    ) -> Veroeffentlichung:
        if not ablage_id:
            raise KanalFehler(
                "Für Pinterest fehlt das Board. Einzutragen am Kanal der "
                "Kampagne."
            )
        if not datei:
            raise KanalFehler("Ein Pin braucht ein Bild.")

        beitrag = {
            "board_id": ablage_id,
            "title": (titel or "")[:MAX_TITEL],
            "description": (beschreibung or "")[: self.max_beschreibung],
            "link": ziel_url,
            "media_source": {
                "source_type": "image_url",
                "url": self._bild_adresse(datei),
            },
        }
        daten = _schicke("/pins", zugang, beitrag)

        kennung = str(daten.get("id") or "")
        if not kennung:
            raise KanalFehler(
                "Pinterest hat den Pin angenommen, aber keine Kennung "
                "geliefert."
            )
        return Veroeffentlichung(
            plattform_id=kennung,
            ablage_id=str(daten.get("board_id") or ablage_id),
            zeitpunkt=_zeitpunkt(daten.get("created_at")),
        )

    def _bild_adresse(self, datei: str) -> str:
        """Die öffentliche Adresse des Bildes, siehe Punkt 3 im Kopf.

        `datei` steht relativ zum Upload-Ordner in `content_items.file_path`.
        """
        wurzel = current_app.config["OEFFENTLICHE_ADRESSE"]
        return f"{wurzel}/medien/{str(datei).lstrip('/')}"

    def zahlen(self, zugang: str, plattform_id: str) -> Zahlen:
        """Impressions, Klicks und Saves eines Pins.

        Pinterest verlangt beide Daten und liefert ohne sie gar nichts. Der
        Zeitraum endet heute und beginnt 90 Tage davor; zurück kommen Summen
        über diesen Zeitraum, keine Tageswerte.
        """
        bis = date.today()
        von = bis - timedelta(days=ZEITRAUM_TAGE)
        daten = _hole(
            f"/pins/{plattform_id}/analytics",
            zugang,
            start_date=von.isoformat(),
            end_date=bis.isoformat(),
            metric_types="IMPRESSION,PIN_CLICK,SAVE",
        )
        # Ohne Anzeigenkonto steht alles unter "all". Der Schlüssel wird
        # nicht vorausgesetzt: verpackt Pinterest die Kennzahlen einmal
        # anders, soll hier eine Null stehen und kein Absturz.
        summen = {}
        block = daten.get("all")
        if isinstance(block, dict):
            summen = block.get("summary_metrics") or {}
        elif isinstance(daten.get("summary_metrics"), dict):
            summen = daten["summary_metrics"]

        return Zahlen(
            impressions=_zahl(summen.get("IMPRESSION")),
            clicks=_zahl(summen.get("PIN_CLICK")),
            saves=_zahl(summen.get("SAVE")),
        )


def _zahl(wert) -> int:
    try:
        return int(wert)
    except (TypeError, ValueError):
        return 0


def _zeitpunkt(wert) -> datetime | None:
    """Der Zeitstempel aus der Antwort, oder nichts.

    Pinterest schreibt `2026-09-04T10:00:00-00:00`. Misslingt das Lesen
    trotzdem, ist der Zeitpunkt die unwichtigste Angabe der ganzen Antwort
    und darf fehlen — einen erfolgreich geposteten Pin nachträglich
    scheitern zu lassen wäre der teurere Fehler.
    """
    if not isinstance(wert, str) or not wert:
        return None
    try:
        return datetime.fromisoformat(wert)
    except ValueError:
        return None
