# Implementierungsplan: Praxis Helper

## Übersicht

Umbau der bestehenden Einzelplatz-Warteliste zu einem server-basierten Praxis-Helper mit Springer-Seite, Login und Docker-Betrieb. Die Reihenfolge geht von innen nach außen: zuerst Datenschicht und Validierung (gut testbar), dann Auth, dann Routes/Templates, dann Entfernen des Lokalbetriebs, zuletzt Docker/CI/README. Jeder Schritt endet mit lauffähigem, getestetem Code.

Die bestehende `contacts`-Logik bleibt erhalten und wird nur erweitert; Springer, Login und Löschung kommen neu dazu.

## Aufgaben

- [ ] 1. Datenschicht erweitern (`src/db.py`)
  - [ ] 1.1 Terminzeit-Konstante und Schema-Erweiterungen
    - `APPOINTMENT_TIMES = ("flexibel", "mittags", "früher Nachmittag", "nachmittags")` in `src/validators.py` definieren
    - DB-Pfad aus `PRAXIS_DB_PATH` lesen, Fallback Projektroot/`contacts.db`
    - `init_db()`: Tabellen `users` und `springer` gemäß Design anlegen (parametrisiert, `IF NOT EXISTS`)
    - Additive Migration: `contacts.appointment_time` per `PRAGMA table_info` prüfen und nur bei Bedarf per `ALTER TABLE ... ADD COLUMN ... DEFAULT 'flexibel'` ergänzen
    - _Anforderungen: 7.3, 8.1, 8.3, 9.3_

  - [ ] 1.2 CRUD-Funktionen für `users`
    - `add_user`, `get_user_by_username`, `list_users`, `delete_user` (alle parametrisiert, Row-Factory wie bestehend). Keine eigene Count-Funktion — Seeding prüft mit `if not list_users()`
    - _Anforderungen: 2.1, 2.2, 2.3_

  - [ ] 1.3 CRUD-Funktionen für `springer`
    - `add_springer`, `get_springer`, `list_springer(therapist=None, include_expired=False)`, `update_springer`, `delete_springer`
    - `list_springer`: Filter nach `therapist` (Anzeigename) optional; `include_expired=False` blendet abgelaufene (`valid_until != '' AND valid_until < heute`) aus
    - _Anforderungen: 4.2, 4.3, 4.5, 4.6, 5.2, 5.3_

  - [ ] 1.4 `contacts`-Funktionen um `appointment_time` erweitern
    - `add_contact`, `update_contact`, `get_*`, `export_contacts`, `import_contacts` um das Feld ergänzen; Import ohne Feld → Default `flexibel`
    - _Anforderungen: 6.1, 6.2_

  - [ ] 1.5 `purge_expired()` implementieren
    - Zwei `DELETE`-Queries (parametrisiert mit heutigem Datum): Warteliste > 42 Tage nach `created_at`; Springer `valid_until != '' AND` > 14 Tage nach `valid_until`
    - _Anforderungen: 7.1, 7.2, 7.3, 7.4, 7.6_

- [ ] 2. Validierung erweitern (`src/validators.py`)
  - [ ] 2.1 `validate_springer(data)`
    - `client_name` Pflicht; `appointment_time` muss in `APPOINTMENT_TIMES` sein; `valid_from` gültiges Datum; `valid_until` leer oder gültig; falls beide gesetzt: `valid_until >= valid_from`; HTML-Strippen/Trimmen wie bestehend
    - _Anforderungen: 3.1, 3.2, 3.5, 3.6_

  - [ ] 2.2 `validate_user(data)`
    - `username`, `password`, `display_name` Pflicht; `role` in `('therapist','office')`
    - _Anforderungen: 2.1_

  - [ ] 2.3 `validate_contact` um `appointment_time` erweitern
    - Wert muss in `APPOINTMENT_TIMES` sein (Default `flexibel` bei fehlendem Wert)
    - _Anforderungen: 6.2, 6.3_

- [ ] 3. Tests Datenschicht & Validierung
  - [ ] 3.1 Property-/Unit-Tests Validierung (`tests/test_validators.py`)
    - Springer: leerer Name abgelehnt; ungültige Terminzeit abgelehnt; `valid_until < valid_from` abgelehnt; leeres `valid_until` akzeptiert
    - User: fehlende Pflichtfelder und ungültige Rolle abgelehnt
    - _Anforderungen: 2.1, 3.1, 3.2, 3.5, 3.6_

  - [ ] 3.2 Tests `purge_expired()` (`tests/test_properties.py`)
    - Warteliste-Grenzfälle 41/42/43 Tage; Springer `valid_until` +13/+14/+15 Tage; Springer ohne `valid_until` wird nie gelöscht; ausgeblendeter-aber-nicht-löschreifer Eintrag bleibt
    - _Anforderungen: 7.1, 7.2, 7.3, 7.4_

  - [ ] 3.3 Test additive Migration
    - `contacts` ohne `appointment_time` anlegen → nach `init_db()` existiert die Spalte, bestehende Zeilen intakt mit Default
    - _Anforderungen: 7.3 (Erhalt), 9.3_

