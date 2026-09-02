"""Verzeichnis der Kanäle.

`AKTIV` steuert, was in der Oberfläche auswählbar ist. Instagram, Facebook
und X stehen bewusst schon als Zeile in der Datenbank, damit eine Kampagne
später ohne Migration dorthin ausgespielt werden kann — solange sie hier
nicht aktiv sind, tauchen sie nur ausgegraut auf.
"""

from .basis import Kanal, KanalFehler
from .pinterest import Pinterest

# Reihenfolge ist die Reihenfolge in der Oberfläche.
BEKANNT: dict[str, Kanal] = {
    "pinterest": Pinterest(),
}

# Was schon benutzt werden kann. Der Rest wird angezeigt, aber nicht
# angeboten.
AKTIV = ("pinterest",)

# Schlüssel und Anzeigename aller vorgesehenen Kanäle. Wird von der
# Migration benutzt, um `channels` zu füllen.
ALLE = (
    ("pinterest", "Pinterest"),
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("x", "X"),
)


def kanal(key: str) -> Kanal:
    if key not in BEKANNT:
        raise KanalFehler(f"Für '{key}' gibt es noch keinen Adapter.")
    return BEKANNT[key]


__all__ = ["AKTIV", "ALLE", "BEKANNT", "Kanal", "KanalFehler", "kanal"]
