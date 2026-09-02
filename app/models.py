"""Datenmodell.

Entspricht dem Schema aus dem Projekt-Briefing, an drei Stellen ergänzt:

* `users` für die Anmeldung. Ein Nutzer, kein Registrierungs-Weg.
* `posted_items.status` und `.fehler`, damit ein gescheiterter Versuch
  nachvollziehbar bleibt. Ohne das steht nur da, dass nichts gepostet wurde,
  aber nicht warum.
* `content_items.geplant_fuer`, weil zeitversetztes Posten sonst nirgends
  steht. Der Scheduler braucht eine Spalte, auf die er filtern kann.

Zeiten stehen überall als TIMESTAMPTZ. Die Umrechnung nach deutscher Zeit
macht `zeit.py`, nie die Datenbank und nie die Prozess-Zeitzone.
"""

import secrets
from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db
from .zeit import jetzt

# Feste Werte, die in mehreren Modulen gebraucht werden. Als Konstanten und
# nicht als Enum in der Datenbank: ein neuer Status soll eine Codeänderung
# sein und keine Migration.
KAMPAGNE_STATUS = ("draft", "active", "paused")
INHALT_STATUS = ("draft", "ready", "posted", "failed")
INHALT_TYP = ("image", "video", "text")
QUELLE = ("upload", "ai_generated")


class User(UserMixin, db.Model):
    """Ein einziger Nutzer. Kein Registrierungs-Weg, kein Passwort-Reset."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    benutzername: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    passwort_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Wird beim Passwortwechsel neu gewürfelt und beendet damit alle noch
    # offenen Anmeldungen. Flask-Login prüft den Wert bei jeder Anfrage.
    session_token: Mapped[str] = mapped_column(
        String(32), nullable=False, default=lambda: secrets.token_hex(16)
    )
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=jetzt, nullable=False
    )

    def get_id(self) -> str:
        return f"{self.id}:{self.session_token}"


class Channel(db.Model):
    """Feste Referenztabelle statt Enum.

    Ein neuer Kanal ist damit eine Zeile und ein Adapter unter app/kanaele,
    keine Migration am Datentyp.
    """

    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    def __repr__(self) -> str:
        return f"<Channel {self.key}>"


class Campaign(db.Model):
    """Die übergeordnete Klammer: ein Ziel-Link, mehrere Kanäle."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=jetzt, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=jetzt, onupdate=jetzt, nullable=False
    )

    # passive_deletes: das Löschen erledigt die Datenbank über ON DELETE
    # CASCADE. Ohne das lädt SQLAlchemy erst alle Kinder und schreibt ihnen
    # einzeln NULL in den Fremdschlüssel, was an posted_items scheitert —
    # und zwar mit einer irreführenden NOT-NULL-Meldung statt mit dem
    # eigentlichen Grund. Siehe die Anmerkung bei PostedItem.
    kanaele: Mapped[list["CampaignChannel"]] = relationship(
        back_populates="kampagne", cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Campaign {self.name}>"


class CampaignChannel(db.Model):
    """Kampagne mal Kanal, plus die Einstellungen dieses einen Paares."""

    __tablename__ = "campaign_channels"
    __table_args__ = (UniqueConstraint("campaign_id", "channel_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    content_source: Mapped[str] = mapped_column(
        String(20), default="ai_generated", nullable=False
    )
    # Kanalspezifisch und deshalb bewusst schemalos, zum Beispiel
    # {"board_ids": [...], "posts_per_day": 3, "time_window": ["09:00", "21:00"]}.
    # Was ein Kanal hier erwartet, steht in seinem Adapter unter app/kanaele.
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=jetzt, nullable=False
    )

    kampagne: Mapped[Campaign] = relationship(back_populates="kanaele")
    kanal: Mapped[Channel] = relationship()
    inhalte: Mapped[list["ContentItem"]] = relationship(
        back_populates="kampagnenkanal", cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Account(db.Model):
    """OAuth-Zugang eines Kanals.

    access_token und refresh_token stehen verschlüsselt drin, siehe
    app/tresor.py. Gelesen wird immer über die beiden Eigenschaften unten,
    nie direkt über die Spalte.
    """

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(255))
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=jetzt, nullable=False
    )

    kanal: Mapped[Channel] = relationship()

    @property
    def zugang(self) -> str:
        from .tresor import aufschliessen

        return aufschliessen(self.access_token)

    @zugang.setter
    def zugang(self, wert: str) -> None:
        from .tresor import einschliessen

        self.access_token = einschliessen(wert)

    @property
    def erneuerung(self) -> str:
        from .tresor import aufschliessen

        return aufschliessen(self.refresh_token or "")

    @erneuerung.setter
    def erneuerung(self, wert: str) -> None:
        from .tresor import einschliessen

        self.refresh_token = einschliessen(wert) or None


