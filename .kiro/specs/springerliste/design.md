# Design — Praxis Helper

## Überblick

Praxis Helper baut direkt auf der bestehenden Flask-/SQLite-App auf. Der Kern (serverseitige Jinja2-Templates, direkte sqlite3-Nutzung mit parametrisierten Queries, Validierungsschicht) bleibt. Wir ergänzen drei Dinge und entfernen eines:

**Dazu:**
1. **Login + Sitzungen** (Flask-Session, gehashte Passwörter) als Identitäts- und Vorbelegungsmechanismus — direkt in `src/app.py`, keine eigene Auth-Datei.
2. **Springer-Datenmodell und -Seite** (neue Tabelle + Routes + Template).
3. **Server-/Docker-Betrieb** (waitress, Dockerfile, Volume, GitHub-Release-Pipeline).

**Weg:**
4. **Einzelplatz-Betrieb** (`main.py`-Tray-Logik, `src/tray.py`, `build.spec`, PyInstaller, pystray/pillow).

Die bestehende Warteliste (`contacts`) bleibt funktional erhalten; sie bekommt nur ein neues Feld `appointment_time` (Terminzeit). Beide Listen erhalten zusätzlich eine zweite Lebenszyklus-Stufe: nach dem Ausblenden folgt nach 14 Tagen die endgültige Löschung (siehe Abschnitt "Automatische Löschung").

## Architektur

```
Browser (PC / Tablet, Praxis-LAN)
        │  HTTP
        ▼
waitress (WSGI)  ──  Flask-App (src/app.py)   ← Routes, Login/Session, Decorator
        │                 │
        │                 ├── Validierung    (src/validators.py)
        │                 └── Datenschicht   (src/db.py)
        ▼
   SQLite-Datei  (NAS-Volume, Pfad via Env PRAXIS_DB_PATH)
```

Ein Prozess, ein Container, eine SQLite-Datei. Kein separater DB-Dienst.

### Entfernte Komponenten

| Datei | Aktion | Grund |
|---|---|---|
| `src/tray.py` | löschen | kein Tray im Serverbetrieb |
| `build.spec` | löschen | kein PyInstaller-Build mehr |
| `main.py` | ersetzen | neuer, schlanker waitress-Einstiegspunkt |
| `tests/test_tray.py` | löschen | Tray entfällt |
| `pyproject.toml` | ändern | `pystray`, `pillow` raus; `waitress`, `werkzeug` rein |

> `werkzeug` kommt mit Flask ohnehin als Abhängigkeit; wir nennen es explizit, weil wir `generate_password_hash`/`check_password_hash` direkt nutzen.

## Datenmodell

Drei Tabellen. `contacts` existiert bereits und wird erweitert.

### `users` (neu)

```sql
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('therapist','office')),
    display_name  TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```

- `display_name` ist der Name, der in der Springer-Zuordnung und im Filter erscheint (z. B. "Frau Müller").
- `username` für den Login (z. B. `mueller`).

### `springer` (neu)

```sql
CREATE TABLE IF NOT EXISTS springer (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name      TEXT NOT NULL,
    therapist        TEXT NOT NULL,            -- users.display_name (Momentaufnahme)
    valid_from       TEXT NOT NULL,            -- 'YYYY-MM-DD'
    valid_until      TEXT DEFAULT '',          -- 'YYYY-MM-DD' oder leer = unbefristet
    appointment_time TEXT NOT NULL,            -- eine der 4 Terminzeiten
    notes            TEXT DEFAULT '',
    created_at       TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```

- `therapist` speichert den **Anzeigenamen als Text**, nicht `user_id`. Grund: Wird eine Therapeutin aus `users` entfernt, bleiben ihre Springer-Einträge lesbar erhalten (Req 2.4). Keine Foreign Key, kein Cascade.
- `valid_until` als leerer String statt NULL — bewusste Abwägung: erzwingt zwar `valid_until != '' AND ...` statt `IS NOT NULL` in den Queries, hält aber den Stil konsistent mit `contacts` (dort `DEFAULT ''`). Konsistenz wiegt hier schwerer als die minimal sauberere NULL-Semantik.

