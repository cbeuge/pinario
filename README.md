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

Erster Kanal ist Pinterest. Google Business Profile hat einen Adapter, ist
aber noch nicht benutzbar (Zugang bei Google nicht beantragt). Instagram,
Facebook und X stehen nur als Struktur bereit.

**Google Business Profile ist der Ausreißer unter den Kanälen** und
verdient zwei Sätze. Er erreicht Leute, die *das Unternehmen* suchen, nicht
Leute, die nach einem Thema stöbern. Für die eigenen Werkzeuge ist er
deshalb genau richtig, für Affiliate-Produkte nicht — und das ist keine
Geschmacksfrage: Googles Richtlinien sind bei werblichen Fremdlinks im
Unternehmensprofil streng, und die Folge ist im Zweifel ein gesperrter
Eintrag. Der Kanal trägt deshalb `affiliate_erlaubt = False`
(`app/kanaele/basis.py`), damit die Regel an einer Stelle lebt statt als
Sonderfall in der Kampagnen-Maske.

## Stand am 03.09.2026

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
* `www.pinario.de` leitet per 301 auf die Hauptadresse um, das Zertifikat
  deckt beide Namen ab

**Eine Regel, die man kennen muss:** eine Kampagne, die schon gepostet hat,
lässt sich nicht löschen — die Datenbank weist es ab. Die Messreihe ist der
Zweck der Anwendung, und sie beim Aufräumen stillschweigend mitzunehmen wäre
der teuerste Knopf im Programm. Kampagnen werden auf `paused` gesetzt. Eine
Kampagne ohne Veröffentlichungen lässt sich normal löschen. Ausführlich im
Docstring von `PostedItem`.

Noch nicht gebaut:

* Videos erzeugen. Text und Bild stehen, Video nicht
* Scheduler fürs zeitversetzte Posten. `content_items.geplant_fuer` ist die
  Spalte dafür und wird bisher von nichts gefüllt
* Pinterest wirklich verbinden und posten. Der Adapter kennt die Adressen,
  ist aber **gegen die echte API noch nie gelaufen** — dafür fehlen die
  Zugangsdaten von developers.pinterest.com
* Google Business Profile verbinden. Dasselbe wie bei Pinterest, plus die
  Freischaltung durch Google, siehe unten
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
  einstellungen.py  Werte, die sich im Betrieb ändern, geheime verschlüsselt
  kanaele/        ein Adapter je Plattform
                  basis.py            was ein Kanal können muss
                  pinterest.py        Pinterest API v5
                  google_business.py  Google Business Profile
marke_quelle/     Vorlage und Werkzeug für die Logo-Dateien
betrieb/          systemd-Unit und nginx-Konfiguration
migrations/       Alembic
pruefe_rechtstext.py  misst den HTML-Säuberer nach (37 Fälle)
pruefe_ki.py          misst die Anfrage an Gemini nach (28 Fälle)
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

## Vier Dinge, die später Zeit kosten werden

**Pinterest-App im Trial-Modus.** Eine frisch angelegte App darf nur auf das
eigene Konto. Für pinario reicht das, weil nur eigene Konten bedient werden.
Wer das übersieht, sucht den Fehler an der falschen Stelle.

**Bilder gehen nicht als Datei-Upload an Pinterest.** Entweder Base64 im
Aufruf oder eine öffentlich erreichbare Adresse. Für die zweite Variante
liefert nginx `uploads/` unter `/medien/` aus, siehe
`betrieb/nginx-pinario.conf`.

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
