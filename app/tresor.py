"""Verschlüsselt die OAuth-Token der Kanäle, bevor sie in die Datenbank gehen.

Warum überhaupt: ein Pinterest-Zugangstoken erlaubt jedem, der ihn hat, im
Namen des Kontos zu posten und zu löschen. In der Datenbank liegt er neben
allem anderen, und Sicherungen wandern verschlüsselt, aber lesbar zu
All-Inkl. Mit dieser Schicht ist der Token dort nur ein Haufen Zeichen; der
Schlüssel steht in der .env und nicht in der Sicherung der Datenbank.

Aufruf von der Kommandozeile, um einen neuen Schlüssel zu erzeugen:

    venv\\Scripts\\python.exe -m app.tresor neu
"""

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


class TresorFehler(RuntimeError):
    pass


def _fernet() -> Fernet:
    schluessel = current_app.config.get("TRESOR_SCHLUESSEL", "")
    if not schluessel:
        raise TresorFehler(
            "TRESOR_SCHLUESSEL fehlt in der .env. Erzeugen mit "
            "`python -m app.tresor neu`."
        )
    try:
        return Fernet(schluessel.encode())
    except (ValueError, TypeError) as fehler:
        raise TresorFehler(
            "TRESOR_SCHLUESSEL ist kein gültiger Fernet-Schlüssel."
        ) from fehler


def einschliessen(klartext: str) -> str:
    if not klartext:
        return ""
    return _fernet().encrypt(klartext.encode()).decode()


def aufschliessen(geheim: str) -> str:
    """Entschlüsselt einen Wert.

    Ein Fehler hier heißt fast immer: der TRESOR_SCHLUESSEL wurde gewechselt.
    Dann sind alle gespeicherten Zugänge unlesbar und die Kanäle müssen neu
    verbunden werden. Deshalb wird das deutlich gesagt statt still ein leerer
    Token zurückgegeben, mit dem das Posten später ohne Grund scheitert.
    """
    if not geheim:
        return ""
    try:
        return _fernet().decrypt(geheim.encode()).decode()
    except InvalidToken as fehler:
        raise TresorFehler(
            "Ein gespeicherter Zugang lässt sich nicht entschlüsseln. "
            "Wurde TRESOR_SCHLUESSEL geändert? Dann müssen die Kanäle unter "
            "Einstellungen neu verbunden werden."
        ) from fehler


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "neu":
        print(Fernet.generate_key().decode())
    else:
        print(__doc__)
