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


@dataclass(frozen=True)
class Zugangsfeld:
    """Ein Feld, das eine Plattform von ihrer eigenen App-Verwaltung verlangt.

    Nicht der Zugang zu einem Konto — das ist OAuth und landet in `accounts`.
    Gemeint sind die Angaben zur *Anwendung*: App-ID und Secret aus dem
    Entwicklerbereich der Plattform. Sie stehen einmal da und ändern sich
    fast nie, gehören aber trotzdem in die Oberfläche und nicht in die .env,
    weil sonst jeder Wechsel eine Anmeldung per ssh braucht.

    `name` ist der Teil, aus dem der Einstellungs-Schlüssel gebaut wird, und
    darf sich deshalb nicht mehr ändern; `beschriftung` heißt so, wie die
    Plattform es in ihrem eigenen Entwicklerbereich nennt. Die beiden sind
    absichtlich getrennt: Pinterest sagt „App-ID", Google sagt „Client-ID",
    und wer zwischen zwei Fenstern sucht, will dasselbe Wort lesen.
    """

    name: str
    beschriftung: str
    geheim: bool = False
    # Ob das Feld ausgefüllt sein muss, damit der Kanal benutzbar ist.
    # Nicht alles ist Pflicht: die Konfigurations-ID bei Meta braucht nur,
    # wer "Facebook Login for Business" nutzt. Ein optionales Feld als
    # Pflicht zu führen hieße, einen fertigen Kanal als unvollständig
    # anzuzeigen.
    pflicht: bool = True
    # Ein Satz unter dem Feld, wenn ohne ihn niemand weiß, was hineingehört
    # oder wo der Wert herkommt.
    hilfe: str = ""


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
    # behandelt. Die Mehrzahl steht mit dabei, weil sie sich im Deutschen
    # nicht anhängen lässt: aus "Board" wird "Boards", aus "Standort" wird
    # "Standorte".
    ablage_bezeichnung: str = "Ablage"
    ablage_mehrzahl: str = "Ablagen"
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
    # Ob der Ziel-Link in den Text muss. Ein Pin hat ein eigenes Feld dafür,
    # ein Foto-Beitrag bei Facebook oder Instagram nicht — dort steht der
    # Link im Text oder nirgends. Das gehört in die Anfrage an das Modell:
    # steht "den Link nicht in den Text schreiben" drin, obwohl es keine
    # andere Stelle gibt, führt der fertige Beitrag ins Leere.
    link_im_text: bool = False
    # Und ob er dort überhaupt anklickbar ist. Bei Instagram ist er das
    # nicht, in keiner Bildunterschrift. Das ist keine Kleinigkeit: ein Text,
    # der "hier klicken" sagt, ist dort schlicht falsch, und die einzige
    # klickbare Stelle des ganzen Kontos ist der Link im Profil.
    link_klickbar: bool = True
    # In welchem Seitenverhältnis das Bild erzeugt wird. Pinterest zeigt
    # Pins hochkant und schneidet ein quadratisches Bild oben und unten
    # weg; Facebook zeigt quer. Ein Bild im falschen Format ist kein
    # Fehler, den jemand meldet — es sieht nur immer etwas daneben aus.
    bild_format: str = "1:1"
    # Wohin der Browser beim Verbinden geschickt wird, nur Schema und Host.
    #
    # **Das steht hier wegen der Content-Security-Policy.** Der Knopf "Konto
    # verbinden" ist ein Formular; die Antwort darauf ist eine Weiterleitung
    # zur Plattform. Browser prüfen solche Weiterleitungen gegen
    # `form-action`, und was dort fehlt, wird **stillschweigend** verworfen —
    # kein Fehler auf der Seite, keine Zeile im Server-Log, der Knopf tut
    # einfach nichts. Am 04.09.2026 genau daran hängengeblieben.
    #
    # Weil der Wert am Kanal steht, zieht die CSP bei einem neuen Adapter von
    # selbst nach. Eine Liste in `create_app` würde beim nächsten Kanal
    # vergessen, und der Fehler sähe wieder aus wie ein kaputter Knopf.
    anmelde_ursprung: str = ""

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
        typ: str = "image",
    ) -> Veroeffentlichung:
        """Schickt einen Beitrag raus.

        `typ` ist "image" oder "video" und kommt aus `content_items.type`.
        Er wird **übergeben und nicht aus der Dateiendung geraten**: der Typ
        steht in der Datenbank, und zwei Wahrheiten über dieselbe Sache
        laufen früher oder später auseinander.

        Der Standard ist "image", damit ein Adapter, der nur Bilder kennt,
        die Angabe schlicht ignorieren kann.
        """
        raise NotImplementedError

    def fehlende_rechte(self, zugang: str) -> list[str]:
        """Welche Rechte dem verbundenen Konto fehlen, um zu posten.

        **Wird direkt nach dem Verbinden gefragt.** Ein Konto kann verbunden
        aussehen, die Seiten anzeigen und trotzdem nichts posten dürfen —
        genau das ist am 05.09.2026 passiert: `pages_show_list` war da,
        `pages_manage_posts` nicht. Aufgefallen ist es erst am ersten
        fälligen Beitrag, also Stunden später und als gescheiterter Versuch
        in der Messreihe.

        Eine leere Liste heißt "alles da" **oder** "der Kanal kann es nicht
        sagen". Das ist Absicht: ein Adapter, der die Rechte nicht abfragen
        kann, soll das Verbinden nicht mit einer Warnung belasten, die er
        gar nicht belegen kann.
        """
        return []

    def zahlen(self, zugang: str, plattform_id: str) -> Zahlen:
        raise NotImplementedError
