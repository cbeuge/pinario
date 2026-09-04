# pinario

Kampagnengesteuertes Erstellen und Posten von Social-Media-Inhalten. Zweck
ist, die eigenen Werkzeuge (welcometap, LeadRadar, gehdirekt, startklar.tools,
Sektor-V) bekannter zu machen und Affiliate-Produkte zu bewerben. Kein
Kundenmaterial, keine echten Fotos von Menschen.

Eine **Kampagne** hat einen Ziel-Link und wird auf mehrere Kanäle
ausgespielt. Je Kanal entstehen mehrere **Varianten** desselben Inhalts:
damit Pinterest keine Dubletten sieht, und damit sich messen lässt, welche
Variante zieht. Dazu kommt bei manchen Kanälen ein Ort innerhalb des
Kontos: Boards bei Pinterest, Standorte bei Google Business Profile.

**Vier von sechs Kanälen haben einen Adapter**: Pinterest, Facebook,
Instagram und Threads. Facebook ist seit dem 04.09.2026 wirklich verbunden
und damit als einziger gegen die echte API belegt. Pinterest wartet auf die
Freischaltung des Trial-Zugriffs, Google Business Profile auf einen Antrag
bei Google, und X hat noch keinen Adapter.

**Google Business Profile ist der Ausreißer unter den Kanälen** und
verdient zwei Sätze. Er erreicht Leute, die *das Unternehmen* suchen, nicht
Leute, die nach einem Thema stöbern. Für die eigenen Werkzeuge ist er
deshalb genau richtig, für Affiliate-Produkte nicht — und das ist keine
Geschmacksfrage: Googles Richtlinien sind bei werblichen Fremdlinks im
Unternehmensprofil streng, und die Folge ist im Zweifel ein gesperrter
Eintrag. Der Kanal trägt deshalb `affiliate_erlaubt = False`
(`app/kanaele/basis.py`), damit die Regel an einer Stelle lebt statt als
Sonderfall in der Kampagnen-Maske.

## Stand am 04.09.2026

**Live unter https://pinario.de.** Gebaut:

* Marke als SVG in hell, dunkel und selbst umschaltend, dazu Favicon und
  PNG-Raster. Erzeugt aus `marke_quelle/logo2.png`, siehe unten
* Startseite: nur Wortmarke und Passwortfeld. Ein Nutzer, kein
  Registrierungs-Weg, Bremse nach fünf Fehlversuchen
* Datenmodell vollständig. `0001_grundgeruest` legt alle Tabellen an und
  trägt die ersten vier Kanäle ein, `0002_google_business` den fünften
* Übersicht hinter der Anmeldung, dazu Kampagnen anlegen, bearbeiten und
  löschen. Je Kampagne lässt sich ein Kanal einschalten, mit Beiträgen pro
  Tag, Zeitfenster und Board-Kennungen
* Verschlüsselung für die OAuth-Token (`app/tresor.py`)
* Kanal-Schnittstelle (`app/kanaele/basis.py`), dazu Pinterest und Google
  Business Profile als Adapter-Gerüst
* Lokale Datenbank steht, Anmeldung von Anfang bis Ende durchgespielt —
  auf dem Server am 03.09.2026 ebenfalls, über die echte Adresse
* Impressum und Datenschutz unter `/impressum` und `/datenschutz`, Texte aus
  LegalHub (Slug `pinariode`). Öffentlich erreichbar, weil Pinterest beim
  Anlegen einer App eine Datenschutz-Adresse verlangt. **Beide Texte stehen
  seit dem 03.09.2026 vollständig**, die Datenschutzerklärung ist eigens für
  pinario geschrieben und nicht aus einer anderen Marke kopiert
* **Varianten erzeugen** über Gemini (`app/ki.py`, Ansicht
  `/kanal/<id>/varianten`). Je Kampagnenkanal ein Schwung Vorschläge, alle
  mit derselben `variant_group`, dazu die Anfrage an der Variante. Bearbeiten,
  freigeben, zurückziehen, löschen. Bilder wahlweise dazu
* **Einstellungen** unter `/einstellungen`: Gemini-Schlüssel eintragen,
  prüfen und entfernen, die Zugangsdaten aller fünf Kanäle, dazu das eigene
  Passwort ändern
* **Zeitplan** (`app/zeitplan.py`, Ansicht `/zeitplan`): freigegebene
  Varianten bekommen Termine, ein systemd-Timer schickt sie raus
* **Konto verbinden** (`app/verbinden.py`): OAuth hin und zurück, Konto
  trennen, Boards des verbundenen Kontos ansehen. Dazu der
  **Pinterest-Adapter vollständig** — Code eintauschen, Zugang erneuern,
  Boards lesen, Pin schreiben, Zahlen holen. Gegen die echte API ist davon
  noch nichts gelaufen, dafür fehlt die App bei Pinterest
* **Facebook und Instagram** (`app/kanaele/meta.py`), beide über die Graph
  API. Anders als bei Pinterest wartet man hier auf niemanden: für eigene
  Konten reicht eine App im Entwicklungsmodus
* **Threads** (`app/kanaele/threads.py`), eigener Host und eigene App.
  Damit haben vier von fünf Kanälen einen Adapter, nur X fehlt
* `www.pinario.de` leitet per 301 auf die Hauptadresse um, das Zertifikat
  deckt beide Namen ab

**Eine Regel, die man kennen muss:** eine Kampagne, die schon gepostet hat,
lässt sich nicht löschen — die Datenbank weist es ab. Die Messreihe ist der
Zweck der Anwendung, und sie beim Aufräumen stillschweigend mitzunehmen wäre
der teuerste Knopf im Programm. Kampagnen werden auf `paused` gesetzt. Eine
Kampagne ohne Veröffentlichungen lässt sich normal löschen. Ausführlich im
Docstring von `PostedItem`.

Noch nicht gebaut:

* **Video posten.** Erzeugen ginge — Veo ist über den Gemini-Schlüssel
  verfügbar —, aber es kostet 0,15 bis 0,40 $ pro Sekunde, und der Upload
  zur Plattform ist überall ein eigener mehrstufiger Weg. Eigene Videos
  lassen sich seit dem 04.09.2026 hochladen; sobald ein Kanal Video posten
  kann, kommt `video` in seine `typen`
* **Einen Beitrag wirklich rausschicken.** Verbinden, Seiten lesen und
  Varianten stehen; `veroeffentlichen` ist bei keinem Kanal gegen die echte
  API gelaufen
* Pinterest: der Trial-Zugriff ist bei Pinterest beantragt und nicht
  freigeschaltet, jeder Aufruf gibt Code 3
* Google Business Profile: Zugang bei Google nicht beantragt, siehe unten
* Auswertung der Zahlen je Variante

## Aufbau

```
app/
  __init__.py     App-Fabrik, Sicherheits-Header, Protokoll
  config.py       alles aus der .env, an einer Stelle
  models.py       Datenmodell
  auth.py         Anmeldung, Anmeldebremse
  sicherheit.py   CSRF-Token, echte Client-IP hinter nginx
  tresor.py       verschlüsselt die OAuth-Token
  zeit.py         Zeitzone an einer einzigen Stelle
  views.py        Seiten hinter der Anmeldung, dazu die Rechtstexte
  rechtstexte.py  holt Impressum und Datenschutz aus LegalHub, mit Cache
  rechtstext_saeubern.py  Erlaubnisliste für das HTML von dort
  cli.py          `flask passwort`, `flask kanaele-abgleichen`
  formular.py     prüft Eingaben, liefert Sätze statt Ausnahmen
  ki.py           baut die Anfrage an Gemini und prüft, was zurückkommt
  zeitplan.py     Termine vergeben und fällige Beiträge rausschicken
  einstellungen.py  Werte, die sich im Betrieb ändern, geheime verschlüsselt
  verbinden.py    OAuth: Konto verbinden, trennen, Ablagen ansehen
  kanaele/        ein Adapter je Plattform
                  basis.py            was ein Kanal können muss
                  pinterest.py        Pinterest API v5
                  meta.py             Facebook-Seiten und Instagram
                  threads.py          Threads
                  google_business.py  Google Business Profile
marke_quelle/     Vorlage und Werkzeug für die Logo-Dateien
betrieb/          systemd-Unit und nginx-Konfiguration
migrations/       Alembic
pruefe_rechtstext.py  misst den HTML-Säuberer nach (37 Fälle)
pruefe_ki.py          misst die Anfragen an Gemini nach (48 Fälle)
pruefe_zeitplan.py    misst Termine und Wochentage nach (28 Fälle)
pruefe_pinterest.py   misst den Pinterest-Adapter nach, ohne Netz (67 Fälle)
pruefe_meta.py        misst Facebook und Instagram nach, ohne Netz (87 Fälle)
pruefe_threads.py     misst den Threads-Adapter nach, ohne Netz (61 Fälle)
pruefe_verbinden.py   misst Verbinden, Ablagen und Upload nach, braucht die
                      Datenbank (73 Fälle)
```

