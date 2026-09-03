"""Tabelle fuer Einstellungen, die sich im Betrieb aendern

Revision ID: 0004_einstellungen
Revises: 0003_varianten
Create Date: 2026-09-03

Schluessel und Wert, mehr nicht. Geheime Werte liegen darin verschluesselt,
mit demselben Tresor wie die OAuth-Token; welche das sind, entscheidet
`app/einstellungen.py` und nicht das Schema. Deshalb gibt es hier auch keine
Spalte "geheim": sie waere eine zweite Wahrheit neben der im Code, und die
beiden wuerden irgendwann auseinanderlaufen.
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_einstellungen"
down_revision = "0003_varianten"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "einstellungen",
        sa.Column("schluessel", sa.String(length=50), primary_key=True),
        sa.Column("wert", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "geaendert_am",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    # Nimmt den gespeicherten Gemini-Schluessel mit. Er steht danach nur noch
    # in der .env, falls er dort ueberhaupt jemals stand.
    op.drop_table("einstellungen")
