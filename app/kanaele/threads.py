"""Threads.

Gehört Meta, ist aber **keine Erweiterung der Graph API** und steht deshalb
in einer eigenen Datei statt bei Facebook und Instagram. Alles ist anders:
ein eigener Host (`graph.threads.net`), ein eigener Anmeldeweg über
`threads.net`, eigene Rechte, eine eigene App im Entwicklerbereich und ein
eigenes Verfahren fürs Erneuern. Wer sie zu `meta.py` dazuschriebe, hätte
eine Klasse, die von ihrer Basis nichts mehr benutzt.

**Es gibt hier keine Ablagen.** Ein Threads-Konto hat keine Boards, keine
Seiten, keine Standorte — gepostet wird auf das Konto, das verbunden ist,
und sonst nirgendwohin. Deshalb `unterstuetzt_ablagen = False`, und der
Zeitplan fragt gar nicht erst nach einem Ziel.

Drei Dinge, die man vorher wissen sollte:

**1. Das Threads-Konto hängt an einem Instagram-Konto**, der Zugang dazu
aber nicht: verbunden wird direkt über Threads, nicht über die
Facebook-Seite. Ein bei Instagram verbundenes Konto hilft hier also nicht,
und die App aus dem Instagram-Kanal auch nicht.

**2. Erneuern geht erst ab 24 Stunden.** Ein Token, das jünger ist, lehnt
Threads beim Erneuern ab. In der Praxis stört das nicht — erneuert wird
kurz vor Ablauf nach 60 Tagen —, aber wer es gleich nach dem Verbinden
ausprobiert, sucht den Fehler sonst im Code.

**3. Ein Token, das 60 Tage nicht erneuert wurde, ist endgültig tot.** Es
lässt sich dann nicht mehr auffrischen, das Konto muss neu verbunden
werden. Der Zeitplan erneuert deshalb rechtzeitig von selbst.

Stand 04.09.2026: gebaut und gegen untergeschobene Antworten geprüft
(`pruefe_threads.py`). Gegen die echte API ist noch nichts gelaufen.
"""

import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from flask import current_app

from .basis import Kanal, KanalFehler, Veroeffentlichung, Zahlen

API = "https://graph.threads.net/v1.0"
# Die beiden Token-Adressen liegen **ohne** Versionsnummer daneben. Das ist
# kein Vertipper, Threads macht das so.
TOKEN = "https://graph.threads.net/oauth/access_token"
TAUSCH = "https://graph.threads.net/access_token"
ERNEUERN = "https://graph.threads.net/refresh_access_token"
ANMELDUNG = "https://threads.net/oauth/authorize"

# `threads_basic` verlangt jeder Endpunkt, auch das Lesen des eigenen
# Kontos. `threads_content_publish` kommt fürs Posten dazu.
BEREICHE = ("threads_basic", "threads_content_publish")

GEDULD = 30

# Threads empfiehlt, vor dem Veröffentlichen rund 30 Sekunden zu warten.
# Statt blind zu warten wird der Container abgefragt: meist ist er lange
# vorher fertig, und die Zeit fehlt sonst jedem weiteren Beitrag des Laufs.
CONTAINER_VERSUCHE = 12
CONTAINER_PAUSE = 3

# Threads schneidet den Text hier ab.
MAX_TEXT = 500


def _fehlertext(antwort) -> str:
    """Was Threads zur Ablehnung sagt, in einem Satz.

    Gleicher Aufbau wie bei der Graph API: der Grund steckt in einem
    verschachtelten `error`-Objekt.
    """
    try:
        daten = antwort.json()
    except ValueError:
        auszug = (antwort.text or "").strip()[:200]
        return f"Threads antwortete mit {antwort.status_code}: {auszug or 'nichts'}"

    fehler = daten.get("error") if isinstance(daten, dict) else None
    if isinstance(fehler, dict):
        meldung = (
            fehler.get("error_user_msg")
            or fehler.get("message")
            or "ohne Begründung"
        )
        code = fehler.get("code")
        return f"Threads: {meldung}" + (f" (Code {code})" if code is not None else "")
    return f"Threads antwortete mit {antwort.status_code}."