> `ponytail:` `therapist` als denormalisierter Text statt FK auf `users.id`. Obergrenze: Umbenennen einer Therapeutin aktualisiert alte Einträge nicht automatisch. Bewusst gewählt, weil "Einträge überleben Personalwechsel" (Req 2.4) wichtiger ist als Normalisierung, und bei <100 Zeilen irrelevant für Performance. Upgrade-Pfad: FK + JOIN, falls Umbenennen je gebraucht wird.

### `contacts` (bestehend, erweitert)

Neues Feld `appointment_time` (Terminzeit). Migration additiv:

```sql
ALTER TABLE contacts ADD COLUMN appointment_time TEXT NOT NULL DEFAULT 'flexibel';
```

`init_db()` prüft per `PRAGMA table_info(contacts)`, ob die Spalte existiert, und fügt sie nur bei Bedarf hinzu — so bleibt eine vorhandene `contacts.db` beim ersten Start der neuen Version intakt (Req 7.3).

### Terminzeit — zentrale Konstante

Eine Stelle, keine verstreuten Strings:

```python
# src/validators.py
APPOINTMENT_TIMES = ("flexibel", "mittags", "früher Nachmittag", "nachmittags")
```

Validatoren und Templates beziehen sich darauf. Eingaben außerhalb dieser Liste werden abgelehnt.

## Login & Sitzungen

Minimal, mit Flask-Bordmitteln — keine zusätzliche Auth-Bibliothek.

- **Session**: Flask-`session` (signiertes Cookie). `session["user"] = {"username", "role", "display_name"}` nach erfolgreichem Login.
- **Passwort**: `werkzeug.security.generate_password_hash` beim Anlegen, `check_password_hash` beim Login. Nie Klartext.
- **Schutz der Routes**: ein `@login_required`-Decorator (~10 Zeilen, direkt in `src/app.py`), der bei fehlender Session auf `/login` umleitet. Das ist die einzige harte Sperre — und zwar nur "angemeldet ja/nein", **keine** Rollenprüfung pro Route (Req 4.4: keine harten Sperren zwischen den Rollen).
- **Hashing**: `werkzeug.security.generate_password_hash`/`check_password_hash` werden direkt in den zwei Routes aufgerufen, die sie brauchen (Login, Nutzer anlegen) — keine eigenen Wrapper, keine `auth.py`.
- **Rolle** steuert ausschließlich Vorbelegungen in den Templates (Filter-Default, Namensvorauswahl).

### Secrets über Umgebungsvariablen (Req 1.7, 9.4)

| Variable | Zweck | Fallback |
|---|---|---|
| `PRAXIS_SECRET_KEY` | Flask-Session-Signatur | **keiner** — Start bricht ab, wenn ungesetzt |
| `PRAXIS_ADMIN_USER` | initialer `office`-Login | `admin` |
| `PRAXIS_ADMIN_PASSWORD` | initiales `office`-Passwort | **keiner** — nur gesetzt, wenn Variable vorhanden |
| `PRAXIS_DB_PATH` | Pfad zur SQLite-Datei | Projektroot/`contacts.db` (Entwicklung) |

Der hartkodierte `app.secret_key = "waitlist-secret-key-local-only"` wird durch `os.environ["PRAXIS_SECRET_KEY"]` ersetzt. Fehlt die Variable, bricht der Start mit klarer Meldung ab (statt mit unsicherem Default weiterzulaufen).

### Erst-Start / Seeding (Req 2.5)

In `init_db()`: Nach dem Anlegen der Tabellen — falls `not list_users()` **und** `PRAXIS_ADMIN_PASSWORD` gesetzt ist — ein `office`-Konto aus `PRAXIS_ADMIN_USER`/`PRAXIS_ADMIN_PASSWORD` anlegen. So kommt beim allerersten Start jemand rein, um weitere Nutzer zu pflegen. Danach greift die Bedingung "users leer" nicht mehr.

