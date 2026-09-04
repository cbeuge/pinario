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

X ist seit dem 04.09.2026 der letzte ohne Adapter. Die Zugangsfelder stehen
trotzdem schon da, siehe `ZUGANGSFELDER`.
"""

from .basis import Kanal, KanalFehler, Zugangsfeld
from .google_business import GoogleBusiness
from .meta import Facebook, Instagram
from .pinterest import Pinterest
from .threads import Threads

BEKANNT: dict[str, Kanal] = {
    "pinterest": Pinterest(),
    "google_business": GoogleBusiness(),
    "instagram": Instagram(),
    "facebook": Facebook(),
    "threads": Threads(),
}

# Facebook und Instagram sind ab dem 04.09.2026 dabei. Anders als bei
# Google gibt es hier nichts zu beantragen: solange nur eigene Konten
# bedient werden, reicht eine App im Entwicklungsmodus, und der App Review
# von Meta greift erst bei fremden Konten.
AKTIV = ("pinterest", "instagram", "facebook", "threads")

# Schlüssel und Anzeigename aller vorgesehenen Kanäle, in der Reihenfolge
# der Oberfläche. Wird von den Migrationen benutzt, um `channels` zu füllen,
# und von `flask kanaele-abgleichen`.
ALLE = (
    ("pinterest", "Pinterest"),
    ("google_business", "Google Business Profile"),
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("threads", "Threads"),
    ("x", "X"),
)


# Was jede Plattform aus ihrem Entwicklerbereich verlangt, damit die
# Anwendung sich dort überhaupt vorstellen darf. **Für alle fünf Kanäle**,
# nicht nur für die mit Adapter: die Angaben lassen sich eintragen, bevor
# der Adapter da ist, und dann ist beim Bauen schon alles hinterlegt.
#
# Die Liste steht hier und nicht in den einzelnen Adaptern, weil sie auch
# für die Kanäle gebraucht wird, für die es noch keine Datei gibt. Ein
# Adapter holt seine Werte über `einstellungen.kanal_wert`, nie direkt aus
# der Konfiguration.
#
# **`name` darf sich nicht mehr ändern**, daraus wird der Schlüssel in der
# Tabelle `einstellungen` gebaut. Ein neuer Name heißt: der alte Wert ist
# nicht weg, aber niemand findet ihn mehr.
ZUGANGSFELDER: dict[str, tuple[Zugangsfeld, ...]] = {
    "pinterest": (
        Zugangsfeld("app_id", "App-ID"),
        Zugangsfeld("app_secret", "App-Secret", geheim=True),
    ),
    "google_business": (
        Zugangsfeld("client_id", "Client-ID"),
        Zugangsfeld("client_secret", "Client-Secret", geheim=True),
    ),
    # Instagram und Facebook laufen beide über eine App im Meta-Entwickler-
    # bereich, und meistens ist es dieselbe. Trotzdem zwei getrennte Paare:
    # eine geteilte Zeile wäre eine Annahme über Metas Kontenlandschaft, die
    # heute stimmt und in zwei Jahren vielleicht nicht mehr. Zweimal
    # denselben Wert einzutragen kostet eine Minute, das Auseinandernehmen
    # später eine Migration.
    "instagram": (
        Zugangsfeld("app_id", "Meta-App-ID"),
        Zugangsfeld("app_secret", "App-Secret", geheim=True),
    ),
    "facebook": (
        Zugangsfeld("app_id", "Meta-App-ID"),
        Zugangsfeld("app_secret", "App-Secret", geheim=True),
    ),
    # Threads braucht eine **eigene** App, nicht die von Instagram oder
    # Facebook: im Meta-Entwicklerbereich ist das ein eigener
    # Anwendungsfall mit eigenen Schluesseln.
    "threads": (
        Zugangsfeld("app_id", "Threads-App-ID"),
        Zugangsfeld("app_secret", "App-Secret", geheim=True),
    ),
    "x": (
        Zugangsfeld("client_id", "Client-ID"),
        Zugangsfeld("client_secret", "Client-Secret", geheim=True),
    ),
}


def rueckruf_pfad(key: str) -> str:
    """Der Pfad, an den die Plattform nach dem Verbinden zurückschickt.

    Einheitlich gebaut, damit die Adresse schon feststeht, bevor es den
    Adapter gibt: sie muss im Entwicklerbereich der Plattform **zeichengenau**
    eingetragen sein, und das macht man dort einmal und nicht zweimal.
    """
    return f"/kanaele/{key}/rueckruf"


def rueckruf_adresse(key: str) -> str:
    """Die volle Rückruf-Adresse, so wie sie beim Anbieter stehen muss.

    **Die einzige Quelle dafür.** Der Adapter schickt sie beim Anmelden und
    noch einmal beim Eintauschen des Codes mit, die Einstellungen-Seite zeigt
    sie zum Abschreiben an — und alle drei müssen zeichengenau dasselbe sein,
    sonst weist Pinterest den Rückruf ab. Sie aus `request.url_root` zu bauen
    sieht bequemer aus, liefert aber je nach aufgerufenem Namen einen anderen
    Wert (mit und ohne `www`) und damit einen, der bei der Plattform nicht
    hinterlegt ist.
    """
    from flask import current_app

    return current_app.config["OEFFENTLICHE_ADRESSE"] + rueckruf_pfad(key)


def kanal(key: str) -> Kanal:
    if key not in BEKANNT:
        raise KanalFehler(f"Für '{key}' gibt es noch keinen Adapter.")
    return BEKANNT[key]


__all__ = [
    "AKTIV",
    "ALLE",
    "BEKANNT",
    "ZUGANGSFELDER",
    "Kanal",
    "KanalFehler",
    "Zugangsfeld",
    "kanal",
    "rueckruf_adresse",
    "rueckruf_pfad",
]
