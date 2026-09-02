"""Was ein Kanal können muss.

Die Anwendung kennt nur diese Schnittstelle, nie eine einzelne Plattform.
Ein neuer Kanal ist damit: eine Zeile in `channels`, eine Datei hier, ein
Eintrag in `__init__.py`. Am Scheduler und an den Ansichten ändert sich
nichts.

Die Eigenschaften oben an `Kanal` beschreiben, was eine Plattform kann und
verlangt. Sie stehen dort, damit die Oberfläche und der Scheduler nie
"ist das Pinterest?" fragen müssen — sonst steht genau diese Frage später
an zehn Stellen und eine davon wird beim nächsten Kanal vergessen.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Ablage:
    """Ein Ort innerhalb eines Kontos.

    Bei Pinterest ein Board, bei Google Business Profile ein Standort. Beide
    beantworten dieselbe Frage — wohin innerhalb des Kontos geht der Beitrag —
    und werden deshalb gleich behandelt. Der Wert landet in
    `posted_items.board_id`; die Spalte heißt aus dem ursprünglichen Entwurf
    so, hält aber beides.
    """

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
    # Ob der Kanal Orte innerhalb des Kontos kennt: Boards bei Pinterest,
    # Standorte bei Google. Die Oberfläche fragt danach, statt "ist das
    # Pinterest?" zu prüfen — sonst steht diese Frage später an zehn Stellen.
    unterstuetzt_ablagen: bool = False
    # Wie so ein Ort in der Oberfläche heißen soll. "Board" und "Standort"
    # sind für den Nutzer verschiedene Dinge, auch wenn der Code sie gleich
    # behandelt.
    ablage_bezeichnung: str = "Ablage"
    # Was diese Plattform annimmt. Der Scheduler überspringt Inhalte, deren
    # Typ hier nicht steht, statt sie ins Leere zu schicken.
    typen: tuple[str, ...] = field(default_factory=lambda: ("image",))
    # Längste Beschreibung, die die Plattform annimmt. Die Content-Erzeugung
    # richtet sich danach; ohne diesen Wert schreibt Gemini Texte, die beim
    # Posten abgeschnitten werden oder den Aufruf scheitern lassen.
    max_beschreibung: int = 500
    # Ob dort Affiliate-Inhalte hingehören. Google Business Profile sagt
    # ausdrücklich nein, siehe den Adapter. Der Wert steht hier und nicht als
    # Sonderfall in der Kampagnen-Maske, damit die Regel an einer Stelle lebt.
    affiliate_erlaubt: bool = True

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
