"""Säubert das HTML der Rechtstexte, bevor es in die Seite geht.

Warum überhaupt, wenn die Texte aus dem eigenen LegalHub kommen: sonst hinge
die Sicherheit von pinario an einer zweiten Anwendung auf einem anderen Host.
Und der Dateicache würde einen bösartigen Text festhalten, auch nachdem die
Quelle längst wieder sauber ist. Dieselbe Überlegung wie bei bestellone,
xtranu und startklar.tools, dort macht es `sanitize-html`.

**Erlaubnisliste, keine Sperrliste.** Der Text wird nicht gefiltert, sondern
neu zusammengesetzt: alles, was hier nicht ausdrücklich steht, existiert
danach nicht mehr. Roher HTML-Text kommt nirgends durch — jeder Textknoten
wird escaped, jeder Attributwert auch.

`style` und `class` stehen bewusst **nicht** in der Erlaubnisliste. Quill
setzt beides gern; die eigene CSP erlaubt aber kein Inline-CSS, das Attribut
würde also ohnehin still verworfen. Lieber gleich weg, dann sieht die Seite
lokal so aus wie auf dem Server.

Warum von Hand und nicht mit einem Paket: `nh3` wäre die naheliegende Wahl,
braucht aber ein passendes Wheel. Auf dem Server läuft Python 3.14, und ein
fehlendes Wheel bedeutet dort einen Rust-Übersetzer oder einen gescheiterten
Deploy. Der Bedarf hier ist eng genug, dass die Standardbibliothek reicht.
Belegt wird das durch `pruefe_rechtstext.py`, das die üblichen Angriffe
durchspielt.
"""

from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse

ERLAUBTE_TAGS = frozenset({
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "strong", "b", "em", "i", "u", "small", "sup", "sub",
    "a", "span", "div",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "blockquote", "pre", "code",
})

# Tags ohne schliessendes Gegenstueck.
LEERE_TAGS = frozenset({"br", "hr"})

# Attribute je Tag. Alles andere faellt weg, auch id, class und style.
ERLAUBTE_ATTRIBUTE = {"a": frozenset({"href", "title", "target", "rel"})}

ERLAUBTE_SCHEMATA = frozenset({"http", "https", "mailto", "tel"})

# Bei diesen Tags wird auch der Inhalt verworfen, nicht nur die Klammer.
# Der Text in einem <script> ist kein Text, den jemand lesen soll, und in
# einem <style> waere es CSS mitten im Absatz.
INHALT_VERWERFEN = frozenset({
    "script", "style", "textarea", "option", "noscript", "iframe", "template",
    "object", "embed", "svg", "math", "title", "head",
})


def _adresse_ok(wert: str) -> bool:
    """Nur die vier erlaubten Schemata, und relative Adressen.

    Der Wert wird vorher entschaerft: `java\\tscript:` und Konsorten leben
    davon, dass Browser Steuerzeichen im Schema ignorieren.
    """
    ohne_steuerzeichen = "".join(z for z in wert if ord(z) > 32 or z == " ")
    geputzt = ohne_steuerzeichen.strip().lower()
    if not geputzt:
        return False
    try:
        schema = urlparse(geputzt).scheme
    except ValueError:
        return False
    if not schema:
        # Relative Adresse wie /impressum oder #abschnitt. Erlaubt, solange
        # sie nicht doch wie ein Schema aussieht.
        return ":" not in geputzt.split("/")[0].split("?")[0].split("#")[0]
    return schema in ERLAUBTE_SCHEMATA


class _Saeuberer(HTMLParser):
    def __init__(self) -> None:
        # convert_charrefs: Entitaeten werden zu Text und danach von uns neu
        # escaped. Sonst koennte &lt;script&gt; im Ergebnis wieder zu einem
        # echten Tag zusammenwachsen.
        super().__init__(convert_charrefs=True)
        self.teile: list[str] = []
        self.offen: list[str] = []
        self._stumm = 0

    # --- Tags ----------------------------------------------------------

    def handle_starttag(self, tag, attrs):
        if tag in INHALT_VERWERFEN:
            self._stumm += 1
            return
        if self._stumm or tag not in ERLAUBTE_TAGS:
            return

        erlaubt = ERLAUBTE_ATTRIBUTE.get(tag, frozenset())
        gesetzt = {}
        for name, wert in attrs:
            name = (name or "").lower()
            if name not in erlaubt or wert is None:
                continue
            if name == "href" and not _adresse_ok(wert):
                continue
            gesetzt[name] = wert

        # Ein Link, der ein neues Fenster oeffnet, bekommt rel. Ohne das
        # kann die Zielseite ueber window.opener auf diese hier zugreifen.
        if tag == "a" and gesetzt.get("target"):
            gesetzt.setdefault("rel", "noopener noreferrer")

        text = "".join(
            f' {name}="{escape(wert, quote=True)}"' for name, wert in gesetzt.items()
        )
        if tag in LEERE_TAGS:
            self.teile.append(f"<{tag}{text}>")
        else:
            self.teile.append(f"<{tag}{text}>")
            self.offen.append(tag)

    def handle_endtag(self, tag):
        if tag in INHALT_VERWERFEN:
            self._stumm = max(0, self._stumm - 1)
            return
        if self._stumm or tag not in ERLAUBTE_TAGS or tag in LEERE_TAGS:
            return
        # Nur schliessen, was wir auch geoeffnet haben, und dabei alles
        # dazwischen mitschliessen. Sonst erzeugt schiefes Eingangs-HTML
        # schiefes Ausgangs-HTML.
        if tag not in self.offen:
            return
        while self.offen:
            offen = self.offen.pop()
            self.teile.append(f"</{offen}>")
            if offen == tag:
                break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in LEERE_TAGS and self.offen and self.offen[-1] == tag:
            self.offen.pop()
            self.teile.append(f"</{tag}>")

    # --- Inhalt --------------------------------------------------------

    def handle_data(self, data):
        if self._stumm:
            return
        self.teile.append(escape(data, quote=False))

    def handle_comment(self, data):
        """Kommentare fallen weg. In einem Rechtstext haben sie nichts zu
        suchen, und bedingte Kommentare sind ein alter Weg, Markup
        einzuschleusen."""

    def handle_decl(self, decl):
        """Doctype faellt weg."""

    def unknown_decl(self, data):
        """CDATA faellt weg."""

    def handle_pi(self, data):
        """Processing Instructions fallen weg."""

    def ergebnis(self) -> str:
        while self.offen:
            self.teile.append(f"</{self.offen.pop()}>")
        return "".join(self.teile)


def saeubern(html: str) -> str:
    if not html:
        return ""
    s = _Saeuberer()
    s.feed(html)
    s.close()
    return s.ergebnis()
