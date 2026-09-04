"""Die Seiten hinter der Anmeldung, dazu die öffentlichen Rechtstexte.

Der Zeitplan kommt als eigene Ansicht dazu.
"""

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

    return render_template(
        "uebersicht.html",
        kampagnen=kampagnen,
        gepostet=gepostet,
        kanaele=kanaele,
    )


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

        # Der Zustand in einem Wort, damit die Tabelle ihn nur anzeigen und
        # nicht selbst zusammenreimen muss. Die Reihenfolge ist die des
        # Weges: erst braucht es einen Adapter, dann ein Konto, dann muss
        # der Kanal an dieser Kampagne eingeschaltet sein.
        if eintrag_kanal.key not in BEKANNT:
            zustand, hinweis = "vorbereitet", "Für diesen Kanal gibt es noch keinen Adapter."
        elif eintrag_kanal.key not in AKTIV:
            zustand, hinweis = "gesperrt", "Der Zugang zu dieser Plattform ist noch nicht freigeschaltet."
        elif not verbunden:
            zustand, hinweis = "kein Konto", "Unter Einstellungen verbinden. Ohne Konto überspringt der Zeitplan diesen Kanal."
        elif not verbindung:
            zustand, hinweis = "aus", "Für diese Kampagne noch nicht eingeschaltet."
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
        }
        if adapter.unterstuetzt_ablagen:
            einstellungen["board_ids"] = formular.kennungen(
                request.form.get("board_ids")
            )
        quelle = formular.aus_auswahl(
            request.form.get("content_source"), QUELLE, "Die Herkunft der Inhalte"
        )
    except formular.Ungueltig as fehler:
        flash(str(fehler), "fehler")
        return redirect(url_for("haupt.kampagne", kampagne_id=kampagne_id))

    if verbindung is None:
        verbindung = CampaignChannel(
            campaign_id=eintrag.id, channel_id=channel_id
        )
        db.session.add(verbindung)
    verbindung.enabled = True
    verbindung.content_source = quelle
    verbindung.settings = einstellungen

    db.session.commit()
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
        kann_erzeugen=bool(einstellungen.gemini_herkunft()),
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
                pfad = ki.bild_ablegen(
                    ki.bild_erzeugen(
                        f"{anfrage}\n\nBild zu diesem Vorschlag:\n"
                        f"{vorschlag.titel}\n{vorschlag.beschreibung}"
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
        flash("Variante gelöscht.", "erfolg")
        return redirect(ziel)

    if aktion == "freigeben":
        inhalt.status = "ready"
        db.session.commit()
        flash("Variante freigegeben. Der Zeitplan nimmt sie mit.", "erfolg")
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

    zuletzt = db.session.scalars(
        select(PostedItem).order_by(PostedItem.posted_at.desc()).limit(30)
    ).all()

    # Wenn nichts rausgeht, ist der Grund fast immer derselbe. Er gehört auf
    # die Seite, sonst sucht man ihn im Code. Zwei Fälle, die verschiedene
    # Schritte verlangen: gar nicht verbunden, oder verbunden und der Zugang
    # ist abgelaufen.
    ohne_konto = []
    abgelaufen = []
    for eintrag in db.session.scalars(select(Channel).order_by(Channel.id)):
        if eintrag.key not in AKTIV:
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
