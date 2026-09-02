"""Kleine Sicherheitshelfer: CSRF-Token und echte Client-IP."""

import hmac
import secrets

from flask import abort, request, session


def csrf_token() -> str:
    """Token der aktuellen Sitzung, wird beim ersten Aufruf erzeugt."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def csrf_pruefen() -> None:
    """Jede schreibende Anfrage muss den Token mitschicken."""
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    mitgeschickt = (
        request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    )
    erwartet = session.get("csrf_token", "")
    if not erwartet or not hmac.compare_digest(mitgeschickt, erwartet):
        abort(400, "Formular abgelaufen. Seite neu laden und noch einmal versuchen.")


def client_ip() -> str:
    """Die IP, die nginx durchreicht.

    x-real-ip zuerst, weil nginx den Wert selbst setzt. x-forwarded-for nur
    als Rückfall und dann der letzte Eintrag: die vorderen Einträge kann der
    Client frei erfinden, und die Anmeldebremse hinge sonst an einem Wert,
    den der Angreifer bei jedem Versuch ändern kann.
    """
    real = request.headers.get("X-Real-IP")
    if real:
        return real.strip()
    weitergereicht = request.headers.get("X-Forwarded-For")
    if weitergereicht:
        return weitergereicht.split(",")[-1].strip()
    return request.remote_addr or "unbekannt"
