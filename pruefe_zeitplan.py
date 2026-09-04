"""Prueft das Rechnen des Zeitplans.

    venv\\Scripts\\python.exe pruefe_zeitplan.py

Warum es dieses Skript gibt: die Termine entstehen aus Uhrzeiten, einem
Zeitfenster und einer Zahl pro Tag, und der Server laeuft auf UTC waehrend
gepostet wird nach deutscher Zeit. Das sind genau die Zutaten, aus denen
still falsche Ergebnisse werden — ein Beitrag um 3 Uhr nachts faellt erst
auf, wenn er drausen ist.

Besonders die beiden Umstellungstage: an ihnen ist das Fenster von 09:00 bis
21:00 nicht zwoelf Stunden lang, sondern elf oder dreizehn. Wer mit
`timedelta(hours=...)` auf nackten Zeiten rechnet, merkt davon nichts und
verschiebt an dem Tag alles um eine Stunde.

Laeuft trocken: ohne Netz, ohne Datenbank. Das Verhalten gegen die Datenbank
(kein doppeltes Posten, Ueberspringen ohne Konto, Zurueckholen haengender
Eintraege) haengt an Postgres und steht im README.
"""

import sys
from datetime import date, timedelta

from app import create_app
from app.zeitplan import STANDARD_PRO_TAG, postet_am, slots

app = create_app()
fehler = 0

NORMAL = date(2026, 6, 17)          # ein gewoehnlicher Mittwoch
FRUEHJAHR = date(2026, 3, 29)       # Umstellung vor, der Tag hat 23 Stunden
HERBST = date(2026, 10, 25)         # Umstellung zurueck, der Tag hat 25
FENSTER = {"posts_per_day": 3, "time_window": ["09:00", "21:00"]}


def pruefe(name, bedingung, zusatz=""):
    global fehler
    if bedingung:
        print(f"  ok      {name}")
    else:
        fehler += 1
        print(f"  FEHLER  {name} {zusatz}")


def _uhrzeiten(tag, einstellungen):
    return [z.strftime("%H:%M") for z in slots(tag, einstellungen)]


