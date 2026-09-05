"""Die Seiten hinter der Anmeldung, dazu die öffentlichen Rechtstexte.

Der Zeitplan kommt als eigene Ansicht dazu.
"""

from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required, login_user
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash

from . import einstellungen, formular, ki
from .auth import MIN_PASSWORTLAENGE, passwort_setzen
from .extensions import db
from .kanaele import AKTIV, BEKANNT, ZUGANGSFELDER, kanal, rueckruf_adresse
from .models import (
    KAMPAGNE_STATUS,
    QUELLE,
    Account,
    Campaign,
    CampaignChannel,
    Channel,
    ContentItem,
    PostedItem,
)
from .rechtstexte import KATEGORIEN, rechtstext
from .zeit import jetzt, nach_berlin
from .zeitplan import WOCHENTAGE

haupt = Blueprint("haupt", __name__)


# Die beiden Adressen stehen ausdrücklich da und nicht als `/<kategorie>`.
# Ein solches Muster fängt sonst auch `/uebersicht` und `/abmelden` ab,
# sobald die Reihenfolge der Regeln sich einmal anders sortiert — ein Fehler,
# der erst auffällt, wenn eine bestehende Seite plötzlich 404 liefert.
@haupt.route("/impressum", endpoint="impressum")
@haupt.route("/datenschutz", endpoint="datenschutz")
def rechtstext_seite():
    """Impressum und Datenschutz, öffentlich und ohne Anmeldung.

    Öffentlich, weil beides von außen erreichbar sein muss: das Impressum
    aus rechtlichen Gründen, die Datenschutzerklärung zusätzlich, weil
    Pinterest beim Anlegen einer App eine erreichbare Adresse dafür
    verlangt.
    """
    kategorie = request.path.lstrip("/")
    if kategorie not in KATEGORIEN:
        abort(404)
    return render_template(
        "rechtstext.html",
        titel=KATEGORIEN[kategorie],
        inhalt=rechtstext(kategorie),
    )


@haupt.route("/uebersicht")
@login_required
def uebersicht():
    kampagnen = db.session.scalars(
        select(Campaign).order_by(Campaign.status, Campaign.name)
    ).all()

    # Ein Zähler je Kampagne in einer Abfrage statt einer Abfrage je
    # Kampagne. Bei fünf Kampagnen egal, bei fünfzig nicht mehr.
    gepostet = dict(
        db.session.execute(
            select(Campaign.id, func.count(PostedItem.id))
            .select_from(Campaign)
            # Die Bedingungen stehen ausgeschrieben da. Ohne sie sucht
            # SQLAlchemy sich den Weg selbst, und zwischen content_items und
            # posted_items gibt es zwei Fremdschlüssel — dann wird es
            # zufällig, welcher genommen wird.
            .outerjoin(
                CampaignChannel, CampaignChannel.campaign_id == Campaign.id
            )
            .outerjoin(
                ContentItem,
                ContentItem.campaign_channel_id == CampaignChannel.id,
            )
            .outerjoin(PostedItem, PostedItem.content_item_id == ContentItem.id)
            .group_by(Campaign.id)
        ).all()
    )

    # Drei Zustände, nicht zwei. Ein Kanal kann einen fertigen Adapter haben
    # und trotzdem nicht benutzbar sein — bei Google Business Profile fehlt
    # die Freischaltung durch Google, nicht der Code.
    kanaele = []
    for eintrag in db.session.scalars(select(Channel).order_by(Channel.id)):
        if eintrag.key in AKTIV:
            zustand, hinweis = "an", ""
        elif eintrag.key in BEKANNT:
            zustand, hinweis = "wartet", "Zugang fehlt"
        else:
            zustand, hinweis = "aus", "vorbereitet"
        kanaele.append({"name": eintrag.name, "zustand": zustand, "hinweis": hinweis})

    # Wo eine Kampagne läuft, gehört auf die Übersicht. Der Ziel-Link allein
    # sagt nur, wohin sie führt, nicht wo sie stattfindet — und genau das
    # ist die Frage, die man sich beim Draufschauen stellt.
    laeuft_auf: dict[int, list[str]] = {}
    for verbindung in db.session.scalars(select(CampaignChannel)):
        laeuft_auf.setdefault(verbindung.campaign_id, []).append(
            verbindung.kanal.name
        )

    return render_template(
        "uebersicht.html",
        kampagnen=kampagnen,
        gepostet=gepostet,
        kanaele=kanaele,
        laeuft_auf=laeuft_auf,
        status_werte=KAMPAGNE_STATUS,
    )


@haupt.route("/kampagnen/<int:kampagne_id>/status", methods=["POST"])
@login_required
def kampagne_status(kampagne_id: int):
    """Nur den Status umstellen, von der Übersicht aus.

    Eigene Adresse und nicht `kampagne_bearbeiten`: dort gehen Name,
    Ziel-Link und Briefing mit, und ein Formular, das nur den Status zeigt,
    würde die drei beim Speichern leeren.
    """
    eintrag = _kampagne_holen(kampagne_id)
    try:
        eintrag.status = formular.aus_auswahl(
            request.form.get("status"), KAMPAGNE_STATUS, "Der Status"
        )
    except formular.Ungueltig as fehler:
        flash(str(fehler), "fehler")
        return redirect(url_for("haupt.uebersicht"))

    db.session.commit()
    flash(f"„{eintrag.name}“ steht jetzt auf {eintrag.status}.", "erfolg")
    return redirect(url_for("haupt.uebersicht"))


# --- Kampagnen ---------------------------------------------------------


def _kampagne_holen(kampagne_id: int) -> Campaign:
    kampagne = db.session.get(Campaign, kampagne_id)
    if kampagne is None:
        abort(404)
    return kampagne


@haupt.route("/kampagnen/neu", methods=["GET", "POST"])
@login_required
def kampagne_neu():
    if request.method == "POST":
        try:
            kampagne = Campaign(
                name=formular.text(
                    request.form.get("name"), "Der Name", max_laenge=255
                ),
                target_url=formular.ziel_adresse(request.form.get("target_url")),
                briefing=formular.text(
                    request.form.get("briefing"),
                    "Das Briefing",
                    max_laenge=4000,
                    pflicht=False,
                )
                or None,
                menschen_erlaubt=request.form.get("menschen") == "ja",
                status=formular.aus_auswahl(
                    request.form.get("status"), KAMPAGNE_STATUS, "Der Status"
                ),
            )
        except formular.Ungueltig as fehler:
            flash(str(fehler), "fehler")
            # Die Eingaben zurückgeben, damit nichts noch einmal getippt
            # werden muss. Ein leeres Formular nach einem Tippfehler ist der
            # sicherste Weg, jemanden zu vergraulen.
            return render_template("kampagne_neu.html", werte=request.form), 400

        db.session.add(kampagne)
        db.session.commit()
        flash(f"Kampagne „{kampagne.name}“ angelegt.", "erfolg")
        return redirect(url_for("haupt.kampagne", kampagne_id=kampagne.id))

    return render_template("kampagne_neu.html", werte={"status": "draft"})


