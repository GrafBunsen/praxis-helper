# Anforderungsdokument — Praxis Helper

## Einleitung

**Praxis Helper** ist eine einfache, interne Web-Anwendung für eine Therapiepraxis. Sie verwaltet zwei getrennte Listen:

- **Springer-Einträge**: Klientinnen, die kurzfristig frei werdende Termine übernehmen können. Jeder Eintrag ist einer Therapeutin zugeordnet (Zeitraum von/bis, mögliche Terminzeit).
- **Warteliste (Neuanmeldungen)**: neu angemeldete Klientinnen ohne feste Termine. Wird v. a. vom Sekretariat gepflegt. (Dies ist die Weiterentwicklung der bestehenden Warteliste.)

Bedient wird die App über zwei Seiten: eine **Springer-Seite** (Anzeige der aktiven Springer mit Therapeutin-Filter sowie Erfassen neuer Einträge) und eine **Warteliste-Seite** (wie bisher). Dieselben Seiten gelten für alle Nutzerinnen; je nach Rolle unterscheiden sich nur der vorbelegte Filter und die Namensvorauswahl. Das konkrete Layout und die Gestaltung sind nicht vorgegeben.

Die App läuft als zentraler Dienst in einem Docker-Container auf der QNAP-NAS der Praxis und wird ausschließlich im Praxis-LAN/WLAN über den Browser bedient — von Praxis-PCs und von Tablets. Es gibt keinen öffentlichen Internetzugriff und keine Installation auf den Endgeräten.

Technisch baut Praxis Helper auf dem bestehenden Stack auf: **Python + Flask + SQLite**, serverseitig gerenderte Jinja2-Templates. Der frühere Einzelplatz-Betrieb als Windows-`.exe` mit System-Tray entfällt vollständig.

### Leitplanken

- **Simpel schlägt umständlich.** Die einfachste Lösung, die den Zweck erfüllt, ist die richtige.
- **Robustheit, nicht Härtung.** Sicherheit kommt aus dem geschlossenen Praxis-LAN. Das Login dient der Identität und einem sinnvollen Startpunkt, nicht der Abschottung gegen böswillige Nutzer.
- **Zwei Listen im Parallelbetrieb.** Die Springerliste kommt neu dazu; die Warteliste bleibt erhalten und wird nicht ersetzt.

## Glossar

- **Praxis Helper**: Der Anzeigename der Anwendung (Browser-Titel, Login, Überschriften). Technischer Name / Docker-Image: `praxis-helper`.
- **Server**: Der Flask-Webserver, der im Docker-Container auf der NAS läuft und die Web-UI im Praxis-LAN bereitstellt.
- **QNAP-NAS**: Das vorhandene Netzwerkspeichergerät der Praxis, auf dem der Container über Container Station betrieben wird.
- **Praxis-LAN**: Das lokale Netzwerk der Praxis (LAN/WLAN) ohne öffentlichen Internetzugriff auf die App.
- **Therapeutin**: Nutzerin, die ihre eigenen Springer-Einträge pflegt. Loggt sich ein; Filter und Namensvorauswahl stehen auf ihr selbst.
- **Sekretariat**: Sammelbegriff für Sekretärin und Praxisinhaberin. Sieht standardmäßig alle Therapeutinnen (kein Filter) und pflegt die Warteliste sowie Springer-Einträge für beliebige Therapeutinnen.
- **Rolle**: Entweder `therapist` oder `office`. Steuert nur Vorbelegungen (Filter, Namensvorauswahl), keine harten Zugriffssperren.
- **Springer-Seite**: Die Seite, die die aktiven Springer (gefiltert nach Therapeutin) anzeigt und das Erfassen neuer Einträge ermöglicht.
- **Nutzer**: Ein Login-Konto mit Benutzername, gehashtem Passwort, Rolle und Anzeigename. In der Datenbank gepflegt.
- **Springer-Eintrag**: Ein Eintrag auf der Springer-Seite (Klientin, Zeitraum von/bis, Terminzeit, Hinweis, zugeordnete Therapeutin).
- **Warteliste**: Zentrale Liste neu angemeldeter Klientinnen (Name, Telefon, E-Mail, Anmeldedatum, Terminzeit, Hinweis).
- **Terminzeit**: Einfachauswahl der möglichen Tageszeit. Erlaubte Werte: `flexibel`, `mittags`, `früher Nachmittag`, `nachmittags`.
- **Zeitraum bis**: Enddatum eines Springer-Eintrags. Nach Ablauf verschwindet der Eintrag aus der aktiven Springerliste. Leer = unbegrenzt gültig.
- **Sichtbarkeitsfrist**: Zeitraum (Standard: 28 Tage ab Anmeldedatum), nach dem ein Warteliste-Eintrag automatisch aus der aktiven Liste verschwindet (ausgeblendet, nicht gelöscht).
- **Löschfrist**: Zeitraum (14 Tage) nach dem Ausblenden, nach dem ein Eintrag endgültig aus der Datenbank gelöscht wird. Warteliste: 42 Tage nach Anmeldedatum. Springer: 14 Tage nach Zeitraum bis.
- **Container Station**: Die Docker-Verwaltung der QNAP-NAS, über die das Image importiert und der Container betrieben wird.

