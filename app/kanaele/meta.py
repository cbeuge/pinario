"""Facebook-Seiten und Instagram, beide über die Graph API von Meta.

Zwei Kanäle, eine Datei: sie teilen sich die App, den Anmeldeweg, das Token
und die Seitenliste. Getrennt sind nur das Posten und die Zahlen. Wer sie
auseinanderzöge, hätte den ganzen oberen Teil zweimal — und beim nächsten
Versionswechsel von Meta zweimal zu ändern.

**Der große Unterschied zu Pinterest: hier wartet man auf niemanden.**
Solange nur eigene Konten bedient werden, reicht eine App im
Entwicklungsmodus mit dem eigenen Konto als Administrator beziehungsweise
Instagram-Tester. Der App Review von Meta greift erst, wenn *fremde* Leute
ihre Konten mit der App verbinden, und genau das passiert bei pinario nie.

Was dafür vorher stehen muss, und ohne das geht gar nichts:

**1. Eine Facebook-Seite.** Die API kann nur Seiten, keine Privatprofile.

**2. Für Instagram ein Professional-Konto** (Business oder Creator), das
**mit dieser Seite verknüpft** ist. Ohne die Verknüpfung taucht das
Instagram-Konto in `/me/accounts` gar nicht auf, und der Kanal hat nichts,
wohin er posten könnte. Das ist der häufigste Grund für eine leere
Kontenliste.

**3. Eine App im Meta-Entwicklerbereich**, App-ID und Secret unter
Einstellungen. Beide Kanäle haben dort eigene Felder, obwohl meistens
dieselbe App dahintersteht — die Annahme, dass das immer so bleibt, wollten
wir nicht in den Code schreiben.

Drei Dinge, die hier anders laufen als bei Pinterest:

**Es gibt zwei Sorten Token.** Was beim Verbinden herauskommt, ist ein
Nutzer-Token; gepostet wird aber mit einem *Seiten*-Token, und den holt man
sich für jede Seite einzeln über `/me/accounts`. Wer mit dem Nutzer-Token
zu posten versucht, bekommt einen Rechtefehler, der nach einem fehlenden
Recht aussieht und keines ist.

**Instagram postet zweistufig.** Erst wird ein Container angelegt
(`/media`), dann veröffentlicht (`/media_publish`). Dazwischen verarbeitet
Meta das Bild. Bei einem Foto geht das meist sofort, aber eben nicht immer,
und ein sofortiges `media_publish` scheitert dann an einem Container, der
noch nicht fertig ist. Deshalb wird der Status abgefragt, bevor
veröffentlicht wird.

**Der Ziel-Link hat bei beiden kein eigenes Feld.** Bei Pinterest hat ein
Pin einen Link, hier gibt es nur den Text. Bei Facebook ist ein Link im Text
anklickbar, bei Instagram nicht — dort steht er zum Abtippen da. Beides
steht als `link_im_text` und `link_klickbar` am Kanal und geht von dort in
die Anfrage an das Modell.

Stand 04.09.2026: gebaut und gegen untergeschobene Antworten geprüft
(`pruefe_meta.py`). **Gegen die echte API ist noch nichts gelaufen**, dafür
fehlt die App. Was hier steht, ist gegen die Dokumentation geschrieben und
wird beim ersten echten Verbinden gegengeprüft.
"""

import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from flask import current_app

from .basis import Ablage, Kanal, KanalFehler, Veroeffentlichung, Zahlen

# Eine Version, die stehen bleibt. Meta hält jede Fassung mindestens zwei
# Jahre; v25.0 ist vom Februar 2026. **Nicht weglassen** — ohne Angabe
# bedient Meta die jeweils älteste noch unterstützte, und die verschwindet
# irgendwann unter der laufenden Anwendung weg.
VERSION = "v25.0"
API = f"https://graph.facebook.com/{VERSION}"
ANMELDUNG = f"https://www.facebook.com/{VERSION}/dialog/oauth"

