"""Grundgeruest: Nutzer, Kanaele, Kampagnen, Inhalte, Veroeffentlichungen

Revision ID: 0001_grundgeruest
Revises:
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_grundgeruest"
down_revision = None
branch_labels = None
depends_on = None

# Die vier vorgesehenen Kanaele. Instagram, Facebook und X stehen von Anfang
# an drin, damit eine Kampagne spaeter ohne Migration dorthin ausgespielt
# werden kann. Welche davon benutzbar sind, entscheidet app/kanaele.
KANAELE = [
    ("pinterest", "Pinterest"),
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("x", "X"),
]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("benutzername", sa.String(80), nullable=False, unique=True),
        sa.Column("passwort_hash", sa.String(255), nullable=False),
        sa.Column("session_token", sa.String(32), nullable=False),
        sa.Column("erstellt_am", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(50), nullable=False),
    )

    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "campaign_channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "campaign_id",
            sa.Integer(),
            sa.ForeignKey("campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channel_id", sa.Integer(), sa.ForeignKey("channels.id"), nullable=False
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "content_source",
            sa.String(20),
            nullable=False,
            server_default="ai_generated",
        ),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("campaign_id", "channel_id"),
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "channel_id", sa.Integer(), sa.ForeignKey("channels.id"), nullable=False
        ),
        sa.Column("account_name", sa.String(255)),
        # Verschluesselt, siehe app/tresor.py. Deshalb Text und nicht String:
        # der Geheimtext ist deutlich laenger als der Token selbst.
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "content_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "campaign_channel_id",
            sa.Integer(),
            sa.ForeignKey("campaign_channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("file_path", sa.Text()),
        sa.Column("variant_group", sa.String(50)),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("geplant_fuer", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Genau die Abfrage des Schedulers: was ist faellig und noch nicht raus.
    op.create_index(
        "ix_content_items_faellig",
        "content_items",
        ["status", "geplant_fuer"],
    )
    # Fuer den A/B-Vergleich: alle Varianten einer Gruppe nebeneinander.
    op.create_index(
        "ix_content_items_variante", "content_items", ["variant_group"]
    )

    op.create_table(
        "posted_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "content_item_id",
            sa.Integer(),
            sa.ForeignKey("content_items.id"),
            nullable=False,
        ),
        sa.Column(
            "campaign_channel_id",
            sa.Integer(),
            sa.ForeignKey("campaign_channels.id"),
            nullable=False,
        ),
        sa.Column("platform_post_id", sa.String(255)),
        sa.Column("board_id", sa.String(255)),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="posted"),
        sa.Column("fehler", sa.Text()),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("saves", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_analytics_fetch_at", sa.DateTime(timezone=True)),
    )
    # Das Nachtragen der Zahlen sucht die aeltesten zuerst.
    op.create_index(
        "ix_posted_items_zahlen_stand",
        "posted_items",
        ["last_analytics_fetch_at"],
    )

    kanaele = sa.table(
        "channels", sa.column("key", sa.String), sa.column("name", sa.String)
    )
    op.bulk_insert(kanaele, [{"key": k, "name": n} for k, n in KANAELE])


def downgrade() -> None:
    op.drop_table("posted_items")
    op.drop_table("content_items")
    op.drop_table("accounts")
    op.drop_table("campaign_channels")
    op.drop_table("campaigns")
    op.drop_table("channels")
    op.drop_table("users")
