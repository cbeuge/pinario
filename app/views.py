"""Die Seiten hinter der Anmeldung.

Bisher nur die Übersicht. Kampagnen anlegen, Varianten erzeugen und der
Zeitplan kommen als eigene Ansichten dazu.
"""

from flask import Blueprint, abort, render_template, request
from flask_login import login_required
from sqlalchemy import func, select

from .extensions import db
from .kanaele import AKTIV, BEKANNT
from .models import Campaign, CampaignChannel, Channel, ContentItem, PostedItem
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