## Lokal starten

Einmalig:

```
py -3 -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

In die `.env` gehören dann:

```
venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"   SECRET_KEY
venv\Scripts\python.exe -m app.tresor neu                                   TRESOR_SCHLUESSEL
```

Die Datenbank steht am Entwicklungsrechner schon: `pinario`, angelegt am
02.09.2026. Danach nur noch:

```
venv\Scripts\python.exe -m alembic upgrade head
venv\Scripts\python.exe wsgi.py
```

Läuft auf http://127.0.0.1:5001. Port 5001, weil betmaster lokal auf 5000
liegt.

**`OEFFENTLICHE_ADRESSE` bleibt dabei auf `https://pinario.de`**, auch lokal.
Daraus wird die Rückruf-Adresse gebaut, die auf der Einstellungen-Seite zum
Abschreiben steht — und abgeschrieben wird sie in den Entwicklerbereich der
Plattform, wo genau eine Adresse hinterlegt ist. Stünde hier `localhost`,
trüge man dort die falsche ein.

**Lokal gehört die Datenbank der Rolle `bestellone`, nicht einer eigenen
Rolle `pinario`.** Das ist Absicht und folgt dem, was auf diesem Rechner
schon da war: `bestellone`, `betmaster`, `startklar` und `xtranu` gehören
alle derselben Arbeitsrolle. Eine eigene Rolle anzulegen bräuchte den
Superuser, und dessen Passwort hat auf dem Entwicklungsrechner keinen
Mehrwert — getrennt werden die Projekte dort, wo es zählt, nämlich auf dem
Server. Wer es lokal trotzdem sauber trennen will:

```
psql -U postgres -c "CREATE ROLE pinario LOGIN PASSWORD 'eigenes'"
psql -U postgres -d pinario -c "ALTER DATABASE pinario OWNER TO pinario"
psql -U postgres -d pinario -c "GRANT ALL ON SCHEMA public TO pinario"
```

Das lokale Anmeldepasswort steht in `.passwort-lokal.txt`, gewürfelt und
nicht im Repository. Ändern:

```
venv\Scripts\python.exe -m flask --app wsgi passwort
```

**Die `.env` gehört nicht ins Repository.** Sie steht in `.gitignore`,
zusammen mit `.passwort-lokal.txt`.

### Pushen

`ssh.exe` kann auf diesem Rechner `github.com` nicht auflösen, alles andere
schon (`git ls-remote https://...` läuft normal). Deshalb geht ein Push über
die IP, mit `HostKeyAlias`, damit der Hostschlüssel weiter gegen den
bekannten `github.com`-Eintrag geprüft wird:

```
Resolve-DnsName github.com -Type A
GIT_SSH_COMMAND='ssh -o HostKeyAlias=github.com' git push git@<IP>:cbeuge/pinario.git main
```

Die IP ändert sich, deshalb steht als `origin` weiter die normale Adresse.

## Rechtstexte

`/impressum` und `/datenschutz` sind öffentlich, ohne Anmeldung, und von
jeder Seite aus verlinkt. Das Impressum muss das sein; die
Datenschutzerklärung zusätzlich, weil **Pinterest beim Anlegen einer App
eine erreichbare Datenschutz-Adresse verlangt** — ohne die geht die
Registrierung dort gar nicht erst los.

Die Texte kommen aus LegalHub (`legal.carstenbeuge.de`), wie bei allen
anderen Marken. **Nie eine zweite Fassung im Projekt ablegen**, sonst laufen
zwei Fassungen auseinander und die falsche steht online.

Der Domain-Slug dort muss `pinariode` heißen, analog zu `bestellonede` und
`startklartools`. **Solange er in LegalHub nicht angelegt ist**, liefert die
API 404 und die Seite zeigt einen Platzhalter — der Rest der Seite
funktioniert normal.

Ein Cache jünger als 24 Stunden wird genommen, sonst wird frisch geholt.
Schlägt der Abruf fehl, gilt der letzte bekannte Stand: Impressum und
Datenschutz dürfen nie leer sein, auch nicht während LegalHub neu startet.
Der Cache liegt unter `cache/legal/` neben der Anwendung, damit ein Deploy
ihn nicht wegräumt.

### Warum das HTML von dort geputzt wird

LegalHub liefert HTML aus einem Rich-Text-Editor. Ungeputzt hinge die
Sicherheit von pinario an einer zweiten Anwendung auf einem anderen Host,
und der Dateicache würde einen bösartigen Text festhalten, auch nachdem
die Quelle wieder sauber ist. In den Next-Projekten macht das
`sanitize-html`; hier steht es in `app/rechtstext_saeubern.py`.

**Selbst geschrieben statt `nh3` genommen**, weil auf dem Server Python 3.14
läuft und ein fehlendes Wheel dort einen Rust-Uebersetzer oder einen
gescheiterten Deploy bedeutet. Der Bedarf ist eng genug, dass die
Standardbibliothek reicht: Erlaubnisliste, alles wird neu zusammengesetzt,
jeder Text- und Attributwert escaped.

Selbst geschriebene Säuberer liegen berühmt still daneben, deshalb wird es
nachgemessen statt geglaubt:

```
venv\Scripts\python.exe pruefe_rechtstext.py
```

37 Prüfungen: Skript-Tags, `javascript:` in allen Schreibweisen, `data:`,
`onerror`, `svg onload`, `<base>`, Meta-Refresh, verschachtelt getarnte
Tags — dazu die Gegenprobe, dass Absätze, Listen, Tabellen, Links und
Umlaute erhalten bleiben.

`style` und `class` stehen bewusst nicht in der Erlaubnisliste. Quill setzt
beides gern, die eigene CSP erlaubt aber kein Inline-CSS: das Attribut
würde ohnehin still verworfen, und dann sähe die Seite lokal anders aus
als auf dem Server.

Getrennt davon, und bewusst nicht im Säuberer, werden Quills Leerzeilen
(`<p><br></p>`) entfernt. In echten Texten stehen davon bis zu drei
hintereinander und reißen Löcher zwischen die Abschnitte. Das eine ist
Sicherheit und darf nichts durchlassen, das andere Darstellung und darf
nichts wegwerfen, was Text ist.

## Varianten erzeugen

Je Kampagnenkanal gibt es unter `/kanal/<id>/varianten` einen Schwung
Vorschläge auf einmal. Sie bekommen dieselbe `variant_group`, weil sie
gegeneinander gemessen werden; einzeln steht dort nur, was von Hand
dazukommt. Neu erzeugte Varianten stehen auf `draft` und werden von Hand
freigegeben. Erst `ready` heißt: der Scheduler darf sie nehmen.

