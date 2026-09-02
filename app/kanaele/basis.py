"""Was ein Kanal können muss.

Die Anwendung kennt nur diese Schnittstelle, nie eine einzelne Plattform.
Ein neuer Kanal ist damit: eine Zeile in `channels`, eine Datei hier, ein
Eintrag in `__init__.py`. Am Scheduler und an den Ansichten ändert sich
nichts.

`unterstuetzt_boards` gibt es, weil Pinterest als einziger Kanal einen Ort
innerhalb des Kontos kennt. Die Oberfläche fragt danach, statt "ist das
Pinterest?" zu prüfen; sonst steht diese Frage später an zehn Stellen.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Ablage:
    """Ein Ort innerhalb eines Kontos, bei Pinterest ein Board."""

    id: str
    name: str


@dataclass
class Veroeffentlichung:
    """Antwort der Plattform auf einen erfolgreichen Beitrag."""

    plattform_id: str
    ablage_id: str | None = None
    zeitpunkt: datetime | None = None


@dataclass
class Zahlen:
    """Was die Plattform später über einen Beitrag sagt."""

    impressions: int = 0
    clicks: int = 0
    saves: int = 0


class KanalFehler(RuntimeError):
    """Die Plattform hat abgelehnt oder war nicht erreichbar.

    Wird vom Scheduler gefangen und landet als Text in `posted_items.fehler`.
    """


@dataclass
class Kanal:
    """Basisklasse. Jeder Adapter erbt davon und füllt die Methoden."""

    key: str = ""
    name: str = ""
    unterstuetzt_boards: bool = False
    # Was diese Plattform annimmt. Der Scheduler überspringt Inhalte, deren
    # Typ hier nicht steht, statt sie ins Leere zu schicken.
    typen: tuple[str, ...] = field(default_factory=lambda: ("image",))

    # --- Verbinden -----------------------------------------------------

    def anmelde_adresse(self, zustand: str) -> str:
        """Adresse, zu der der Browser zum Verbinden geschickt wird."""
        raise NotImplementedError

    def zugang_holen(self, code: str) -> dict:
        """Tauscht den Rückruf-Code gegen Token. Liefert die Felder für
        `accounts`: zugang, erneuerung, laeuft_ab, kontoname."""
        raise NotImplementedError

    def zugang_erneuern(self, erneuerung: str) -> dict:
        raise NotImplementedError

    # --- Betrieb -------------------------------------------------------

    def ablagen(self, zugang: str) -> list[Ablage]:
        """Boards oder Vergleichbares. Kanäle ohne so etwas liefern []."""
        return []

    def veroeffentlichen(
        self,
        zugang: str,
        *,
        titel: str,
        beschreibung: str,
        ziel_url: str,
        datei: str | None,
        ablage_id: str | None,
    ) -> Veroeffentlichung:
        raise NotImplementedError

    def zahlen(self, zugang: str, plattform_id: str) -> Zahlen:
        raise NotImplementedError