# Kein Aufruf darf den Zeitplan aufhalten, siehe die Anmerkung im
# Pinterest-Adapter.
GEDULD = 30

# Wie lange auf einen fertig verarbeiteten Instagram-Container gewartet
# wird, und in welchem Abstand nachgefragt. Ein Foto ist meist sofort
# fertig; die Grenze ist für den Fall da, dass Meta hängt, und nicht der
# Normalfall.
CONTAINER_VERSUCHE = 10
CONTAINER_PAUSE = 3


def _fehlertext(antwort) -> str:
    """Was Meta zur Ablehnung sagt, in einem Satz.

    Landet in `posted_items.fehler` und wird auf `/zeitplan` gelesen. Meta
    packt den Grund in ein verschachteltes `error`-Objekt; die
    `error_user_msg` daraus ist der Satz, den Meta selbst einem Menschen
    zeigen würde, und deshalb der bessere von beiden.
    """
    try:
        daten = antwort.json()
    except ValueError:
        auszug = (antwort.text or "").strip()[:200]
        return f"Meta antwortete mit {antwort.status_code}: {auszug or 'nichts'}"

    fehler = daten.get("error") if isinstance(daten, dict) else None
    if isinstance(fehler, dict):
        meldung = (
            fehler.get("error_user_msg")
            or fehler.get("message")
            or "ohne Begründung"
        )
        code = fehler.get("code")
        unter = fehler.get("error_subcode")
        kennung = ", ".join(
            str(teil) for teil in (code, unter) if teil is not None
        )
        return f"Meta: {meldung}" + (f" (Code {kennung})" if kennung else "")
    return f"Meta antwortete mit {antwort.status_code}."


def _auswerten(antwort) -> dict:
    if antwort.status_code >= 400:
        raise KanalFehler(_fehlertext(antwort))
    try:
        daten = antwort.json()
    except ValueError as fehler:
        raise KanalFehler("Meta antwortete nicht mit JSON.") from fehler
    return daten if isinstance(daten, dict) else {}


def _hole(pfad: str, zugang: str, **parameter) -> dict:
    # Das Token geht als Parameter mit und nicht im Kopf. Meta nimmt beides,
    # aber die eigene Dokumentation und jede Fehlermeldung sprechen von
    # `access_token` — wer danach sucht, soll es im Code wiederfinden.
    parameter["access_token"] = zugang
    try:
        antwort = requests.get(API + pfad, params=parameter, timeout=GEDULD)
    except requests.RequestException as fehler:
        raise KanalFehler(f"Meta war nicht erreichbar: {fehler}") from fehler
    return _auswerten(antwort)


def _schicke(pfad: str, zugang: str, **felder) -> dict:
    felder["access_token"] = zugang
    try:
        antwort = requests.post(API + pfad, data=felder, timeout=GEDULD)
    except requests.RequestException as fehler:
        raise KanalFehler(f"Meta war nicht erreichbar: {fehler}") from fehler
    return _auswerten(antwort)


def _text_mit_link(beschreibung: str, ziel_url: str, grenze: int) -> str:
    """Hängt den Ziel-Link an, ohne die Grenze der Plattform zu reißen.

    Der Link wird **nie** abgeschnitten: ein halber Link ist schlimmer als
    gar keiner, weil er aussieht, als führte er irgendwohin. Passt er nicht
    mehr, wird stattdessen der Text gekürzt.

    Dass er überhaupt in den Text muss, steht als `link_im_text` am Kanal:
    ein Foto-Beitrag hat bei Meta kein eigenes Feld dafür.
    """
    text = (beschreibung or "").strip()
    ziel_url = (ziel_url or "").strip()
    if not ziel_url:
        return text[:grenze]
    if ziel_url in text:
        # Das Modell hat ihn schon hineingeschrieben, siehe die Regel in
        # `ki.anfrage_bauen`. Ein zweites Mal wäre nur Rauschen.
        return text[:grenze]

    anhang = f"\n\n{ziel_url}"
    if len(anhang) > grenze:
        # Ein Ziel-Link, der allein schon zu lang ist, gehört gemeldet und
        # nicht stillschweigend weggelassen.
        raise KanalFehler(
            "Der Ziel-Link ist länger als die Plattform an Text zulässt."
        )
    return (text[: grenze - len(anhang)]).rstrip() + anhang


