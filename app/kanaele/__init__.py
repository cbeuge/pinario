"""Verzeichnis der Kanäle.

Drei Listen, die absichtlich nicht dasselbe sind:

* `ALLE` sind die Zeilen in der Tabelle `channels`. Sie stehen dort, damit
  eine Kampagne später ohne Migration dorthin ausgespielt werden kann.
* `BEKANNT` sind die, für die es einen Adapter gibt.
* `AKTIV` sind die, die in der Oberfläche ausgewählt werden können. Der Rest
  wird angezeigt, aber ausgegraut.

Google Business Profile hat einen Adapter, ist aber nicht aktiv: der
API-Zugang muss bei Google erst beantragt und freigeschaltet werden, und bis
dahin führt jede Auswahl nur zu einem 403. Das ist kein Versehen, sondern
der Unterschied zwischen "gebaut" und "benutzbar".
"""

from .basis import Kanal, KanalFehler
from .google_business import GoogleBusiness
from .pinterest import Pinterest

BEKANNT: dict[str, Kanal] = {
    "pinterest": Pinterest(),
    "google_business": GoogleBusiness(),
}

AKTIV = ("pinterest",)

# Schlüssel und Anzeigename aller vorgesehenen Kanäle, in der Reihenfolge
# der Oberfläche. Wird von den Migrationen benutzt, um `channels` zu füllen,
# und von `flask kanaele-abgleichen`.
ALLE = (
    ("pinterest", "Pinterest"),
    ("google_business", "Google Business Profile"),
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("x", "X"),
)


def kanal(key: str) -> Kanal:
    if key not in BEKANNT:
        raise KanalFehler(f"Für '{key}' gibt es noch keinen Adapter.")
    return BEKANNT[key]


__all__ = ["AKTIV", "ALLE", "BEKANNT", "Kanal", "KanalFehler", "kanal"]