## Routes

Alle außer `/login` sind mit `@login_required` geschützt.

| Methode | Pfad | Zweck |
|---|---|---|
| GET/POST | `/login` | Anmeldeseite / Anmeldung |
| GET | `/logout` | Abmelden, Session leeren |
| GET | `/` | Redirect auf `/springer` |
| GET | `/springer` | Springer-Seite: aktive (optional ausgeblendete) Einträge + Filter + Erfassen-Formular |
| POST | `/springer/add` | neuen Springer-Eintrag anlegen |
| GET | `/springer/edit/<id>` | Eintrag zum Bearbeiten laden |
| POST | `/springer/edit/<id>` | Eintrag aktualisieren |
| POST | `/springer/delete/<id>` | Eintrag löschen (mit Bestätigung im UI) |
| GET | `/warteliste` | Warteliste (heutiges `/` der alten App), + Terminzeit |
| POST | `/warteliste/add` | Kontakt anlegen |
| GET/POST | `/warteliste/edit/<id>` | Kontakt bearbeiten |
| POST | `/warteliste/delete/<id>` | Kontakt löschen |
| GET | `/warteliste/export` | JSON-Export |
| GET/POST | `/warteliste/import` | JSON-Import |
| GET | `/users` | Nutzerverwaltung (Liste + Anlegen-Formular) |
| POST | `/users/add` | Nutzer anlegen |
| POST | `/users/delete/<id>` | Nutzer entfernen |

Die bestehenden Warteliste-Routes werden von `/` und `/add` etc. auf `/warteliste/*` umgezogen; die Logik bleibt gleich, nur `appointment_time` kommt in Formular und Tabelle dazu.

### Filter-Logik Springer (`/springer`)

Query-Parameter:
- `therapist=<display_name>` — Filter. Default: bei `office` leer (alle), bei `therapist` die eigene `display_name`.
- `show_hidden=1` — auch abgelaufene Einträge zeigen.

"Aktiv" = `valid_until == '' OR valid_until >= heute` (String-Vergleich funktioniert bei ISO-Datum `YYYY-MM-DD`). "Abgelaufen" = `valid_until != '' AND valid_until < heute`.

## Automatische Löschung (zweistufig)

Beide Listen folgen demselben zweistufigen Lebenszyklus:

| Stufe | Warteliste | Springer |
|---|---|---|
| **Ausblenden** (reversibel via "Ausgeblendete anzeigen") | Anmeldedatum + 28 Tage | `valid_until` erreicht |
| **Endgültig löschen** (irreversibel) | Anmeldedatum + 42 Tage | `valid_until` + 14 Tage |

Springer ohne `valid_until` werden weder ausgeblendet noch gelöscht.

### Wann wird gelöscht — einmal pro Tag, ohne Scheduler

Der Container läuft im Dauerbetrieb (wochenlang ohne Neustart). "Nur beim Start löschen" würde deshalb faktisch nie greifen — die Löschung muss im laufenden Betrieb passieren. Da der Container keinen Cron hat, hängen wir sie an eingehende Requests, aber nur **höchstens einmal pro Tag**:

```python
# src/app.py — Modulvariable, kein DB-State nötig
_last_purge_date = None

@app.before_request
def _maybe_purge():
    global _last_purge_date
    today = date.today()
    if _last_purge_date != today:
        db.purge_expired()
        _last_purge_date = today
```

Plus ein `db.purge_expired()` direkt nach `db.init_db()` beim Start, damit nach einem Neustart sofort aufgeräumt ist. Die Löschung ist datumsbasiert und idempotent — mehrfaches Aufrufen am selben Tag schadet nicht, ein verpasster Tag wird beim nächsten Request nachgeholt.