class MetaKanal(Kanal):
    """Was Facebook und Instagram gemeinsam haben.

    Alles hier gilt für beide: anmelden, Token tauschen, Token erneuern, die
    Seiten des Kontos holen. Was sich unterscheidet, steht in den beiden
    Klassen darunter.
    """

    # Welche Rechte dieser Kanal beim Anmelden verlangt. Getrennt, weil ein
    # Kanal nur das erfragen soll, was er wirklich braucht: wer Facebook
    # verbindet, muss dafür nicht Instagram freigeben.
    bereiche: tuple[str, ...] = ()

    def _zugangsdaten(self) -> tuple[str, str]:
        """App-ID und Secret aus den Einstellungen.

        Import in der Funktion: `einstellungen` liest umgekehrt das
        Verzeichnis der Kanäle, oben im Modul wäre das ein Kreis.
        """
        from ..einstellungen import kanal_wert

        app_id = kanal_wert(self.key, "app_id")
        app_secret = kanal_wert(self.key, "app_secret")
        if not app_id or not app_secret:
            raise KanalFehler(
                f"Für {self.name} fehlen die Zugangsdaten der App. Einzutragen "
                "unter Einstellungen; die App wird im Meta-Entwicklerbereich "
                "angelegt."
            )
        return app_id, app_secret

    def _rueckruf(self) -> str:
        from . import rueckruf_adresse

        return rueckruf_adresse(self.key)

    # --- Verbinden -----------------------------------------------------

    def anmelde_adresse(self, zustand: str) -> str:
        from ..einstellungen import kanal_wert

        app_id = kanal_wert(self.key, "app_id")
        if not app_id:
            raise KanalFehler(
                f"Für {self.name} ist keine App-ID hinterlegt. Einzutragen "
                "unter Einstellungen; die App wird im Meta-Entwicklerbereich "
                "angelegt."
            )
        return ANMELDUNG + "?" + urlencode({
            "client_id": app_id,
            "redirect_uri": self._rueckruf(),
            "response_type": "code",
            "scope": ",".join(self.bereiche),
            "state": zustand,
        })

    def zugang_holen(self, code: str) -> dict:
        """Code eintauschen und das Ergebnis gleich haltbar machen.

        Meta gibt hier ein Token, das **eine Stunde** gilt. Damit allein
        wäre der Kanal nach dem Mittagessen tot. Der zweite Schritt tauscht
        es gegen eins mit rund 60 Tagen — das ist kein Feinschliff, sondern
        der Unterschied zwischen benutzbar und nicht.
        """
        app_id, app_secret = self._zugangsdaten()
        kurz = self._token_aufruf({
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": self._rueckruf(),
            "code": code,
        })
        felder = self._verlaengern(kurz["zugang"])
        felder["kontoname"] = self._kontoname(felder["zugang"])
        return felder

    def zugang_erneuern(self, erneuerung: str) -> dict:
        """Verlängert das langlebige Token, solange es noch gilt.

        **Meta kennt kein Erneuerungs-Token.** Erneuert wird, indem man das
        alte Zugangs-Token noch einmal eintauscht — und das geht nur,
        solange es nicht abgelaufen ist. Deshalb steht in `accounts` als
        `erneuerung` dasselbe wie in `zugang`, und deshalb erneuert der
        Zeitplan rechtzeitig statt erst am Ablauftag: ist die Frist einmal
        um, hilft nur noch neu verbinden.
        """
        if not erneuerung:
            raise KanalFehler(
                f"Für {self.name} ist kein Token zum Verlängern hinterlegt. "
                "Das Konto muss neu verbunden werden."
            )
        return self._verlaengern(erneuerung)

    def _verlaengern(self, zugang: str) -> dict:
        app_id, app_secret = self._zugangsdaten()
        felder = self._token_aufruf({
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": zugang,
        })
        # Siehe `zugang_erneuern`: das Token ist zugleich sein eigenes
        # Erneuerungs-Token.
        felder["erneuerung"] = felder["zugang"]
        return felder

    def _token_aufruf(self, parameter: dict) -> dict:
        from ..zeit import UTC

        try:
            antwort = requests.get(
                API + "/oauth/access_token", params=parameter, timeout=GEDULD
            )
        except requests.RequestException as fehler:
            raise KanalFehler(f"Meta war nicht erreichbar: {fehler}") from fehler

        daten = _auswerten(antwort)
        zugang = daten.get("access_token") or ""
        if not zugang:
            raise KanalFehler("Meta hat keinen Zugang geliefert.")

        sekunden = daten.get("expires_in")
        laeuft_ab = None
        if isinstance(sekunden, (int, float)) and sekunden > 0:
            laeuft_ab = datetime.now(tz=UTC) + timedelta(seconds=int(sekunden))
        # Ohne `expires_in` antwortet Meta bei einem Token, das nicht
        # abläuft. Dann bleibt die Spalte leer und der Zeitplan lässt es in
        # Ruhe — genau richtig.

        return {"zugang": zugang, "erneuerung": "", "laeuft_ab": laeuft_ab}

    def _kontoname(self, zugang: str) -> str:
        daten = _hole("/me", zugang, fields="name")
        return str(daten.get("name") or "")

    # --- Seiten --------------------------------------------------------

    def _seiten(self, zugang: str, felder: str) -> list[dict]:
        """Die Seiten des Kontos, über alle Ergebnisseiten hinweg.

        Der Kern beider Kanäle: hier hängt das Seiten-Token dran, mit dem
        wirklich gepostet wird, und bei Instagram auch das verknüpfte Konto.
        """
        gefunden: list[dict] = []
        pfad = "/me/accounts"
        parameter = {"fields": felder, "limit": 100}
        # Harte Grenze gegen eine Antwort, die immer weiterblättert.
        for _ in range(10):
            daten = _hole(pfad, zugang, **parameter)
            eintraege = daten.get("data")
            if isinstance(eintraege, list):
                gefunden.extend(e for e in eintraege if isinstance(e, dict))
            weiter = (daten.get("paging") or {}).get("cursors") or {}
            nach = weiter.get("after")
            if not nach or not eintraege:
                break
            parameter["after"] = nach
        return gefunden

    def _seiten_token(self, zugang: str, seiten_id: str) -> str:
        """Das Token *dieser* Seite. Ohne das geht kein Beitrag raus.

        Siehe den Kopf der Datei: mit dem Nutzer-Token zu posten gibt einen
        Rechtefehler, der nach einem fehlenden Recht aussieht und keines ist.
        """
        for seite in self._seiten(zugang, "id,name,access_token"):
            if str(seite.get("id") or "") == str(seiten_id):
                token = str(seite.get("access_token") or "")
                if not token:
                    raise KanalFehler(
                        f"Für die Seite {seite.get('name') or seiten_id} gibt "
                        "Meta kein Seiten-Token heraus. Meist fehlt die Rolle "
                        "auf der Seite oder das Recht pages_show_list."
                    )
                return token
        raise KanalFehler(
            f"Die Seite {seiten_id} gehört nicht zu diesem Konto. Wurde sie "
            "am Kanal der Kampagne von Hand eingetragen?"
        )


