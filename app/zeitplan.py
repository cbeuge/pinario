"""Einplanen und Posten.

Zwei Schritte, die absichtlich getrennt sind:

**Einplanen** vergibt `geplant_fuer` an freigegebene Varianten. Es rechnet
nur mit Zeiten und der Datenbank, ruft nichts von außen auf und lässt sich
deshalb trocken prüfen.

**Posten** nimmt fällige Einträge und schickt sie über den Adapter raus.
Erst hier kann etwas schiefgehen, das nicht in unserer Hand liegt.

Vier Entscheidungen, die man kennen muss:

**1. Der Scheduler läuft nicht im Webserver.** gunicorn startet zwei Worker;
ein Scheduler im Prozess liefe damit zweimal und würde jeden Beitrag doppelt
posten. Ausgelöst wird über einen systemd-Timer, der `flask zeitplan` ruft,
siehe `betrieb/pinario-zeitplan.timer`.

**2. Ein Kanal ohne verbundenes Konto wird übersprungen, nicht versucht.**
Sonst brennt der erste Lauf alle eingeplanten Varianten auf `failed`, bevor
Pinterest überhaupt verbunden ist — und wer den Fehler danach behebt, hat
trotzdem einen Haufen Leichen in der Messreihe.

**3. Zwischen Herausnehmen und Antwort steht der Eintrag auf `posting`.**
Der Übergang wird sofort committet, damit ein zweiter Lauf ihn nicht noch
einmal nimmt. Bricht der Lauf danach ab, holt der nächste ihn nach
`HAENGT_AB` zurück auf `ready`.

**4. Was der Kanal nicht annimmt, wird gar nicht erst eingeplant.** Ein
Pinterest-Pin braucht ein Bild; eine Variante ohne Bild ist dort kein
gescheiterter Versuch, sondern einer, der nie hätte stattfinden dürfen.

**5. Ein abgelaufener Zugang wird vor dem Lauf erneuert, nicht während er
scheitert.** Pinterest gibt einen Zugang für 30 Tage aus. Ohne diesen
Schritt liefe alles einen Monat lang gut und dann gar nichts mehr, mit einem
`Authentication failed` an jedem einzelnen Beitrag — und niemand sähe, dass
es nur ein Token war. Lässt sich der Zugang nicht erneuern, gilt derselbe
Umgang wie unter Punkt 2: der Kanal wird übersprungen, nicht versucht.
"""

from __future__ import annotations

from datetime import date, time, timedelta

from flask import current_app
from sqlalchemy import func, select

from .extensions import db
from .kanaele import AKTIV, KanalFehler, kanal
from .models import (
    Account,
    Campaign,
    CampaignChannel,
    Channel,
    ContentItem,
    PostedItem,
)
from .zeit import berliner_zeitpunkt, jetzt, nach_berlin

# Wie lange ein Eintrag auf "posting" stehen darf, bevor der nächste Lauf ihn
# als liegengeblieben ansieht. Großzügig gewählt: ein Bild-Upload zu einer
# lahmen API darf dauern, und ein zu früh zurückgeholter Eintrag wird doppelt
# gepostet — der teurere der beiden Fehler.
HAENGT_AB = timedelta(minutes=30)

# Wie lange vor dem Ablauf ein Zugang erneuert wird. Ein Token, das in fünf
# Minuten abläuft, ist für einen Lauf, der jetzt losschickt, schon abgelaufen
# — und der Fehler käme dann mitten aus dem Posten statt davor.
FRIST = timedelta(hours=6)

# So weit im Voraus wird geplant. Ohne Obergrenze läuft die Suche nach einem
# freien Platz endlos, wenn ein Kanal mehr fertige Varianten hat, als in
# absehbarer Zeit Plätze frei werden.
TAGE_VORAUS = 30

STANDARD_FENSTER = ("09:00", "21:00")
STANDARD_PRO_TAG = 3

