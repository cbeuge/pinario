"""Baut aus logo2.png die fertigen Marken-Dateien.

    venv\\Scripts\\python.exe marke_quelle\\bauen.py

Schreibt nach app/static/marke:

    pinario.svg          Wortmarke dunkel, für helle Flächen
    pinario-dunkel.svg   Wortmarke weiß, für dunkle Flächen
    pinario-auto.svg     richtet sich nach dem Farbschema des Geräts
    favicon.svg          p auf dunkler Kachel
    pinario-dunkel.png   Raster für Stellen ohne SVG (Pinterest, OG-Bild)
    pinario.png

Warum aus einem Bild und nicht aus einer Schriftdatei: die Vorlage war ein
PNG, und welche Schrift darin steckt, weiß niemand mehr. Arial Bold kommt
auf 1,6 % Abweichung heran, unterscheidet sich aber sichtbar am 'a' und am
'r'. Der Umriss wird deshalb aus dem Bild gelesen (siehe trace.py und
kurven.py) und dabei mit echter Kurvenanpassung geglättet. Gegen das
Original nachgemessen: 99,4 % Deckung, die Abweichung sind einzelne
Randpixel.

Die orangen Teile werden nicht getract. Es sind fünf exakte Rechtecke, und
die stehen als Rechtecke im SVG statt als Viereck mit 0,2 Pixel Schräglage.
"""

import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

HIER = Path(__file__).resolve().parent
ZIEL = HIER.parent / "app" / "static" / "marke"

DUNKEL = "#1a1a2e"
ORANGE = "#e8590c"
WEISS = "#ffffff"

# Aus dem Original ausgemessen, Füllgrad jeweils 1,000.
AKZENT = [
    (60, 1, 12, 12),      # Punkt über dem ersten i
    (60, 21, 12, 49),     # Stamm des ersten i
    (231, 1, 12, 12),     # Punkt über dem zweiten i
    (231, 21, 12, 49),    # Stamm des zweiten i
    (20, 81, 283, 10),    # Unterstrich
]


def pfade_holen():
    """Tracet neu, falls pfade.txt fehlt oder älter ist als die Vorlage."""
    datei = HIER / "pfade.txt"
    vorlage = HIER / "logo2.png"
    if not datei.exists() or datei.stat().st_mtime < vorlage.stat().st_mtime:
        subprocess.run([sys.executable, str(HIER / "trace.py")], check=True, cwd=HIER)
    zeilen = datei.read_text(encoding="utf-8").splitlines()
    breite, hoehe = (int(v) for v in zeilen[0].split())
    return breite, hoehe, zeilen[2]


BREITE, HOEHE, WORT = pfade_holen()


def teilpfade(d):
    return ["M" + t for t in d.split("M") if t.strip()]


def kasten(teil):
    zahlen = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", teil)]
    return min(zahlen[0::2]), min(zahlen[1::2]), max(zahlen[0::2]), max(zahlen[1::2])


def rechtecke(farbe):
    zeilen = [
        f'    <rect x="{x}" y="{y}" width="{b}" height="{h}"/>'
        for x, y, b, h in AKZENT
    ]
    return f'  <g fill="{farbe}">\n' + "\n".join(zeilen) + "\n  </g>"


def wortmarke(schriftfarbe):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BREITE} {HOEHE}"'
        ' role="img" aria-label="pinario">\n'
        "  <title>pinario</title>\n"
        f'  <path fill="{schriftfarbe}" fill-rule="evenodd" d="{WORT}"/>\n'
        f"{rechtecke(ORANGE)}\n</svg>\n"
    )


def rastern(d, groesse, schriftfarbe, ueber=3):
    """Zeichnet die Pfade selbst, ohne SVG-Renderer.

    Kurven werden in Geraden zerlegt und die Teilflächen per XOR verrechnet,
    was der Even-Odd-Regel des SVG entspricht: die Punzen von p, a und o
    bleiben offen.
    """
    faktor = groesse / BREITE
    W = int(BREITE * faktor * ueber)
    H = int(HOEHE * faktor * ueber)
    maske = Image.new("1", (W, H), 0)
    for poly in _polygone(d):
        eins = Image.new("1", (W, H), 0)
        ImageDraw.Draw(eins).polygon(
            [(x * faktor * ueber, y * faktor * ueber) for x, y in poly], fill=1
        )
        maske = ImageChops.logical_xor(maske, eins)

    bild = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bild.paste(Image.new("RGBA", (W, H), schriftfarbe), (0, 0), maske)
    zeichner = ImageDraw.Draw(bild)
    for x, y, b, h in AKZENT:
        zeichner.rectangle(
            [x * faktor * ueber, y * faktor * ueber,
             (x + b) * faktor * ueber - 1, (y + h) * faktor * ueber - 1],
            fill=(232, 89, 12, 255),
        )
    return bild.resize((int(BREITE * faktor), int(HOEHE * faktor)), Image.LANCZOS)