@haupt.route("/kampagnen/<int:kampagne_id>")
@login_required
def kampagne(kampagne_id: int):
    eintrag = _kampagne_holen(kampagne_id)

    verknuepft = {k.channel_id: k for k in eintrag.kanaele}
    zeilen = []
    for eintrag_kanal in db.session.scalars(select(Channel).order_by(Channel.id)):
        adapter = kanal(eintrag_kanal.key) if eintrag_kanal.key in BEKANNT else None
        verbindung = verknuepft.get(eintrag_kanal.id)
        einstellungen = (verbindung.settings if verbindung else {}) or {}
        verbunden = bool(db.session.scalar(
            select(func.count(Account.id))
            .where(Account.channel_id == eintrag_kanal.id)
        ))

        # Die Ablagen des verbundenen Kontos, damit man sie auswählen kann
        # statt Kennungen abzutippen. Kostet einen Aufruf bei der Plattform
        # und kann scheitern — dann bleibt es beim Textfeld, statt dass die
        # ganze Seite stehenbleibt.
        ablagen = None
        ablagen_fehler = ""
        if verbunden and adapter is not None and adapter.unterstuetzt_ablagen:
            konto = db.session.scalars(
                select(Account)
                .where(Account.channel_id == eintrag_kanal.id)
                .order_by(Account.id)
            ).first()
            try:
                ablagen = adapter.ablagen(konto.zugang)
            except Exception as fehler:  # noqa: BLE001
                current_app.logger.warning(
                    "%s abrufen gescheitert: %s", adapter.ablage_mehrzahl, fehler
                )
                ablagen_fehler = str(fehler)

        gewaehlt = einstellungen.get("board_ids") or []

        # Der Zustand in einem Wort, damit die Tabelle ihn nur anzeigen und
        # nicht selbst zusammenreimen muss. Die Reihenfolge ist die des
        # Weges: erst braucht es einen Adapter, dann ein Konto, dann muss
        # der Kanal an dieser Kampagne eingeschaltet sein, und zuletzt
        # braucht er ein Ziel.
        if eintrag_kanal.key not in BEKANNT:
            zustand, hinweis = "vorbereitet", "Für diesen Kanal gibt es noch keinen Adapter."
        elif eintrag_kanal.key not in AKTIV:
            zustand, hinweis = "gesperrt", "Der Zugang zu dieser Plattform ist noch nicht freigeschaltet."
        elif not verbunden:
            zustand, hinweis = "kein Konto", "Unter Einstellungen verbinden. Ohne Konto überspringt der Zeitplan diesen Kanal."
        elif not verbindung:
            zustand, hinweis = "aus", "Für diese Kampagne noch nicht eingeschaltet."
        elif adapter is not None and adapter.unterstuetzt_ablagen and not gewaehlt:
            # **Kein „läuft".** Ohne Ziel kann der Kanal nichts posten, und
            # das ist der Zustand, in dem man am ehesten glaubt, es liefe.
            zustand = f"{adapter.ablage_bezeichnung} fehlt"
            hinweis = (
                f"Unten {adapter.ablage_bezeichnung.lower()} auswählen, sonst "
                "geht kein Beitrag raus."
            )
        else:
            zustand, hinweis = "läuft", ""

        # Wie viele Varianten es schon gibt, und wie viele davon der
        # Zeitplan nehmen darf. Ohne die zweite Zahl sieht ein Kanal voll
        # aus, obwohl nichts freigegeben ist und deshalb nichts rausgeht.
        fertig = bereit = 0
        if verbindung:
            fertig = db.session.scalar(
                select(func.count(ContentItem.id))
                .where(ContentItem.campaign_channel_id == verbindung.id)
            ) or 0
            bereit = db.session.scalar(
                select(func.count(ContentItem.id))
                .where(
                    ContentItem.campaign_channel_id == verbindung.id,
                    ContentItem.status == "ready",
                )
            ) or 0

        zeilen.append({
            "kanal": eintrag_kanal,
            "verfuegbar": eintrag_kanal.key in AKTIV,
            "adapter": adapter,
            "verbindung": verbindung,
            "einstellungen": einstellungen,
            "verbunden": verbunden,
            "ablagen": ablagen,
            "ablagen_fehler": ablagen_fehler,
            "gewaehlt": gewaehlt,
            "zustand": zustand,
            "hinweis": hinweis,
            "varianten": fertig,
            "freigegeben": bereit,
        })

    return render_template(
        "kampagne.html",
        kampagne=eintrag,
        zeilen=zeilen,
        status_werte=KAMPAGNE_STATUS,
        quellen=QUELLE,
        wochentage=WOCHENTAGE,
        loeschbar=_ist_loeschbar(eintrag),
    )


def _ist_loeschbar(eintrag: Campaign) -> bool:
    """Ob es zu dieser Kampagne schon Veröffentlichungen gibt.

    Wird nur für die Anzeige gebraucht: der eigentliche Schutz sitzt in der
    Datenbank, siehe den Docstring von PostedItem. Die Abfrage hier sorgt
    dafür, dass gar nicht erst ein Knopf angeboten wird, der scheitern muss.
    """
    return not db.session.scalar(
        select(func.count(PostedItem.id))
        .select_from(PostedItem)
        .join(
            CampaignChannel,
            CampaignChannel.id == PostedItem.campaign_channel_id,
        )
        .where(CampaignChannel.campaign_id == eintrag.id)
    )


