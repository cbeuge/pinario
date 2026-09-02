"""Vektorisiert logo2.png. Zweiter Anlauf, mit echter Kurvenanpassung.

Ablauf: Farben trennen, Maske achtfach hochrechnen, Umriss als Pixelkante
verfolgen, Ecken finden, und zwischen zwei Ecken entweder eine Gerade oder
so wenige Bezier wie moeglich legen (siehe kurven.py).
"""
import math
from pathlib import Path

from PIL import Image

import kurven

QUELLE = str(Path(__file__).resolve().parent / 'logo2.png')
ZIEL = Path(__file__).resolve().parent / 'pfade.txt'

SKALA = 8            # Vergroesserung vor dem Tracen
ECKWINKEL = 48       # ab diesem Winkel gilt eine Stelle als Ecke
ECKFENSTER = 14      # Abstand der Vergleichspunkte, in 8x-Pixeln
GERADE = 2.4         # bis zu dieser Abweichung ist ein Abschnitt eine Gerade
TOLERANZ = 2.2       # erlaubter Kurvenfehler, 8x-Pixel (0,28 Originalpixel)

NAVY = (26, 26, 46)
ORANGE = (232, 89, 12)


def masken():
    im = Image.open(QUELLE).convert('RGB')
    W, H = im.size
    px = im.load()
    navy = Image.new('L', (W, H), 0)
    orange = Image.new('L', (W, H), 0)
    np_, op_ = navy.load(), orange.load()
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            deckung = 255 - min(255, int(round((r + g + b) / 3)))
            if deckung < 8:
                continue
            # Randpixel sind Mischungen mit Weiss. Erst auf volle Deckung
            # zurueckrechnen, dann nach Farbton zuordnen.
            sk = 255 / deckung
            rr = 255 - (255 - r) * sk
            gg = 255 - (255 - g) * sk
            bb = 255 - (255 - b) * sk
            dn = sum((a - c) ** 2 for a, c in zip((rr, gg, bb), NAVY))
            do = sum((a - c) ** 2 for a, c in zip((rr, gg, bb), ORANGE))
            if dn <= do:
                np_[x, y] = min(255, deckung)
            else:
                op_[x, y] = min(255, deckung)
    return navy, orange


def gitter_von(maske):
    W, H = maske.size
    gross = maske.resize((W * SKALA, H * SKALA), Image.BICUBIC)
    d = gross.load()
    return ([[1 if d[x, y] >= 128 else 0 for x in range(W * SKALA)]
             for y in range(H * SKALA)], W * SKALA, H * SKALA)


def konturen(gitter, W, H):
    """Kante zwischen gefuellt und leer verfolgen.

    Aussenkanten laufen im Uhrzeigersinn, Loecher gegen den Uhrzeigersinn.
    Zusammen mit fill-rule="evenodd" bleiben die Punzen von p, a und o offen.
    """
    def voll(x, y):
        return 0 <= x < W and 0 <= y < H and gitter[y][x]

    kanten = {}
    for y in range(H):
        for x in range(W):
            if not gitter[y][x]:
                continue
            if not voll(x, y - 1):
                kanten.setdefault((x, y), []).append((x + 1, y))
            if not voll(x + 1, y):
                kanten.setdefault((x + 1, y), []).append((x + 1, y + 1))
            if not voll(x, y + 1):
                kanten.setdefault((x + 1, y + 1), []).append((x, y + 1))
            if not voll(x - 1, y):
                kanten.setdefault((x, y + 1), []).append((x, y))

    schleifen = []
    while kanten:
        start = next(iter(kanten))
        weg, akt = [start], start
        while True:
            folge = kanten.get(akt)
            if not folge:
                break
            naechst = folge.pop()
            if not folge:
                del kanten[akt]
            weg.append(naechst)
            akt = naechst
            if akt == start:
                break
        if len(weg) > 8:
            schleifen.append([(float(x), float(y)) for x, y in weg[:-1]])
    return schleifen


def glaetten(schleife, fenster=3):
    """Gleitender Mittelwert ueber die Treppenstufen.

    Die Kante springt in ganzen Pixeln. Ohne diese Vorstufe misst die
    Eckensuche die Stufen statt der Form.
    """
    n = len(schleife)
    aus = []
    for i in range(n):
        xs = ys = 0.0
        for k in range(-fenster, fenster + 1):
            p = schleife[(i + k) % n]
            xs += p[0]
            ys += p[1]
        anzahl = 2 * fenster + 1
        aus.append((xs / anzahl, ys / anzahl))
    return aus


def ecken(schleife):
    """Stellen mit starkem Richtungswechsel, je Haeufung nur die schaerfste."""
    n = len(schleife)
    if n < 3 * ECKFENSTER:
        return []
    winkel = []
    for i in range(n):
        a = schleife[(i - ECKFENSTER) % n]
        p = schleife[i]
        b = schleife[(i + ECKFENSTER) % n]
        v1 = math.atan2(p[1] - a[1], p[0] - a[0])
        v2 = math.atan2(b[1] - p[1], b[0] - p[0])
        winkel.append(abs((math.degrees(v2 - v1) + 180) % 360 - 180))

    gefunden = []
    for i in range(n):
        if winkel[i] < ECKWINKEL:
            continue
        # nur das Maximum einer Haeufung behalten
        if all(winkel[i] >= winkel[(i + k) % n]
               for k in range(-ECKFENSTER, ECKFENSTER + 1)):
            if not gefunden or (i - gefunden[-1]) > ECKFENSTER // 2:
                gefunden.append(i)
    return gefunden