class Facebook(MetaKanal):
    """Beiträge auf einer Facebook-Seite.

    Gepostet wird als **Foto mit Bildunterschrift** (`/photos`) und nicht
    als Beitrag mit Link (`/feed`). Der Unterschied ist sichtbar: bei
    `/feed` mit `link` baut Facebook eine eigene Vorschaukarte aus der
    Zielseite, und das selbst erzeugte Bild taucht gar nicht auf. Genau
    dieses Bild ist aber der Grund, warum es pinario gibt.
    """

    def __init__(self) -> None:
        super().__init__(
            key="facebook",
            name="Facebook",
            unterstuetzt_ablagen=True,
            ablage_bezeichnung="Seite",
            ablage_mehrzahl="Seiten",
            # Video braucht bei Meta einen eigenen, mehrstufigen Weg, und
            # die Anwendung erzeugt bisher keine Videos. Dieselbe
            # Entscheidung wie bei Pinterest, aus demselben Grund: sonst
            # plant der Zeitplan etwas ein, das der Adapter ablehnt.
            typen=("image",),
            # Eine Bildunterschrift bei Facebook darf sehr lang sein. Die
            # Grenze hier ist keine der Plattform, sondern eine des
            # Anstands: einen Beitrag, den niemand zu Ende liest, muss man
            # nicht erzeugen lassen.
            max_beschreibung=2000,
            link_im_text=True,
            link_klickbar=True,
        )

    bereiche = (
        "pages_show_list",
        "pages_read_engagement",
        "pages_manage_posts",
    )

    def ablagen(self, zugang: str) -> list[Ablage]:
        return [
            Ablage(id=str(seite["id"]), name=str(seite.get("name") or seite["id"]))
            for seite in self._seiten(zugang, "id,name")
            if seite.get("id")
        ]

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
                "Für Facebook fehlt die Seite. Einzutragen am Kanal der "
                "Kampagne."
            )
        if not datei:
            raise KanalFehler("Ein Beitrag braucht ein Bild.")

        # Der Titel steht bei Facebook nicht getrennt, es gibt nur einen
        # Text. Er kommt deshalb als erste Zeile davor — sonst wäre die
        # Arbeit, die in ihn geflossen ist, hier einfach weg.
        text = beschreibung or ""
        if titel:
            text = f"{titel}\n\n{text}".strip()
        text = _text_mit_link(text, ziel_url, self.max_beschreibung)

        seiten_token = self._seiten_token(zugang, ablage_id)
        daten = _schicke(
            f"/{ablage_id}/photos",
            seiten_token,
            url=bild_adresse(datei),
            caption=text,
        )

        # `post_id` ist der Beitrag, `id` nur das Foto. Für die Zahlen
        # später ist der Beitrag der richtige.
        kennung = str(daten.get("post_id") or daten.get("id") or "")
        if not kennung:
            raise KanalFehler(
                "Facebook hat den Beitrag angenommen, aber keine Kennung "
                "geliefert."
            )
        return Veroeffentlichung(plattform_id=kennung, ablage_id=str(ablage_id))

    def zahlen(self, zugang: str, plattform_id: str) -> Zahlen:
        """Aufrufe und Klicks eines Beitrags.

        **Facebook kennt kein "Saves".** Das Feld bleibt 0, und in der
        Auswertung dürfen Kanäle deshalb nicht über diese Zahl hinweg
        verglichen werden.

        Der wackligste Teil dieses Adapters: Meta räumt bei den Kennzahlen
        laufend um, `post_impressions` verschwindet 2026 zugunsten neuer
        Namen. Deshalb wird jeder Name einzeln gesucht und ein fehlender zu
        einer Null, statt den ganzen Aufruf scheitern zu lassen.
        """
        daten = _hole(
            f"/{plattform_id}/insights",
            zugang,
            metric="post_impressions,post_clicks",
        )
        werte = _insights_lesen(daten)
        return Zahlen(
            impressions=_zahl(werte.get("post_impressions")),
            clicks=_zahl(werte.get("post_clicks")),
        )


