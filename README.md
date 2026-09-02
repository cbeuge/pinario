# pinario

Kampagnengesteuertes Erstellen und Posten von Social-Media-Inhalten. Zweck
ist, die eigenen Werkzeuge (welcometap, LeadRadar, gehdirekt, startklar.tools,
Sektor-V) bekannter zu machen und Affiliate-Produkte zu bewerben. Kein
Kundenmaterial, keine echten Fotos von Menschen.

Eine **Kampagne** hat einen Ziel-Link und wird auf mehrere Kanäle
ausgespielt. Je Kanal entstehen mehrere **Varianten** desselben Inhalts:
damit Pinterest keine Dubletten sieht, und damit sich messen lässt, welche
Variante zieht. Bei Pinterest kommt die Zuordnung zu Boards dazu.

Erster Kanal ist Pinterest. Instagram, Facebook und X stehen als Struktur
schon bereit, sind aber nicht aktiv.

## Stand am 02.09.2026

Gebaut:

* Marke als SVG in hell, dunkel und selbst umschaltend, dazu Favicon und
  PNG-Raster. Erzeugt aus `marke_quelle/logo2.png`, siehe unten
* Startseite: nur Wortmarke und Passwortfeld. Ein Nutzer, kein
  Registrierungs-Weg, Bremse nach fünf Fehlversuchen
* Datenmodell vollständig, Migration `0001_grundgeruest` legt alle Tabellen
  an und trägt die vier Kanäle ein
* Übersicht hinter der Anmeldung: Kampagnen und Kanäle, noch ohne Anlegen
* Verschlüsselung für die OAuth-Token (`app/tresor.py`)
* Kanal-Schnittstelle (`app/kanaele/basis.py`) und Pinterest-Adapter als
  Gerüst
* Lokale Datenbank steht, Anmeldung von Anfang bis Ende durchgespielt

**Eine Regel, die man kennen muss:** eine Kampagne, die schon gepostet hat,
lässt sich nicht löschen — die Datenbank weist es ab. Die Messreihe ist der
Zweck der Anwendung, und sie beim Aufräumen stillschweigend mitzunehmen wäre
der teuerste Knopf im Programm. Kampagnen werden auf `paused` gesetzt. Eine
Kampagne ohne Veröffentlichungen lässt sich normal löschen. Ausführlich im
Docstring von `PostedItem`.

Noch nicht gebaut:

* Kampagnen anlegen und bearbeiten
* Content-Erzeugung über Gemini (Text, Bild, später Video)
* Scheduler fürs zeitversetzte Posten
* Pinterest wirklich verbinden und posten. Der Adapter kennt die Adressen,
  ist aber **gegen die echte API noch nie gelaufen** — dafür fehlen die
  Zugangsdaten von developers.pinterest.com
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
  views.py        Seiten hinter der Anmeldung
  cli.py          `flask passwort`, `flask kanaele-abgleichen`
  kanaele/        ein Adapter je Plattform
marke_quelle/     Vorlage und Werkzeug für die Logo-Dateien
betrieb/          systemd-Unit und nginx-Konfiguration
migrations/       Alembic
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

Noch nicht ausgerollt. Vorgesehen analog zu betmaster und LeadRadar:

```
/var/www/pinario               Code, venv, .env, logs, uploads
pinario.service                gunicorn auf 127.0.0.1:3008, 2 Arbeiter
/etc/nginx/sites-available/pinario
Datenbank pinario              eigene Rolle, nicht die der anderen Projekte
```

**Auf dem Server dann wirklich eine eigene Rolle**, anders als lokal. Sonst
käme pinario an die Daten der anderen Anwendungen auf demselben Postgres.

`pinario.de` und `www.pinario.de` zeigen auf den Server, `admin.pinario.de`
ebenfalls. Die Anwendung läuft auf `pinario.de`; für `admin` gibt es
bewusst keinen eigenen Block, weil sie nicht gebraucht wird (Entscheidung
vom 02.09.2026). Der DNS-Eintrag darf stehenbleiben. Wer sie später doch
will: einen zweiten `server`-Block mit demselben `proxy_pass` anlegen und
das Zertifikat um den Namen erweitern.

Die Vorlagen liegen unter `betrieb/`. Der Ablauf beim ersten Mal:

```
# Datenbank
sudo -u postgres createdb pinario
sudo -u postgres psql -c "CREATE ROLE pinario LOGIN PASSWORD '<neu>'"
sudo -u postgres psql -d pinario -c "GRANT ALL ON SCHEMA public TO pinario"

# Code
git clone <repo> /var/www/pinario
cd /var/www/pinario
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env          # PRODUKTION=1 nicht vergessen
chown -R www-data:www-data /var/www/pinario
chmod 600 .env
./venv/bin/alembic upgrade head
./venv/bin/flask --app wsgi passwort

# Dienst und Proxy
cp betrieb/pinario.service /etc/systemd/system/
systemctl enable --now pinario
cp betrieb/nginx-pinario.conf /etc/nginx/sites-available/pinario
ln -s /etc/nginx/sites-available/pinario /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d pinario.de -d www.pinario.de
```

Aktualisieren danach (als root, nicht als `www-data`: der GitHub-Schlüssel
liegt bei root, deshalb wird der Besitzer nach dem Ziehen wieder gerade
gerückt):

```
cd /var/www/pinario
git pull
chown -R www-data:www-data /var/www/pinario
chmod 600 .env
./venv/bin/pip install -q -r requirements.txt
./venv/bin/alembic upgrade head
systemctl restart pinario
```

## Zwei Dinge, die später Zeit kosten werden

**Pinterest-App im Trial-Modus.** Eine frisch angelegte App darf nur auf das
eigene Konto. Für pinario reicht das, weil nur eigene Konten bedient werden.
Wer das übersieht, sucht den Fehler an der falschen Stelle.

**Bilder gehen nicht als Datei-Upload an Pinterest.** Entweder Base64 im
Aufruf oder eine öffentlich erreichbare Adresse. Für die zweite Variante
liefert nginx `uploads/` unter `/medien/` aus, siehe
`betrieb/nginx-pinario.conf`.

## Zeitzone

Der Server läuft auf UTC, geplant wird in deutscher Zeit. Wer einen Pin für
"morgen 9 Uhr" einplant, meint 9 Uhr in Deutschland. Jede Datums- und
Uhrzeitfrage geht deshalb durch `app/zeit.py`, nie über die Prozess-Zeitzone
und nie über die Datenbank.
