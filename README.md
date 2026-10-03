# Praxis Helper

Interne Web-Anwendung für eine Therapiepraxis. Verwaltet zwei Listen:

- **Springerliste** – Klientinnen, die kurzfristig frei werdende Termine übernehmen können. Jede Therapeutin pflegt ihre eigenen Einträge (Zeitraum von/bis, mögliche Terminzeit).
- **Warteliste** – neu angemeldete Klientinnen ohne feste Termine.

Läuft als zentraler Dienst in einem Docker-Container auf der QNAP-NAS der Praxis und wird im Browser bedient – von Praxis-PCs und Tablets, ausschließlich im Praxis-LAN/WLAN. Technisch: Python + Flask + SQLite, serverseitig gerenderte Jinja2-Templates, ausgeliefert über waitress.

## Features

- Springer-Einträge und Warteliste getrennt pflegen
- Einfaches Login mit zwei Rollen (Therapeutin / Sekretariat)
- Terminzeit-Auswahl (flexibel / mittags / früher Nachmittag / nachmittags)
- Automatisches Ausblenden abgelaufener Einträge, endgültige Löschung nach weiteren 14 Tagen
- Export/Import der Warteliste als JSON (Backup)
- Deutschsprachige, tabletfreundliche Oberfläche

## Rollen und Login

Es gibt zwei Ansichten:

- **Therapeutin** (`role = therapist`): landet beim Login in der eigenen Springerliste (Filter und Namensvorauswahl auf sie selbst).
- **Sekretariat** (`role = office`): sieht standardmäßig alle Therapeutinnen und pflegt zusätzlich die Warteliste.

Das Login dient der Identität und der Vorbelegung, nicht der Abschottung – es gibt keine harten Zugriffssperren zwischen den Rollen. Die Sicherheit kommt aus dem geschlossenen Praxis-LAN (kein öffentlicher Internetzugriff). Passwörter werden gehasht gespeichert.

Nutzer werden in der App unter **Nutzer** vom Sekretariat gepflegt (anlegen/entfernen). Wird eine Therapeutin entfernt, bleiben ihre Springer-Einträge erhalten.

## Konfiguration (Umgebungsvariablen)

| Variable | Zweck | Pflicht |
|---|---|---|
| `PRAXIS_SECRET_KEY` | Signatur der Session-Cookies | **ja** – ohne startet die App nicht |
| `PRAXIS_ADMIN_USER` | Benutzername des initialen Sekretariats-Kontos (Default `admin`) | nein |
| `PRAXIS_ADMIN_PASSWORD` | Passwort des initialen Kontos (nur beim allerersten Start, solange keine Nutzer existieren) | beim ersten Start |
| `PRAXIS_DB_PATH` | Pfad zur SQLite-Datei (im Container `/data/contacts.db`) | nein |
| `PRAXIS_PORT` | Port des Servers (Default `5000`) | nein |

Beim allerersten Start wird – falls noch kein Nutzer existiert und `PRAXIS_ADMIN_PASSWORD` gesetzt ist – ein Sekretariats-Konto angelegt. Danach weitere Nutzer in der App pflegen.

## Deployment auf der QNAP-NAS

Das Image wird nicht in einer Container-Registry veröffentlicht, sondern als tar-Datei an ein [GitHub Release](https://github.com/GrafBunsen/waitlist/releases) gehängt (automatisch beim Pushen eines Versions-Tags `vX.Y.Z`).

1. `praxis-helper-<version>.tar` vom gewünschten Release herunterladen.
2. Datei auf die NAS kopieren (File Station o. Ä.).
3. In **Container Station** → *Images* → **Importieren** die tar-Datei auswählen.
4. Container aus dem Image erstellen mit:
   - **Port-Mapping**: Host `5000` → Container `5000`
   - **Volume**: ein NAS-Ordner (z. B. `/share/praxis-helper-data`) → Container `/data`
   - **Umgebungsvariablen**: `PRAXIS_SECRET_KEY` (ein langes zufälliges Geheimnis), beim ersten Start zusätzlich `PRAXIS_ADMIN_USER` und `PRAXIS_ADMIN_PASSWORD`
5. Container starten und im Browser `http://<nas-ip>:5000` öffnen, als Sekretariat anmelden, Nutzer anlegen.

**Backup**: Die gesamte Datenhaltung liegt in der Datei `contacts.db` im gemounteten Volume. Für ein Backup diese Datei kopieren.

**Update**: Neue tar-Version importieren und den Container neu aus dem neuen Image erstellen – das Volume (und damit die Daten) bleibt erhalten.

## Entwicklung

```bash
# Abhängigkeiten installieren
uv sync --all-extras

# Server starten (Entwicklung, Flask-Dev-Server)
PRAXIS_SECRET_KEY=dev uv run flask --app src.app run --port 5000

# Oder wie in Produktion über waitress
PRAXIS_SECRET_KEY=dev uv run python main.py

# Tests ausführen
uv run pytest tests/ -v
```

Beim ersten lokalen Start ein Konto seeden:

```bash
PRAXIS_SECRET_KEY=dev PRAXIS_ADMIN_USER=admin PRAXIS_ADMIN_PASSWORD=admin uv run python main.py
```

Ohne gesetztes `PRAXIS_DB_PATH` liegt die Datenbank im Projektroot (`contacts.db`).

## Image lokal bauen (optional)

```bash
docker build -t praxis-helper:dev .
docker run --rm -p 5000:5000 \
  -e PRAXIS_SECRET_KEY=dev \
  -e PRAXIS_ADMIN_USER=admin -e PRAXIS_ADMIN_PASSWORD=admin \
  -v "$(pwd)/data:/data" \
  praxis-helper:dev
```

## Projektstruktur

```
├── main.py          # Einstiegspunkt (waitress-Server)
├── Dockerfile       # Container-Build
├── src/
│   ├── app.py       # Flask-App, Routes, Login/Session
│   ├── db.py        # SQLite-Datenbankschicht
│   └── validators.py
├── templates/       # Jinja2-Templates (login, springer, warteliste, users)
├── static/          # CSS + JS
├── tests/           # pytest + Hypothesis
└── pyproject.toml
```
