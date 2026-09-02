"""Die Seiten hinter der Anmeldung.

Bisher nur die Übersicht. Kampagnen anlegen, Varianten erzeugen und der
Zeitplan kommen als eigene Ansichten dazu.
"""

from flask import Blueprint, render_template
from flask_login import login_required
from sqlalchemy import func, select

from .extensions import db
from .kanaele import AKTIV, BEKANNT
from .models import Campaign, CampaignChannel, Channel, ContentItem, PostedItem

haupt = Blueprint("haupt", __name__)


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