> `ponytail:` In-Memory-Tagesmarke statt persistierter "zuletzt aufgeräumt"-Spalte oder echtem Scheduler. ~5 Zeilen. Obergrenze: Nach einem Neustart wird einmal zusätzlich aufgeräumt (idempotent, harmlos). Diese Variante ist bewusst gewählt, weil der Dauerbetrieb ein Aufräumen im laufenden Betrieb braucht — "nur beim Start" würde den Datenschutzzweck verfehlen.

### `db.purge_expired()`

Zwei `DELETE`-Queries, parametrisiert mit dem heutigen Datum:

```sql
-- Warteliste: 42 Tage nach Anmeldedatum (created_at)
DELETE FROM contacts
WHERE julianday(?) - julianday(created_at) > 42;

-- Springer: 14 Tage nach valid_until (nur wenn gesetzt)
DELETE FROM springer
WHERE valid_until != '' AND julianday(?) - julianday(valid_until) > 14;
```

## Datenschicht (`src/db.py`)

Neue Funktionen, gleiches Muster wie bestehend (eigene Connection pro Call, `try/finally`, parametrisierte Queries):

- **users**: `add_user`, `get_user_by_username`, `list_users`, `delete_user` (Seeding prüft mit `if not list_users()`, keine eigene Count-Funktion)
- **springer**: `add_springer`, `get_springer`, `list_springer(therapist=None, include_expired=False)`, `update_springer`, `delete_springer`
- **contacts**: bestehende Funktionen um `appointment_time` erweitern (add/update/get/export/import).
- **Aufräumen**: `purge_expired()` — löscht endgültig abgelaufene Einträge beider Listen (siehe Abschnitt "Automatische Löschung").

Das Export/Import-Format der Warteliste erhält `appointment_time` additiv; alte Export-Dateien ohne das Feld importieren mit Default `flexibel` (Round-Trip-Eigenschaft aus der alten Spec bleibt gewahrt).

## Validierung (`src/validators.py`)

Bestehendes Muster (HTML-Tags strippen, trimmen) wiederverwenden. Neu:

- `validate_springer(data)`: `client_name` Pflicht; `appointment_time` muss in `APPOINTMENT_TIMES` sein; `valid_from` gültiges Datum; `valid_until` leer oder gültiges Datum; falls beide gesetzt: `valid_until >= valid_from` (Req 3.6).
- `validate_user(data)`: `username`, `password`, `display_name` Pflicht; `role` in `('therapist','office')`.
- `validate_contact` um `appointment_time`-Prüfung erweitern.

## Templates

Bestehendes `base.html` wiederverwenden, Navigation ergänzen (Springer / Warteliste / Nutzer / Abmelden + angemeldeter Name). Neue Templates:

- `login.html`
- `springer.html` — Liste (mit Filter + "Ausgeblendete anzeigen") und Erfassen-/Bearbeiten-Formular. Terminzeit als Schaltflächen (Radio-Buttons, tabletfreundlich groß). **Layout/Gestaltung bewusst offen** — nur die Funktion ist vorgegeben.
- `users.html` — Nutzerliste + Anlegen.
- `index.html` → nach `warteliste.html` (Terminzeit-Spalte + -Auswahl ergänzt).

Deutschsprachig, responsives Layout, Jinja2-Auto-Escaping bleibt aktiv (XSS-Schutz).

## Betrieb: Docker

