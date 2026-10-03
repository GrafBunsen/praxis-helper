"""Datenbankschicht für die Wartelisten-Kontaktverwaltung.

Verwendet sqlite3 direkt (kein ORM). Alle Queries nutzen parametrisierte
Platzhalter (?), um SQL-Injection zu verhindern.
"""

import os
import sqlite3
from datetime import datetime

DB_NAME = "contacts.db"


def _db_path() -> str:
    """Gibt den Pfad zur Datenbankdatei zurück.

    Priorität: Umgebungsvariable PRAXIS_DB_PATH (Server-/Docker-Betrieb),
    sonst Projektroot/contacts.db (Entwicklung).
    """
    env_path = os.environ.get("PRAXIS_DB_PATH")
    if env_path:
        return env_path
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, DB_NAME)


def get_db() -> sqlite3.Connection:
    """Gibt eine neue Datenbankverbindung zurück (Row-Factory aktiviert)."""
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Erstellt Datenbank und Schema, falls nicht vorhanden, und migriert bestehende Daten.

    Legt die Tabellen contacts, users und springer an (IF NOT EXISTS) und
    ergänzt bei einer vorhandenen contacts-Tabelle additiv die Spalte
    appointment_time, ohne vorhandene Daten zu verändern.
    """
    conn = get_db()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT DEFAULT '',
                email TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('therapist','office')),
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS springer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                therapist TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                valid_until TEXT DEFAULT '',
                appointment_time TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )"""
        )

        # Additive Migration: appointment_time zu bestehender contacts-Tabelle
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(contacts)")}
        if "appointment_time" not in columns:
            conn.execute(
                "ALTER TABLE contacts ADD COLUMN appointment_time TEXT NOT NULL DEFAULT 'flexibel'"
            )

        conn.commit()
    finally:
        conn.close()


def add_contact(
    name: str, phone: str = "", email: str = "", notes: str = "",
    appointment_time: str = "flexibel",
) -> int:
    """Fügt einen neuen Kontakt hinzu und gibt die neue ID zurück."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO contacts (name, phone, email, notes, appointment_time) VALUES (?, ?, ?, ?, ?)",
            (name, phone, email, notes, appointment_time),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_all_contacts() -> list[dict]:
    """Gibt alle Kontakte zurück, sortiert nach Erstellungsdatum (älteste zuerst)."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, name, phone, email, notes, appointment_time, created_at FROM contacts ORDER BY created_at ASC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_contact(contact_id: int) -> dict | None:
    """Gibt einen einzelnen Kontakt zurück oder None, falls nicht gefunden."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, name, phone, email, notes, appointment_time, created_at FROM contacts WHERE id = ?",
            (contact_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_contact(
    contact_id: int, name: str, phone: str = "", email: str = "", notes: str = "",
    appointment_time: str = "flexibel",
) -> bool:
    """Aktualisiert einen Kontakt. Gibt True zurück, wenn der Kontakt existierte."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "UPDATE contacts SET name = ?, phone = ?, email = ?, notes = ?, appointment_time = ? WHERE id = ?",
            (name, phone, email, notes, appointment_time, contact_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_contact(contact_id: int) -> bool:
    """Löscht einen Kontakt. Gibt True zurück, wenn der Kontakt existierte."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "DELETE FROM contacts WHERE id = ?",
            (contact_id,),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_visible_contacts(visibility_days: int = 28) -> list[dict]:
    """Gibt Kontakte zurück, deren Erstellungsdatum innerhalb der Sichtbarkeitsfrist liegt."""
    conn = get_db()
    try:
        cutoff = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute(
            """SELECT id, name, phone, email, notes, appointment_time, created_at FROM contacts
               WHERE julianday(?) - julianday(created_at) <= ?
               ORDER BY created_at ASC""",
            (cutoff, visibility_days),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def export_contacts() -> dict:
    """Exportiert alle Kontakte als Dict mit Version, Zeitstempel und Kontaktliste (ohne ID)."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT name, phone, email, notes, appointment_time, created_at FROM contacts ORDER BY created_at ASC"
        ).fetchall()
        return {
            "version": 1,
            "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "contacts": [dict(row) for row in rows],
        }
    finally:
        conn.close()


def import_contacts(data: dict, mode: str = "replace") -> int:
    """Importiert Kontakte aus einem Export-Dict.

    Args:
        data: Dict mit 'contacts'-Array (jeder Eintrag hat name, phone, email, notes, created_at).
        mode: 'replace' löscht alle bestehenden Kontakte vor dem Import,
              'merge' fügt die Kontakte zu den bestehenden hinzu.

    Returns:
        Anzahl der importierten Kontakte.
    """
    contacts = data.get("contacts", [])
    conn = get_db()
    try:
        if mode == "replace":
            conn.execute("DELETE FROM contacts")

        count = 0
        for contact in contacts:
            conn.execute(
                "INSERT INTO contacts (name, phone, email, notes, appointment_time, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    contact.get("name", ""),
                    contact.get("phone", ""),
                    contact.get("email", ""),
                    contact.get("notes", ""),
                    contact.get("appointment_time", "flexibel"),
                    contact.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                ),
            )
            count += 1

        conn.commit()
        return count
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Nutzer (users)
# ---------------------------------------------------------------------------

