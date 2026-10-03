"""Eingabevalidierung und Sanitisierung für die Wartelisten-Kontaktverwaltung.

Schützt gegen XSS durch HTML-Tag-Entfernung (zusätzlich zu Jinja2-Auto-Escaping).
Validiert Pflichtfelder und Import-Datenstrukturen.
"""

import re
from datetime import datetime

# Erlaubte Terminzeiten (Einfachauswahl), zentral an einer Stelle.
APPOINTMENT_TIMES = ("flexibel", "mittags", "früher Nachmittag", "nachmittags")

# Gültige Nutzerrollen.
USER_ROLES = ("therapist", "office")

# Regex zum Entfernen von HTML-Tags
_HTML_TAG_RE = re.compile(r"<[^>]*>")


def _is_valid_date(value: str) -> bool:
    """Prüft, ob value ein gültiges Datum im Format YYYY-MM-DD ist."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


def _strip_html(value: str) -> str:
    """Entfernt HTML-Tags aus einem String."""
    return _HTML_TAG_RE.sub("", value)


def _clean_field(value: str) -> str:
    """Bereinigt ein Textfeld: HTML-Tags entfernen und Whitespace trimmen."""
    return _strip_html(value).strip()


def validate_contact(data: dict) -> tuple[bool, dict | list[str]]:
    """Validiert und bereinigt Kontaktdaten.

    Args:
        data: Dict mit Schlüsseln 'name', 'phone', 'email', 'notes'.

    Returns:
        (True, cleaned_data) bei gültigen Daten,
        (False, error_messages) bei ungültigen Daten.
    """
    errors = []

    name = _clean_field(str(data.get("name", "")))
    if not name:
        errors.append("Name ist ein Pflichtfeld und darf nicht leer sein.")

    appointment_time = str(data.get("appointment_time", "flexibel")) or "flexibel"
    if appointment_time not in APPOINTMENT_TIMES:
        errors.append("Ungültige Terminzeit.")

    if errors:
        return False, errors

    cleaned = {
        "name": name,
        "phone": _clean_field(str(data.get("phone", ""))),
        "email": _clean_field(str(data.get("email", ""))),
        "notes": _clean_field(str(data.get("notes", ""))),
        "appointment_time": appointment_time,
    }
    return True, cleaned


def validate_import_json(data: dict) -> tuple[bool, dict | list[str]]:
    """Validiert die Struktur einer Import-JSON-Datei.

    Args:
        data: Dict, das die importierte JSON-Struktur repräsentiert.

    Returns:
        (True, data) bei gültiger Struktur,
        (False, error_messages) bei ungültiger Struktur.
    """
    errors = []

    if not isinstance(data, dict):
        return False, ["Ungültiges JSON-Format: Objekt erwartet."]

    if "version" not in data:
        errors.append("Pflichtfeld 'version' fehlt.")

    if "contacts" not in data:
        errors.append("Pflichtfeld 'contacts' fehlt.")
    elif not isinstance(data["contacts"], list):
        errors.append("'contacts' muss ein Array sein.")
    else:
        for i, contact in enumerate(data["contacts"]):
            if not isinstance(contact, dict):
                errors.append(f"Kontakt {i + 1}: Muss ein Objekt sein.")
                continue
            name = str(contact.get("name", "")).strip()
            if not name:
                errors.append(f"Kontakt {i + 1}: Name ist ein Pflichtfeld und darf nicht leer sein.")

    if errors:
        return False, errors

    return True, data


def validate_springer(data: dict) -> tuple[bool, dict | list[str]]:
    """Validiert und bereinigt einen Springer-Eintrag.

    Args:
        data: Dict mit 'client_name', 'therapist', 'valid_from',
              'valid_until' (optional), 'appointment_time', 'notes'.

    Returns:
        (True, cleaned_data) bei gültigen Daten,
        (False, error_messages) bei ungültigen Daten.
    """
    errors = []

    client_name = _clean_field(str(data.get("client_name", "")))
    if not client_name:
        errors.append("Name der Klientin ist ein Pflichtfeld und darf nicht leer sein.")

    therapist = _clean_field(str(data.get("therapist", "")))
    if not therapist:
        errors.append("Eine Therapeutin muss zugeordnet sein.")

    valid_from = str(data.get("valid_from", "")).strip()
    if not _is_valid_date(valid_from):
        errors.append("Zeitraum von muss ein gültiges Datum sein.")

    valid_until = str(data.get("valid_until", "")).strip()
    if valid_until and not _is_valid_date(valid_until):
        errors.append("Zeitraum bis muss leer oder ein gültiges Datum sein.")

    # Reihenfolge nur prüfen, wenn beide Datumswerte für sich gültig sind.
    if (
        _is_valid_date(valid_from)
        and valid_until
        and _is_valid_date(valid_until)
        and valid_until < valid_from
    ):
        errors.append("Zeitraum bis darf nicht vor Zeitraum von liegen.")

    appointment_time = str(data.get("appointment_time", ""))
    if appointment_time not in APPOINTMENT_TIMES:
        errors.append("Ungültige Terminzeit.")

    if errors:
        return False, errors

    cleaned = {
        "client_name": client_name,
        "therapist": therapist,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "appointment_time": appointment_time,
        "notes": _clean_field(str(data.get("notes", ""))),
    }
    return True, cleaned


def validate_user(data: dict) -> tuple[bool, dict | list[str]]:
    """Validiert und bereinigt Nutzerdaten für die Anlage.

    Args:
        data: Dict mit 'username', 'password', 'role'.

    Returns:
        (True, cleaned_data) bei gültigen Daten,
        (False, error_messages) bei ungültigen Daten.
    """
    errors = []

    username = _clean_field(str(data.get("username", "")))
    if not username:
        errors.append("Benutzername ist ein Pflichtfeld.")

    # Passwort nicht bereinigen/trimmen – es wird gehasht, nicht angezeigt.
    password = str(data.get("password", ""))
    if not password:
        errors.append("Passwort ist ein Pflichtfeld.")

    role = str(data.get("role", ""))
    if role not in USER_ROLES:
        errors.append("Ungültige Rolle.")

    if errors:
        return False, errors

    cleaned = {
        "username": username,
        "password": password,
        "role": role,
    }
    return True, cleaned