# Die Wochentage, an denen gepostet wird. Montag ist 0, wie bei
# `date.weekday()` — die Zahlen kommen so aus der Maske und werden nirgends
# umgerechnet, weil jede Umrechnung eine Stelle ist, an der man sich um
# eins vertun kann.
WOCHENTAGE = (
    (0, "Mo"),
    (1, "Di"),
    (2, "Mi"),
    (3, "Do"),
    (4, "Fr"),
    (5, "Sa"),
    (6, "So"),
)


# --- Termine rechnen ---------------------------------------------------


def _fenster(einstellungen: dict) -> tuple[time, time]:
    roh = einstellungen.get("time_window") or list(STANDARD_FENSTER)
    try:
        von = time(*(int(t) for t in str(roh[0]).split(":")[:2]))
        bis = time(*(int(t) for t in str(roh[1]).split(":")[:2]))
    except (ValueError, IndexError, TypeError):
        von = time(9, 0)
        bis = time(21, 0)
    return von, bis


def _tage(einstellungen: dict) -> set[int]:
    """An welchen Wochentagen dieser Kanal postet.

    **Eine leere oder fehlende Angabe heißt: an allen.** Das ist wichtig für
    alles, was vor dem 04.09.2026 eingerichtet wurde — dort steht das Feld
    gar nicht, und ein leeres Set würde bedeuten, dass nie wieder etwas
    rausgeht. Ein stummer Stillstand wäre der teuerste Fehler dieser Datei.
    """
    roh = einstellungen.get("weekdays")
    if not roh:
        return {tag for tag, _ in WOCHENTAGE}
    gewaehlt = set()
    for wert in roh:
        try:
            zahl = int(wert)
        except (TypeError, ValueError):
            continue
        if 0 <= zahl <= 6:
            gewaehlt.add(zahl)
    # Steht dort nur Unsinn, gilt wieder "an allen Tagen". Sonst hörte der
    # Kanal wegen eines kaputten Werts auf zu posten, ohne dass es jemand
    # merkt.
    return gewaehlt or {tag for tag, _ in WOCHENTAGE}


def postet_am(tag: date, einstellungen: dict) -> bool:
    """Ob an diesem Wochentag überhaupt gepostet wird."""
    return tag.weekday() in _tage(einstellungen)


def slots(tag: date, einstellungen: dict) -> list:
    """Die Uhrzeiten eines Tages, an denen gepostet werden darf.

    Gleichmäßig vom Beginn des Fensters aus, nicht über das ganze Fenster
    gestreckt: bei drei Beiträgen zwischen 09:00 und 21:00 sind das 09:00,
    13:00 und 17:00. Der Rest des Fensters bleibt als Puffer, wenn ein Lauf
    einmal ausfällt und Nachzügler abgearbeitet werden.

    Bewusst ohne Zufall. Etwas Streuung sähe menschlicher aus, aber sie macht
    jede Prüfung zur Glücksfrage und jeden Fehlerbericht unwiederholbar.
    """
    # An einem Tag, der nicht gewählt ist, gibt es keine Termine. Die Prüfung
    # steht hier und nicht beim Aufrufer, damit sie niemand vergessen kann.
    if not postet_am(tag, einstellungen):
        return []

    von, bis = _fenster(einstellungen)
    # Fehlt der Wert oder ist er keine Zahl, gilt der Standard. Steht dort
    # eine Zahl außerhalb des Erlaubten, wird sie in die Grenzen gezogen und
    # nicht auf den Standard geworfen: wer 0 schreibt, meint erkennbar
    # "möglichst wenig" und nicht "gib mir drei". Über die Maske ist beides
    # ohnehin nicht erreichbar, dort steht min=1 und max=25.
    roh_anzahl = einstellungen.get("posts_per_day")
    try:
        anzahl = max(1, min(25, int(roh_anzahl)))
    except (TypeError, ValueError):
        anzahl = STANDARD_PRO_TAG

    beginn = berliner_zeitpunkt(tag, von)
    ende = berliner_zeitpunkt(tag, bis)
    spanne = (ende - beginn).total_seconds()
    if spanne <= 0:
        return [beginn]

    abstand = spanne / anzahl
    return [beginn + timedelta(seconds=abstand * i) for i in range(anzahl)]