### `Dockerfile` (neu)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir flask waitress werkzeug
COPY src/ ./src/
COPY templates/ ./templates/
COPY static/ ./static/
COPY main.py .
ENV PRAXIS_DB_PATH=/data/contacts.db
EXPOSE 5000
CMD ["python", "main.py"]
```

- `/data` ist der Mountpoint für das NAS-Volume. `contacts.db` liegt dort, nicht im Image (Req 7.2, 7.5).
- Kein Quellcode-Secret im Image (Req 9.4).

### `main.py` (ersetzt)

Schlanker Einstiegspunkt ohne Tray/Browser:

```python
from waitress import serve
from src.app import app

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=int(os.environ.get("PRAXIS_PORT", "5000")))
```

### `.dockerignore` (neu)

`tests/`, `.venv/`, `.git/`, `.hypothesis/`, `.pytest_cache/`, `__pycache__/`, `*.db` — hält Image klein und Patientendaten draußen.

### `.gitignore`

Ergänzen: `*.tar` (gespeicherte Images), `contacts.db` (prüfen, dass die echte DB nicht eingecheckt ist).

## Deployment: GitHub Release statt Registry (Req 9)

Umbau der bestehenden `.github/workflows/ci.yml`:

- `test`-Job bleibt (pytest).
- `build-exe` und der PyInstaller-Weg **entfallen**.
- Neuer `build-image`-Job (nur bei Tag `v*`): `docker build -t praxis-helper:<tag> .`, dann `docker save praxis-helper:<tag> -o praxis-helper-<tag>.tar`.
- `release`-Job hängt die `.tar` ans GitHub Release (`softprops/action-gh-release`, wie bisher) — **kein** Push in eine Registry (Req 9.2).

### Ablauf auf der QNAP (Dokumentation im README)

1. `praxis-helper-<tag>.tar` vom GitHub Release laden.
2. In Container Station → Images → Import.
3. Container starten mit:
   - Port-Mapping `5000:5000`
   - Volume: NAS-Ordner → `/data`
   - Umgebungsvariablen: `PRAXIS_SECRET_KEY`, `PRAXIS_ADMIN_USER`, `PRAXIS_ADMIN_PASSWORD`
4. Im Browser `http://<nas-ip>:5000` öffnen, als Admin anmelden, Nutzer anlegen.

## Teststrategie

Bestehende pytest/Hypothesis-Struktur weiternutzen. Anpassen/ergänzen:

- `test_tray.py` entfernen.
- `test_validators.py`: Fälle für `validate_springer`, `validate_user`, Terminzeit.
- `test_main.py` (Routes): Login-Flow (Umleitung ohne Session, erfolgreicher Login), Springer-CRUD, Filter + `show_hidden`, Warteliste mit Terminzeit.
- `test_properties.py`: Round-Trip Export/Import der Warteliste inkl. `appointment_time`; Springer "aktiv/abgelaufen"-Grenzfall um `valid_until`.
- Ein kleiner Check für die additive Migration (`contacts` ohne `appointment_time` → nach `init_db()` vorhanden, Daten intakt).
- `purge_expired()`: Grenzfälle — Warteliste bei 41/42/43 Tagen, Springer bei `valid_until` +13/+14/+15 Tagen, Springer ohne `valid_until` wird nie gelöscht, ausgeblendeter-aber-nicht-löschreifer Eintrag bleibt erhalten.

## Bewusste Vereinfachungen

- **Keine `auth.py`** — der eine `@login_required`-Decorator lebt in `app.py`, Hashing wird direkt aus `werkzeug.security` aufgerufen. Keine Datei für ~10 Zeilen.
- **Aufräumen via `before_request`, max. 1×/Tag** — In-Memory-Tagesmarke, kein Scheduler, keine DB-Spalte. Nötig wegen Dauerbetrieb; "nur beim Start" würde nicht greifen.
- **Keine Rollen-Autorisierung pro Route** — nur "angemeldet ja/nein". Entspricht Req 4.4; Sicherheit kommt aus dem LAN.
- **`therapist` als Text, kein FK** — siehe ponytail-Hinweis oben.
- **SQLite ohne Migrations-Framework** — eine additive `ALTER TABLE` reicht; kein Alembic o. Ä. für dieses eine Feld.
- **Kein Rate-Limiting / CSRF-Token** — bewusst weggelassen für den LAN-Betrieb; dokumentiert als bekannte Grenze, falls die App je öffentlich würde.