- [ ] 4. Zwischenprüfung – alle Tests bestehen
  - Sicherstellen, dass alle Tests bestehen; bei Fragen den Anwender konsultieren.

- [ ] 5. Login-Grundlagen (in `src/app.py`, keine eigene Datei)
  - [ ] 5.1 Decorator & Secret-Key
    - `@login_required`-Decorator (~10 Zeilen, nur "angemeldet ja/nein", keine Rollenprüfung) der auf `/login` umleitet; `werkzeug.security`-Hashfunktionen direkt nutzen (keine Wrapper)
    - Secret-Key aus `PRAXIS_SECRET_KEY` lesen; Start abbrechen mit klarer Meldung, falls ungesetzt
    - _Anforderungen: 1.4, 1.5, 1.7_

  - [ ] 5.2 Seeding des initialen `office`-Kontos
    - In `init_db()` nach Tabellen: falls `not list_users()` und `PRAXIS_ADMIN_PASSWORD` gesetzt → `office`-Nutzer aus `PRAXIS_ADMIN_USER`/`PRAXIS_ADMIN_PASSWORD` (gehasht) anlegen
    - _Anforderungen: 2.5, 1.4_

- [ ] 6. Routes umbauen und ergänzen (`src/app.py`)
  - [ ] 6.1 Login/Logout
    - `GET/POST /login` (Fehlermeldung generisch bei falschen Daten), `GET /logout`; `GET /` → Redirect `/springer`
    - `@app.before_request`-Hook: `db.purge_expired()` höchstens einmal pro Tag (In-Memory-Tagesmarke); zusätzlich einmal nach `db.init_db()` beim Start (Dauerbetrieb — "nur beim Start" würde nicht greifen)
    - Hartkodierten `app.secret_key` durch Env-Variante ersetzen
    - _Anforderungen: 1.1, 1.2, 1.3, 1.6, 7.5_

  - [ ] 6.2 Springer-Routes
    - `GET /springer` (Filter `therapist`, `show_hidden`; rollenabhängige Defaults), `POST /springer/add`, `GET/POST /springer/edit/<id>`, `POST /springer/delete/<id>`
    - Zuordnung: bei `therapist` eigener `display_name` vorgewählt, bei `office` Auswahl Pflicht
    - _Anforderungen: 3.3, 3.4, 4.1, 4.3, 4.4, 5.1, 5.2, 5.4_

  - [ ] 6.3 Warteliste-Routes umziehen
    - Bestehende Routes von `/`, `/add`, `/edit`, `/delete`, `/export`, `/import` nach `/warteliste/*` verschieben; Logik gleich, `appointment_time` ergänzen
    - _Anforderungen: 6.1, 6.4, 6.5, 6.6, 6.7_

  - [ ] 6.4 Nutzerverwaltung-Routes
    - `GET /users`, `POST /users/add`, `POST /users/delete/<id>`; entfernte Therapeutin → Springer-Einträge bleiben (kein Cascade)
    - _Anforderungen: 2.1, 2.2, 2.3, 2.4_

- [ ] 7. Templates (`templates/`)
  - [ ] 7.1 Navigation in `base.html` ergänzen
    - Links Springer / Warteliste / Nutzer / Abmelden + angemeldeter Anzeigename; deutschsprachig, responsiv
    - _Anforderungen: 1.6, 9.6_

  - [ ] 7.2 `login.html`
    - Benutzername/Passwort-Formular, generische Fehlermeldung
    - _Anforderungen: 1.1, 1.3_

  - [ ] 7.3 `springer.html`
    - Liste (Therapeutin, Name, Zeitraum von/bis, Terminzeit, Hinweis) mit Filter + "Ausgeblendete anzeigen", abgelaufene visuell unterscheidbar; Erfassen-/Bearbeiten-Formular mit Terminzeit als große Schaltflächen (tabletfreundlich); Löschen mit Bestätigung. Layout bewusst frei gestaltbar
    - _Anforderungen: 3.1, 3.2, 3.7, 4.1, 4.2, 4.3, 4.4, 4.8, 4.9, 5.1, 5.3_

  - [ ] 7.4 `index.html` → `warteliste.html`
    - Terminzeit-Auswahl im Formular und -Spalte in der Tabelle ergänzen; Rest wie bestehend (Ausgeblendete-Toggle, Export/Import, Löschbestätigung)
    - _Anforderungen: 6.1, 6.2, 6.5, 6.6_

  - [ ] 7.5 `users.html`
    - Nutzerliste + Anlegen-Formular (Benutzername, Passwort, Rolle, Anzeigename), Entfernen mit Bestätigung
    - _Anforderungen: 2.1, 2.3_

  - [ ] 7.6 `static/` anpassen
    - CSS für Terminzeit-Schaltflächen, abgelaufene Springer (`.expired`), Login/Nutzer-Seiten; `script.js` Bestätigungsdialoge
    - _Anforderungen: 3.7, 4.8, 9.6_