# --- Einplanen ---------------------------------------------------------


def _offene(verbindung: CampaignChannel, typen: tuple[str, ...]) -> list[ContentItem]:
    """Freigegebene Varianten ohne Termin, die dieser Kanal auch annimmt."""
    return list(
        db.session.scalars(
            select(ContentItem)
            .where(
                ContentItem.campaign_channel_id == verbindung.id,
                ContentItem.status == "ready",
                ContentItem.geplant_fuer.is_(None),
                ContentItem.type.in_(typen),
            )
            .order_by(ContentItem.id)
        )
    )


def _belegt(verbindung: CampaignChannel) -> set:
    """Termine, die an diesem Kanal schon vergeben sind.

    Auch die von bereits geposteten Einträgen: sonst bekäme ein Tag, an dem
    schon drei Beiträge rausgingen, noch einmal drei dazu.
    """
    return {
        nach_berlin(wert)
        for wert in db.session.scalars(
            select(ContentItem.geplant_fuer).where(
                ContentItem.campaign_channel_id == verbindung.id,
                ContentItem.geplant_fuer.is_not(None),
            )
        )
    }


def einplanen() -> int:
    """Vergibt Termine an alles, was freigegeben ist und noch keinen hat.

    Nur aktive Kampagnen und eingeschaltete Kanäle. Läuft ohne Netz und darf
    beliebig oft laufen: was schon einen Termin hat, wird nicht angefasst.
    """
    nun = jetzt()
    vergeben = 0

    for verbindung in _verbindungen():
        adapter = kanal(verbindung.kanal.key)
        offen = _offene(verbindung, adapter.typen)
        if not offen:
            continue

        belegt = _belegt(verbindung)
        warteschlange = list(offen)

        for versatz in range(TAGE_VORAUS):
            if not warteschlange:
                break
            for zeitpunkt in slots(nun.date() + timedelta(days=versatz), verbindung.settings):
                if not warteschlange:
                    break
                if zeitpunkt <= nun or zeitpunkt in belegt:
                    continue
                eintrag = warteschlange.pop(0)
                eintrag.geplant_fuer = zeitpunkt
                belegt.add(zeitpunkt)
                vergeben += 1

    if vergeben:
        db.session.commit()
        current_app.logger.info("Zeitplan: %s Termin(e) vergeben", vergeben)
    return vergeben


def _verbindungen() -> list[CampaignChannel]:
    """Alle Kampagnenkanäle, die überhaupt posten dürfen."""
    return list(
        db.session.scalars(
            select(CampaignChannel)
            .join(Campaign, Campaign.id == CampaignChannel.campaign_id)
            .join(Channel, Channel.id == CampaignChannel.channel_id)
            .where(
                Campaign.status == "active",
                CampaignChannel.enabled.is_(True),
                Channel.key.in_(AKTIV),
            )
            .order_by(CampaignChannel.id)
        )
    )


# --- Posten ------------------------------------------------------------


def zurueckholen() -> int:
    """Setzt liegengebliebene `posting`-Einträge zurück auf `ready`.

    Das passiert, wenn ein Lauf zwischen Herausnehmen und Antwort abbricht.
    Ohne das bliebe der Eintrag für immer hängen, ohne dass irgendwo stünde,
    warum nichts mehr passiert.
    """
    grenze = jetzt() - HAENGT_AB
    haengende = list(
        db.session.scalars(
            select(ContentItem).where(
                ContentItem.status == "posting",
                ContentItem.posten_seit.is_not(None),
                ContentItem.posten_seit < grenze,
            )
        )
    )
    for eintrag in haengende:
        eintrag.status = "ready"
        eintrag.posten_seit = None
        current_app.logger.warning(
            "Zeitplan: Variante %s hing auf posting und ist wieder ready",
            eintrag.id,
        )
    if haengende:
        db.session.commit()
    return len(haengende)


