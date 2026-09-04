"""Ein Konto mit einem Kanal verbinden, per OAuth.

Drei Adressen, für jeden Kanal dieselben: hin zur Plattform, zurück von der
Plattform, und wieder trennen. Die Anwendung kennt dabei keine einzelne
Plattform — was sich unterscheidet, steht im Adapter.

**Der `zustand` ist kein Beiwerk.** Er wird gewürfelt, liegt in der Sitzung
und muss beim Rückruf wieder passen. Ohne diese Prüfung könnte jemand einem
angemeldeten Nutzer einen Rückruf mit *seinem* Code unterschieben, und die
Anwendung würde fremde Zugangsdaten unter dem eigenen Konto ablegen — von da
an ginge jeder Pin auf ein fremdes Board.

**Je Kanal gibt es genau ein Konto.** Der Zeitplan nimmt das erste, das er
findet; ein zweites daneben wäre ein Zugang, der aussieht, als würde er
benutzt, und es nie wird. Wer neu verbindet, überschreibt deshalb das
bestehende Konto, statt ein weiteres anzulegen.
"""

import secrets

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import login_required
from sqlalchemy import select

from .extensions import db
from .kanaele import AKTIV, BEKANNT, KanalFehler, kanal
from .models import Account, Channel

verbinden = Blueprint("verbinden", __name__, url_prefix="/kanaele")

# Wo der gewürfelte Wert in der Sitzung liegt. Zusammen mit dem Kanal, damit
# ein Rückruf von Pinterest nicht mit einem offenen Vorgang bei Google
# verrechnet wird.
ZUSTAND = "verbinden_zustand"
ZUSTAND_KANAL = "verbinden_kanal"


def _kanal_zeile(key: str) -> Channel:
    eintrag = db.session.scalar(select(Channel).where(Channel.key == key))
    if eintrag is None or key not in BEKANNT:
        abort(404)
    return eintrag


def _konto(channel_id: int) -> Account | None:
    return db.session.scalars(
        select(Account).where(Account.channel_id == channel_id).order_by(Account.id)
    ).first()


def _zurueck():
    return redirect(url_for("haupt.einstellungen_seite"))


@verbinden.route("/<kanal_key>/verbinden", methods=["POST"])
@login_required
def starten(kanal_key: str):
    zeile = _kanal_zeile(kanal_key)
    if kanal_key not in AKTIV:
        flash(
            f"{zeile.name} ist noch nicht freigeschaltet und lässt sich nicht "
            "verbinden.",
            "fehler",
        )
        return _zurueck()

    zustand = secrets.token_urlsafe(32)
    try:
        ziel = kanal(kanal_key).anmelde_adresse(zustand)
    except KanalFehler as fehler:
        flash(str(fehler), "fehler")
        return _zurueck()

    # Erst nach der Adresse setzen: schlägt das Bauen fehl, soll kein
    # halber Vorgang in der Sitzung zurückbleiben.
    session[ZUSTAND] = zustand
    session[ZUSTAND_KANAL] = kanal_key
    current_app.logger.info("Verbinden gestartet: %s", kanal_key)
    return redirect(ziel)


