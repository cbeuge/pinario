"""Google Business Profile, früher Google My Business.

Stand 02.09.2026: Gerüst. Der Ablauf und die Adressen stehen, gegen die
echte API ist noch nichts gelaufen — der Zugang ist noch nicht beantragt.

Drei Dinge, die diesen Kanal von allen anderen unterscheiden und die man
besser vorher weiß als hinterher:

**1. Der API-Zugang ist ein Antrag, kein Knopf.** Bei Pinterest legt man
eine App an und hat sofort Schlüssel. Hier braucht es ein Projekt in der
Google Cloud Console, die aktivierten Business-Profile-APIs *und* eine
gesonderte Freischaltung durch Google über ein Formular. Bis die durch ist,
liefert jeder Aufruf 403, und zwar ohne dass an der eigenen Einrichtung
etwas falsch wäre. Wer das nicht weiß, sucht den Fehler tagelang im Code.

**2. Beiträge brauchen einen bestätigten Standort.** Ein Business Profile
hängt an einem echten, von Google bestätigten Eintrag. Ohne den gibt es
nichts, wohin gepostet werden könnte. Standorte sind hier das, was bei
Pinterest die Boards sind, deshalb `unterstuetzt_ablagen`.

**3. Affiliate-Inhalte gehören hier nicht hin.** Googles Richtlinien für
Beiträge im Unternehmensprofil sind bei werblichen Fremdlinks streng, und
die Folge ist im Zweifel nicht ein abgelehnter Beitrag, sondern ein
gesperrter Eintrag — den man mühsam zurückholt. Deshalb steht am Kanal
`affiliate_erlaubt = False`. Für die eigenen Werkzeuge ist der Kanal
dagegen genau richtig: wer nach dem Unternehmen sucht, sieht dort, woran
gerade gearbeitet wird.

Aufbau der API, falls das hier jemand fortsetzt: die alte einheitliche
"Google My Business API v4" ist in mehrere kleinere Dienste zerfallen.
Konten und Standorte kommen aus den neueren Diensten
(`mybusinessaccountmanagement`, `mybusinessbusinessinformation`), die
Beiträge selbst liegen weiterhin unter dem alten `v4`-Pfad. **Das ist der
wackligste Teil dieser Datei**: Google baut an dieser Ecke seit Jahren um,
und was hier steht, ist gegen die Dokumentation geschrieben und nicht gegen
einen echten Aufruf. Vor dem ersten Einsatz die aktuelle Dokumentation
gegenlesen, nicht diesen Kommentar glauben.
"""

from urllib.parse import urlencode

from flask import current_app

from .basis import Ablage, Kanal, KanalFehler, Veroeffentlichung, Zahlen

ANMELDUNG = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"

# Konten und Standorte
KONTEN = "https://mybusinessaccountmanagement.googleapis.com/v1"
STANDORTE = "https://mybusinessbusinessinformation.googleapis.com/v1"
# Beiträge. Siehe die Warnung im Kopf: dieser Pfad ist der unsicherste.
BEITRAEGE = "https://mybusiness.googleapis.com/v4"

# Ein einziger Bereich deckt alles ab, was hier gebraucht wird. Google
# vergibt für Business Profile keine feineren Rechte.
BEREICHE = ("https://www.googleapis.com/auth/business.manage",)

# Google schneidet die Zusammenfassung eines Beitrags bei 1500 Zeichen ab.
MAX_ZUSAMMENFASSUNG = 1500


class GoogleBusiness(Kanal):
    def __init__(self) -> None:
        super().__init__(
            key="google_business",
            name="Google Business Profile",
            unterstuetzt_ablagen=True,
            ablage_bezeichnung="Standort",
            ablage_mehrzahl="Standorte",
            # Nur Bilder. Video geht im Unternehmensprofil zwar, aber nicht
            # über denselben Weg wie ein Beitrag mit Bild, und ohne Not
            # kommt das hier nicht rein.
            typen=("image",),
            max_beschreibung=MAX_ZUSAMMENFASSUNG,
            affiliate_erlaubt=False,
        )

    def anmelde_adresse(self, zustand: str) -> str:
        kennung = current_app.config["GOOGLE_CLIENT_ID"]
        if not kennung:
            raise KanalFehler(
                "GOOGLE_CLIENT_ID fehlt in der .env. Das Projekt wird in der "
                "Google Cloud Console angelegt, danach muss der Zugang zu den "
                "Business-Profile-APIs zusätzlich bei Google beantragt werden."
            )
        return ANMELDUNG + "?" + urlencode({
            "client_id": kennung,
            "redirect_uri": current_app.config["GOOGLE_REDIRECT_URI"],
            "response_type": "code",
            "scope": " ".join(BEREICHE),
            "state": zustand,
            # Ohne diese beiden gibt Google beim ersten Mal zwar einen
            # refresh_token heraus, bei jeder weiteren Anmeldung aber nicht
            # mehr. Dann läuft der Zugang nach einer Stunde ab und lässt sich
            # nicht erneuern, ohne den Kanal neu zu verbinden.
            "access_type": "offline",
            "prompt": "consent",
        })

    def zugang_holen(self, code: str) -> dict:
        raise NotImplementedError("Noch nicht gebaut, siehe Kopf dieser Datei.")

    def zugang_erneuern(self, erneuerung: str) -> dict:
        raise NotImplementedError("Noch nicht gebaut, siehe Kopf dieser Datei.")

    def ablagen(self, zugang: str) -> list[Ablage]:
        """Die bestätigten Standorte des Kontos."""
        raise NotImplementedError("Noch nicht gebaut, siehe Kopf dieser Datei.")

    def veroeffentlichen(self, zugang: str, **_) -> Veroeffentlichung:
        raise NotImplementedError("Noch nicht gebaut, siehe Kopf dieser Datei.")

    def zahlen(self, zugang: str, plattform_id: str) -> Zahlen:
        """Aufrufe und Klicks eines Beitrags.

        Achtung beim Ausbauen: Google liefert hier keine "Saves". Das Feld
        bleibt 0, und in der Auswertung dürfen Kanäle deshalb nicht über
        diese Zahl hinweg verglichen werden.
        """
        raise NotImplementedError("Noch nicht gebaut, siehe Kopf dieser Datei.")