def _faellige(verbindung: CampaignChannel) -> list[ContentItem]:
    """Was an diesem Kanal dran ist.

    `skip_locked`, damit zwei Läufe sich nicht gegenseitig blockieren und
    vor allem nicht denselben Eintrag nehmen. Der Timer sollte das ohnehin
    verhindern; sollte reicht hier nicht.
    """
    return list(
        db.session.scalars(
            select(ContentItem)
            .where(
                ContentItem.campaign_channel_id == verbindung.id,
                ContentItem.status == "ready",
                ContentItem.geplant_fuer.is_not(None),
                ContentItem.geplant_fuer <= jetzt(),
            )
            .order_by(ContentItem.geplant_fuer)
            .with_for_update(skip_locked=True)
        )
    )


def _konto(channel_id: int) -> Account | None:
    return db.session.scalars(
        select(Account).where(Account.channel_id == channel_id).order_by(Account.id)
    ).first()


def _zugang_sichern(konto: Account, adapter) -> None:
    """Erneuert den Zugang, wenn er bald abläuft.

    Wirft `KanalFehler`, wenn das nicht geht. Der Aufrufer überspringt den
    Kanal dann, statt jeden einzelnen Beitrag daran scheitern zu lassen:
    ein abgelaufenes Token ist kein Problem des Beitrags.

    Ein Konto ohne `expires_at` bleibt unangetastet. Das ist kein Versehen,
    sondern der Fall "die Plattform hat keinen Ablauf genannt" — dort
    ungefragt zu erneuern hieße, ein gültiges Token gegen ein neues zu
    tauschen, ohne zu wissen, ob es überhaupt eins gibt.
    """
    if konto.expires_at is None:
        return
    if nach_berlin(konto.expires_at) - jetzt() > FRIST:
        return

    felder = adapter.zugang_erneuern(konto.erneuerung)
    konto.zugang = felder["zugang"]
    konto.erneuerung = felder.get("erneuerung") or ""
    konto.expires_at = felder.get("laeuft_ab")
    db.session.commit()
    current_app.logger.info("Zeitplan: Zugang erneuert für %s", adapter.key)


def _ablage(verbindung: CampaignChannel) -> str | None:
    """Welches Board beziehungsweise welcher Standort dran ist.

    Reihum über die eingetragenen Kennungen, nach der Zahl der bisherigen
    Veröffentlichungen dieses Kampagnenkanals. Deterministisch, damit sich
    ein Ergebnis später nachvollziehen lässt, und gleichmäßig, damit nicht
    ein Board alles abbekommt.
    """
    kennungen = verbindung.settings.get("board_ids") or []
    if not kennungen:
        return None
    bisher = db.session.scalar(
        select(func.count(PostedItem.id)).where(
            PostedItem.campaign_channel_id == verbindung.id
        )
    ) or 0
    return kennungen[bisher % len(kennungen)]