@haupt.route("/kampagnen/<int:kampagne_id>/bearbeiten", methods=["POST"])
@login_required
def kampagne_bearbeiten(kampagne_id: int):
    eintrag = _kampagne_holen(kampagne_id)
    try:
        eintrag.name = formular.text(
            request.form.get("name"), "Der Name", max_laenge=255
        )
        eintrag.target_url = formular.ziel_adresse(request.form.get("target_url"))
        eintrag.briefing = formular.text(
            request.form.get("briefing"),
            "Das Briefing",
            max_laenge=4000,
            pflicht=False,
        ) or None
        eintrag.menschen_erlaubt = request.form.get("menschen") == "ja"
        eintrag.status = formular.aus_auswahl(
            request.form.get("status"), KAMPAGNE_STATUS, "Der Status"
        )
    except formular.Ungueltig as fehler:
        db.session.rollback()
        flash(str(fehler), "fehler")
        return redirect(url_for("haupt.kampagne", kampagne_id=kampagne_id))

    db.session.commit()
    flash("Gespeichert.", "erfolg")
    return redirect(url_for("haupt.kampagne", kampagne_id=kampagne_id))


@haupt.route("/kampagnen/<int:kampagne_id>/loeschen", methods=["POST"])
@login_required
def kampagne_loeschen(kampagne_id: int):
    eintrag = _kampagne_holen(kampagne_id)
    name = eintrag.name
    try:
        db.session.delete(eintrag)
        db.session.commit()
    except IntegrityError:
        # Die Datenbank hält die Veröffentlichungen fest. Kann nur passieren,
        # wenn zwischen dem Aufbau der Seite und dem Klick etwas gepostet
        # wurde — dann ist die Meldung wichtiger als der Knopf.
        db.session.rollback()
        flash(
            "Zu dieser Kampagne gibt es schon Veröffentlichungen. Sie lässt "
            "sich nicht löschen, ohne die Auswertung mitzunehmen. Setz sie "
            "stattdessen auf „paused“.",
            "fehler",
        )
        return redirect(url_for("haupt.kampagne", kampagne_id=kampagne_id))

    flash(f"Kampagne „{name}“ gelöscht.", "erfolg")
    return redirect(url_for("haupt.uebersicht"))


@haupt.route("/kampagnen/<int:kampagne_id>/kanal/<int:channel_id>", methods=["POST"])
@login_required
def kampagne_kanal(kampagne_id: int, channel_id: int):
    """Einen Kanal für diese Kampagne einrichten oder abschalten."""
    eintrag = _kampagne_holen(kampagne_id)
    kanal_eintrag = db.session.get(Channel, channel_id)
    if kanal_eintrag is None:
        abort(404)
    if kanal_eintrag.key not in AKTIV:
        # Nicht nur die Oberfläche fragen. Wer das Formular nachbaut, käme
        # sonst an einem Kanal vorbei, für den es keinen Zugang gibt.
        abort(400, "Dieser Kanal ist noch nicht benutzbar.")

    verbindung = db.session.scalar(
        select(CampaignChannel).where(
            CampaignChannel.campaign_id == eintrag.id,
            CampaignChannel.channel_id == channel_id,
        )
    )

    if request.form.get("aktion") == "entfernen":
        if verbindung is not None:
            db.session.delete(verbindung)
            db.session.commit()
        flash(f"{kanal_eintrag.name} ist für diese Kampagne aus.", "erfolg")
        return redirect(url_for("haupt.kampagne", kampagne_id=kampagne_id))

    adapter = kanal(kanal_eintrag.key)
    try:
        einstellungen = {
            "posts_per_day": formular.ganze_zahl(
                request.form.get("posts_per_day"),
                "Beiträge pro Tag",
                min_wert=1,
                max_wert=25,
            ),
            "time_window": formular.zeitfenster(
                request.form.get("zeit_von"), request.form.get("zeit_bis")
            ),
            "weekdays": formular.wochentage(request.form.getlist("weekdays")),
        }
        if adapter.unterstuetzt_ablagen:
            if request.form.get("ablagen_gewaehlt") == "ja":
                # Die Auswahl aus Kästchen. `getlist` und nicht `get`: ohne
                # das käme nur das erste Häkchen an, und wer drei Seiten
                # anhakt, bespielt am Ende eine.
                einstellungen["board_ids"] = formular.kennungen(
                    "\n".join(request.form.getlist("board_ids"))
                )
            else:
                # Das Textfeld. Steht noch da, solange kein Konto verbunden
                # ist oder die Liste sich nicht abrufen ließ — dann darf ein
                # Speichern die von Hand eingetragenen Kennungen nicht
                # wegwerfen.
                einstellungen["board_ids"] = formular.kennungen(
                    request.form.get("board_ids")
                )
        quelle = formular.aus_auswahl(
            request.form.get("content_source"), QUELLE, "Die Herkunft der Inhalte"
        )
    except formular.Ungueltig as fehler:
        flash(str(fehler), "fehler")
        return redirect(url_for("haupt.kampagne", kampagne_id=kampagne_id))

    neu = verbindung is None
    if neu:
        verbindung = CampaignChannel(
            campaign_id=eintrag.id, channel_id=channel_id
        )
        db.session.add(verbindung)

    # **Ändert sich der Takt, gelten die alten Termine nicht mehr.**
    # `einplanen` fasst nur an, was noch keinen Termin hat — sonst würde ein
    # Lauf ständig alles umsortieren. Für schon vergebene Termine hieß das
    # aber: wer das Zeitfenster verschiebt, ändert nichts, und der Beitrag
    # geht weiter zur alten Zeit raus. Also werden sie hier freigegeben und
    # gleich neu vergeben.
    #
    # Nur bei den drei Werten, die den Takt bestimmen. Wer bloß eine Seite
    # dazuwählt, soll seine Termine behalten.
    alt_werte = (verbindung.settings or {}) if not neu else {}
    takt_geaendert = any(
        alt_werte.get(feld) != einstellungen.get(feld)
        for feld in ("posts_per_day", "time_window", "weekdays")
    )

    verbindung.enabled = True
    verbindung.content_source = quelle
    verbindung.settings = einstellungen
    db.session.commit()

    neu_vergeben = 0
    if takt_geaendert and not neu:
        # `posting` bleibt unangetastet: dieser Eintrag ist gerade unterwegs
        # zur Plattform, und ihm den Termin wegzunehmen hieße, ihn ein
        # zweites Mal einzuplanen.
        offen = db.session.scalars(
            select(ContentItem).where(
                ContentItem.campaign_channel_id == verbindung.id,
                ContentItem.status == "ready",
                ContentItem.geplant_fuer.is_not(None),
            )
        ).all()
        for inhalt in offen:
            inhalt.geplant_fuer = None
        if offen:
            db.session.commit()
        neu_vergeben = len(offen)

    # **Immer einplanen, nicht nur bei geändertem Takt.** `einplanen` fasst
    # nur an, was keinen Termin hat, ist also billig und harmlos — und wer
    # gerade gespeichert hat, will das Ergebnis sehen und nicht bis zum
    # nächsten Timer-Lauf warten. Es rechnet nur mit Zeiten und der
    # Datenbank, geht nicht ins Netz und darf deshalb hier stehen.
    from .zeitplan import einplanen

    einplanen()

    # **Nach dem Einschalten geht es zu den Varianten und nicht zurück auf
    # die Kampagne.** Ein frisch eingeschalteter Kanal hat nichts zu posten;
    # der nächste Schritt ist immer derselbe, und ihn selbst suchen zu
    # müssen war der Bruch im Ablauf. Beim bloßen Ändern bleibt man dagegen,
    # wo man war — dort wollte man ja etwas anderes.
    if neu:
        flash(
            f"{kanal_eintrag.name} eingeschaltet. Jetzt fehlen noch Varianten.",
            "erfolg",
        )
        return redirect(
            url_for("haupt.varianten", verbindung_id=verbindung.id)
        )

    if neu_vergeben:
        flash(
            f"{kanal_eintrag.name} gespeichert. {neu_vergeben} Termin(e) neu "
            "vergeben, weil sich der Takt geändert hat.",
            "erfolg",
        )
    else:
        flash(f"{kanal_eintrag.name} gespeichert.", "erfolg")
    return redirect(url_for("haupt.kampagne", kampagne_id=kampagne_id))