class ContentItem(db.Model):
    """Eine einzelne Variante: ein Pin, ein Post, ein Reel.

    Mehrere Varianten mit derselben `variant_group` gehören zusammen und
    werden gegeneinander gemessen. Sie unterscheiden sich in Bild oder Text,
    nicht im Ziel-Link.
    """

    __tablename__ = "content_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_channel_id: Mapped[int] = mapped_column(
        ForeignKey("campaign_channels.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)
    variant_group: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    # Nicht im ursprünglichen Schema. Ohne diese Spalte hat der Scheduler
    # nichts, worauf er filtern kann, und zeitversetztes Posten wäre nur eine
    # Absicht ohne Ort.
    geplant_fuer: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=jetzt, nullable=False
    )

    kampagnenkanal: Mapped[CampaignChannel] = relationship(back_populates="inhalte")
    # passive_deletes="all": SQLAlchemy fasst die Veröffentlichungen beim
    # Löschen gar nicht an. Die Datenbank entscheidet, und die sagt Nein,
    # solange es Zeilen gibt. Genau so ist es gewollt.
    veroeffentlichungen: Mapped[list["PostedItem"]] = relationship(
        back_populates="inhalt", passive_deletes="all"
    )


class PostedItem(db.Model):
    """Was tatsächlich rausgegangen ist, plus die Zahlen dazu.

    **Diese Tabelle bremst das Löschen, und das ist Absicht.** Die
    Fremdschlüssel auf `content_items` und `campaign_channels` haben
    bewusst kein ON DELETE. Eine Kampagne, die schon gepostet hat, lässt
    sich deshalb nicht löschen — die Datenbank weist es ab.

    Der Grund: die ganze Anwendung existiert, um zu messen, welche Variante
    zieht. Eine Kampagne zu löschen und dabei die Messreihe mitzunehmen,
    wäre stillschweigend der teuerste Knopf im Programm. Kampagnen werden
    deshalb auf `paused` gesetzt, nicht gelöscht.

    Eine Kampagne ohne Veröffentlichungen lässt sich weiterhin löschen, da
    steht nichts im Weg. Wer das Verhalten ändern will, ändert es hier und
    in der Migration, nicht nebenbei über eine Kaskade im Modell.
    """

    __tablename__ = "posted_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_item_id: Mapped[int] = mapped_column(
        ForeignKey("content_items.id"), nullable=False
    )
    campaign_channel_id: Mapped[int] = mapped_column(
        ForeignKey("campaign_channels.id"), nullable=False
    )
    platform_post_id: Mapped[str | None] = mapped_column(String(255))
    # Nur bei Pinterest belegt. Steht hier und nicht in einer eigenen Tabelle,
    # weil sonst jede Auswertung über einen zusätzlichen Join ginge.
    board_id: Mapped[str | None] = mapped_column(String(255))
    posted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=jetzt, nullable=False
    )
    # Nicht im ursprünglichen Schema. Ein Versuch, der an der API scheitert,
    # soll als Zeile stehenbleiben und den Grund nennen. Sonst sieht man
    # später nur, dass nichts gepostet wurde.
    status: Mapped[str] = mapped_column(String(20), default="posted", nullable=False)
    fehler: Mapped[str | None] = mapped_column(Text)

    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saves: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_analytics_fetch_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    inhalt: Mapped[ContentItem] = relationship(back_populates="veroeffentlichungen")
