"""Kanal Threads ergaenzen

Revision ID: 0006_threads
Revises: 0005_zeitplan
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_threads"
down_revision = "0005_zeitplan"
branch_labels = None
depends_on = None

SCHLUESSEL = "threads"
NAME = "Threads"


def upgrade() -> None:
    kanaele = sa.table(
        "channels",
        sa.column("id", sa.Integer),
        sa.column("key", sa.String),
        sa.column("name", sa.String),
    )
    # Wiederholbar, wie bei 0002: wer vorher `flask kanaele-abgleichen`
    # laufen liess, hat die Zeile schon. Ein blindes INSERT wuerde an der
    # Eindeutigkeit von `key` scheitern und die Migration abbrechen.
    verbindung = op.get_bind()
    da = verbindung.execute(
        sa.select(kanaele.c.id).where(kanaele.c.key == SCHLUESSEL)
    ).first()
    if da is None:
        op.bulk_insert(kanaele, [{"key": SCHLUESSEL, "name": NAME}])


def downgrade() -> None:
    kanaele = sa.table("channels", sa.column("key", sa.String))
    # Nur die Kanalzeile. Haengt eine Kampagne daran, weisen die
    # Fremdschluessel das Loeschen ab, und das ist richtig so.
    op.execute(kanaele.delete().where(kanaele.c.key == SCHLUESSEL))
