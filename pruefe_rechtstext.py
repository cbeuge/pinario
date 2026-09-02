"""Prueft den Saeuberer fuer Rechtstexte gegen die ueblichen Angriffe.

    venv\\Scripts\\python.exe pruefe_rechtstext.py

Warum es dieses Skript gibt: fuer das Saeubern von HTML wird sonst ein
fertiges Paket genommen. Hier steht es selbst geschrieben in
`app/rechtstext_saeubern.py`, und selbst geschriebene Saeuberer sind
beruehmt dafuer, still danebenzuliegen. Also wird es nachgemessen statt
geglaubt.

Laeuft trocken, ohne Datenbank und ohne Netz.
"""

import sys

from app.rechtstext_saeubern import saeubern

# (Beschreibung, Eingabe, was danach nicht mehr drinstehen darf)
ANGRIFFE = [
    ("Skript-Tag",
     '<p>Hallo</p><script>alert(1)</script>',
     ["<script", "alert(1)"]),
    ("Skript ueber Attribut",
     '<p onclick="alert(1)">Text</p>',
     ["onclick", "alert(1)"]),
    ("javascript: im Link",
     '<a href="javascript:alert(1)">klick</a>',
     ["javascript:"]),
    ("javascript: mit Steuerzeichen",
     '<a href="java\tscript:alert(1)">klick</a>',
     ["javascript:", "java\tscript"]),
    ("javascript: mit Zeilenumbruch",
     '<a href="java\nscript:alert(1)">klick</a>',
     ["javascript:"]),
    ("javascript: gross geschrieben",
     '<a href="JaVaScRiPt:alert(1)">klick</a>',
     ["JaVaScRiPt:", "javascript:"]),
    ("data: im Link",
     '<a href="data:text/html;base64,PHNjcmlwdD4=">klick</a>',
     ["data:text/html"]),
    ("vbscript: im Link",
     '<a href="vbscript:msgbox(1)">klick</a>',
     ["vbscript:"]),
    ("iframe",
     '<iframe src="https://fremd.example"></iframe>',
     ["<iframe", "fremd.example"]),
    ("object und embed",
     '<object data="x"></object><embed src="y">',
     ["<object", "<embed"]),
    ("style-Tag",
     '<style>body{display:none}</style><p>ok</p>',
     ["<style", "display:none"]),
    ("style-Attribut",
     '<p style="position:fixed;top:0">Text</p>',
     ["style=", "position:fixed"]),
    ("svg mit onload",
     '<svg onload="alert(1)"><circle /></svg>',
     ["<svg", "onload"]),
    ("img mit onerror",
     '<img src=x onerror="alert(1)">',
     ["<img", "onerror"]),
    ("verschachtelt getarnt",
     '<scr<script>ipt>alert(1)</script>',
     ["<script"]),
    ("Entitaet wird nicht wieder zum Tag",
     '&lt;script&gt;alert(1)&lt;/script&gt;',
     ["<script>"]),
    ("Kommentar",
     '<!-- <script>alert(1)</script> --><p>ok</p>',
     ["<script", "<!--"]),
    ("form und input",
     '<form action="https://fremd.example"><input name="pw"></form>',
     ["<form", "<input"]),
    ("base-Tag",
     '<base href="https://fremd.example/"><p>ok</p>',
     ["<base"]),
    ("meta refresh",
     '<meta http-equiv="refresh" content="0;url=https://fremd.example">',
     ["<meta", "refresh"]),
    ("id-Attribut",
     '<p id="etwas">Text</p>',
     ["id="]),
    ("class-Attribut von Quill",
     '<p class="ql-align-center">Text</p>',
     ["class="]),
]

# (Beschreibung, Eingabe, was danach noch drinstehen muss)
ERHALTEN = [
    ("Absatz", "<p>Ein Absatz.</p>", ["<p>", "Ein Absatz."]),
    ("Ueberschrift", "<h2>Datenschutz</h2>", ["<h2>", "Datenschutz"]),
    ("Liste", "<ul><li>eins</li><li>zwei</li></ul>", ["<ul>", "<li>", "eins"]),
    ("Fettdruck", "<p><strong>wichtig</strong></p>", ["<strong>", "wichtig"]),
    ("Zeilenumbruch", "<p>a<br>b</p>", ["<br>"]),
    ("Link mit https",
     '<a href="https://pinario.de/x" title="Ziel">hier</a>',
     ['href="https://pinario.de/x"', 'title="Ziel"', "hier"]),
    ("Link mit mailto",
     '<a href="mailto:carstenbeuge@gmail.com">Mail</a>',
     ["mailto:carstenbeuge@gmail.com"]),
    ("relativer Link", '<a href="/impressum">Impressum</a>', ['href="/impressum"']),
    ("Tabelle",
     "<table><tr><th>A</th><td>B</td></tr></table>",
     ["<table>", "<th>", "<td>"]),
    ("Umlaute bleiben",
     "<p>Datenschutzerklärung für Nutzer</p>",
     ["Datenschutzerklärung für Nutzer"]),
]

SONSTIGES = [
    ("target bekommt rel",
     '<a href="https://x.example" target="_blank">x</a>',
     lambda e: 'rel="noopener noreferrer"' in e),
    ("schiefes HTML wird geschlossen",
     "<p>offen<div>tiefer",
     lambda e: e.count("</p>") == 1 and e.count("</div>") == 1),
    ("leere Eingabe",
     "", lambda e: e == ""),
    ("reiner Text ohne Tags",
     "Nur Text", lambda e: e == "Nur Text"),
    ("spitze Klammer im Text wird escaped",
     "<p>a < b und c > d</p>",
     lambda e: "&lt;" in e and "&gt;" in e),
]


def main() -> int:
    fehler = 0
    print("Angriffe, die nicht durchkommen duerfen")
    for name, eingabe, verboten in ANGRIFFE:
        ergebnis = saeubern(eingabe)
        durchgerutscht = [v for v in verboten if v.lower() in ergebnis.lower()]
        if durchgerutscht:
            fehler += 1
            print(f"  FEHLER  {name}: {durchgerutscht} steht noch drin")
            print(f"          -> {ergebnis!r}")
        else:
            print(f"  ok      {name}")

    print()
    print("Inhalt, der erhalten bleiben muss")
    for name, eingabe, noetig in ERHALTEN:
        ergebnis = saeubern(eingabe)
        fehlt = [n for n in noetig if n not in ergebnis]
        if fehlt:
            fehler += 1
            print(f"  FEHLER  {name}: {fehlt} fehlt")
            print(f"          -> {ergebnis!r}")
        else:
            print(f"  ok      {name}")

    print()
    print("Sonderfaelle")
    for name, eingabe, pruefung in SONSTIGES:
        ergebnis = saeubern(eingabe)
        if not pruefung(ergebnis):
            fehler += 1
            print(f"  FEHLER  {name} -> {ergebnis!r}")
        else:
            print(f"  ok      {name}")

    print()
    if fehler:
        print(f"{fehler} Prüfung(en) fehlgeschlagen.")
    else:
        gesamt = len(ANGRIFFE) + len(ERHALTEN) + len(SONSTIGES)
        print(f"Alle {gesamt} Prüfungen bestanden.")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