def _aufteilen(stellen, n):
    """Sorgt fuer mindestens vier Stuetzstellen und keine zu langen Bogen."""
    stellen = sorted(set(stellen))
    if len(stellen) < 4:
        anfang = stellen[0] if stellen else 0
        stellen = sorted({(anfang + round(k * n / 4)) % n for k in range(4)}
                         | set(stellen))
    grenze = n / 3
    while True:
        neu = []
        geteilt = False
        for k in range(len(stellen)):
            a, b = stellen[k], stellen[(k + 1) % len(stellen)]
            neu.append(a)
            laenge = (b - a) % n or n
            if laenge > grenze:
                neu.append((a + laenge // 2) % n)
                geteilt = True
        stellen = sorted(set(neu))
        if not geteilt:
            return stellen


def ist_gerade(punkte):
    a, b = punkte[0], punkte[-1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    laenge = math.hypot(dx, dy)
    if laenge == 0:
        return False
    weit = max(abs(dy * (p[0] - a[0]) - dx * (p[1] - a[1])) / laenge for p in punkte)
    return weit <= GERADE


def zahl(v):
    s = f'{v / SKALA:.2f}'
    return s.rstrip('0').rstrip('.') if '.' in s else s


def pfad(schleife):
    weich = glaetten(schleife)
    stellen = ecken(weich)
    n = len(weich)

    # Eine geschlossene Kurve laesst sich nicht als ein Abschnitt anpassen:
    # Anfang und Ende faellen zusammen, und die Ausgleichsrechnung hat dann
    # keine sinnvolle Richtung mehr. Deshalb werden Punzen und Ringe, die
    # gar keine Ecke haben, an vier Stellen aufgeteilt. Und kein Abschnitt
    # darf laenger als ein Drittel des Umfangs sein, sonst wird die
    # Tangentenschaetzung am Rand ungenau.
    echte_ecken = set(stellen)
    stellen = _aufteilen(stellen, n)

    abschnitte = []
    for k in range(len(stellen)):
        a, b = stellen[k], stellen[(k + 1) % len(stellen)]
        idx = []
        i = a
        while True:
            idx.append(i)
            if i == b:
                break
            i = (i + 1) % n
        abschnitte.append(idx)

    # Nur an echten Ecken wird der ungeglaettete Punkt genommen: dort muss
    # die Form scharf bleiben. An den zusaetzlich eingezogenen Stuetzstellen
    # waere der Rohpunkt nur die Treppenstufe und damit ein halber Pixel
    # Zittern mitten in einer glatten Kurve.
    def stuetze(i):
        return schleife[i] if i in echte_ecken else weich[i]

    teile = []
    erst = abschnitte[0][0]
    teile.append(f'M{zahl(stuetze(erst)[0])} {zahl(stuetze(erst)[1])}')

    for idx in abschnitte:
        rohpunkte = [weich[i] for i in idx]
        rohpunkte[0] = stuetze(idx[0])
        rohpunkte[-1] = stuetze(idx[-1])
        ziel = rohpunkte[-1]
        if len(rohpunkte) < 3 or ist_gerade(rohpunkte):
            teile.append(f'L{zahl(ziel[0])} {zahl(ziel[1])}')
            continue
        t1 = kurven._tangente(rohpunkte, 0)
        t2 = kurven._mul(kurven._tangente(rohpunkte, len(rohpunkte) - 1), -1)
        for steuer in kurven.anpassen(rohpunkte, t1, t2, TOLERANZ):
            teile.append(
                f'C{zahl(steuer[1][0])} {zahl(steuer[1][1])} '
                f'{zahl(steuer[2][0])} {zahl(steuer[2][1])} '
                f'{zahl(steuer[3][0])} {zahl(steuer[3][1])}')
    return ' '.join(teile) + 'Z'


def vektor(maske):
    gitter, W, H = gitter_von(maske)
    return ' '.join(pfad(s) for s in konturen(gitter, W, H))


if __name__ == '__main__':
    navy, orange = masken()
    bb_n, bb_o = navy.getbbox(), orange.getbbox()
    x0, y0 = min(bb_n[0], bb_o[0]), min(bb_n[1], bb_o[1])
    x1, y1 = max(bb_n[2], bb_o[2]), max(bb_n[3], bb_o[3])
    navy = navy.crop((x0, y0, x1, y1))
    d = vektor(navy)
    ZIEL.write_text(f'{x1 - x0} {y1 - y0}\nWORT\n{d}\n', encoding='utf-8')
    print('viewBox', x1 - x0, y1 - y0)
    print('Pfadlaenge', len(d), 'Zeichen,', d.count('C'), 'Kurven,', d.count('L'), 'Geraden')