def _auswerten(antwort) -> dict:
    if antwort.status_code >= 400:
        raise KanalFehler(_fehlertext(antwort))
    try:
        daten = antwort.json()
    except ValueError as fehler:
        raise KanalFehler("Threads antwortete nicht mit JSON.") from fehler
    return daten if isinstance(daten, dict) else {}


def _hole(url: str, zugang: str, **parameter) -> dict:
    parameter["access_token"] = zugang
    try:
        antwort = requests.get(url, params=parameter, timeout=GEDULD)
    except requests.RequestException as fehler:
        raise KanalFehler(f"Threads war nicht erreichbar: {fehler}") from fehler
    return _auswerten(antwort)


def _schicke(pfad: str, zugang: str, **felder) -> dict:
    felder["access_token"] = zugang
    try:
        antwort = requests.post(API + pfad, data=felder, timeout=GEDULD)
    except requests.RequestException as fehler:
        raise KanalFehler(f"Threads war nicht erreichbar: {fehler}") from fehler
    return _auswerten(antwort)


class Threads(Kanal):
    def __init__(self) -> None:
        super().__init__(
            key="threads",
            name="Threads",
            # Siehe den Kopf: es gibt hier nichts, wohin man wählen könnte.
            unterstuetzt_ablagen=False,
            anmelde_ursprung="https://threads.net",
            typen=("image",),
            max_beschreibung=MAX_TEXT,
            bild_format="1:1",
            # Kein eigenes Feld für den Ziel-Link, er gehört in den Text.
            link_im_text=True,
            # **Anders als bei Instagram ist er dort anklickbar.** Threads
            # erkennt die erste Adresse im Text und baut eine Vorschau
            # daraus. Deshalb steht der Link am Ende und nicht mittendrin.
            link_klickbar=True,
        )

    def _zugangsdaten(self) -> tuple[str, str]:
        from ..einstellungen import kanal_wert

        app_id = kanal_wert(self.key, "app_id")
        app_secret = kanal_wert(self.key, "app_secret")
        if not app_id or not app_secret:
            raise KanalFehler(
                "Für Threads fehlen die Zugangsdaten der App. Einzutragen "
                "unter Einstellungen; die App wird im Meta-Entwicklerbereich "
                "angelegt, mit dem Anwendungsfall Threads API — die App für "
                "Instagram oder Facebook passt hier nicht."
            )
        return app_id, app_secret

    def _rueckruf(self) -> str:
        from . import rueckruf_adresse

        return rueckruf_adresse(self.key)

    # --- Verbinden -----------------------------------------------------

    def anmelde_adresse(self, zustand: str) -> str:
        from ..einstellungen import kanal_wert

        app_id = kanal_wert("threads", "app_id")
        if not app_id:
            raise KanalFehler(
                "Für Threads ist keine App-ID hinterlegt. Einzutragen unter "
                "Einstellungen."
            )
        return ANMELDUNG + "?" + urlencode({
            "client_id": app_id,
            "redirect_uri": self._rueckruf(),
            "response_type": "code",
            # Threads trennt die Rechte mit Komma, wie Pinterest.
            "scope": ",".join(BEREICHE),
            "state": zustand,
        })

    def zugang_holen(self, code: str) -> dict:
        """Code eintauschen und sofort haltbar machen.

        Der erste Tausch gibt ein Token für **eine Stunde**. Damit allein
        wäre der Kanal nach dem Mittagessen tot, deshalb folgt der zweite
        Schritt hier direkt und nicht irgendwann später.
        """
        app_id, app_secret = self._zugangsdaten()

        try:
            antwort = requests.post(
                TOKEN,
                data={
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": self._rueckruf(),
                    "code": code,
                },
                timeout=GEDULD,
            )
        except requests.RequestException as fehler:
            raise KanalFehler(f"Threads war nicht erreichbar: {fehler}") from fehler

        daten = _auswerten(antwort)
        kurz = daten.get("access_token") or ""
        if not kurz:
            raise KanalFehler("Threads hat keinen Zugang geliefert.")

        felder = self._verlaengern(kurz)
        felder["kontoname"] = self._kontoname(felder["zugang"])
        return felder

    def _verlaengern(self, kurz: str) -> dict:
        """Tauscht das kurzlebige Token gegen eins mit 60 Tagen."""
        _, app_secret = self._zugangsdaten()
        daten = _hole(
            TAUSCH, kurz, grant_type="th_exchange_token", client_secret=app_secret
        )
        return self._token_felder(daten)

    def zugang_erneuern(self, erneuerung: str) -> dict:
        """Frischt das langlebige Token auf, wieder für 60 Tage.

        **Threads kennt kein eigenes Erneuerungs-Token**, aufgefrischt wird
        das Zugangs-Token selbst. In `accounts` steht unter `erneuerung`
        deshalb dasselbe wie unter `zugang`.

        Zwei Grenzen dabei, beide von Threads gesetzt: es muss **mindestens
        24 Stunden alt** und darf **noch nicht abgelaufen** sein. Ist die
        Frist einmal um, hilft nur neu verbinden — genau deshalb erneuert
        der Zeitplan lange vorher und nicht am Ablauftag.
        """
        if not erneuerung:
            raise KanalFehler(
                "Für Threads ist kein Token zum Auffrischen hinterlegt. Das "
                "Konto muss neu verbunden werden."
            )
        daten = _hole(ERNEUERN, erneuerung, grant_type="th_refresh_token")
        return self._token_felder(daten)

    def _token_felder(self, daten: dict) -> dict:
        from ..zeit import UTC

        zugang = daten.get("access_token") or ""
        if not zugang:
            raise KanalFehler("Threads hat keinen Zugang geliefert.")

        sekunden = daten.get("expires_in")
        laeuft_ab = None
        if isinstance(sekunden, (int, float)) and sekunden > 0:
            laeuft_ab = datetime.now(tz=UTC) + timedelta(seconds=int(sekunden))

        # Siehe `zugang_erneuern`: das Token ist sein eigenes
        # Erneuerungs-Token.
        return {"zugang": zugang, "erneuerung": zugang, "laeuft_ab": laeuft_ab}

    def _kontoname(self, zugang: str) -> str:
        daten = _hole(f"{API}/me", zugang, fields="id,username")
        name = str(daten.get("username") or "")
        return f"@{name}" if name else ""

    def _konto_id(self, zugang: str) -> str:
        """Die eigene Kennung, an die gepostet wird.

        Threads erlaubt zwar `me` als Platzhalter im Pfad, aber nicht
        überall gleich zuverlässig. Einmal nachfragen kostet einen Aufruf
        und spart eine Fehlersuche.
        """
        daten = _hole(f"{API}/me", zugang, fields="id")
        kennung = str(daten.get("id") or "")
        if not kennung:
            raise KanalFehler("Threads nennt keine Konto-Kennung.")
        return kennung

    # --- Betrieb -------------------------------------------------------

    def veroeffentlichen(
        self,
        zugang: str,
        *,
        titel: str,
        beschreibung: str,
        ziel_url: str,
        datei: str | None,
        ablage_id: str | None,
        typ: str = "image",
    ) -> Veroeffentlichung:
        # `ablage_id` wird bewusst ignoriert: der Kanal hat keine Ablagen,
        # und ein Wert darin wäre ein Missverständnis und kein Ziel.
        if not datei:
            raise KanalFehler("Ein Beitrag braucht ein Bild.")

        text = beschreibung or ""
        if titel:
            text = f"{titel}\n\n{text}".strip()
        text = _text_mit_link(text, ziel_url, MAX_TEXT)

        konto = self._konto_id(zugang)

        container = _schicke(
            f"/{konto}/threads",
            zugang,
            media_type="IMAGE",
            image_url=bild_adresse(datei),
            text=text,
        )
        container_id = str(container.get("id") or "")
        if not container_id:
            raise KanalFehler("Threads hat keinen Container angelegt.")

        self._auf_container_warten(zugang, container_id)

        daten = _schicke(
            f"/{konto}/threads_publish", zugang, creation_id=container_id
        )
        kennung = str(daten.get("id") or "")
        if not kennung:
            raise KanalFehler(
                "Threads hat den Beitrag angenommen, aber keine Kennung "
                "geliefert."
            )
        return Veroeffentlichung(plattform_id=kennung)

    def _auf_container_warten(self, zugang: str, container_id: str) -> None:
        """Fragt den Container ab, bis er fertig ist.

        Threads empfiehlt pauschal 30 Sekunden Wartezeit. Abgefragt statt
        abgewartet: meist ist der Container lange vorher fertig, und die
        Zeit fehlt sonst jedem weiteren Beitrag desselben Laufs. Bei `ERROR`
        und `EXPIRED` hat Warten keinen Sinn mehr.
        """
        for versuch in range(CONTAINER_VERSUCHE):
            daten = _hole(
                f"{API}/{container_id}", zugang, fields="status,error_message"
            )
            stand = str(daten.get("status") or "")
            if stand in ("FINISHED", "PUBLISHED"):
                return
            if stand in ("ERROR", "EXPIRED"):
                grund = str(daten.get("error_message") or stand)
                raise KanalFehler(
                    f"Threads konnte das Bild nicht verarbeiten: {grund}"
                )
            if versuch < CONTAINER_VERSUCHE - 1:
                time.sleep(CONTAINER_PAUSE)

        raise KanalFehler(
            "Threads hat das Bild nicht rechtzeitig verarbeitet. Der Beitrag "
            "ist nicht draußen; der nächste Lauf versucht es erneut."
        )

    def zahlen(self, zugang: str, plattform_id: str) -> Zahlen:
        """Aufrufe eines Beitrags.

        **Threads liefert weder Klicks noch Speicherungen**, nur `views` und
        Reaktionen. Beide Felder bleiben 0 — und darin liegt der Grund,
        warum die Auswertung Kanäle später nicht einfach nebeneinander
        stellen darf: eine 0 heißt hier "gibt es nicht", nicht "war nicht".
        """
        daten = _hole(
            f"{API}/{plattform_id}/insights", zugang, metric="views"
        )
        werte = {}
        for eintrag in daten.get("data") or []:
            if not isinstance(eintrag, dict) or not eintrag.get("name"):
                continue
            # Threads schreibt einen einzelnen Wert nach `values`, wie die
            # Graph API, bei manchen Kennzahlen aber direkt nach `total_value`.
            gesamt = eintrag.get("total_value")
            if isinstance(gesamt, dict):
                werte[eintrag["name"]] = gesamt.get("value")
                continue
            liste = eintrag.get("values")
            if isinstance(liste, list) and liste and isinstance(liste[-1], dict):
                werte[eintrag["name"]] = liste[-1].get("value")

        return Zahlen(impressions=_zahl(werte.get("views")))


