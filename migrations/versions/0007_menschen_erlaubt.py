"""Kampagne: Menschen im Bild erlauben

Revision ID: 0007_menschen_erlaubt
Revises: 0006_threads
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_menschen_erlaubt"
down_revision = "0006_threads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default, damit bestehende Zeilen einen Wert bekommen. Ohne das
    # scheitert die Migration an NOT NULL, sobald schon eine Kampagne da ist
    # -- und auf dem Server sind es vier.
    op.add_column(
        "campaigns",
        sa.Column(
            "menschen_erlaubt",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("campaigns", "menschen_erlaubt")