- [ ] 8. Zwischenprüfung – alle Tests bestehen
  - Sicherstellen, dass alle Tests bestehen; bei Fragen den Anwender konsultieren.

- [ ] 9. Route-/UI-Tests (`tests/test_main.py`, `tests/test_ui.py`)
  - [ ] 9.1 Login-Flow
    - Ohne Session → Umleitung auf `/login`; erfolgreicher Login setzt Session und leitet auf `/springer`; falsche Daten → generische Fehlermeldung, keine Session
    - _Anforderungen: 1.2, 1.3, 1.5_

  - [ ] 9.2 Springer-CRUD und Filter
    - Anlegen/Bearbeiten/Löschen; Filter `therapist`; `show_hidden` zeigt abgelaufene; `office` ohne Filter-Default, `therapist` mit eigenem Default
    - _Anforderungen: 3.3, 4.3, 4.5, 4.8, 5.1, 5.2_

  - [ ] 9.3 Warteliste mit Terminzeit + Nutzerverwaltung
    - Warteliste-Eintrag mit Terminzeit anlegen; Nutzer anlegen/entfernen; entfernte Therapeutin → ihre Springer-Einträge weiter sichtbar
    - _Anforderungen: 2.3, 2.4, 6.1, 6.2_

- [ ] 10. Lokalbetrieb entfernen
  - [ ] 10.1 Tray/PyInstaller-Artefakte löschen
    - `src/tray.py`, `build.spec`, `tests/test_tray.py` entfernen
    - `pyproject.toml`: `pystray`, `pillow` raus; `waitress`, `werkzeug` ergänzen
    - _Anforderungen: 9.5_

  - [ ] 10.2 `main.py` auf waitress umstellen
    - Schlanker Einstiegspunkt: `waitress.serve(app, host="0.0.0.0", port=PRAXIS_PORT)`; kein Thread/Tray/Browser-Open
    - _Anforderungen: 9.2, 9.3_

- [ ] 11. Docker & Deployment
  - [ ] 11.1 `Dockerfile` und `.dockerignore`
    - `python:3.11-slim`, flask/waitress/werkzeug installieren, `src`/`templates`/`static`/`main.py` kopieren, `ENV PRAXIS_DB_PATH=/data/contacts.db`, `EXPOSE 5000`
    - `.dockerignore`: `tests/`, `.venv/`, `.git/`, `.hypothesis/`, `.pytest_cache/`, `__pycache__/`, `*.db`
    - `.gitignore`: `*.tar`, DB-Datei absichern
    - _Anforderungen: 8.1, 8.2, 8.3, 8.4, 8.5 (Image), 9.3, 9.4_

  - [ ] 11.2 CI-Workflow umbauen (`.github/workflows/ci.yml`)
    - `test`-Job behalten; `build-exe` + PyInstaller entfernen; neuer `build-image`-Job (nur bei Tag `v*`): `docker build` + `docker save` → `.tar`; `release`-Job hängt `.tar` ans Release (keine Registry)
    - _Anforderungen: 10.1, 10.2, 10.3, 10.4_

  - [ ] 11.3 README aktualisieren
    - `.exe`/Tray-Abschnitte durch Docker/QNAP-Deployment ersetzen: tar vom Release laden, Container Station Import, Port-Mapping + `/data`-Volume + Env-Variablen (`PRAXIS_SECRET_KEY`, `PRAXIS_ADMIN_USER`, `PRAXIS_ADMIN_PASSWORD`); Entwicklung lokal mit `flask run`; Namens-/Zweck-Update "Praxis Helper"
    - _Anforderungen: 10.5, 8.6_

- [ ] 12. Abschlussprüfung
  - [ ] 12.1 Alle Tests grün
    - `uv run pytest tests/ -v` fehlerfrei
  - [ ] 12.2 Container lokal verifizieren
    - Image bauen, Container mit gesetzten Env-Variablen und Test-Volume starten, `http://localhost:5000` prüfen: Login, Springer anlegen/filtern, Warteliste mit Terminzeit, Nutzer anlegen; danach Test-Volume aufräumen
    - _Anforderungen: 8.1, 8.3, 8.4_

## Hinweise

- Jede Aufgabe referenziert spezifische Anforderungen zur Nachverfolgbarkeit.
- Zwischenprüfungen (4, 8) und die Abschlussprüfung (12) stellen inkrementelle Validierung sicher.
- Reihenfolge innen→außen: Datenschicht/Validierung zuerst (gut isoliert testbar), UI/Docker zuletzt.
- Die automatische Löschung (`purge_expired`) ist irreversibel — die Grenzfall-Tests in 3.2 sind kein optionales Extra.