# --- Varianten ---------------------------------------------------------


def _verbindung_holen(verbindung_id: int) -> CampaignChannel:
    verbindung = db.session.get(CampaignChannel, verbindung_id)
    if verbindung is None:
        abort(404)
    return verbindung


def _gruppen(verbindung: CampaignChannel, adapter) -> list[dict]:
    """Varianten nach `variant_group` gebündelt, neueste Gruppe zuerst.

    Zusammen erzeugte Varianten werden gegeneinander gemessen, also gehören
    sie auch in der Ansicht zusammen. Eine einzeln hochgeladene Variante hat
    keine Gruppe und steht für sich.
    """
    inhalte = db.session.scalars(
        select(ContentItem)
        .where(ContentItem.campaign_channel_id == verbindung.id)
        .order_by(ContentItem.created_at.desc(), ContentItem.id.desc())
    ).all()

    # Ob eine Variante schon draußen ist, entscheidet über den Löschen-Knopf.
    # Eine Abfrage für alle statt einer je Variante.
    gepostet = set(
        db.session.scalars(
            select(PostedItem.content_item_id).where(
                PostedItem.campaign_channel_id == verbindung.id
            )
        ).all()
    )

    reihenfolge: list[str] = []
    gebuendelt: dict[str, list] = {}
    for inhalt in inhalte:
        schluessel = inhalt.variant_group or f"einzeln-{inhalt.id}"
        if schluessel not in gebuendelt:
            gebuendelt[schluessel] = []
            reihenfolge.append(schluessel)
        gebuendelt[schluessel].append({
            "inhalt": inhalt,
            "loeschbar": inhalt.id not in gepostet,
            # Ein Pin braucht ein Bild. Eine Variante ohne wird gar nicht
            # erst eingeplant — und das muss man sehen, bevor man sie
            # freigibt und sich wundert, dass nie etwas passiert.
            "passt": inhalt.type in adapter.typen,
        })

    return [
        {
            "schluessel": schluessel,
            "varianten": gebuendelt[schluessel],
            "erzeugt_am": gebuendelt[schluessel][0]["inhalt"].created_at,
            # Die Anfrage steht an jeder Variante der Gruppe gleich. Einmal
            # anzeigen reicht, sonst steht derselbe Absatz achtmal da.
            "prompt": gebuendelt[schluessel][0]["inhalt"].prompt,
        }
        for schluessel in reihenfolge
    ]


@haupt.route("/kanal/<int:verbindung_id>/varianten")
@login_required
def varianten(verbindung_id: int):
    verbindung = _verbindung_holen(verbindung_id)
    adapter = kanal(verbindung.kanal.key)
    return render_template(
        "varianten.html",
        verbindung=verbindung,
        kampagne=verbindung.kampagne,
        adapter=adapter,
        gruppen=_gruppen(verbindung, adapter),
        max_varianten=ki.MAX_VARIANTEN,
        # Vorbelegt mit dem, was am Kanal eingestellt ist. Dort stehen drei
        # pro Tag und hier trotzdem eine feste 3 -- das war der Moment, in
        # dem die Zahl von vorhin verschwunden schien.
        vorschlag_anzahl=min(
            ki.MAX_VARIANTEN,
            max(1, int((verbindung.settings or {}).get("posts_per_day", 3) or 3)),
        ),
        kann_erzeugen=bool(einstellungen.gemini_herkunft()),
        # Ausgeschrieben, weil "image, video" vor dem Nutzer nichts zu suchen
        # hat. Die Liste kommt vom Kanal, nicht aus dem Template.
        typen_klartext=", ".join(
            {"image": "Bilder", "video": "Videos", "text": "reinen Text"}.get(t, t)
            for t in adapter.typen
        ),
    )


