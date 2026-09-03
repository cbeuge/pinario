import secrets
from datetime import timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager
from .models import User
from .sicherheit import client_ip
from .zeit import jetzt

auth = Blueprint("auth", __name__)

# Einfache Bremse gegen Durchprobieren. Ein Ein-Personen-Tool braucht dafür
# keine Tabelle, ein Eintrag je IP im Speicher reicht. Nach einem Neustart
# ist die Bremse gelöst, das ist hier vertretbar.
_fehlversuche: dict[str, tuple[int, object]] = {}
MAX_VERSUCHE = 5
SPERRE = timedelta(minutes=5)

# Ein Nutzer, kein zweiter Faktor, keine Wiederherstellung: das Passwort ist
# der einzige Schutz vor der Tür. Die Zahl steht hier und nicht zweimal im
# Code, damit die Kommandozeile und die Oberfläche dieselbe Grenze ziehen.
MIN_PASSWORTLAENGE = 12


def _gesperrt(ip: str) -> bool:
    eintrag = _fehlversuche.get(ip)
    if not eintrag:
        return False
    anzahl, letzter = eintrag
    if jetzt() - letzter > SPERRE:
        _fehlversuche.pop(ip, None)
        return False
    return anzahl >= MAX_VERSUCHE


def _fehlversuch(ip: str) -> None:
    anzahl, _ = _fehlversuche.get(ip, (0, jetzt()))
    _fehlversuche[ip] = (anzahl + 1, jetzt())


@login_manager.user_loader
def lade_nutzer(kennung: str):
    """Kennung ist "id:session_token".

    Passt der Token nicht mehr, wurde das Passwort geändert und die alte
    Anmeldung ist damit ungültig.
    """
    nutzer_id, _, token = kennung.partition(":")
    if not nutzer_id.isdigit():
        return None
    nutzer = db.session.get(User, int(nutzer_id))
    if nutzer is None or not secrets.compare_digest(nutzer.session_token, token):
        return None
    return nutzer


@auth.route("/", methods=["GET", "POST"])
def login():
    """Startseite und Anmeldung in einem.

    pinario.de zeigt nichts als die Marke und das Passwortfeld. Es gibt
    genau einen Nutzer, deshalb steht auch kein Benutzername im Formular:
    ein Feld, das immer denselben Wert hat, ist nur eine Hürde.
    """
    if current_user.is_authenticated:
        return redirect(url_for("haupt.uebersicht"))

    if request.method == "POST":
        ip = client_ip()
        if _gesperrt(ip):
            flash("Zu viele Fehlversuche. In 5 Minuten noch einmal probieren.", "fehler")
            return render_template("login.html"), 429

        passwort = request.form.get("passwort", "")
        nutzer = db.session.query(User).order_by(User.id).first()

        if nutzer and check_password_hash(nutzer.passwort_hash, passwort):
            _fehlversuche.pop(ip, None)
            login_user(nutzer, remember=True)
            current_app.logger.info("Anmeldung erfolgreich von %s", ip)
            ziel = request.args.get("next", "")
            # Nur eigene Pfade zulassen, keine fremden Adressen.
            if ziel.startswith("/") and not ziel.startswith("//"):
                return redirect(ziel)
            return redirect(url_for("haupt.uebersicht"))

        _fehlversuch(ip)
        current_app.logger.warning("Anmeldung gescheitert von %s", ip)
        flash("Passwort stimmt nicht.", "fehler")

    return render_template("login.html")


@auth.route("/abmelden", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


def passwort_setzen(nutzer: User, passwort: str) -> None:
    """Setzt das Passwort und beendet dabei alle offenen Anmeldungen."""
    nutzer.passwort_hash = generate_password_hash(passwort)
    nutzer.session_token = secrets.token_hex(16)