class Instagram(MetaKanal):
    """Beiträge auf einem Instagram-Professional-Konto.

    Die Ablagen sind hier die **Konten**, nicht die Seiten: ein Konto hängt
    zwar an einer Seite, gepostet wird aber an die Instagram-Kennung. In der
    Oberfläche heißen sie deshalb "Konten", im Code sind sie dasselbe wie
    Boards bei Pinterest.
    """

    def __init__(self) -> None:
        super().__init__(
            key="instagram",
            name="Instagram",
            unterstuetzt_ablagen=True,
            ablage_bezeichnung="Konto",
            ablage_mehrzahl="Konten",
            typen=("image",),
            # Instagram schneidet die Bildunterschrift hier ab.
            max_beschreibung=2200,
            link_im_text=True,
            # Der Punkt, der diesen Kanal von allen anderen unterscheidet.
            link_klickbar=False,
        )

    bereiche = (
        "pages_show_list",
        "pages_read_engagement",
        "instagram_basic",
        "instagram_content_publish",
    )

    def ablagen(self, zugang: str) -> list[Ablage]:
        """Die Instagram-Konten hinter den Seiten des Kontos.

        **Eine leere Liste heißt fast immer dasselbe**: das Instagram-Konto
        ist kein Professional-Konto oder nicht mit der Seite verknüpft. Es
        taucht dann in `/me/accounts` gar nicht auf. Siehe den Kopf der
        Datei.
        """
        gefunden = []
        for seite in self._seiten(
            zugang, "id,name,instagram_business_account{id,username}"
        ):
            konto = seite.get("instagram_business_account")
            if not isinstance(konto, dict) or not konto.get("id"):
                continue
            name = str(konto.get("username") or "")
            gefunden.append(Ablage(
                id=str(konto["id"]),
                # Der Seitenname steht dabei, weil man beim Eintragen sonst
                # nicht erkennt, welches Konto zu welcher Seite gehört.
                name=(f"@{name}" if name else str(konto["id"]))
                + f" ({seite.get('name') or 'ohne Seitenname'})",
            ))
        return gefunden

    def _seite_zum_konto(self, zugang: str, konto_id: str) -> str:
        """Das Seiten-Token der Seite, an der dieses Konto hängt."""
        for seite in self._seiten(
            zugang, "id,name,access_token,instagram_business_account{id}"
        ):
            konto = seite.get("instagram_business_account")
            if isinstance(konto, dict) and str(konto.get("id") or "") == str(konto_id):
                token = str(seite.get("access_token") or "")
                if not token:
                    raise KanalFehler(
                        f"Für die Seite {seite.get('name') or ''} gibt Meta "
                        "kein Seiten-Token heraus."
                    )
                return token
        raise KanalFehler(
            f"Das Instagram-Konto {konto_id} hängt an keiner Seite dieses "
            "Zugangs. Ist es ein Professional-Konto und mit der Seite "
            "verknüpft?"
        )

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
                "Für Instagram fehlt das Konto. Einzutragen am Kanal der "
                "Kampagne."
            )
        if not datei:
            raise KanalFehler("Ein Beitrag braucht ein Bild.")

        text = beschreibung or ""
        if titel:
            text = f"{titel}\n\n{text}".strip()
        text = _text_mit_link(text, ziel_url, self.max_beschreibung)

        seiten_token = self._seite_zum_konto(zugang, ablage_id)

        # Schritt 1: Container. Das Bild holt Meta selbst ab, siehe
        # `bild_adresse`.
        container = _schicke(
            f"/{ablage_id}/media",
            seiten_token,
            image_url=bild_adresse(datei),
            caption=text,
        )
        container_id = str(container.get("id") or "")
        if not container_id:
            raise KanalFehler("Instagram hat keinen Container angelegt.")

        # Schritt 2: warten, bis er fertig ist. Siehe den Kopf der Datei.
        self._auf_container_warten(seiten_token, container_id)

        # Schritt 3: veröffentlichen.
        daten = _schicke(
            f"/{ablage_id}/media_publish",
            seiten_token,
            creation_id=container_id,
        )
        kennung = str(daten.get("id") or "")
        if not kennung:
            raise KanalFehler(
                "Instagram hat den Beitrag angenommen, aber keine Kennung "
                "geliefert."
            )
        return Veroeffentlichung(plattform_id=kennung, ablage_id=str(ablage_id))

    def _auf_container_warten(self, token: str, container_id: str) -> None:
        """Fragt den Container ab, bis er fertig ist.

        `FINISHED` heißt fertig zum Veröffentlichen, `PUBLISHED` ist er
        schon draußen. Bei `ERROR` und `EXPIRED` hat das Warten keinen Sinn
        mehr — dann bricht es sofort ab, statt die volle Zeit abzusitzen.
        """
        for versuch in range(CONTAINER_VERSUCHE):
            daten = _hole(f"/{container_id}", token, fields="status_code,status")
            stand = str(daten.get("status_code") or "")
            if stand in ("FINISHED", "PUBLISHED"):
                return
            if stand in ("ERROR", "EXPIRED"):
                grund = str(daten.get("status") or stand)
                raise KanalFehler(
                    f"Instagram konnte das Bild nicht verarbeiten: {grund}"
                )
            if versuch < CONTAINER_VERSUCHE - 1:
                time.sleep(CONTAINER_PAUSE)

        raise KanalFehler(
            "Instagram hat das Bild nicht rechtzeitig verarbeitet. Der "
            "Beitrag ist nicht draußen; der nächste Lauf versucht es erneut."
        )

    def zahlen(self, zugang: str, plattform_id: str) -> Zahlen:
        """Aufrufe und Speicherungen eines Beitrags.

        **Instagram kennt keine Klicks auf einen Link im Text** — es gibt ja
        keinen anklickbaren. Das Feld bleibt 0, und darin liegt der Grund,
        warum Kanäle in der Auswertung nicht einfach nebeneinander gestellt
        werden dürfen.

        Wie bei Facebook wird jede Kennzahl einzeln gesucht: Meta hat
        `impressions` zugunsten von `views` abgelöst, und welcher Name gilt,
        hängt am Alter des Kontos. Beide werden gelesen, ein fehlender wird
        zur Null.
        """
        daten = _hole(
            f"/{plattform_id}/insights",
            zugang,
            metric="views,impressions,reach,saved",
        )
        werte = _insights_lesen(daten)
        return Zahlen(
            impressions=_zahl(
                werte.get("views")
                or werte.get("impressions")
                or werte.get("reach")
            ),
            saves=_zahl(werte.get("saved")),
        )