@haupt.route("/kanal/<int:verbindung_id>/varianten/erzeugen", methods=["POST"])
@login_required
def varianten_erzeugen(verbindung_id: int):
    verbindung = _verbindung_holen(verbindung_id)
    kampagne_eintrag = verbindung.kampagne
    adapter = kanal(verbindung.kanal.key)

    try:
        anzahl = formular.ganze_zahl(
            request.form.get("anzahl"),
            "Die Anzahl",
            min_wert=ki.MIN_VARIANTEN,
            max_wert=ki.MAX_VARIANTEN,
        )
    except formular.Ungueltig as fehler:
        flash(str(fehler), "fehler")
        return redirect(url_for("haupt.varianten", verbindung_id=verbindung_id))

    mit_bild = request.form.get("mit_bild") == "ja"

    anfrage = ki.anfrage_bauen(
        kampagne_name=kampagne_eintrag.name,
        ziel_url=kampagne_eintrag.target_url,
        briefing=kampagne_eintrag.briefing,
        kanal_name=verbindung.kanal.name,
        max_beschreibung=adapter.max_beschreibung,
        anzahl=anzahl,
        affiliate_erlaubt=adapter.affiliate_erlaubt,
        link_im_text=adapter.link_im_text,
        link_klickbar=adapter.link_klickbar,
    )

    try:
        vorschlaege = ki.texte_erzeugen(
            anfrage, anzahl=anzahl, max_beschreibung=adapter.max_beschreibung
        )
    except ki.KIFehler as fehler:
        current_app.logger.warning("Varianten erzeugen gescheitert: %s", fehler)
        flash(str(fehler), "fehler")
        return redirect(url_for("haupt.varianten", verbindung_id=verbindung_id))

    gruppe = ki.variantengruppe()
    bilder_gescheitert = 0

    for vorschlag in vorschlaege:
        pfad = None
        if mit_bild:
            # Ein gescheitertes Bild darf den ganzen Schwung nicht kosten.
            # Der Text ist das Teure am Vorgang, das Bild lässt sich einzeln
            # nachreichen.
            try:
                # **Eine eigene Anfrage, nicht die für den Text.** Bis zum
                # 04.09.2026 ging hier der komplette Text-Prompt an das
                # Bildmodell — "Du schreibst 3 Vorschläge für einen Beitrag
                # auf Facebook, Titel höchstens 100 Zeichen…" — und deshalb
                # kam nie ein Bild zurück. Siehe `ki.bild_anfrage_bauen`.
                pfad = ki.bild_ablegen(
                    ki.bild_erzeugen(
                        ki.bild_anfrage_bauen(
                            titel=vorschlag.titel,
                            beschreibung=vorschlag.beschreibung,
                            briefing=kampagne_eintrag.briefing,
                            format=adapter.bild_format,
                        ),
                        adapter.bild_format,
                    )
                )
            except ki.KIFehler as fehler:
                current_app.logger.warning("Bild gescheitert: %s", fehler)
                bilder_gescheitert += 1

        db.session.add(
            ContentItem(
                campaign_channel_id=verbindung.id,
                type="image" if pfad else "text",
                title=vorschlag.titel,
                description=vorschlag.beschreibung,
                file_path=pfad,
                variant_group=gruppe,
                quelle="ai_generated",
                prompt=anfrage,
                status="draft",
            )
        )

    db.session.commit()

    flash(f"{len(vorschlaege)} Variante(n) erzeugt.", "erfolg")
    if bilder_gescheitert:
        flash(
            f"Bei {bilder_gescheitert} davon hat das Bild nicht geklappt. "
            "Der Text steht trotzdem.",
            "fehler",
        )
    return redirect(url_for("haupt.varianten", verbindung_id=verbindung_id))


def _datei_wegraeumen(pfad: str) -> None:
    """Löscht eine Datei unterhalb des Upload-Ordners.

    Der Pfad kommt aus der Datenbank und wird trotzdem geprüft: er wird an
    den Upload-Ordner gehängt, und ein `..` darin zeigte sonst irgendwohin.
    Dass dort heute nur eigene Werte stehen, ist kein Grund, es zu glauben.
    """
    wurzel = Path(current_app.config["UPLOAD_ORDNER"]).resolve()
    ziel = (wurzel / pfad).resolve()
    if not ziel.is_relative_to(wurzel):
        current_app.logger.warning("Pfad zeigt aus dem Ordner heraus: %s", pfad)
        return
    try:
        ziel.unlink()
    except OSError as fehler:
        # Kein Grund, den Nutzer zu behelligen: die Variante ist weg, nur
        # ein paar Bytes bleiben liegen.
        current_app.logger.warning("Datei nicht gelöscht: %s (%s)", pfad, fehler)


