import hashlib
import logging
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, current_app, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .extensions import db, login_manager
from .sicherheit import csrf_pruefen, csrf_token
from .zeit import formatiere_datum, formatiere_uhrzeit


@lru_cache(maxsize=32)
def _stand(pfad: str, stempel: float) -> str:
    """Kurzer Fingerabdruck einer Datei. Der Zeitstempel steht nur im
    Schlüssel, damit sich der Wert bei einer Änderung neu berechnet."""
    return hashlib.sha256(Path(pfad).read_bytes()).hexdigest()[:8]


def beigabe(name: str) -> str:
    """Adresse einer statischen Datei mit Fingerabdruck.

    Ohne den bleibt eine geänderte CSS auf jedem Gerät unsichtbar, das die
    Seite schon einmal geöffnet hat: der Browser hält sich an die Adresse,
    und die war ja dieselbe. Mit Fingerabdruck ist eine neue Fassung eine
    neue Adresse.
    """
    datei = Path(current_app.static_folder) / name
    adresse = url_for("static", filename=name)
    try:
        return f"{adresse}?v={_stand(str(datei), datei.stat().st_mtime)}"
    except OSError:
        return adresse


def create_app(config_klasse: type[Config] = Config) -> Flask:
    Config.pruefen()

    app = Flask(__name__)
    app.config.from_object(config_klasse)

    # nginx sitzt davor und setzt X-Real-IP und X-Forwarded-Proto.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    login_manager.init_app(app)

    _logging_einrichten(app)

    from .auth import auth
    from .cli import befehle_registrieren
    from .verbinden import verbinden
    from .views import haupt

    app.register_blueprint(auth)
    app.register_blueprint(haupt)
    app.register_blueprint(verbinden)
    befehle_registrieren(app)

    app.before_request(csrf_pruefen)

    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["beigabe"] = beigabe
    app.jinja_env.filters["uhrzeit"] = formatiere_uhrzeit
    app.jinja_env.filters["datum"] = formatiere_datum

    @app.after_request
    def sicherheits_header(antwort):
        antwort.headers.setdefault("X-Content-Type-Options", "nosniff")
        antwort.headers.setdefault("X-Frame-Options", "DENY")
        antwort.headers.setdefault("Referrer-Policy", "same-origin")
        # Eigene CSP je Anwendung. Wer hier später etwas Externes einbaut,
        # muss diese Zeile mitziehen, sonst fällt die Funktion still aus.
        # img-src erlaubt data:, weil erzeugte Vorschaubilder so eingebettet
        # werden; blob: für Vorschauen vor dem Hochladen.
        antwort.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; "
            "script-src 'self'; base-uri 'none'; form-action 'self'; "
            "frame-ancestors 'none'",
        )
        return antwort

    return app


def _logging_einrichten(app: Flask) -> None:
    app.config["LOG_ORDNER"].mkdir(parents=True, exist_ok=True)
    ziel = app.config["LOG_ORDNER"] / "app.log"

    handler = RotatingFileHandler(
        ziel, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.setLevel(logging.INFO)

    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