def add_user(username: str, password_hash: str, role: str) -> int:
    """Legt einen Nutzer an und gibt die neue ID zurück."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, password_hash, role),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_user_by_username(username: str) -> dict | None:
    """Gibt einen Nutzer anhand des Benutzernamens zurück oder None."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_users() -> list[dict]:
    """Gibt alle Nutzer zurück (ohne Passwort-Hash), sortiert nach Benutzername."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, username, role, created_at FROM users ORDER BY username ASC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def delete_user(user_id: int) -> bool:
    """Löscht einen Nutzer. Gibt True zurück, wenn der Nutzer existierte.

    Springer-Einträge der Person bleiben erhalten (kein Cascade), da therapist
    als Text gespeichert wird.
    """
    conn = get_db()
    try:
        cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Springer-Einträge (springer)
# ---------------------------------------------------------------------------

def add_springer(
    client_name: str, therapist: str, valid_from: str,
    valid_until: str = "", appointment_time: str = "flexibel", notes: str = "",
) -> int:
    """Legt einen Springer-Eintrag an und gibt die neue ID zurück."""
    conn = get_db()
    try:
        cursor = conn.execute(
            """INSERT INTO springer
               (client_name, therapist, valid_from, valid_until, appointment_time, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (client_name, therapist, valid_from, valid_until, appointment_time, notes),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_springer(springer_id: int) -> dict | None:
    """Gibt einen Springer-Eintrag zurück oder None, falls nicht gefunden."""
    conn = get_db()
    try:
        row = conn.execute(
            """SELECT id, client_name, therapist, valid_from, valid_until,
                      appointment_time, notes, created_at
               FROM springer WHERE id = ?""",
            (springer_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_springer(therapist: str | None = None, include_expired: bool = False) -> list[dict]:
    """Gibt Springer-Einträge zurück.

    Args:
        therapist: Falls gesetzt, nur Einträge dieser Therapeutin (Anzeigename).
        include_expired: Falls False, werden abgelaufene Einträge ausgeblendet
            (valid_until gesetzt und vor heute). Unbefristete (valid_until == '')
            gelten immer als aktiv.

    Returns:
        Liste von Einträgen, sortiert nach valid_from (früheste zuerst).
    """
    conn = get_db()
    try:
        clauses = []
        params: list = []
        if therapist is not None:
            clauses.append("therapist = ?")
            params.append(therapist)
        if not include_expired:
            today = datetime.now().strftime("%Y-%m-%d")
            clauses.append("(valid_until = '' OR valid_until >= ?)")
            params.append(today)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"""SELECT id, client_name, therapist, valid_from, valid_until,
                       appointment_time, notes, created_at
                FROM springer{where} ORDER BY valid_from ASC""",
            params,
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_springer(
    springer_id: int, client_name: str, therapist: str, valid_from: str,
    valid_until: str = "", appointment_time: str = "flexibel", notes: str = "",
) -> bool:
    """Aktualisiert einen Springer-Eintrag. True, wenn der Eintrag existierte."""
    conn = get_db()
    try:
        cursor = conn.execute(
            """UPDATE springer SET client_name = ?, therapist = ?, valid_from = ?,
                   valid_until = ?, appointment_time = ?, notes = ? WHERE id = ?""",
            (client_name, therapist, valid_from, valid_until, appointment_time, notes, springer_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_springer(springer_id: int) -> bool:
    """Löscht einen Springer-Eintrag. True, wenn der Eintrag existierte."""
    conn = get_db()
    try:
        cursor = conn.execute("DELETE FROM springer WHERE id = ?", (springer_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Automatische Löschung
# ---------------------------------------------------------------------------

def purge_expired() -> int:
    """Löscht endgültig abgelaufene Einträge beider Listen (irreversibel).

    - Warteliste: Kontakte, deren Anmeldedatum (created_at) mehr als 42 Tage
      zurückliegt (28 Tage Sichtbarkeit + 14 Tage Löschfrist).
    - Springer: Einträge mit gesetztem valid_until, das mehr als 14 Tage
      zurückliegt. Einträge ohne valid_until werden nie gelöscht.

    Returns:
        Anzahl gelöschter Zeilen insgesamt.
    """
    conn = get_db()
    try:
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c1 = conn.execute(
            "DELETE FROM contacts WHERE julianday(?) - julianday(created_at) > 42",
            (today,),
        )
        c2 = conn.execute(
            "DELETE FROM springer WHERE valid_until != '' AND julianday(?) - julianday(valid_until) > 14",
            (today,),
        )
        conn.commit()
        return c1.rowcount + c2.rowcount
    finally:
        conn.close()