@verbinden.route("/<kanal_key>/rueckruf")
@login_required
def rueckruf(kanal_key: str):
    """Die Adresse, die im Entwicklerbereich der Plattform steht.

    Angemeldet, obwohl die Plattform hierher zurückschickt: der Rückruf legt
    einen Zugang an, und das darf nur, wer auch sonst an dieser Anwendung
    etwas ändern dürfte.
    """
    zeile = _kanal_zeile(kanal_key)

    erwartet = session.pop(ZUSTAND, "")
    erwarteter_kanal = session.pop(ZUSTAND_KANAL, "")
    mitgeschickt = request.args.get("state", "")

    # Der Nutzer hat bei der Plattform abgebrochen. Kein Fehler, sondern eine
    # Entscheidung — und der Text kommt von dort, deshalb nur der Code.
    fehlercode = request.args.get("error")
    if fehlercode:
        flash(
            f"{zeile.name} hat das Verbinden abgelehnt oder es wurde dort "
            f"abgebrochen ({fehlercode}).",
            "fehler",
        )
        return _zurueck()

    if (
        not erwartet
        or erwarteter_kanal != kanal_key
        or not secrets.compare_digest(mitgeschickt, erwartet)
    ):
        # Bewusst ohne Einzelheiten: wer hier landet, ohne den Vorgang selbst
        # gestartet zu haben, soll nicht erfahren, woran es lag.
        current_app.logger.warning("Rückruf %s mit falschem Zustand", kanal_key)
        flash(
            "Der Vorgang passt nicht zu dieser Sitzung. Bitte noch einmal von "
            "vorn verbinden.",
            "fehler",
        )
        return _zurueck()

    code = request.args.get("code", "")
    if not code:
        flash(f"{zeile.name} hat keinen Code mitgeschickt.", "fehler")
        return _zurueck()

    try:
        felder = kanal(kanal_key).zugang_holen(code)
    except KanalFehler as fehler:
        flash(str(fehler), "fehler")
        return _zurueck()
    except Exception as fehler:  # noqa: BLE001
        # Ein Adapter darf werfen, was seine Bibliothek für richtig hält. Der
        # Nutzer soll dabei eine Seite sehen und keinen 500er.
        current_app.logger.exception("Rückruf %s gescheitert", kanal_key)
        flash(f"Das Verbinden ist gescheitert: {fehler}", "fehler")
        return _zurueck()

    konto = _konto(zeile.id)
    if konto is None:
        konto = Account(channel_id=zeile.id, access_token="")
        db.session.add(konto)

    konto.zugang = felder["zugang"]
    konto.erneuerung = felder.get("erneuerung") or ""
    konto.expires_at = felder.get("laeuft_ab")
    konto.account_name = felder.get("kontoname") or None
    db.session.commit()

    current_app.logger.info(
        "Konto verbunden: %s als %s", kanal_key, konto.account_name or "ohne Namen"
    )
    flash(
        f"{zeile.name} verbunden"
        + (f" als {konto.account_name}." if konto.account_name else "."),
        "erfolg",
    )
    return _zurueck()


@verbinden.route("/<kanal_key>/trennen", methods=["POST"])
@login_required
def trennen(kanal_key: str):
    zeile = _kanal_zeile(kanal_key)
    konto = _konto(zeile.id)
    if konto is None:
        flash(f"Für {zeile.name} ist nichts verbunden.", "fehler")
        return _zurueck()

    db.session.delete(konto)
    db.session.commit()
    current_app.logger.info("Konto getrennt: %s", kanal_key)
    # Was schon gepostet wurde, bleibt stehen. Nur der Zugang ist weg, und
    # der Zeitplan überspringt den Kanal ab jetzt wieder, statt zu scheitern.
    flash(
        f"{zeile.name} getrennt. Eingeplante Beiträge bleiben stehen und "
        "warten, bis wieder ein Konto verbunden ist.",
        "erfolg",
    )
    return _zurueck()


@verbinden.route("/<kanal_key>/ablagen")
@login_required
def ablagen(kanal_key: str):
    """Die Boards beziehungsweise Standorte des verbundenen Kontos.

    Zum Abschreiben der Kennungen: am Kanal einer Kampagne stehen sie bisher
    von Hand. Die Liste hier ist der Zwischenschritt dahin, dass die Maske
    sie selbst anbietet — vorher gab es nichts, wo man sie überhaupt hätte
    nachsehen können.
    """
    zeile = _kanal_zeile(kanal_key)
    adapter = kanal(kanal_key)
    konto = _konto(zeile.id)

    if konto is None:
        flash(f"Für {zeile.name} ist kein Konto verbunden.", "fehler")
        return _zurueck()
    if not adapter.unterstuetzt_ablagen:
        flash(f"{zeile.name} kennt keine {adapter.ablage_mehrzahl}.", "fehler")
        return _zurueck()

    try:
        gefunden = adapter.ablagen(konto.zugang)
    except KanalFehler as fehler:
        flash(str(fehler), "fehler")
        return _zurueck()
    except Exception as fehler:  # noqa: BLE001
        current_app.logger.exception("%s abrufen gescheitert", adapter.ablage_mehrzahl)
        flash(f"Abrufen gescheitert: {fehler}", "fehler")
        return _zurueck()

    return render_template(
        "ablagen.html",
        kanal=zeile,
        adapter=adapter,
        konto=konto,
        ablagen=gefunden,
    )