## Anforderungen

### Anforderung 1: Anmelden

**User Story:** Als Nutzerin möchte ich mich mit Benutzername und Passwort anmelden, damit die App weiß, wer ich bin, und meine Ansicht entsprechend vorbelegt.

#### Akzeptanzkriterien

1. THE App SHALL eine Anmeldeseite mit den Feldern Benutzername und Passwort anzeigen.
2. WHEN eine Nutzerin gültige Zugangsdaten eingibt, THE App SHALL eine Sitzung starten und die Nutzerin auf die Springer-Seite weiterleiten.
3. IF Benutzername oder Passwort falsch sind, THEN THE App SHALL eine allgemeine Fehlermeldung anzeigen und keine Sitzung starten.
4. THE App SHALL Passwörter ausschließlich als Hash speichern (werkzeug `generate_password_hash`), niemals im Klartext.
5. WHEN eine nicht angemeldete Nutzerin eine andere Seite als die Anmeldeseite aufruft, THE App SHALL sie zur Anmeldeseite weiterleiten.
6. THE App SHALL eine Abmeldefunktion bereitstellen, die die Sitzung beendet.
7. THE App SHALL den Flask-Secret-Key und das initiale Admin-Passwort aus Umgebungsvariablen lesen und NICHT im Quellcode hinterlegen.

### Anforderung 2: Nutzer verwalten

**User Story:** Als Sekretariat möchte ich Nutzer anlegen und entfernen können, damit ich auf personelle Wechsel reagieren kann, wenn jemand geht oder dazukommt.

#### Akzeptanzkriterien

1. THE App SHALL dem Sekretariat eine Nutzerverwaltung bereitstellen, um Nutzer mit Benutzername, Passwort, Rolle (`therapist` oder `office`) und Anzeigename anzulegen.
2. WHEN das Sekretariat einen Nutzer anlegt, THE App SHALL das Passwort gehasht speichern.
3. WHEN das Sekretariat einen Nutzer entfernt, THE App SHALL das Login-Konto löschen.
4. WHEN eine Therapeutin entfernt wird, THE App SHALL deren bestehende Springer-Einträge erhalten (nicht automatisch mitlöschen) und weiterhin in der Springerliste anzeigen.
5. WHEN noch kein Nutzer existiert, THE App SHALL beim ersten Start ein initiales `office`-Konto aus Umgebungsvariablen anlegen, damit die Nutzerverwaltung überhaupt erreichbar ist.

### Anforderung 3: Springer-Eintrag erfassen

**User Story:** Als Therapeutin möchte ich auf dem Tablet schnell eine Springer-Klientin eintragen, damit das Sekretariat bei frei werdenden Terminen weiß, wen es anrufen kann.

#### Akzeptanzkriterien

1. THE App SHALL ein Formular für Springer-Einträge mit den Feldern Name der Klientin, Zeitraum von (Datum), Zeitraum bis (Datum, optional), Terminzeit und Hinweis (optional) anzeigen.
2. THE App SHALL die Terminzeit als Auswahl der Werte `flexibel`, `mittags`, `früher Nachmittag`, `nachmittags` anbieten (Einfachauswahl, als anklickbare Schaltflächen).
3. THE App SHALL beim Erfassen jeden Eintrag einer Therapeutin zuordnen. Bei Rolle `therapist` ist die angemeldete Therapeutin vorausgewählt; bei Rolle `office` ist zunächst keine Therapeutin vorausgewählt und muss gewählt werden.
4. WHEN eine Nutzerin das Formular absendet, THE App SHALL den Eintrag mit der zugeordneten Therapeutin in der Datenbank speichern.
5. IF das Feld Name leer ist, THEN THE App SHALL eine Fehlermeldung anzeigen und den Eintrag nicht speichern.
6. IF Zeitraum bis vor Zeitraum von liegt, THEN THE App SHALL eine Fehlermeldung anzeigen und den Eintrag nicht speichern.
7. THE App SHALL die Oberfläche für Springer-Einträge tabletfreundlich gestalten (große Schaltflächen, Auswahl statt Freitext, wenige Eingaben).