**Was in der Anfrage fehlt, denkt sich das Modell aus.** Das ist die eine
Regel, um die hier alles gebaut ist. Preise, Prozente, Fristen, Garantien,
Nutzerzahlen, Ortsangaben — wenn so etwas im Ergebnis stehen darf, muss es
in der Anfrage stehen. Sonst kommt es trotzdem, nur eben erfunden, und ein
erfundener Preis in einem Pin ist Werbung mit einer falschen Angabe unter
eigenem Namen.

Deshalb:

* `campaigns.briefing` ist der Ort für die Wahrheit. Was dort steht, geht
  wörtlich in die Anfrage. Ohne Briefing hätte sie nur Name und Ziel-Link
* `anfrage_bauen` verbietet ausdrücklich alles darüber hinaus, und sagt bei
  fehlendem Briefing im Anfragetext selbst, dass es keine Beschreibung gibt.
  Eine Lücke, die benannt ist, wird seltener gefüllt als eine, die schweigt
* `content_items.prompt` speichert die Anfrage mit. Die Anwendung existiert,
  um zu messen, welche Variante zieht; ohne die Frage daneben ist das
  Ergebnis eine Zahl ohne Bedeutung
* `affiliate_erlaubt` am Kanal reicht die Google-Regel bis in die Anfrage
  durch, statt sie als Sonderfall in einer Maske zu wiederholen

`anfrage_bauen` und `variante_pruefen` sind absichtlich reine Funktionen
ohne Netz und ohne Schlüssel. So lässt sich das Nachdenken prüfen, ohne für
jede Prüfung zu bezahlen:

```
venv\Scripts\python.exe pruefe_ki.py
```

28 Fälle: dass jede Angabe wirklich in der Anfrage landet, dass die Verbote
drinstehen, dass die Google-Regel nur bei Google auftaucht, und dass zu
lange Antworten an der Wortgrenze gekürzt werden statt mitten im Wort.

### Der Weg durch die Anwendung

Vier Schritte, und die Seiten führen von einem zum nächsten:

1. **Kampagne anlegen** — Name, Ziel-Link, Briefing. Der Ziel-Link darf ohne
   `https://` eingetippt werden, es wird ergänzt; abgelehnt wird nur, was
   gar keine Adresse ist (ein fremdes Schema, ein Name ohne Endung).
2. **Kanal einschalten** an der Kampagne. Danach geht es **direkt zu den
   Varianten** — ein frisch eingeschalteter Kanal hat nichts zu posten, und
   den nächsten Schritt selbst suchen zu müssen war der Bruch im Ablauf.
   Beim bloßen Ändern bleibt man dagegen, wo man war.
3. **Varianten** erzeugen oder hochladen, siehe unten.
4. **Freigeben** und die Kampagne auf `active`.

Auf der Varianten-Seite stehen die beiden Wege **nebeneinander und nicht
untereinander**. Untereinander liest sich das wie ein Ablauf, und dann
klickt jemand unten auf „Erzeugen" und erwartet, dass die eigene Datei von
oben mitgenommen wird — genau das ist passiert.

„Wie viele" ist mit dem vorbelegt, was am Kanal steht (`posts_per_day`).
Vorher stand dort eine feste 3, egal was eingestellt war, und die Zahl von
vorhin schien verschwunden.

### Eigene Dateien hochladen

Seit dem 04.09.2026 lässt sich unter `/kanal/<id>/varianten` eine eigene
Datei als Variante anlegen — der Weg für Material, das nicht hier entsteht.
Ein Video aus der Gemini-App zum Beispiel: erzeugen kostet dort nichts
extra, und der Text lässt sich danach hier dazuschreiben oder erzeugen
lassen.

**Das Format wird am Inhalt erkannt, nicht an der Endung.** Die ersten Bytes
weisen eine Datei aus; der Name kommt vom Absender. Eine umbenannte Datei
fällt sonst erst bei der Plattform auf, Tage später, als gescheiterter
Beitrag.

**Und der Kanal wird vorher gefragt.** Ein Video an einen Kanal, der keins
posten kann, wird gar nicht erst gespeichert: sonst läge die Datei da, die
Variante sähe fertig aus, und der Zeitplan überspränge sie stillschweigend.
Was ein Kanal annimmt, steht in `typen` — heute überall nur `image`.

**Der Text entsteht zur Datei, nicht neben ihr.** Beim Hochladen lässt sich
angeben, wie viele Textvorschläge dazu erzeugt werden sollen. Sie bekommen
alle **dieselbe Datei** — so misst die Auswertung später den Text und nicht
das Bild. Bei einem Bild geht es wirklich an das Modell mit (`bild=` an
`texte_erzeugen`, dazu `zu_vorlage=True` in der Anfrage); bei einem Video
nicht, dort bleibt nur das Briefing, und die Meldung sagt das auch.

Bis zum 04.09.2026 fehlte dieser Schritt ganz: hochgeladen wurde, aber
„Erzeugen" daneben übersprang die Datei und schrieb über das Thema. Der
Beitrag beschrieb dann etwas anderes, als das Bild daneben zeigte.

**0 Vorschläge** heißt: nur ablegen, Titel und Text von Hand. Scheitert das
Erzeugen, bleibt die Datei als Variante ohne Text stehen — sie wegzuwerfen
wäre die teurere Entscheidung, hochgeladen ist sie ja schon.

Beim Löschen einer Variante verschwindet auch die Datei. Sicher ist das,
weil eine **veröffentlichte** Variante sich gar nicht löschen lässt; es kann
also kein Bild verschwinden, das ein Kanal noch abholt.

### Die Anfrage fürs Bild ist eine eigene

**Das kostete am 04.09.2026 einen halben Tag.** Vorher ging die komplette
Text-Anfrage an das Bildmodell — also „Du schreibst 3 Vorschläge für einen
Beitrag auf Facebook, Titel höchstens 100 Zeichen, Deutsch, geduzt…". Ein
Bildmodell kann damit nichts anfangen: es antwortete mit
`finish_reason=NO_IMAGE` und lieferte **jedes Mal** nichts. Nachgemessen mit
demselben Briefing gegen beide Fassungen: alte Anfrage 0 Bilder, reine
Bildbeschreibung sofort eines.

Die irreführende Spur dabei war die eigene Fehlermeldung. Sie riet auf
„beschreibt Menschen oder eine Marke und läuft in einen Filter", und weil im
Briefing zufällig Personen vorkamen, sah das nach der Erklärung aus. Sie war
falsch. Seitdem nennt die Meldung den `finish_reason`, den Gemini
mitschickt: `NO_IMAGE` heißt „mit der Anfrage nichts anfangen können",
`SAFETY` heißt Filter. Das sind zwei verschiedene Probleme und sie sahen
vorher gleich aus.

`bild_anfrage_bauen` beschreibt deshalb nur, was zu sehen sein soll. Drei
Regeln stehen fest darin:

* **Keine Schrift im Bild.** Bildmodelle setzen gern Wörter hinein und
  schreiben sie falsch. Ein Pin mit Tippfehler im Bild fällt erst draußen
  auf.
* **Keine Menschen.** pinario erzeugt keine erfundenen Fotos von Personen —
  und Anfragen mit Personenbeschreibung laufen zusätzlich in Filter.
* **Keine Logos und Marken**, aus demselben Grund.

Dazu das **Seitenverhältnis vom Kanal** (`bild_format`): Pinterest 2:3,
Instagram 4:5, Facebook 16:9, Threads 1:1. Es geht als `aspect_ratio` an
Gemini. Ein quadratisches Bild auf Pinterest ist kein Fehler, den jemand
meldet — es sieht nur immer etwas daneben aus.

**Ein gescheitertes Bild kostet nicht den ganzen Schwung.** Der Text ist das
Teure am Vorgang; wenn das Bild in einen Filter läuft, bleibt die Variante
stehen und sagt es. Nachreichen geht einzeln.

Bilder liegen unter `uploads/erzeugt/` mit gewürfeltem Namen. Nicht aus dem
Titel gebaut: Pinterest holt Bilder über eine öffentlich erreichbare
Adresse, ein sprechender Dateiname stünde damit im Netz.