def bild_adresse(datei: str) -> str:
    """Die öffentliche Adresse des Bildes.

    Meta holt das Bild selbst ab, genau wie Pinterest, und dafür liefert
    nginx `uploads/` unter `/medien/` ohne Anmeldung aus. **Vom
    Entwicklungsrechner aus geht das nicht** — er ist von außen nicht
    erreichbar.
    """
    wurzel = current_app.config["OEFFENTLICHE_ADRESSE"]
    return f"{wurzel}/medien/{str(datei).lstrip('/')}"


def _insights_lesen(daten: dict) -> dict:
    """Macht aus Metas Insights-Antwort ein flaches Verzeichnis.

    Die Antwort ist verschachtelt: eine Liste von Kennzahlen, jede mit einer
    Liste von Werten. Gelesen wird der letzte Wert, das ist der aktuelle.
    Alles wird vorsichtig angefasst — eine fehlende Kennzahl ist hier
    normal und kein Fehler.
    """
    werte = {}
    for eintrag in daten.get("data") or []:
        if not isinstance(eintrag, dict):
            continue
        name = eintrag.get("name")
        liste = eintrag.get("values")
        if not name or not isinstance(liste, list) or not liste:
            continue
        letzter = liste[-1]
        if isinstance(letzter, dict):
            werte[name] = letzter.get("value")
    return werte


def _zahl(wert) -> int:
    try:
        return int(wert)
    except (TypeError, ValueError):
        return 0