### Anforderung 4: Springer-Seite anzeigen

**User Story:** Als Nutzerin möchte ich auf einer Springer-Seite die aktiven Springer sehen und neue erfassen, damit ich bei einem frei werdenden Termin schnell eine passende Klientin finde.

#### Akzeptanzkriterien

1. THE App SHALL auf der Springer-Seite die aktiven Springer anzeigen und das Erfassen neuer Einträge ermöglichen.
2. THE App SHALL je Springer-Eintrag die zugeordnete Therapeutin, Name, Zeitraum von/bis, Terminzeit und Hinweis anzeigen.
3. THE App SHALL den Therapeutin-Filter rollenabhängig vorbelegen: bei Rolle `office` ohne Filter (alle Therapeutinnen), bei Rolle `therapist` auf die angemeldete Therapeutin.
4. THE App SHALL erlauben, den Filter jederzeit zu ändern (keine harte Zugriffssperre zwischen den Rollen).
5. THE App SHALL nur aktive Einträge anzeigen; ein Eintrag gilt als abgelaufen, wenn Zeitraum bis gesetzt ist und vor dem heutigen Datum liegt.
6. WHEN Zeitraum bis leer ist, THE App SHALL den Eintrag unbefristet als aktiv behandeln.
7. THE App SHALL abgelaufene Einträge nicht löschen, sondern nur aus der aktiven Liste ausblenden.
8. WHEN eine Nutzerin die Option "Ausgeblendete anzeigen" aktiviert, THE App SHALL auch die abgelaufenen Springer-Einträge anzeigen und visuell unterscheidbar darstellen.
9. WHEN die gefilterte Liste keine aktiven Einträge enthält, THE App SHALL einen entsprechenden Hinweistext anzeigen.

### Anforderung 5: Springer-Eintrag bearbeiten und löschen

**User Story:** Als Nutzerin möchte ich Springer-Einträge ändern oder entfernen, damit die Liste aktuell bleibt.

#### Akzeptanzkriterien

1. WHEN eine Nutzerin einen Springer-Eintrag zum Bearbeiten öffnet, THE App SHALL die vorhandenen Werte im Formular anzeigen.
2. WHEN eine Nutzerin die Bearbeitung speichert, THE App SHALL die geänderten Werte in der Datenbank aktualisieren (gleiche Validierung wie beim Erfassen).
3. WHEN eine Nutzerin einen Springer-Eintrag löscht, THE App SHALL eine Bestätigung einholen und den Eintrag anschließend dauerhaft entfernen.
4. THE App SHALL dem Sekretariat erlauben, Springer-Einträge beliebiger Therapeutinnen zu bearbeiten und zu löschen.

### Anforderung 6: Warteliste pflegen

**User Story:** Als Sekretariat möchte ich neu angemeldete Klientinnen in der Warteliste erfassen und verwalten, damit ich den Überblick über Neuanmeldungen behalte.

#### Akzeptanzkriterien

1. THE App SHALL ein Formular für Warteliste-Einträge mit den Feldern Name, Telefonnummer, E-Mail-Adresse, Terminzeit und Hinweis anzeigen; das Anmeldedatum wird beim Anlegen automatisch gesetzt.
2. THE App SHALL die Terminzeit als Auswahl derselben Werte wie bei Springer-Einträgen anbieten (`flexibel`, `mittags`, `früher Nachmittag`, `nachmittags`).
3. IF das Feld Name leer ist, THEN THE App SHALL eine Fehlermeldung anzeigen und den Eintrag nicht speichern.
4. THE App SHALL Warteliste-Einträge, deren Anmeldedatum länger als die Sichtbarkeitsfrist (Standard: 28 Tage) zurückliegt, aus der aktiven Warteliste ausblenden, ohne sie zu löschen.
5. WHEN eine Nutzerin die Option "Ausgeblendete anzeigen" aktiviert, THE App SHALL auch die ausgeblendeten Warteliste-Einträge anzeigen und visuell unterscheidbar darstellen.
6. THE App SHALL das Bearbeiten und Löschen von Warteliste-Einträgen ermöglichen (Löschen mit Bestätigung).
7. THE App SHALL die Warteliste-Pflege für die Rolle `office` als Standardfunktion bereitstellen.

### Anforderung 7: Automatische endgültige Löschung nach Ablauf