## Einstellungen

`/einstellungen` ist der Ort für Werte, die sich im Betrieb ändern. Die
`.env` bleibt für alles, was zum Aufsetzen gehört und danach steht:
Datenbank, `SECRET_KEY`, `TRESOR_SCHLUESSEL`.

**Der Gemini-Schlüssel** lässt sich dort eintragen, prüfen und entfernen.
Er liegt **verschlüsselt** in der Tabelle `einstellungen`, mit demselben
Tresor wie die OAuth-Token; wer `TRESOR_SCHLUESSEL` wechselt, muss ihn neu
eintragen, und die Seite sagt das dann auch. Angezeigt wird er nie ganz,
nur die ersten und letzten vier Zeichen.

**Die Einstellung schlägt die `.env`.** Wer einen Wert in der Maske setzt,
will genau den; `GEMINI_API_KEY` in der `.env` ist ab dann nur noch der
Rückfall für einen frisch aufgesetzten Server. Andersherum wäre die
Oberfläche eine Maske, die etwas anzeigt, das nicht gilt. Die Seite schreibt
dazu, woher der Schlüssel gerade kommt — sonst versteht später niemand,
warum das Erzeugen läuft, obwohl das Feld leer aussieht.

Welche Werte verschlüsselt abgelegt werden, leitet `ist_geheim` aus dem
Verzeichnis der Kanäle ab statt aus einer zweiten Liste von Hand. Eine
zweite Liste würde beim nächsten Kanal vergessen, und das Ergebnis wäre ein
Secret im Klartext in jeder Sicherung.

`Verbindung prüfen` macht einen echten, sehr kurzen Aufruf gegen das
Textmodell. Sinn: ein falscher Schlüssel oder ein falscher Modellname soll
hier auffallen und nicht erst beim ersten Schwung Varianten.

**Die Zugangsdaten der Kanäle** stehen dort ebenfalls, und zwar für **alle
fünf** — auch für Instagram, Facebook und X, für die es noch keinen Adapter
gibt. Sie lassen sich eintragen, bevor der Adapter da ist; dann ist beim
Bauen schon alles hinterlegt. Damit daraus kein falscher Eindruck wird,
steht an jedem Kanal, woran es hängt: `kein Adapter`, `Freischaltung fehlt`,
`Zugangsdaten fehlen` oder `vollständig`. **`vollständig` heißt nur, dass
die Angaben da sind**, nicht dass jemals etwas darüber gepostet wurde.

Gemeint sind die Angaben zur *Anwendung* (App-ID und Secret aus dem
Entwicklerbereich der Plattform), nicht der Zugang zu einem Konto — der
läuft über OAuth und landet in `accounts`. Welche Felder eine Plattform
verlangt, steht in `ZUGANGSFELDER` in `app/kanaele/__init__.py`, an einer
Stelle für alle Kanäle. **Der `name` eines Feldes darf sich nicht mehr
ändern**, daraus wird der Schlüssel in der Tabelle gebaut.

Drei Dinge, die dabei absichtlich so sind:

* **Ein leeres Feld lässt den gespeicherten Wert stehen.** Sonst müsste man
  das Secret jedes Mal neu eintippen, nur weil die App-ID sich geändert hat
  — und angezeigt wird es ja bewusst nicht.
* **Nur das Secret wird verdeckt.** Eine App-ID steht ohnehin offen im
  Entwicklerbereich der Plattform und ist beim Abgleichen nützlicher, wenn
  man sie ganz sieht.
* **Instagram und Facebook haben getrennte Felder**, obwohl beide meistens
  über dieselbe Meta-App laufen. Eine geteilte Zeile wäre eine Annahme über
  Metas Kontenlandschaft, die heute stimmt und in zwei Jahren vielleicht
  nicht mehr. Zweimal denselben Wert einzutragen kostet eine Minute, das
  Auseinandernehmen später eine Migration.

Die **Rückruf-Adresse** steht je Kanal ausgeschrieben auf der Seite. Sie
muss im Entwicklerbereich der Plattform zeichengenau eingetragen sein, und
das macht man dort einmal und nicht zweimal.

Adapter holen ihre Zugangsdaten über `einstellungen.kanal_wert` und nie
direkt aus der Konfiguration — sonst läge ein Wert in der Maske, der nicht
benutzt wird. Der Import steht dabei **in der Funktion**: `einstellungen`
liest umgekehrt das Verzeichnis der Kanäle, und oben im Modul wäre das ein
Kreis.

**Das Passwort** lässt sich dort ebenfalls ändern. Das alte wird verlangt,
obwohl die Sitzung schon angemeldet ist — sonst reicht ein offener Browser,
um sich dauerhaft einzurichten. Der Wechsel würfelt `users.session_token`
neu und beendet damit alle Anmeldungen; die eigene wird direkt danach
erneuert, sonst landet man unmittelbar nach dem Wechsel auf der Startseite
und weiß nicht, ob er geklappt hat.

**Danach stimmt `/root/.pinario-login` auf dem Server nicht mehr.** Diese
Datei ist eine Notiz und keine Quelle; wer das Passwort über die Maske
ändert, zieht sie von Hand nach oder löscht sie. Der Weg über die
Kommandozeile bleibt daneben bestehen:

```
cd /var/www/pinario && sudo -u www-data ./venv/bin/flask --app wsgi passwort
```

## Ein Konto verbinden

Drei Adressen, für jeden Kanal dieselben — die Anwendung kennt dabei keine
einzelne Plattform:

```
POST /kanaele/<key>/verbinden   hin zur Plattform
GET  /kanaele/<key>/rueckruf    zurück von der Plattform
POST /kanaele/<key>/trennen     Zugang wieder weg
GET  /kanaele/<key>/ablagen     Boards des verbundenen Kontos
```

Der Knopf dazu steht auf `/einstellungen` am jeweiligen Kanal, und zwar erst
dann, wenn es einen Adapter gibt, der Kanal freigeschaltet ist und die
Zugangsdaten der App hinterlegt sind. Ein Knopf, der sonst nur in eine
Fehlermeldung führt, ist keine Hilfe.

**Die Ablagen werden ausgewählt, nicht abgetippt.** Sobald ein Konto
verbunden ist, holt die Kampagnen-Seite die Seiten, Boards oder Konten beim
Adapter und zeigt sie zum Anhaken. Das Textfeld für Kennungen bleibt als
Rückfall: solange kein Konto verbunden ist, und wenn der Abruf scheitert.
Ein verstecktes Feld sagt der Verarbeitung, welche der beiden Formen kam —
sonst wäre "nichts angehakt" nicht von "gar nicht angezeigt" zu
unterscheiden, und ein Speichern würde die Auswahl stillschweigend leeren.

Beim Auslesen `getlist` und nicht `get`: sonst kommt nur das erste Häkchen
an, und wer drei Seiten anhakt, bespielt eine.

**Ein Kanal ohne Ziel steht nicht auf „läuft"**, sondern auf „Seite fehlt"
beziehungsweise „Board fehlt". Das ist der Zustand, in dem man am ehesten
glaubt, es liefe — der Kanal ist eingeschaltet, ein Konto ist verbunden, und
trotzdem kann nichts rausgehen.

**Die Rückruf-Adresse kommt aus `OEFFENTLICHE_ADRESSE` in der `.env`**, nicht
aus der laufenden Anfrage. Sie steht auf der Einstellungen-Seite zum
Abschreiben und muss im Entwicklerbereich der Plattform **zeichengenau** so
eingetragen sein. Käme sie aus `request.url_root`, hieße sie über
`www.pinario.de` plötzlich anders als über `pinario.de` — und Pinterest weist
den Rückruf dann mit einem `invalid_grant` ab, das nicht sagt, woran es lag.