@haupt.route("/kanal/<int:verbindung_id>/varianten/hochladen", methods=["POST"])
@login_required
def variante_hochladen(verbindung_id: int):
    """Eine eigene Datei als neue Variante.

    Der Weg für Material, das nicht hier entsteht — ein Video aus der
    Gemini-App zum Beispiel. Der Text lässt sich danach von pinario erzeugen
    oder selbst schreiben; erzeugt wird hier nichts, hochgeladen wird nur.
    """
    verbindung = _verbindung_holen(verbindung_id)
    kampagne_eintrag = verbindung.kampagne
    adapter = kanal(verbindung.kanal.key)
    ziel = url_for("haupt.varianten", verbindung_id=verbindung_id)

    try:
        inhalt, endung, typ = formular.datei_pruefen(
            request.files.get("datei")
        )
        titel = formular.text(
            request.form.get("titel"), "Der Titel", max_laenge=255, pflicht=False
        )
        beschreibung = formular.text(
            request.form.get("beschreibung"),
            "Die Beschreibung",
            max_laenge=4000,
            pflicht=False,
        )
    except formular.Ungueltig as fehler:
        flash(str(fehler), "fehler")
        return redirect(ziel)

    # **Vor dem Speichern prüfen, ob der Kanal das überhaupt annimmt.** Sonst
    # liegt die Datei da, die Variante sieht fertig aus, und der Zeitplan
    # überspringt sie stillschweigend — oder schlimmer, versucht es und
    # brennt einen Fehlschlag in die Messreihe.
    if typ not in adapter.typen:
        wort = {"image": "Bild", "video": "Video", "text": "reinen Text"}
        angenommen = ", ".join(wort.get(t, t) for t in adapter.typen)
        flash(
            f"{verbindung.kanal.name} nimmt hier kein {wort.get(typ, typ)}. "
            f"Angenommen wird: {angenommen}.",
            "fehler",
        )
        return redirect(ziel)

    # Wie viele Textvorschläge zu dieser Datei entstehen sollen. 0 heißt:
    # nur ablegen, Text kommt von Hand.
    try:
        vorschlaege = formular.ganze_zahl(
            request.form.get("anzahl") or "0",
            "Die Anzahl der Textvorschläge",
            min_wert=0,
            max_wert=ki.MAX_VARIANTEN,
        )
    except formular.Ungueltig as fehler:
        flash(str(fehler), "fehler")
        return redirect(ziel)

    pfad = ki.datei_ablegen(inhalt, endung)
    gruppe = ki.variantengruppe()

    if not vorschlaege:
        db.session.add(
            ContentItem(
                campaign_channel_id=verbindung.id,
                type=typ,
                title=titel or None,
                description=beschreibung or None,
                file_path=pfad,
                variant_group=gruppe,
                quelle="upload",
                status="draft",
            )
        )
        db.session.commit()
        current_app.logger.info(
            "Variante hochgeladen: %s für %s", typ, verbindung.kanal.key
        )
        flash(
            "Hochgeladen. Titel und Beschreibung lassen sich unten bearbeiten; "
            "freigegeben wird von Hand.",
            "erfolg",
        )
        return redirect(ziel)

    # **Der Text entsteht zur Datei, nicht neben ihr.** Bei einem Bild geht
    # es mit an das Modell; bei einem Video nicht, dort bleibt nur das
    # Briefing. Das steht ausdrücklich in der Meldung, sonst wundert man
    # sich, warum der Text zum Video allgemeiner ausfällt.
    anfrage = ki.anfrage_bauen(
        kampagne_name=kampagne_eintrag.name,
        ziel_url=kampagne_eintrag.target_url,
        briefing=kampagne_eintrag.briefing,
        kanal_name=verbindung.kanal.name,
        max_beschreibung=adapter.max_beschreibung,
        anzahl=vorschlaege,
        affiliate_erlaubt=adapter.affiliate_erlaubt,
        link_im_text=adapter.link_im_text,
        link_klickbar=adapter.link_klickbar,
        zu_vorlage=typ == "image",
    )

    try:
        varianten = ki.texte_erzeugen(
            anfrage,
            anzahl=vorschlaege,
            max_beschreibung=adapter.max_beschreibung,
            bild=inhalt if typ == "image" else None,
        )
    except ki.KIFehler as fehler:
        # Die Datei bleibt liegen und bekommt eine Variante ohne Text. Sie
        # wegzuwerfen wäre die teurere Entscheidung: hochgeladen ist sie ja
        # schon, und der Text lässt sich nachreichen.
        current_app.logger.warning("Text zur Datei gescheitert: %s", fehler)
        db.session.add(
            ContentItem(
                campaign_channel_id=verbindung.id,
                type=typ,
                title=titel or None,
                description=beschreibung or None,
                file_path=pfad,
                variant_group=gruppe,
                quelle="upload",
                status="draft",
            )
        )
        db.session.commit()
        flash(
            f"Hochgeladen, aber der Text ist gescheitert: {fehler} Die Datei "
            "liegt als Variante ohne Text da.",
            "fehler",
        )
        return redirect(ziel)

    for variante in varianten:
        db.session.add(
            ContentItem(
                campaign_channel_id=verbindung.id,
                type=typ,
                title=variante.titel,
                description=variante.beschreibung,
                # **Dieselbe Datei an allen.** Sie sollen sich im Text
                # unterscheiden und nicht im Bild — sonst misst die Auswertung
                # später zwei Dinge auf einmal.
                file_path=pfad,
                variant_group=gruppe,
                quelle="upload",
                prompt=anfrage,
                status="draft",
            )
        )
    db.session.commit()
    current_app.logger.info(
        "Variante hochgeladen: %s für %s, %s Textvorschläge",
        typ, verbindung.kanal.key, len(varianten),
    )
    flash(
        f"Hochgeladen, {len(varianten)} Textvorschläge dazu erzeugt"
        + (
            " — zum Bild selbst."
            if typ == "image"
            else ", allein nach dem Briefing: ein Video sieht das Modell nicht an."
        )
        + " Freigegeben wird von Hand.",
        "erfolg",
    )
    return redirect(ziel)


@haupt.route(
    "/kanal/<int:verbindung_id>/varianten/<int:inhalt_id>", methods=["POST"]
)
@login_required
def variante_aendern(verbindung_id: int, inhalt_id: int):
    verbindung = _verbindung_holen(verbindung_id)
    inhalt = db.session.get(ContentItem, inhalt_id)
    # Die Zugehörigkeit wird geprüft, nicht angenommen. Sonst ließe sich über
    # eine fremde Kennung eine Variante einer anderen Kampagne ändern.
    if inhalt is None or inhalt.campaign_channel_id != verbindung.id:
        abort(404)

    ziel = url_for("haupt.varianten", verbindung_id=verbindung_id)
    aktion = request.form.get("aktion", "speichern")

    if aktion == "loeschen":
        # Den Pfad vorher merken: nach dem commit ist das Objekt weg.
        datei = inhalt.file_path
        try:
            db.session.delete(inhalt)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash(
                "Diese Variante ist schon veröffentlicht. Sie lässt sich "
                "nicht löschen, ohne die Auswertung mitzunehmen.",
                "fehler",
            )
            return redirect(ziel)

        # Erst die Zeile, dann die Datei. Andersherum stünde bei einem
        # Fehler eine Variante ohne Bild da, und das sähe aus wie ein
        # gescheitertes Erzeugen.
        #
        # Sicher ist das, weil eine **veröffentlichte** Variante sich gar
        # nicht löschen lässt — die Datenbank weist es ab, siehe oben. Es
        # kann also kein Bild verschwinden, das ein Kanal noch abholt.
        if datei:
            _datei_wegraeumen(datei)

        flash("Variante gelöscht.", "erfolg")
        return redirect(ziel)

    if aktion == "freigeben":
        inhalt.status = "ready"
        db.session.commit()
        # **Nicht mehr versprechen, als der nächste Schritt hält.** Termine
        # vergibt der Zeitplan nur für Kampagnen auf `active`; steht die
        # Kampagne auf `draft`, passiert nach dem Freigeben gar nichts, und
        # "der Zeitplan nimmt sie mit" schickt einen auf die Suche.
        if verbindung.kampagne.status == "active":
            flash("Variante freigegeben. Der Zeitplan nimmt sie mit.", "erfolg")
        else:
            flash(
                "Variante freigegeben. Sie bekommt einen Termin, sobald die "
                f"Kampagne auf active steht — sie steht auf "
                f"{verbindung.kampagne.status}.",
                "erfolg",
            )
        return redirect(ziel)

    if aktion == "zurueckziehen":
        inhalt.status = "draft"
        db.session.commit()
        flash("Variante zurückgezogen.", "erfolg")
        return redirect(ziel)

    try:
        inhalt.title = formular.text(
            request.form.get("titel"), "Der Titel", max_laenge=255
        )
        inhalt.description = formular.text(
            request.form.get("beschreibung"), "Die Beschreibung", max_laenge=4000
        )
    except formular.Ungueltig as fehler:
        db.session.rollback()
        flash(str(fehler), "fehler")
        return redirect(ziel)

    db.session.commit()
    flash("Gespeichert.", "erfolg")
    return redirect(ziel)


# --- Zeitplan ----------------------------------------------------------


