"""Pinterest, API v5.

Stand 02.09.2026: Gerüst. Die Adressen und der Ablauf stehen, gegen die
echte API ist noch nichts gelaufen — dafür fehlen die App-Zugangsdaten von
developers.pinterest.com. Was hier steht, ist deshalb ausdrücklich noch
nicht belegt und wird beim ersten echten Verbinden gegengeprüft.

Zwei Punkte, die dabei erfahrungsgemäß Zeit kosten:

* Eine neue Pinterest-App steht im Trial-Modus und darf nur auf das eigene
  Konto. Für mehr ist eine Freigabe nötig. Für pinario reicht Trial, weil
  nur eigene Konten bedient werden.
* Bilder werden nicht als Datei hochgeladen, sondern entweder als Base64
  mitgeschickt oder über eine öffentlich erreichbare Adresse geholt. Die
  zweite Variante braucht einen Ort, an dem das erzeugte Bild liegt.
"""

from urllib.parse import urlencode

from flask import current_app

from .basis import Ablage, Kanal, KanalFehler, Veroeffentlichung, Zahlen

API = "https://api.pinterest.com/v5"
ANMELDUNG = "https://www.pinterest.com/oauth/"

# Nur was gebraucht wird: Boards lesen, Pins schreiben, Zahlen lesen.
BEREICHE = (
    "boards:read",
    "pins:read",
    "pins:write",
    "user_accounts:read",
)


class Pinterest(Kanal):
    def __init__(self) -> None:
        super().__init__(
            key="pinterest",
            name="Pinterest",
            unterstuetzt_boards=True,
            typen=("image", "video"),
        )

    def anmelde_adresse(self, zustand: str) -> str:
        app_id = current_app.config["PINTEREST_APP_ID"]
        if not app_id:
            raise KanalFehler(
                "PINTEREST_APP_ID fehlt in der .env. Die App wird unter "
                "developers.pinterest.com angelegt."
            )
        return ANMELDUNG + "?" + urlencode({
            "client_id": app_id,
            "redirect_uri": current_app.config["PINTEREST_REDIRECT_URI"],
            "response_type": "code",
            "scope": ",".join(BEREICHE),
            "state": zustand,
        })

    def zugang_holen(self, code: str) -> dict:
        raise NotImplementedError("Noch nicht gebaut, siehe Kopf dieser Datei.")

    def zugang_erneuern(self, erneuerung: str) -> dict:
        raise NotImplementedError("Noch nicht gebaut, siehe Kopf dieser Datei.")

    def ablagen(self, zugang: str) -> list[Ablage]:
        raise NotImplementedError("Noch nicht gebaut, siehe Kopf dieser Datei.")

    def veroeffentlichen(self, zugang: str, **_) -> Veroeffentlichung:
        raise NotImplementedError("Noch nicht gebaut, siehe Kopf dieser Datei.")

    def zahlen(self, zugang: str, plattform_id: str) -> Zahlen:
        raise NotImplementedError("Noch nicht gebaut, siehe Kopf dieser Datei.")