def posten(trocken: bool = False) -> dict:
    """Schickt alles raus, was dran ist. Liefert eine Zählung.

    `trocken` sagt nur, was passieren würde, und fasst nichts an. Gedacht für
    den Blick vor dem ersten echten Lauf.
    """
    bericht = {
        "gepostet": 0,
        "gescheitert": 0,
        "uebersprungen": 0,
        "kein_konto": [],
        "zugang_abgelaufen": [],
    }

    for verbindung in _verbindungen():
        faellig = _faellige(verbindung)
        if not faellig:
            continue

        konto = _konto(verbindung.channel_id)
        if konto is None:
            # Nicht als Fehler zählen und nichts anfassen: der Kanal ist
            # schlicht noch nicht verbunden. Siehe Punkt 2 im Kopf.
            bericht["kein_konto"].append(verbindung.kanal.name)
            bericht["uebersprungen"] += len(faellig)
            continue

        adapter = kanal(verbindung.kanal.key)

        if not trocken:
            try:
                _zugang_sichern(konto, adapter)
            except Exception as fehler:  # noqa: BLE001
                # Wie bei "kein Konto": nicht auf die Beiträge brennen. Der
                # Zugang muss erneuert oder das Konto neu verbunden werden,
                # und das steht dann auf /zeitplan statt an jeder Variante.
                current_app.logger.warning(
                    "Zeitplan: Zugang %s nicht erneuerbar: %s",
                    verbindung.kanal.key,
                    fehler,
                )
                if verbindung.kanal.name not in bericht["zugang_abgelaufen"]:
                    bericht["zugang_abgelaufen"].append(verbindung.kanal.name)
                bericht["uebersprungen"] += len(faellig)
                continue

        for eintrag in faellig:
            if trocken:
                bericht["gepostet"] += 1
                continue
            if _einen_posten(eintrag, verbindung, adapter, konto):
                bericht["gepostet"] += 1
            else:
                bericht["gescheitert"] += 1

    return bericht


def _einen_posten(eintrag, verbindung, adapter, konto) -> bool:
    # Erst den Zustand festschreiben, dann erst rausgehen. Der commit hier
    # ist der Punkt, ab dem kein zweiter Lauf denselben Eintrag mehr nimmt.
    eintrag.status = "posting"
    eintrag.posten_seit = jetzt()
    db.session.commit()

    ablage = _ablage(verbindung)
    ziel = verbindung.kampagne.target_url

    try:
        antwort = adapter.veroeffentlichen(
            konto.zugang,
            titel=eintrag.title or "",
            beschreibung=eintrag.description or "",
            ziel_url=ziel,
            datei=eintrag.file_path,
            ablage_id=ablage,
            # Aus der Datenbank, nicht aus der Dateiendung geraten.
            typ=eintrag.type,
        )
    except Exception as fehler:  # noqa: BLE001
        # Breit gefangen, und das ist Absicht. Ein Adapter darf alles
        # werfen, was seine Bibliothek für richtig hält — ein einzelner
        # Fehlschlag darf aber nie den ganzen Lauf mitnehmen und die
        # übrigen Beiträge des Tages verschlucken. Der Grund landet als
        # Text an der Veröffentlichung, genau dafür gibt es die Spalte.
        grund = f"{type(fehler).__name__}: {fehler}"
        if isinstance(fehler, NotImplementedError):
            grund = "Der Adapter kann noch nicht posten."
        elif isinstance(fehler, KanalFehler):
            grund = str(fehler)

        db.session.add(
            PostedItem(
                content_item_id=eintrag.id,
                campaign_channel_id=verbindung.id,
                board_id=ablage,
                status="failed",
                fehler=grund[:2000],
            )
        )
        eintrag.status = "failed"
        eintrag.posten_seit = None
        db.session.commit()
        current_app.logger.warning(
            "Zeitplan: Variante %s gescheitert: %s", eintrag.id, grund
        )
        return False

    db.session.add(
        PostedItem(
            content_item_id=eintrag.id,
            campaign_channel_id=verbindung.id,
            platform_post_id=antwort.plattform_id,
            board_id=antwort.ablage_id or ablage,
            posted_at=antwort.zeitpunkt or jetzt(),
            status="posted",
        )
    )
    eintrag.status = "posted"
    eintrag.posten_seit = None
    db.session.commit()
    current_app.logger.info(
        "Zeitplan: Variante %s gepostet als %s", eintrag.id, antwort.plattform_id
    )
    return True


# --- Ein Lauf ----------------------------------------------------------


def lauf(trocken: bool = False) -> dict:
    """Aufräumen, einplanen, posten. Der Timer ruft genau das."""
    bericht = {"zurueckgeholt": 0, "eingeplant": 0}
    if not trocken:
        bericht["zurueckgeholt"] = zurueckholen()
        bericht["eingeplant"] = einplanen()
    bericht.update(posten(trocken=trocken))
    return bericht