@haupt.route("/zeitplan")
@login_required
def zeitplan_seite():
    """Was ansteht und was zuletzt rausging.

    Zwei Listen auf einer Seite, weil man sie zusammen liest: was kommt, und
    ob das, was kam, angekommen ist.
    """
    ansteht = db.session.scalars(
        select(ContentItem)
        .where(
            ContentItem.geplant_fuer.is_not(None),
            ContentItem.status.in_(("ready", "posting")),
        )
        .order_by(ContentItem.geplant_fuer)
        .limit(50)
    ).all()

    # **Freigegeben, aber ohne Termin.** Das ist der Zustand, in dem man
    # ratlos vor einer leeren Seite steht: die Variante ist freigegeben, die
    # Meldung sagte "der Zeitplan nimmt sie mit", und trotzdem steht sie
    # nirgends. Der Grund ist fast immer, dass die Kampagne auf `draft`
    # steht — dann vergibt `einplanen()` gar keine Termine.
    wartet = db.session.scalars(
        select(ContentItem)
        .where(
            ContentItem.geplant_fuer.is_(None),
            ContentItem.status == "ready",
        )
        .order_by(ContentItem.id)
        .limit(50)
    ).all()

    zuletzt = db.session.scalars(
        select(PostedItem).order_by(PostedItem.posted_at.desc()).limit(30)
    ).all()

    # Wenn nichts rausgeht, ist der Grund fast immer derselbe. Er gehört auf
    # die Seite, sonst sucht man ihn im Code. Zwei Fälle, die verschiedene
    # Schritte verlangen: gar nicht verbunden, oder verbunden und der Zugang
    # ist abgelaufen.
    #
    # **Gemeldet wird nur, was auch gebraucht wird.** Vorher standen dort
    # alle freigeschalteten Kanäle, also auch drei, die in keiner Kampagne
    # eingeschaltet sind. Wer dann "Kein Konto verbunden" liest, während sein
    # eigener Kanal längst verbunden ist, sucht den Fehler am falschen Ort.
    gebraucht = {
        verbindung.channel_id
        for verbindung in db.session.scalars(select(CampaignChannel))
    }

    ohne_konto = []
    abgelaufen = []
    for eintrag in db.session.scalars(select(Channel).order_by(Channel.id)):
        if eintrag.key not in AKTIV or eintrag.id not in gebraucht:
            continue
        konto = db.session.scalars(
            select(Account)
            .where(Account.channel_id == eintrag.id)
            .order_by(Account.id)
        ).first()
        if konto is None:
            ohne_konto.append(eintrag.name)
        elif konto.expires_at is not None and nach_berlin(konto.expires_at) <= jetzt():
            abgelaufen.append(eintrag.name)

    return render_template(
        "zeitplan.html",
        ansteht=ansteht,
        wartet=wartet,
        zuletzt=zuletzt,
        ohne_konto=ohne_konto,
        abgelaufen=abgelaufen,
    )


# --- Einstellungen -----------------------------------------------------


def _kanal_zeilen() -> list[dict]:
    """Alle Kanäle mit ihren Zugangsfeldern, in der Reihenfolge der Tabelle.

    Auch die ohne Adapter. Die Zugangsdaten lassen sich eintragen, bevor es
    den Adapter gibt, und dann ist beim Bauen schon alles hinterlegt. Damit
    daraus kein falscher Eindruck wird, steht an jedem Kanal, woran es noch
    hängt: fehlender Adapter, fehlende Freischaltung, fehlende Daten.
    """
    zeilen = []

    for eintrag in db.session.scalars(select(Channel).order_by(Channel.id)):
        felder = [
            {
                "feld": feld,
                "name": feld.name,
                "herkunft": einstellungen.kanal_herkunft(eintrag.key, feld.name),
                # Nur das Secret wird verdeckt. Eine App-ID steht ohnehin
                # im Entwicklerbereich der Plattform und ist beim Abgleichen
                # nützlicher, wenn man sie ganz sieht.
                "anzeige": (
                    einstellungen.verdeckt(
                        einstellungen.kanal_wert(eintrag.key, feld.name)
                    )
                    if feld.geheim
                    else einstellungen.kanal_wert(eintrag.key, feld.name)
                ),
                "lesbar": einstellungen.lesbar(
                    einstellungen.kanal_name(eintrag.key, feld.name)
                ),
            }
            for feld in ZUGANGSFELDER.get(eintrag.key, ())
        ]

        vollstaendig = einstellungen.kanal_vollstaendig(eintrag.key)
        konto = db.session.scalars(
            select(Account)
            .where(Account.channel_id == eintrag.id)
            .order_by(Account.id)
        ).first()

        if eintrag.key not in BEKANNT:
            zustand = "kein Adapter"
        elif eintrag.key not in AKTIV:
            zustand = "Freischaltung fehlt"
        elif not vollstaendig:
            zustand = "Zugangsdaten fehlen"
        elif konto is None:
            # Bewusst nicht "bereit": vollstaendig heisst, dass die Angaben
            # da sind, nicht dass ein Konto verbunden waere. Solange keins
            # da ist, ueberspringt der Zeitplan den Kanal.
            zustand = "nicht verbunden"
        else:
            # Auch das heisst noch nicht, dass jemals etwas gepostet wurde.
            zustand = "verbunden"

        zeilen.append({
            "kanal": eintrag,
            "felder": felder,
            "zustand": zustand,
            "vollstaendig": vollstaendig,
            "konto": konto,
            # Verbinden geht nur mit Adapter, Freischaltung und Zugangsdaten.
            # Der Knopf steht sonst da und fuehrt in eine Fehlermeldung.
            "verbindbar": (
                eintrag.key in BEKANNT
                and eintrag.key in AKTIV
                and vollstaendig
            ),
            "ablagen_moeglich": (
                eintrag.key in BEKANNT
                and BEKANNT[eintrag.key].unterstuetzt_ablagen
            ),
            "ablage_mehrzahl": (
                BEKANNT[eintrag.key].ablage_mehrzahl
                if eintrag.key in BEKANNT
                else ""
            ),
            # Muss im Entwicklerbereich der Plattform zeichengenau stehen.
            # Deshalb hier ausgeschrieben statt in einer Anleitung, und aus
            # der Konfiguration statt aus der laufenden Anfrage: ueber
            # www.pinario.de stuende hier sonst ein anderer Wert als der,
            # den der Adapter beim Anmelden mitschickt.
            "rueckruf": rueckruf_adresse(eintrag.key),
        })

    return zeilen


