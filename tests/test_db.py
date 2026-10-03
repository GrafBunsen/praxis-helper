"""Tests für db.py – Datenschicht: Springer, purge_expired, Migration."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from src import db


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path, monkeypatch):
    """Jeder Test bekommt eine eigene temporäre Datenbank."""
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(db, "_db_path", lambda: db_file)
    db.init_db()


def _days_ago_date(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


def _days_ago_datetime(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


# --- Springer CRUD + Filter ---


class TestSpringerListing:
    def test_add_and_get(self):
        sid = db.add_springer("Klient", "Müller", "2026-01-01", "2026-02-01", "mittags", "x")
        row = db.get_springer(sid)
        assert row["client_name"] == "Klient"
        assert row["therapist"] == "Müller"
        assert row["appointment_time"] == "mittags"

    def test_filter_by_therapist(self):
        db.add_springer("A", "Müller", "2026-01-01")
        db.add_springer("B", "Schmidt", "2026-01-01")
        only_mueller = db.list_springer(therapist="Müller")
        assert len(only_mueller) == 1
        assert only_mueller[0]["therapist"] == "Müller"

    def test_expired_hidden_by_default(self):
        db.add_springer("Abgelaufen", "Müller", "2025-01-01", _days_ago_date(1))
        db.add_springer("Aktiv", "Müller", "2025-01-01", _days_ago_date(-5))
        active = db.list_springer()
        names = {r["client_name"] for r in active}
        assert "Aktiv" in names
        assert "Abgelaufen" not in names

    def test_expired_shown_when_included(self):
        db.add_springer("Abgelaufen", "Müller", "2025-01-01", _days_ago_date(1))
        all_entries = db.list_springer(include_expired=True)
        assert len(all_entries) == 1

    def test_no_valid_until_is_always_active(self):
        db.add_springer("Unbefristet", "Müller", "2025-01-01", "")
        active = db.list_springer()
        assert len(active) == 1

    def test_update_and_delete(self):
        sid = db.add_springer("Klient", "Müller", "2026-01-01")
        assert db.update_springer(sid, "Neu", "Müller", "2026-01-01", "", "nachmittags", "") is True
        assert db.get_springer(sid)["client_name"] == "Neu"
        assert db.delete_springer(sid) is True
        assert db.get_springer(sid) is None


# --- purge_expired: Grenzfälle ---


class TestPurgeWarteliste:
    def _add_contact_days_ago(self, days: int):
        return db.import_contacts(
            {"contacts": [{"name": f"K{days}", "created_at": _days_ago_datetime(days)}]},
            mode="merge",
        )

    def test_contact_41_days_kept(self):
        self._add_contact_days_ago(41)
        db.purge_expired()
        assert len(db.get_all_contacts()) == 1

    def test_contact_43_days_deleted(self):
        self._add_contact_days_ago(43)
        db.purge_expired()
        assert len(db.get_all_contacts()) == 0

    def test_fresh_contact_kept(self):
        self._add_contact_days_ago(1)
        db.purge_expired()
        assert len(db.get_all_contacts()) == 1


class TestPurgeSpringer:
    def test_springer_13_days_after_until_kept(self):
        db.add_springer("K", "Müller", "2025-01-01", _days_ago_date(13))
        db.purge_expired()
        assert len(db.list_springer(include_expired=True)) == 1

    def test_springer_15_days_after_until_deleted(self):
        db.add_springer("K", "Müller", "2025-01-01", _days_ago_date(15))
        db.purge_expired()
        assert len(db.list_springer(include_expired=True)) == 0

    def test_springer_without_valid_until_never_deleted(self):
        db.add_springer("K", "Müller", "2020-01-01", "")
        db.purge_expired()
        assert len(db.list_springer(include_expired=True)) == 1

    def test_hidden_but_not_purge_ready_kept(self):
        # Ausgeblendet (abgelaufen vor 5 Tagen), aber noch nicht löschreif (<14 Tage).
        db.add_springer("K", "Müller", "2025-01-01", _days_ago_date(5))
        db.purge_expired()
        assert len(db.list_springer()) == 0  # ausgeblendet
        assert len(db.list_springer(include_expired=True)) == 1  # aber noch da


# --- Additive Migration ---


class TestMigration:
    def test_appointment_time_added_to_legacy_contacts(self, tmp_path, monkeypatch):
        """Eine alte contacts-Tabelle ohne appointment_time wird additiv migriert,
        bestehende Daten bleiben intakt."""
        legacy_file = str(tmp_path / "legacy.db")

        # Alte Tabelle ohne appointment_time von Hand anlegen und befüllen.
        conn = sqlite3.connect(legacy_file)
        conn.execute(
            """CREATE TABLE contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, phone TEXT DEFAULT '', email TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )"""
        )
        conn.execute("INSERT INTO contacts (name) VALUES ('Altkontakt')")
        conn.commit()
        conn.close()

        monkeypatch.setattr(db, "_db_path", lambda: legacy_file)
        db.init_db()

        contacts = db.get_all_contacts()
        assert len(contacts) == 1
        assert contacts[0]["name"] == "Altkontakt"
        assert contacts[0]["appointment_time"] == "flexibel"
