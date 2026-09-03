"""Briefing an der Kampagne, Herkunft und Anfrage an der Variante

Revision ID: 0003_varianten
Revises: 0002_google_business
Create Date: 2026-09-03

Drei Spalten fuer die Content-Erzeugung:

* `campaigns.briefing` — was beworben wird, in eigenen Worten. Ohne dieses
  Feld haette die Anfrage an Gemini nur Name und Ziel-Link, und was in der
  Anfrage fehlt, denkt sich das Modell aus. Genau das soll hier nicht
  passieren, also bekommt der Text einen Ort.
* `content_items.quelle` — erzeugt oder selbst hochgeladen. Steht bisher nur
  am Kanal (`campaign_channels.content_source`), also als Absicht. An der
  einzelnen Variante steht damit spaeter in der Auswertung, was sie
  tatsaechlich war, auch wenn die Absicht zwischendurch umgestellt wurde.
* `content_items.prompt` — die Anfrage, aus der die Variante entstanden ist.
  Die ganze Anwendung existiert, um zu messen welche Variante zieht; ohne
  diese Spalte laesst sich das Ergebnis nicht auf die Frage zurueckfuehren.

`quelle` ist NOT NULL und braucht deshalb ein server_default, sonst
scheitert die Migration an den Zeilen, die schon da sind.
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_varianten"
down_revision = "0002_google_business"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaigns", sa.Column("briefing", sa.Text(), nullable=True))
    op.add_column(
        "content_items",
        sa.Column(
            "quelle",
            sa.String(length=20),
            nullable=False,
            server_default="upload",
        ),
    )
    op.add_column("content_items", sa.Column("prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("content_items", "prompt")
    op.drop_column("content_items", "quelle")
    op.drop_column("campaigns", "briefing")