@haupt.route("/einstellungen")
@login_required
def einstellungen_seite():
    schluessel = einstellungen.hole(einstellungen.GEMINI_SCHLUESSEL)
    return render_template(
        "einstellungen.html",
        herkunft=einstellungen.gemini_herkunft(),
        verdeckt=einstellungen.verdeckt(schluessel),
        lesbar=einstellungen.lesbar(einstellungen.GEMINI_SCHLUESSEL),
        modell_text=current_app.config["GEMINI_MODELL_TEXT"],
        modell_bild=current_app.config["GEMINI_MODELL_BILD"],
        kanaele=_kanal_zeilen(),
        min_laenge=MIN_PASSWORTLAENGE,
    )


@haupt.route("/einstellungen/kanal/<kanal_key>", methods=["POST"])
@login_required
def einstellungen_kanal(kanal_key: str):
    ziel = url_for("haupt.einstellungen_seite")
    felder = ZUGANGSFELDER.get(kanal_key)
    if not felder:
        abort(404)

    if request.form.get("aktion") == "entfernen":
        einstellungen.kanal_entferne(kanal_key)
        current_app.logger.info("Zugangsdaten %s entfernt", kanal_key)
        flash("Zugangsdaten entfernt.", "erfolg")
        return redirect(ziel)

    # Leere Felder lassen den gespeicherten Wert stehen. Sonst müsste man
    # das Secret jedes Mal neu eintippen, nur weil die App-ID sich geändert
    # hat — und angezeigt wird es ja bewusst nicht.
    geaendert = 0
    for feld in felder:
        wert = (request.form.get(feld.name) or "").strip()
        if not wert:
            continue
        if len(wert) > 200:
            flash(f"{feld.beschriftung} ist zu lang.", "fehler")
            return redirect(ziel)
        einstellungen.setze(
            einstellungen.kanal_name(kanal_key, feld.name), wert
        )
        geaendert += 1

    if not geaendert:
        flash("Da stand nichts drin.", "fehler")
        return redirect(ziel)

    current_app.logger.info("Zugangsdaten %s geändert", kanal_key)
    flash("Gespeichert.", "erfolg")
    return redirect(ziel)


@haupt.route("/einstellungen/gemini", methods=["POST"])
@login_required
def einstellungen_gemini():
    ziel = url_for("haupt.einstellungen_seite")
    aktion = request.form.get("aktion", "speichern")

    if aktion == "entfernen":
        einstellungen.entferne(einstellungen.GEMINI_SCHLUESSEL)
        # Nach dem Entfernen greift wieder die .env, falls dort etwas steht.
        # Das muss dastehen, sonst wundert sich später jemand, warum das
        # Erzeugen noch läuft.
        if einstellungen.gemini_herkunft() == "env":
            flash(
                "Schlüssel entfernt. Es gilt jetzt wieder der aus der .env.",
                "erfolg",
            )
        else:
            flash("Schlüssel entfernt.", "erfolg")
        return redirect(ziel)

    if aktion == "pruefen":
        try:
            modell = ki.verbindung_pruefen()
        except ki.KIFehler as fehler:
            flash(str(fehler), "fehler")
            return redirect(ziel)
        flash(f"{modell} hat geantwortet.", "erfolg")
        return redirect(ziel)

    # Nicht `formular.text`: ein Schlüssel wird eingefügt, und beim Einfügen
    # kommt gern ein Zeilenumbruch mit. Der fällt beim strip weg, alles
    # andere bleibt Zeichen für Zeichen stehen.
    neuer = (request.form.get("schluessel") or "").strip()
    if not neuer:
        flash("Da stand nichts drin.", "fehler")
        return redirect(ziel)
    if len(neuer) > 200:
        flash("Das ist zu lang für einen Schlüssel.", "fehler")
        return redirect(ziel)

    einstellungen.setze(einstellungen.GEMINI_SCHLUESSEL, neuer)
    current_app.logger.info("Gemini-Schlüssel geändert")
    flash("Schlüssel gespeichert.", "erfolg")
    return redirect(ziel)


@haupt.route("/einstellungen/passwort", methods=["POST"])
@login_required
def einstellungen_passwort():
    ziel = url_for("haupt.einstellungen_seite")

    alt = request.form.get("alt") or ""
    neu = request.form.get("neu") or ""
    noch_mal = request.form.get("noch_mal") or ""

    # Das alte Passwort wird verlangt, obwohl die Sitzung schon angemeldet
    # ist. Sonst reicht ein offener Browser, um sich dauerhaft einzurichten.
    if not check_password_hash(current_user.passwort_hash, alt):
        current_app.logger.warning("Passwortwechsel mit falschem alten Passwort")
        flash("Das alte Passwort stimmt nicht.", "fehler")
        return redirect(ziel)

    if neu != noch_mal:
        flash("Die beiden neuen Passwörter sind nicht gleich.", "fehler")
        return redirect(ziel)

    if len(neu) < MIN_PASSWORTLAENGE:
        flash(f"Mindestens {MIN_PASSWORTLAENGE} Zeichen.", "fehler")
        return redirect(ziel)

    if neu == alt:
        flash("Das neue Passwort ist das alte.", "fehler")
        return redirect(ziel)

    nutzer = current_user._get_current_object()
    passwort_setzen(nutzer, neu)
    db.session.commit()

    # `passwort_setzen` würfelt den session_token neu und beendet damit alle
    # Anmeldungen — auch diese hier. Ohne das erneute Anmelden landet man
    # unmittelbar nach dem Wechsel auf der Startseite und weiß nicht, ob er
    # geklappt hat.
    login_user(nutzer, remember=True)
    current_app.logger.info("Passwort geändert")
    flash(
        "Passwort geändert. Anmeldungen auf anderen Geräten sind beendet.",
        "erfolg",
    )
    return redirect(ziel)


# --- Erzeugte Bilder ---------------------------------------------------


@haupt.route("/medien/<path:pfad>")
def medien(pfad: str):
    """Erzeugte und hochgeladene Bilder.

    Auf dem Server liefert nginx diesen Ort direkt aus und diese Funktion
    wird nie erreicht; sie ist der Weg für die lokale Entwicklung. Bewusst
    ohne Anmeldung, weil Pinterest Bilder über eine öffentlich erreichbare
    Adresse holt — dieselbe Entscheidung wie im nginx-Block.
    """
    return send_from_directory(current_app.config["UPLOAD_ORDNER"], pfad)