def _polygone(d):
    marken = re.findall(r"([MLCZ])([^MLCZ]*)", d)
    aus, akt, start, letzt = [], [], None, (0.0, 0.0)
    for befehl, rest in marken:
        z = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", rest)]
        if befehl == "M":
            if len(akt) > 2:
                aus.append(akt)
            letzt = start = (z[0], z[1])
            akt = [letzt]
        elif befehl == "L":
            letzt = (z[0], z[1])
            akt.append(letzt)
        elif befehl == "C":
            p0, p1, p2, p3 = letzt, (z[0], z[1]), (z[2], z[3]), (z[4], z[5])
            for i in range(1, 25):
                t = i / 24
                u = 1 - t
                akt.append((
                    u ** 3 * p0[0] + 3 * u * u * t * p1[0]
                    + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
                    u ** 3 * p0[1] + 3 * u * u * t * p1[1]
                    + 3 * u * t * t * p2[1] + t ** 3 * p3[1],
                ))
            letzt = p3
        elif befehl == "Z":
            if start:
                akt.append(start)
            if len(akt) > 2:
                aus.append(akt)
            akt = []
    if len(akt) > 2:
        aus.append(akt)
    return aus


def main() -> None:
    ZIEL.mkdir(parents=True, exist_ok=True)
    (ZIEL / "pinario.svg").write_text(wortmarke(DUNKEL), encoding="utf-8")
    (ZIEL / "pinario-dunkel.svg").write_text(wortmarke(WEISS), encoding="utf-8")

    # Passt sich dem Farbschema des Geräts an. Eine Media Query im SVG wirkt
    # auch dann, wenn die Datei über <img> eingebunden ist.
    auto = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BREITE} {HOEHE}"'
        ' role="img" aria-label="pinario">\n'
        "  <title>pinario</title>\n"
        "  <style>\n"
        f"    .wort {{ fill: {DUNKEL}; }}\n"
        f"    @media (prefers-color-scheme: dark) {{ .wort {{ fill: {WEISS}; }} }}\n"
        "  </style>\n"
        f'  <path class="wort" fill-rule="evenodd" d="{WORT}"/>\n'
        f"{rechtecke(ORANGE)}\n</svg>\n"
    )
    (ZIEL / "pinario-auto.svg").write_text(auto, encoding="utf-8")

    # Favicon: das p aus der Wortmarke auf dunkler Kachel, darunter der
    # orange Strich. Eine Kachel wirkt auf hellem wie auf dunklem Grund,
    # deshalb braucht das Symbol keine zweite Fassung.
    p_teile = [t for t in teilpfade(WORT) if kasten(t)[2] <= 52]
    k = [kasten(t) for t in p_teile]
    px0, py0 = min(v[0] for v in k), min(v[1] for v in k)
    px1, py1 = max(v[2] for v in k), max(v[3] for v in k)
    p_breite, p_hoehe = px1 - px0, py1 - py0

    kachel = 64
    s = (kachel * 0.62) / p_hoehe
    vx = (kachel - p_breite * s) / 2 - px0 * s
    vy = (kachel - (p_hoehe + 14) * s) / 2 - py0 * s

    favicon = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {kachel} {kachel}"'
        ' role="img" aria-label="pinario">\n'
        "  <title>pinario</title>\n"
        f'  <rect width="{kachel}" height="{kachel}" rx="14" fill="{DUNKEL}"/>\n'
        f'  <path fill="{WEISS}" fill-rule="evenodd"'
        f' transform="translate({vx:.3f} {vy:.3f}) scale({s:.5f})"'
        f' d="{" ".join(p_teile)}"/>\n'
        f'  <rect x="{vx + (px0 - 3) * s:.2f}" y="{vy + (py1 + 4) * s:.2f}"'
        f' width="{(p_breite + 6) * s:.2f}" height="{6 * s:.2f}"'
        f' rx="{1.5 * s:.2f}" fill="{ORANGE}"/>\n</svg>\n'
    )
    (ZIEL / "favicon.svg").write_text(favicon, encoding="utf-8")

    # Raster mit Transparenz, 1200 px breit. Für Stellen, die kein SVG
    # nehmen: Pinterest-Profil, Vorschaubilder, Grafiken.
    rastern(WORT, 1200, (255, 255, 255, 255)).save(ZIEL / "pinario-dunkel.png")
    rastern(WORT, 1200, (26, 26, 46, 255)).save(ZIEL / "pinario.png")

    for datei in sorted(ZIEL.iterdir()):
        print(f"{datei.name:22s} {datei.stat().st_size:>7} Bytes")


if __name__ == "__main__":
    main()