**User Story:** Als Praxis möchte ich, dass ausgeblendete Einträge nach einer Frist endgültig gelöscht werden, damit keine Patientendaten unbegrenzt gespeichert bleiben.

#### Akzeptanzkriterien

1. THE App SHALL ausgeblendete Einträge beider Listen 14 Tage nach dem Ausblenden endgültig aus der Datenbank löschen (Löschfrist).
2. THE App SHALL für die Warteliste als Ausblend-Zeitpunkt Anmeldedatum + Sichtbarkeitsfrist (28 Tage) verwenden; endgültige Löschung somit 42 Tage nach Anmeldedatum.
3. THE App SHALL für Springer-Einträge als Ausblend-Zeitpunkt das Datum Zeitraum bis verwenden; endgültige Löschung somit 14 Tage nach Zeitraum bis.
4. WHEN ein Springer-Eintrag kein Zeitraum bis hat, THE App SHALL ihn weder ausblenden noch automatisch löschen.
5. THE App SHALL die Löschung ohne externen Scheduler durchführen: einmal beim Serverstart und danach höchstens einmal pro Tag beim ersten eingehenden Request.
6. THE App SHALL die automatische Löschung als endgültig behandeln; gelöschte Einträge sind nicht über "Ausgeblendete anzeigen" wiederherstellbar.

### Anforderung 8: Datenpersistenz auf der NAS

**User Story:** Als Praxis möchte ich, dass alle Daten zentral und dauerhaft auf der NAS liegen, damit nichts verloren geht und ein Backup einfach möglich ist.

#### Akzeptanzkriterien

1. THE App SHALL alle Daten (Nutzer, Springer-Einträge, Warteliste) in einer SQLite-Datenbankdatei speichern.
2. THE App SHALL die Datenbankdatei an einem konfigurierbaren Pfad ablegen, der im Container auf ein NAS-Volume außerhalb des Images zeigt, sodass sie Updates übersteht.
3. WHEN der Server startet, THE App SHALL die Datenbank initialisieren und fehlende Tabellen anlegen, ohne vorhandene Daten zu verändern.
4. WHEN ein Eintrag angelegt, geändert oder gelöscht wird, THE App SHALL die Änderung sofort persistieren.
5. THE App SHALL keine Patientendaten im Docker-Image oder im Quellcode-Repository ablegen.

### Anforderung 9: Betrieb als Docker-Container auf der QNAP-NAS

**User Story:** Als Betreiber möchte ich die App als einzelnen Docker-Container auf der NAS laufen lassen, damit der Betrieb simpel bleibt und keine Installation auf den Endgeräten nötig ist.

#### Akzeptanzkriterien

1. THE App SHALL als einzelner Docker-Container lauffähig sein, ohne separaten Datenbank-Container.
2. THE App SHALL im Container über einen produktionstauglichen WSGI-Server (`waitress`) ausgeliefert werden, nicht über den Flask-Entwicklungsserver.
3. THE App SHALL einen konfigurierbaren Port bereitstellen (Standard: 5000), der im Praxis-LAN erreichbar ist.
4. THE App SHALL ohne Internetzugriff vollständig funktionsfähig sein.
5. THE App SHALL die bisherige Einzelplatz-Auslieferung (Windows-`.exe`, PyInstaller, System-Tray) nicht mehr enthalten.
6. THE App SHALL eine deutschsprachige Oberfläche mit responsivem Layout für Desktop- und Tablet-Bildschirme bereitstellen.

### Anforderung 10: Auslieferung über GitHub Release

**User Story:** Als Betreiber möchte ich ein versioniertes, reproduzierbares Image bekommen, ohne eine Container-Registry zu betreiben, damit das Deployment auf die QNAP einfach bleibt.

#### Akzeptanzkriterien

1. THE Repository SHALL einen automatisierten Build bereitstellen, der bei einem Versions-Tag ein Docker-Image baut und als tar-Datei (`docker save`) an ein GitHub Release anhängt.
2. THE App SHALL NICHT auf eine Container-Registry (z. B. ghcr.io, Docker Hub) veröffentlicht werden; die Auslieferung erfolgt ausschließlich als Release-Asset.
3. THE Repository SHALL die Image-tar-Datei und die Datenbankdatei über `.gitignore` von der Versionskontrolle ausschließen.
4. THE Build SHALL keine Secrets (Passwörter, Secret-Key) in das Image einbacken.
5. THE Dokumentation SHALL den Deployment-Weg beschreiben: Image-tar vom Release laden, in Container Station importieren, Container mit Port-Mapping und NAS-Volume starten.
