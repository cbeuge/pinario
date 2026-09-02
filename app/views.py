"""Die Seiten hinter der Anmeldung, dazu die öffentlichen Rechtstexte.

Varianten erzeugen und der Zeitplan kommen als eigene Ansichten dazu.
"""

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from . import formular
from .extensions import db
from .kanaele import AKTIV, BEKANNT, kanal
from .models import (
    KAMPAGNE_STATUS,
    QUELLE,
    Campaign,
    CampaignChannel,
    Channel,
    ContentItem,
    PostedItem,
)
from .rechtstexte import KATEGORIEN, rechtstext

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
        zeilen.append({
            "kanal": eintrag_kanal,
            "verfuegbar": eintrag_kanal.key in AKTIV,
            "adapter": adapter,
            "verbindung": verbindung,
            "einstellungen": (verbindung.settings if verbindung else {}) or {},
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