**Die CSP muss die Weiterleitung durchlassen.** Der teuerste Fehler des
04.09.2026, und der mit den wenigsten Spuren: `form-action 'self'` verbietet
nicht nur, ein Formular woandershin zu schicken, sondern auch die
**Weiterleitung, die auf einen Formular-POST folgt**. Der Knopf „Konto
verbinden" ist so ein Formular. Der Browser verwarf die Antwort
stillschweigend — keine Meldung auf der Seite, keine Zeile im Server-Log
außer „Verbinden gestartet", der Knopf tat einfach nichts. Nachgestellt mit
zwei Seiten, die sich nur in der CSP unterschieden: mit der alten blieb die
Seite stehen, mit der neuen kam die Weiterleitung an.

Die erlaubten Ziele kommen deshalb aus den Adaptern (`anmelde_ursprung` am
Kanal, gesammelt in `kanaele.anmelde_urspruenge`) und nicht aus einer Liste
in `create_app`. Eine Liste dort würde beim nächsten Kanal vergessen, und
der Fehler sähe wieder aus wie ein kaputter Knopf.

**Der `zustand` ist kein Beiwerk.** Er wird gewürfelt, liegt in der Sitzung
und muss beim Rückruf wieder passen. Ohne diese Prüfung könnte jemand einem
angemeldeten Nutzer einen Rückruf mit *seinem* Code unterschieben, und ab da
gingen alle Pins auf ein fremdes Board. Er gilt genau einmal.

**Je Kanal gibt es ein Konto.** Der Zeitplan nimmt das erste, das er findet;
ein zweites daneben wäre ein Zugang, der aussieht, als würde er benutzt, und
es nie wird. Neu verbinden überschreibt deshalb.

**Ein abgelaufener Zugang wird vor dem Lauf erneuert, nicht während er
scheitert.** Pinterest gibt einen Zugang für 30 Tage aus. Ohne diesen Schritt
liefe alles einen Monat lang gut und dann gar nichts mehr, mit einem
`Authentication failed` an jedem einzelnen Beitrag. Lässt sich der Zugang
nicht erneuern, wird der Kanal übersprungen statt versucht — dieselbe Regel
wie bei einem Kanal ohne Konto, und auf `/zeitplan` steht der Grund.

Beim Erneuern schickt Pinterest normalerweise **kein neues
Erneuerungs-Token** mit. Das alte bleibt gültig und muss stehen bleiben; wer
es dabei mit einem leeren Wert überschreibt, verliert den Zugang dauerhaft
und merkt es 30 Tage später.

Nachgemessen ohne Netz und ohne Schlüssel:

```
venv\Scripts\python.exe pruefe_pinterest.py    67 Fälle, Adapter allein
venv\Scripts\python.exe pruefe_verbinden.py    44 Fälle, gegen die Anwendung
```

`pruefe_verbinden.py` ist das einzige Prüfskript, das die **lokale Datenbank**
braucht: gemessen wird, was zwischen Browser, Sitzung und Tabelle passiert.
Es sichert vorher, was an Pinterest-Zugangsdaten dasteht, und schreibt genau
das zurück.

Zwei Fallen darin, die eine funktionierende Anwendung als kaputt melden und
beide nichts mit ihr zu tun haben: Flask-Login vergleicht bei jeder Anfrage
einen Abdruck aus IP und Browserkennung, den eine von außen gesetzte Sitzung
nicht mitbringt (deshalb ist der Schutz dort abgeschaltet), und es merkt sich
den angemeldeten Nutzer in `g`, das sich alle Anfragen innerhalb eines
`app_context` teilen — eine einzige Anfrage ohne Anmeldung färbt sonst auf
alle folgenden ab.

### Ein Token von Hand eintragen

Pinterest gibt im Entwicklerbereich ein Zugriffstoken zum Ausprobieren aus,
bevor der Trial-Zugriff freigeschaltet ist. Das hat **nur Leserechte**
(`pins:read, boards:read, user_accounts:read, ads:read, catalogs:read`) —
Konto und Boards abfragen geht damit, einen Pin schreiben nicht. Solange der
geheime Schlüssel der App auf "trial-Zugriff ausstehend" steht, ist das der
einzige Weg, überhaupt etwas gegen die echte API zu messen.

```
venv\Scripts\python.exe -m flask --app wsgi token-eintragen pinterest
```

Das Token wird abgefragt und nicht als Argument genommen, sonst stünde es in
der Verlaufsdatei der Shell. Der Befehl fragt damit zuerst `/user_account`
ab und **speichert erst, wenn Pinterest antwortet** — ein Token, das nicht
angenommen wird, soll gar nicht erst in der Datenbank landen, sonst hielte
der Zeitplan den Kanal für verbunden.

**Die Falle beim Einfügen** (am 04.09.2026 einmal voll hineingelaufen):
Terminals umschließen eingefügten Text mit unsichtbaren Steuerzeichen,
`ESC[200~` davor und `ESC[201~` dahinter — "Bracketed Paste". Bei einem
versteckten Eingabefeld sieht man davon nichts. Die Sequenz landet im
`Authorization`-Kopf, und Pinterest antwortet darauf **nicht** mit "Token
ungültig", sondern mit einer HTML-Fehlerseite seines CDN und einem 400, die
über die Ursache gar nichts sagt:

```
Error: Pinterest antwortete mit 400: <HTML><HEAD><TITLE>Error</TITLE>...
```

Der Befehl räumt solche Zeichen jetzt weg und **sagt, wie viele es waren**.
Steht dort eine Zahl, war es das. Danach nennt er Länge und Anfang des
Tokens, damit man sieht, ob es vollständig angekommen ist. Wer ganz
sichergehen will, nimmt `--datei` und umgeht das Terminal:

```
venv\Scripts\python.exe -m flask --app wsgi token-eintragen pinterest --datei token.txt
```

Die Datei danach löschen, darin steht ein gültiger Zugang.

Ein so eingetragenes Token hat kein Erneuerungs-Token und keinen bekannten
Ablauf. Es steht deshalb ohne `expires_at` da, damit der Zeitplan nicht
versucht zu erneuern, was sich nicht erneuern lässt. **Sobald die App
freigeschaltet ist, richtig über `/einstellungen` verbinden.**

Was damit belegt werden kann: `/user_account` (der Befehl selbst) und
`/boards` (danach `/kanaele/pinterest/ablagen` in der Oberfläche). Das
Schreiben eines Pins bleibt offen, bis das Token `pins:write` hat.

**Was am 04.09.2026 schon gegen die echte API gelaufen ist:** ein Aufruf mit
einem absichtlich falschen Token. Pinterest antwortete mit
`Authentication failed. (Code 2)`, und genau dieser Satz landet über
`_fehlertext` in `posted_items.fehler`. Damit sind Adresse, Aufbau der
Anfrage und der Fehlerweg belegt — der Erfolgsweg nicht.

**Was noch fehlt: die App bei Pinterest.** Ohne App-ID und Secret aus
developers.pinterest.com läuft nichts davon gegen die echte API. Die
Redirect-URI dort muss `https://pinario.de/kanaele/pinterest/rueckruf`
lauten. Eingetragen werden die beiden Werte unter `/einstellungen`, nicht in
die `.env` — dann ist auch kein Neustart nötig.

## Facebook und Instagram

Beide laufen über dieselbe Graph API von Meta und stehen deshalb in einer
Datei (`app/kanaele/meta.py`). Sie teilen sich App, Anmeldeweg, Token und
Seitenliste; getrennt sind nur das Posten und die Zahlen.

**Hier wartet man auf niemanden.** Solange nur eigene Konten bedient werden,
reicht eine App im Entwicklungsmodus mit dem eigenen Konto als Administrator
beziehungsweise Instagram-Tester. Metas App Review greift erst, wenn fremde
Leute ihre Konten mit der App verbinden, und das passiert bei pinario nie.
Das ist der eine große Unterschied zu Pinterest.

Was vorher stehen muss:

1. **Eine Facebook-Seite.** Die API kann nur Seiten, keine Privatprofile.
2. **Für Instagram ein Professional-Konto** (Business oder Creator), das
   **mit dieser Seite verknüpft ist**. Ohne die Verknüpfung taucht es in
   `/me/accounts` gar nicht auf — das ist der häufigste Grund für eine leere
   Kontenliste unter „Konten ansehen".
3. **Eine App im Meta-Entwicklerbereich**, App-ID und Secret unter
   `/einstellungen`. Beide Kanäle haben dort eigene Felder, obwohl meistens
   dieselbe App dahintersteht; zweimal denselben Wert einzutragen kostet
   eine Minute, das Auseinandernehmen später eine Migration.

### Zwei Anmeldewege, die sich nicht vertragen

**Das hat am 04.09.2026 einen Nachmittag gekostet.** Meta hat zwei
Login-Produkte:

* **„Facebook Login"** (klassisch) bekommt die Rechte als `scope` in der
  Adresse.
* **„Facebook Login for Business"** nicht. Dort stehen die Rechte in einer
  *Konfiguration*, die man im Entwicklerbereich anlegt, und mitgeschickt
  wird nur deren `config_id`.

Ruft man eine Business-Anmeldung mit `scope` auf, passiert etwas
Unangenehmes: **kein Dialog, keine Fehlermeldung, die hier ankäme.** Der
Nutzer wird gar nicht erst zurückgeschickt. Im eigenen Log steht dann nur
„Verbinden gestartet" und danach nichts mehr, und man sucht den Fehler in
der Rückruf-Adresse, wo keiner ist.

Deshalb hat der Kanal ein **optionales** Feld `config_id` unter
Einstellungen. Steht sie da, geht der Business-Weg (`config_id` plus
`override_default_response_type=true`, sonst nimmt der Dialog seinen eigenen
Antworttyp und liefert ein Token statt eines Codes zurück). Steht sie nicht
da, bleibt es beim klassischen `scope`.

Zu finden ist sie im Entwicklerbereich unter **Facebook Login for Business →
Konfigurationen**. Beim Anlegen der Konfiguration werden dort die Assets
(Seiten) und die Berechtigungen ausgewählt — die Liste unten steht dann
nicht mehr im Code, sondern bei Meta.

Die Rechte werden je Kanal einzeln erfragt: wer Facebook verbindet, muss
dafür nicht Instagram freigeben.

| Kanal | Rechte |
|---|---|
| Facebook | `pages_show_list`, `pages_read_engagement`, `pages_manage_posts` |
| Instagram | `pages_show_list`, `pages_read_engagement`, `instagram_basic`, `instagram_content_publish` |

### Vier Dinge, die hier anders laufen als bei Pinterest

**Es gibt zwei Sorten Token.** Beim Verbinden kommt ein *Nutzer*-Token
heraus, gepostet wird aber mit einem *Seiten*-Token, und den holt man für
jede Seite einzeln über `/me/accounts`. Wer es verwechselt, bekommt einen
Rechtefehler, der nach einem fehlenden Recht aussieht und keines ist.

**Das erste Token gilt eine Stunde.** `zugang_holen` tauscht es deshalb
sofort gegen ein langlebiges mit rund 60 Tagen. Das ist kein Feinschliff,
sondern der Unterschied zwischen benutzbar und nicht.

**Meta kennt kein Erneuerungs-Token.** Verlängert wird, indem man das
gültige Token noch einmal eintauscht — und das geht nur, solange es *nicht*
abgelaufen ist. Deshalb steht in `accounts` unter `erneuerung` dasselbe wie
unter `zugang`, und deshalb erneuert der Zeitplan sechs Stunden vor Ablauf
statt am Ablauftag. Ist die Frist einmal um, hilft nur neu verbinden.

**Instagram postet zweistufig.** Erst ein Container (`/media`), dann
veröffentlichen (`/media_publish`). Dazwischen verarbeitet Meta das Bild;
bei einem Foto geht das meist sofort, aber eben nicht immer. Der Adapter
fragt deshalb `status_code` ab, bis `FINISHED` dasteht, und bricht bei
`ERROR` oder `EXPIRED` sofort ab, statt die Zeit abzusitzen.

### Der Ziel-Link

Bei Pinterest hat ein Pin ein eigenes Feld dafür. Hier gibt es nur den Text,
und daraus folgen zwei Dinge, die am Kanal stehen und von dort in die
Anfrage an Gemini gehen:

* `link_im_text = True` bei beiden. Stünde in der Anfrage weiter pauschal
  „den Ziel-Link nicht in den Text", führte jeder Beitrag ins Leere.
* `link_klickbar = False` bei **Instagram**. Dort ist ein Link in der
  Bildunterschrift nicht anklickbar. Das Modell wird deshalb angewiesen,
  ihn zum Abtippen hinzuschreiben, aber nicht zum Klicken aufzufordern und
  auch nicht auf einen Link in der Biografie zu verweisen, den es
  vielleicht gar nicht gibt.

Angehängt wird er in `_text_mit_link`, und dabei gilt: **der Link wird nie
abgeschnitten.** Ein halber Link sieht aus, als führte er irgendwohin. Passt
er nicht mehr, wird stattdessen der Text gekürzt.

### Was dabei bewusst nicht geht

**Facebook postet als Foto (`/photos`), nicht als Beitrag mit Link
(`/feed`).** Der Unterschied ist sichtbar: bei `/feed` mit `link` baut
Facebook eine eigene Vorschaukarte aus der Zielseite, und das selbst
erzeugte Bild taucht gar nicht auf. Genau dieses Bild ist aber der Grund,
warum es pinario gibt.

**Facebook postet seit dem 04.09.2026 auch Video**, Instagram noch nicht.
Der Weg ist derselbe wie beim Foto: Facebook holt die Datei über `file_url`
selbst ab, der dreistufige Upload in Stücken wäre erst über 1 GB nötig.
Zwei Unterschiede: es geht an `/videos` statt `/photos`, und **ein Video hat
ein eigenes Titelfeld** — dort wird der Titel zur Überschrift statt zur
ersten Zeile des Textes. Danach verarbeitet Facebook noch; erst wenn das
durch ist, gilt der Beitrag als draußen. Ohne diese Prüfung stünde ein
Beitrag als „gepostet" da, der an einer kaputten Datei gescheitert ist.

**Welcher Typ kommt, sagt der Zeitplan** (`typ` an `veroeffentlichen`, aus
`content_items.type`) und nicht die Dateiendung. Der Typ steht in der
Datenbank; zwei Wahrheiten über dieselbe Sache laufen früher oder später
auseinander.

**Die Kennzahlen sind der wackligste Teil.** Meta räumt dort laufend um,
`post_impressions` verschwindet 2026 und `impressions` ist bei Instagram
schon durch `views` abgelöst. Der Adapter sucht deshalb jede Kennzahl
einzeln und macht aus einer fehlenden eine Null, statt den Aufruf scheitern
zu lassen. **Facebook kennt kein „Saves", Instagram keine Klicks** — beide
Felder bleiben 0, und in der Auswertung dürfen Kanäle deshalb nicht über
diese Zahlen hinweg verglichen werden.

Nachgemessen ohne Netz:

```
venv\Scripts\python.exe pruefe_meta.py    81 Fälle
```

## Threads

Gehört Meta, ist aber **keine Erweiterung der Graph API** und steht deshalb
in einer eigenen Datei. Alles ist anders: eigener Host
(`graph.threads.net`), eigener Anmeldeweg über `threads.net`, eigene Rechte
(`threads_basic`, `threads_content_publish`), **eine eigene App** im
Entwicklerbereich und ein eigenes Verfahren fürs Erneuern. Wer sie zu
`meta.py` dazuschriebe, hätte eine Klasse, die von ihrer Basis nichts mehr
benutzt.