def bild_adresse(datei: str) -> str:
    """Die öffentliche Adresse des Bildes.

    Threads holt es selbst ab, wie Pinterest und Meta. Dafür liefert nginx
    `uploads/` unter `/medien/` ohne Anmeldung aus.
    """
    wurzel = current_app.config["OEFFENTLICHE_ADRESSE"]
    return f"{wurzel}/medien/{str(datei).lstrip('/')}"


def _text_mit_link(beschreibung: str, ziel_url: str, grenze: int) -> str:
    """Hängt den Ziel-Link ans Ende, ohne ihn je abzuschneiden.

    Dieselbe Regel wie bei Meta: ein halber Link ist schlimmer als keiner.
    Bei Threads kommt ein zweiter Grund dazu — die **erste** Adresse im Text
    wird zur Vorschau. Steht der Ziel-Link hinten und das Modell hat vorne
    eine andere Adresse untergebracht, zeigt die Vorschau die falsche. Genau
    deshalb verbietet die Anfrage an das Modell fremde Adressen.
    """
    text = (beschreibung or "").strip()
    ziel_url = (ziel_url or "").strip()
    if not ziel_url:
        return text[:grenze]
    if ziel_url in text:
        return text[:grenze]

    anhang = f"\n\n{ziel_url}"
    if len(anhang) > grenze:
        raise KanalFehler(
            "Der Ziel-Link ist länger als die Plattform an Text zulässt."
        )
    return (text[: grenze - len(anhang)]).rstrip() + anhang


def _zahl(wert) -> int:
    try:
        return int(wert)
    except (TypeError, ValueError):
        return 0