with app.app_context():
    print("Ein gewoehnlicher Tag")
    drei = slots(NORMAL, FENSTER)
    pruefe("Drei Termine", len(drei) == 3, len(drei))
    pruefe("Gleichmaessig ab dem Beginn des Fensters",
           _uhrzeiten(NORMAL, FENSTER) == ["09:00", "13:00", "17:00"],
           _uhrzeiten(NORMAL, FENSTER))
    pruefe("Sie stehen in der Reihenfolge", drei == sorted(drei))
    pruefe("Berliner Zeitzone", str(drei[0].tzinfo) == "Europe/Berlin", drei[0].tzinfo)

    einer = slots(NORMAL, {"posts_per_day": 1, "time_window": ["09:00", "21:00"]})
    pruefe("Ein Termin liegt am Anfang des Fensters",
           einer[0].strftime("%H:%M") == "09:00", einer[0])

    viele = slots(NORMAL, {"posts_per_day": 12, "time_window": ["09:00", "21:00"]})
    pruefe("Zwoelf Termine im Stundentakt",
           [z.strftime("%H:%M") for z in viele][:3] == ["09:00", "10:00", "11:00"])
    pruefe("Der letzte liegt noch im Fenster",
           viele[-1].strftime("%H:%M") == "20:00", viele[-1])

    print()
    print("Die beiden Umstellungstage")
    fruehjahr = slots(FRUEHJAHR, FENSTER)
    herbst = slots(HERBST, FENSTER)
    pruefe("Im Fruehjahr faengt es trotzdem um 09:00 an",
           fruehjahr[0].strftime("%H:%M") == "09:00", fruehjahr[0])
    pruefe("Im Herbst faengt es trotzdem um 09:00 an",
           herbst[0].strftime("%H:%M") == "09:00", herbst[0])
    # Die Umstellung liegt nachts, das Fenster selbst ist an beiden Tagen
    # zwoelf Stunden lang. Geprueft wird deshalb, dass die Rechnung ueber
    # echte Zeitpunkte laeuft und nicht ueber nackte Uhrzeiten: sonst waere
    # der Abstand hier anders als an einem gewoehnlichen Tag.
    pruefe("Der Abstand bleibt derselbe wie sonst",
           (fruehjahr[1] - fruehjahr[0]) == (drei[1] - drei[0]) == timedelta(hours=4),
           fruehjahr[1] - fruehjahr[0])
    pruefe("Auch im Herbst",
           (herbst[1] - herbst[0]) == timedelta(hours=4), herbst[1] - herbst[0])
    pruefe("Alle Termine kennen ihren Versatz",
           all(z.utcoffset() is not None for z in fruehjahr + herbst))

    print()
    print("Kaputte Einstellungen")
    leer = slots(NORMAL, {})
    pruefe("Ohne Angaben gilt der Standard",
           len(leer) == STANDARD_PRO_TAG and leer[0].strftime("%H:%M") == "09:00",
           _uhrzeiten(NORMAL, {}))
    pruefe("Unsinn im Fenster faellt auf den Standard zurueck",
           _uhrzeiten(NORMAL, {"time_window": ["neun", "einundzwanzig"]})[0] == "09:00")
    pruefe("Fehlende Zahl faellt auf den Standard zurueck",
           len(slots(NORMAL, {"posts_per_day": None})) == STANDARD_PRO_TAG)
    pruefe("Unsinn als Zahl faellt auf den Standard zurueck",
           len(slots(NORMAL, {"posts_per_day": "drei"})) == STANDARD_PRO_TAG)
    pruefe("Null wird auf eins gehoben",
           len(slots(NORMAL, {"posts_per_day": 0})) == 1)
    pruefe("Zu viele werden gedeckelt",
           len(slots(NORMAL, {"posts_per_day": 999})) == 25)
    verdreht = slots(NORMAL, {"posts_per_day": 3, "time_window": ["21:00", "09:00"]})
    pruefe("Ein verdrehtes Fenster gibt genau einen Termin statt negativer Abstaende",
           len(verdreht) == 1, len(verdreht))

    print()
    print("Wochentage")
    # Mo 07.09.2026 bis So 13.09.2026.
    WOCHE = [date(2026, 9, 7) + timedelta(days=i) for i in range(7)]

    def _woche(einstellungen):
        """Beide Wege messen: die Frage allein nuetzt nichts, wenn die
        Termine sie nicht beachten."""
        gefragt = [postet_am(tag, einstellungen) for tag in WOCHE]
        gerechnet = [bool(slots(tag, einstellungen)) for tag in WOCHE]
        return gefragt if gefragt == gerechnet else [gefragt, gerechnet]

    pruefe("Mo und Do: nur an diesen beiden",
           _woche({"posts_per_day": 1, "weekdays": [0, 3]})
           == [True, False, False, True, False, False, False])
    pruefe("Nur Sonntag",
           _woche({"posts_per_day": 1, "weekdays": [6]})
           == [False] * 6 + [True])
    pruefe("Alle sieben ausdruecklich",
           _woche({"posts_per_day": 1, "weekdays": [0, 1, 2, 3, 4, 5, 6]})
           == [True] * 7)

    # Der teure Fall. Alles, was vor dem 04.09.2026 eingerichtet wurde, hat
    # das Feld gar nicht -- waere "leer" gleich "nie", hoerten diese Kanaele
    # stillschweigend auf zu posten, ohne dass jemand einen Fehler saehe.
    pruefe("Ohne Angabe gilt jeder Tag",
           _woche({"posts_per_day": 1}) == [True] * 7)
    pruefe("Eine leere Liste gilt auch als jeder Tag",
           _woche({"posts_per_day": 1, "weekdays": []}) == [True] * 7)
    pruefe("Unsinn faellt auf jeden Tag zurueck, nicht auf keinen",
           _woche({"posts_per_day": 1, "weekdays": ["Montag", 99, None]})
           == [True] * 7)

    am_montag = slots(WOCHE[0], {"posts_per_day": 3, "weekdays": [0]})
    pruefe("An einem gewaehlten Tag gelten die Uhrzeiten weiter",
           len(am_montag) == 3 and am_montag[0].hour == 9,
           am_montag)

print()
if fehler:
    print(f"{fehler} Prüfung(en) fehlgeschlagen.")
    sys.exit(1)
print("Alle Prüfungen bestanden.")