**Die App aus dem Instagram- oder Facebook-Kanal passt hier nicht.** Threads
ist im Meta-Entwicklerbereich ein eigener Anwendungsfall mit eigenen
Schlüsseln; deshalb hat der Kanal unter `/einstellungen` eigene Felder.

**Es gibt hier keine Ablagen.** Ein Threads-Konto hat keine Boards, keine
Seiten, keine Standorte — gepostet wird auf das verbundene Konto und sonst
nirgendwohin. Am Kampagnen-Kanal ist deshalb nichts einzutragen, und ein
Wert in `ablage_id` lenkt den Beitrag auch nicht um.

Drei Dinge, die man vorher wissen sollte:

**Das Threads-Konto hängt an einem Instagram-Konto, der Zugang dazu aber
nicht.** Verbunden wird direkt über Threads. Ein bei Instagram verbundenes
Konto hilft hier nicht.

**Erneuern geht erst ab 24 Stunden.** Ein jüngeres Token lehnt Threads beim
Auffrischen ab. Im Betrieb stört das nicht — erneuert wird kurz vor Ablauf
nach 60 Tagen —, aber wer es gleich nach dem Verbinden ausprobiert, sucht
den Fehler sonst im Code.

**Ein Token, das 60 Tage nicht erneuert wurde, ist endgültig tot.** Es lässt
sich dann nicht mehr auffrischen, das Konto muss neu verbunden werden. Der
Zeitplan erneuert deshalb rechtzeitig von selbst.

Sonst läuft es wie bei Instagram: erst ein Container (`/threads`), dann
veröffentlichen (`/threads_publish`), dazwischen die Statusabfrage. Threads
empfiehlt pauschal 30 Sekunden zu warten; der Adapter fragt stattdessen ab,
weil der Container meist lange vorher fertig ist und die Zeit sonst jedem
weiteren Beitrag desselben Laufs fehlt.

**Der Ziel-Link ist hier anklickbar**, anders als bei Instagram: Threads
erkennt die **erste** Adresse im Text und baut eine Vorschau daraus. Genau
deshalb steht der Ziel-Link am Ende und die Anfrage an das Modell verbietet
fremde Adressen — sonst zeigt die Vorschau die falsche Seite.

**Threads liefert weder Klicks noch Speicherungen**, nur `views`. Beide
Felder bleiben 0. Eine 0 heißt hier "gibt es nicht", nicht "war nicht", und
darin liegt der Grund, warum die Auswertung Kanäle nicht einfach
nebeneinander stellen darf.

```
venv\Scripts\python.exe pruefe_threads.py    61 Fälle
```

## Zeitplan

Zwei Schritte, absichtlich getrennt. **Einplanen** vergibt `geplant_fuer` an
freigegebene Varianten und rechnet dabei nur mit Zeiten und der Datenbank.
**Posten** nimmt fällige Einträge und schickt sie über den Adapter raus;
erst hier kann etwas schiefgehen, das nicht in unserer Hand liegt.

Beides zusammen ist ein Lauf:

```
venv\Scripts\python.exe -m flask --app wsgi zeitplan --trocken
```

`--trocken` sagt nur, was rausginge, und fasst nichts an. Ohne die Option
läuft es echt, mit `--nur-planen` werden nur Termine vergeben.

**Der Scheduler läuft nicht im Webserver.** gunicorn startet zwei Worker;
ein Scheduler im Prozess liefe damit zweimal und würde jeden Beitrag doppelt
posten. Ausgelöst wird über einen systemd-Timer alle fünf Minuten:

```
cp /var/www/pinario/betrieb/pinario-zeitplan.* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now pinario-zeitplan.timer
```

### Vier Regeln, die den Unterschied machen

**Ein Kanal ohne verbundenes Konto wird übersprungen, nicht versucht.**
Sonst brennt der erste Lauf alle eingeplanten Varianten auf `failed`, bevor
Pinterest überhaupt verbunden ist — und wer den Fehler danach behebt, hat
trotzdem einen Haufen Leichen in der Messreihe. Auf `/zeitplan` steht
deshalb oben, welcher Kanal noch kein Konto hat.

**Zwischen Herausnehmen und Antwort steht der Eintrag auf `posting`.** Der
Übergang wird sofort committet; ab da nimmt kein zweiter Lauf ihn mehr.
Bricht der Lauf danach ab, holt der nächste ihn nach `HAENGT_AB` (30
Minuten) zurück auf `ready`. Dafür gibt es `content_items.posten_seit` —
`geplant_fuer` taugt nicht dazu, weil ein Eintrag auch verspätet drankommen
kann und dann falsch alt aussieht.

**Was der Kanal nicht annimmt, wird gar nicht erst eingeplant.** Ein Pin
braucht ein Bild; eine Variante ohne ist dort kein gescheiterter Versuch,
sondern einer, der nie hätte stattfinden dürfen. In der Varianten-Ansicht
steht an solchen Einträgen `Bild fehlt`.

**Ein Fehler nimmt nie den ganzen Lauf mit.** Der Aufruf des Adapters ist
breit abgesichert, der Grund landet als Text in `posted_items.fehler` und
ist auf `/zeitplan` zu lesen. Sonst verschluckt ein einzelner Fehlschlag die
übrigen Beiträge des Tages.

### An welchen Tagen

Seit dem 04.09.2026 lässt sich je Kanal wählen, an **welchen Wochentagen**
gepostet wird (`weekdays` in den Einstellungen, Montag ist 0 wie bei
`date.weekday()`). „Zweimal die Woche, Mo und Do" heißt also: diese beiden
Tage anhaken und einen Beitrag pro Tag. Vorher ging nur „X pro Tag", und
drei am Tag sind für Facebook zu viel.

**Eine fehlende oder leere Angabe heißt: an allen Tagen.** Das ist die
wichtigste Zeile dieser Funktion. Alles, was vorher eingerichtet wurde, hat
das Feld gar nicht — wäre leer gleich „nie", hörten diese Kanäle
stillschweigend auf zu posten, und niemand sähe einen Fehler. Dasselbe gilt
für unbrauchbare Werte: sie fallen auf „alle Tage" zurück, nicht auf keinen.
Die Regel steht deshalb an beiden Stellen, im Formular und im Zeitplan, und
`pruefe_zeitplan.py` misst beide Wege — `postet_am` allein nützt nichts,
wenn `slots` die Antwort nicht beachtet.

### Wie die Termine liegen

Gleichmäßig vom Beginn des Fensters aus, nicht über das ganze Fenster
gestreckt: bei drei Beiträgen zwischen 09:00 und 21:00 sind das 09:00, 13:00
und 17:00. Der Rest bleibt Puffer, wenn ein Lauf ausfällt und Nachzügler
abgearbeitet werden. **Bewusst ohne Zufall** — etwas Streuung sähe
menschlicher aus, macht aber jede Prüfung zur Glücksfrage und jeden
Fehlerbericht unwiederholbar.

Sind mehrere Boards eingetragen, gehen die Beiträge reihum darauf, nach der
Zahl der bisherigen Veröffentlichungen. Deterministisch, damit sich ein
Ergebnis später nachvollziehen lässt.

Gerechnet wird über echte Zeitpunkte mit Zeitzone, nie über nackte
Uhrzeiten. `pruefe_zeitplan.py` misst genau das nach, inklusive der beiden
Umstellungstage:

```
venv\Scripts\python.exe pruefe_zeitplan.py
```

Das Verhalten gegen die Datenbank — kein doppeltes Posten, Überspringen
ohne Konto, Zurückholen hängengebliebener Einträge, Board-Reihum — hängt
an Postgres und ist am 03.09.2026 mit einer Wegwerf-Kampagne und einem
untergeschobenen Adapter geprüft worden (31 Fälle).

## Die Marke

Die Vorlage `marke_quelle/logo2.png` ist ein Bild, kein Vektor, und welche
Schrift darin steckt, ist nicht bekannt. Arial Bold kommt auf 1,6 %
Abweichung heran, unterscheidet sich aber sichtbar am `a` (Sporn unten
rechts) und am `r` (Endung). Deshalb wird der Umriss aus dem Bild gelesen:

