import os
from pathlib import Path

from dotenv import load_dotenv

BASIS = Path(__file__).resolve().parent.parent
load_dotenv(BASIS / ".env")


def _bool(name: str, standard: bool = False) -> bool:
    wert = os.environ.get(name)
    if wert is None:
        return standard
    return wert.strip().lower() in {"1", "true", "ja", "yes", "on"}


class Config:
    PRODUKTION = _bool("PRODUKTION", False)

    SECRET_KEY = os.environ.get("SECRET_KEY") or "nur-fuer-lokale-entwicklung"

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://pinario:pinario@localhost:5432/pinario",
    )
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = PRODUKTION
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 30  # 30 Tage

    # Hochgeladene Bilder und Videos. Pinterest nimmt Videos bis 2 GB an,
    # so viel geht hier bewusst nicht durch: was hier hochgeladen wird, ist
    # eigenes Material für Pins, kein Filmmaterial.
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024
    UPLOAD_ORDNER = BASIS / "uploads"
    LOG_ORDNER = BASIS / "logs"

    # Schlüssel für die verschlüsselten OAuth-Token in der Tabelle accounts.
    TRESOR_SCHLUESSEL = os.environ.get("TRESOR_SCHLUESSEL", "")

    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODELL_TEXT = os.environ.get("GEMINI_MODELL_TEXT", "gemini-3.7-flash")
    GEMINI_MODELL_BILD = os.environ.get(
        "GEMINI_MODELL_BILD", "gemini-3-pro-image-preview"
    )

    PINTEREST_APP_ID = os.environ.get("PINTEREST_APP_ID", "")
    PINTEREST_APP_SECRET = os.environ.get("PINTEREST_APP_SECRET", "")
    PINTEREST_REDIRECT_URI = os.environ.get(
        "PINTEREST_REDIRECT_URI", "https://pinario.de/kanaele/pinterest/rueckruf"
    )

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.environ.get(
        "GOOGLE_REDIRECT_URI", "https://pinario.de/kanaele/google/rueckruf"
    )

    @staticmethod
    def pruefen() -> None:
        """Beim Start abbrechen, wenn in Produktion etwas Wichtiges fehlt.

        Lieber ein Dienst, der nicht hochkommt und das im Protokoll sagt, als
        einer, der mit dem Entwicklungs-SECRET_KEY läuft.
        """
        if not Config.PRODUKTION:
            return
        fehlt = [
            name
            for name in ("SECRET_KEY", "DATABASE_URL", "TRESOR_SCHLUESSEL")
            if not os.environ.get(name)
        ]
        if fehlt:
            raise RuntimeError(
                "PRODUKTION=1, aber diese Werte fehlen in der .env: "
                + ", ".join(fehlt)
            )
