"""Zeitstempel fuer den Zwischenzustand beim Posten

Revision ID: 0005_zeitplan
Revises: 0004_einstellungen
Create Date: 2026-09-03

Eine Spalte. `content_items.posten_seit` haelt fest, seit wann ein Eintrag
auf "posting" steht, also zwischen Herausnehmen und Antwort der Plattform.

Warum nicht `geplant_fuer` dafuer benutzen: ein Eintrag kann auch verspaetet
drankommen, etwa wenn der Timer eine Weile nicht lief. Dann liegt
`geplant_fuer` schon weit zurueck, obwohl der Versuch gerade erst begonnen
hat — und ein zweiter Lauf wuerde ihn faelschlich als liegengeblieben
zurueckholen und ein zweites Mal posten.

Der Status "posting" selbst braucht keine Migration: `INHALT_STATUS` ist
eine Konstante im Code und kein Enum in der Datenbank, genau damit ein neuer
Status eine Codeaenderung bleibt.
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_zeitplan"
down_revision = "0004_einstellungen"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "content_items",
        sa.Column("posten_seit", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # Eintraege, die gerade auf "posting" stehen, verlieren dabei ihren
    # Zeitstempel und muessten von Hand auf "ready" zurueckgesetzt werden.
    op.drop_column("content_items", "posten_seit")