```
venv\Scripts\python.exe marke_quelle\bauen.py
```

Der Weg dorthin, falls das je wieder angefasst wird:

1. Farben trennen. Randpixel sind Mischungen mit Weiß und werden erst auf
   volle Deckung zurückgerechnet, sonst landen sie in der falschen Gruppe
2. Maske achtfach hochrechnen und schwellen. Das rekonstruiert die Kante
   unterhalb der Pixelauflösung
3. Umriss als Pixelkante verfolgen. Außenkanten im Uhrzeigersinn, Löcher
   dagegen, damit `fill-rule="evenodd"` die Punzen von p, a und o offen lässt
4. Ecken suchen, und zwischen zwei Ecken entweder eine Gerade legen oder so
   wenige Bezier wie möglich (Ausgleichsrechnung mit Newton-Nachführung,
   `marke_quelle/kurven.py`)

Der erste Anlauf legte stattdessen eine Kurve durch **jeden** Punkt des
vereinfachten Umrisses. Das traf die Vorlage genauso gut, übernahm aber
jede Unebenheit des 92 Pixel hohen Originals: bei zwölffacher Vergrößerung
beulte die Punze des p sichtbar aus. Die Kurvenanpassung halbierte
nebenbei die Pfadlänge.

Nachgemessen gegen das Original: **99,4 % Deckung**, die Abweichung sind 70
einzelne Randpixel bei 11.776 Pixeln Fläche.

Die orangen Teile werden nicht getract. Es sind fünf Rechtecke mit Füllgrad
1,000, und die stehen als `<rect>` im SVG statt als Viereck mit 0,2 Pixel
Schräglage.

Farben: `#1a1a2e` dunkel, `#e8590c` orange.

## Auf dem Server

**Live seit dem 03.09.2026 unter https://pinario.de.**

```
/var/www/pinario               Code, venv, .env, logs, uploads, cache
pinario.service                gunicorn auf 127.0.0.1:3008, 2 Arbeiter
/etc/nginx/sites-available/pinario
Datenbank pinario              eigene Rolle, Passwort in /root/.pinario-dbpw
Anmeldepasswort                in /root/.pinario-login
```

Beide Passwörter sind auf dem Server gewürfelt worden und stehen nur dort,
mit Rechten 600 für root. Das Anmeldepasswort ändern:

```
cd /var/www/pinario && sudo -u www-data ./venv/bin/flask --app wsgi passwort
```

**Nur `pinario.de` ist erreichbar.** `www.pinario.de` und
`admin.pinario.de` zeigen am 03.09.2026 noch auf All-Inkl
(85.13.157.138). Das Zertifikat deckt deshalb nur die Hauptadresse ab.
Sobald `www` auf `5.75.232.101` umgebogen ist:

```
certbot --nginx -d pinario.de -d www.pinario.de
```

und in `betrieb/nginx-pinario.conf` den `server_name` erweitern. `admin`
wird nicht gebraucht, siehe die Entscheidung vom 02.09.2026.

Ein paar Dinge, die beim Ausrollen aufgefallen sind und beim nächsten Mal
Zeit sparen:

* **`git config --global --add safe.directory /var/www/pinario`** war nötig,
  weil nach `chown -R www-data` das Repository root nicht mehr gehört.
  Dasselbe steht dort schon für betmaster und cockpit.
* Die Unit hat **`Type=notify`** und ein Timeout, wie bei betmaster. Die
  Vorlage in `betrieb/` hatte das anfangs nicht.
* **`cache/` gehört in `ReadWritePaths`.** Sonst kann die Anwendung die
  Rechtstexte nicht zwischenspeichern und holt sie bei jedem Aufruf neu.
* Alle festgenagelten Pakete haben unter **Python 3.14** sauber installiert.

### Sicherung

**Die Datenbank `pinario` wird nicht gesichert.** Auf dem Server läuft genau
ein automatisches Sicherungsskript, `bestellone-backup.sh`, und das nimmt
nur `bestellone` mit. Für die anderen Datenbanken liegen bloß von Hand
gezogene Dumps unter `/root`.

Solange nichts drinsteht, kostet das nichts. Sobald aber Kampagnen laufen,
hält diese Datenbank die Messreihe, wegen der es die Anwendung überhaupt
gibt — und die verschlüsselten Kanal-Zugänge. Spätestens dann gehört sie in
eine Sicherung. Das ist bewusst nicht nebenbei mit ausgerollt worden: es ist
eine Server-Aufgabe für alle acht Datenbanken, keine für pinario allein.

## Aktualisieren

Als root, nicht als `www-data`: der GitHub-Schlüssel liegt bei root,
deshalb wird der Besitzer nach dem Ziehen wieder gerade gerückt.

```
cd /var/www/pinario
git pull
chown -R www-data:www-data /var/www/pinario
chmod 600 .env
./venv/bin/pip install -q -r requirements.txt
./venv/bin/alembic upgrade head
systemctl restart pinario
```

## Fünf Dinge, die später Zeit kosten werden

**Pinterest-App im Trial-Modus.** Eine frisch angelegte App darf nur auf das
eigene Konto. Für pinario reicht das, weil nur eigene Konten bedient werden.
Wer das übersieht, sucht den Fehler an der falschen Stelle.

**Bilder gehen nicht als Datei-Upload an Pinterest.** Entweder Base64 im
Aufruf oder eine öffentlich erreichbare Adresse. Der Adapter nimmt die
zweite: nginx liefert `uploads/` unter `/medien/` ohne Anmeldung aus, siehe
`betrieb/nginx-pinario.conf`, und die Adresse wird aus
`OEFFENTLICHE_ADRESSE` gebaut. **Vom Entwicklungsrechner aus geht das
nicht** — er ist von außen nicht erreichbar, Pinterest holt das Bild also
nirgends ab.

**Video geht bei Pinterest absichtlich nicht.** Ein Pin mit Video braucht den
dreistufigen Medien-Upload, und die Anwendung erzeugt bisher gar keine
Videos. Stünde `video` trotzdem in `typen`, würde der Zeitplan ein
hochgeladenes Video einplanen und der Adapter es beim Posten ablehnen — ein
gescheiterter Versuch, der nie hätte stattfinden dürfen. Kommt zurück,
sobald es Videos gibt.

**Der Google-Zugang ist ein Antrag, kein Knopf.** Ein Projekt in der Cloud
Console anzulegen und die Business-Profile-APIs zu aktivieren reicht nicht;
der Zugang muss bei Google gesondert über ein Formular beantragt und
freigeschaltet werden. Vorher liefert jeder Aufruf 403, obwohl an der
eigenen Einrichtung nichts falsch ist. Deshalb steht `google_business`
nicht in `AKTIV`.

**Ohne bestätigten Standort gibt es bei Google nichts zu posten.** Ein
Beitrag geht immer an einen Standort des Profils. Standorte sind dort das,
was bei Pinterest die Boards sind, und werden im Code gleich behandelt
(`Ablage`); in der Oberfläche heißen sie aber verschieden, dafür gibt es
`ablage_bezeichnung`.

Was in `app/kanaele/google_business.py` am wackligsten ist: Google hat die
alte einheitliche My-Business-API in mehrere Dienste zerlegt, Konten und
Standorte liegen woanders als die Beiträge. Die Pfade dort sind gegen die
Dokumentation geschrieben, nicht gegen einen echten Aufruf. Vor dem ersten
Einsatz gegenlesen.

## Zeitzone

Der Server läuft auf UTC, geplant wird in deutscher Zeit. Wer einen Pin für
"morgen 9 Uhr" einplant, meint 9 Uhr in Deutschland. Jede Datums- und
Uhrzeitfrage geht deshalb durch `app/zeit.py`, nie über die Prozess-Zeitzone
und nie über die Datenbank.
