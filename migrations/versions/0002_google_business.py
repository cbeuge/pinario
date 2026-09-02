"""Kanal Google Business Profile ergaenzen

Revision ID: 0002_google_business
Revises: 0001_grundgeruest
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_google_business"
down_revision = "0001_grundgeruest"
branch_labels = None
depends_on = None

SCHLUESSEL = "google_business"
NAME = "Google Business Profile"


def upgrade() -> None:
    kanaele = sa.table(
        "channels",
        sa.column("id", sa.Integer),
        sa.column("key", sa.String),
        sa.column("name", sa.String),
    )
    # Wiederholbar: wer vorher schon `flask kanaele-abgleichen` laufen
    # liess, hat die Zeile bereits. Ein blindes INSERT wuerde hier an der
    # Eindeutigkeit von `key` scheitern und die ganze Migration abbrechen.
    verbindung = op.get_bind()
    da = verbindung.execute(
        sa.select(kanaele.c.id).where(kanaele.c.key == SCHLUESSEL)
    ).first()
    if da is None:
        op.bulk_insert(kanaele, [{"key": SCHLUESSEL, "name": NAME}])


def downgrade() -> None:
    kanaele = sa.table(
        "channels", sa.column("key", sa.String)
    )
    # Nur die Kanalzeile. Haengt eine Kampagne daran, weisen die
    # Fremdschluessel das Loeschen ab, und das ist richtig so: dann wuerde
    # ein Downgrade sonst stillschweigend Kampagnendaten mitnehmen.
    op.execute(kanaele.delete().where(kanaele.c.key == SCHLUESSEL))
