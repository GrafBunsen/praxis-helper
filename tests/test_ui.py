"""Route-/UI-Tests für Praxis Helper.

Verwendet den Flask-Test-Client und eine temporäre SQLite-Datenbank.
Deckt Login-Flow, Springer-CRUD + Filter, Warteliste mit Terminzeit und
Nutzerverwaltung ab.
"""

import io
from datetime import datetime, timedelta

import pytest
from werkzeug.security import generate_password_hash

from src import db
from src.app import app


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path, monkeypatch):
    """Jeder Test bekommt eine eigene temporäre Datenbank mit zwei Nutzern."""
    db_file = str(tmp_path / "test.db")
    monkeypatch.setattr(db, "_db_path", lambda: db_file)
    db.init_db()
    db.add_user("sekretariat", generate_password_hash("pw"), "office")
    db.add_user("mueller", generate_password_hash("pw"), "therapist")


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _login(client, username="sekretariat"):
    return client.post(
        "/login", data={"username": username, "password": "pw"}, follow_redirects=True
    )


# --- Login-Flow ---


class TestLogin:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/springer")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_successful_login_lands_on_springer(self, client):
        resp = _login(client)
        assert resp.status_code == 200
        assert "Springerliste" in resp.data.decode()

    def test_wrong_password_shows_error_no_session(self, client):
        resp = client.post(
            "/login", data={"username": "sekretariat", "password": "falsch"},
            follow_redirects=True,
        )
        html = resp.data.decode()
        assert "falsch" in html.lower()
        # Keine Session: Zugriff weiterhin gesperrt
        resp2 = client.get("/springer")
        assert resp2.status_code == 302

    def test_logout_clears_session(self, client):
        _login(client)
        client.get("/logout")
        resp = client.get("/springer")
        assert resp.status_code == 302


# --- Springer-CRUD und Filter ---


class TestSpringer:
    def _add(self, client, **overrides):
        data = {
            "client_name": "Klient A",
            "therapist": "mueller",
            "valid_from": "2026-01-01",
            "valid_until": "",
            "appointment_time": "mittags",
            "notes": "",
        }
        data.update(overrides)
        return client.post("/springer/add", data=data, follow_redirects=True)

    def test_add_shows_in_list(self, client):
        _login(client)
        resp = self._add(client)
        assert "Klient A" in resp.data.decode()

    def test_edit_loads_values(self, client):
        _login(client)
        sid = db.add_springer("Klient B", "mueller", "2026-01-01", "", "nachmittags", "Hinweis X")
        resp = client.get(f"/springer/edit/{sid}")
        html = resp.data.decode()
        assert "Klient B" in html and "Hinweis X" in html

    def test_update_persists(self, client):
        _login(client)
        sid = db.add_springer("Alt", "mueller", "2026-01-01")
        client.post(
            f"/springer/edit/{sid}",
            data={"client_name": "Neu", "therapist": "mueller",
                  "valid_from": "2026-01-01", "valid_until": "",
                  "appointment_time": "flexibel", "notes": ""},
            follow_redirects=True,
        )
        assert db.get_springer(sid)["client_name"] == "Neu"

    def test_delete_removes(self, client):
        _login(client)
        sid = db.add_springer("Weg", "mueller", "2026-01-01")
        client.post(f"/springer/delete/{sid}", follow_redirects=True)
        assert db.get_springer(sid) is None

    def test_filter_by_therapist(self, client):
        _login(client)
        db.add_springer("Mueller-Klient", "mueller", "2026-01-01")
        db.add_springer("Andere-Klient", "sekretariat", "2026-01-01")
        resp = client.get("/springer?therapist=mueller")
        html = resp.data.decode()
        assert "Mueller-Klient" in html
        assert "Andere-Klient" not in html

    def test_show_hidden_reveals_expired(self, client):
        _login(client)
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        db.add_springer("Abgelaufen", "mueller", "2025-01-01", yesterday)
        # Default: nicht sichtbar
        assert "Abgelaufen" not in client.get("/springer").data.decode()
        # show_hidden: sichtbar
        assert "Abgelaufen" in client.get("/springer?show_hidden=1").data.decode()

    def test_office_filter_default_shows_all(self, client):
        _login(client, "sekretariat")
        db.add_springer("K1", "mueller", "2026-01-01")
        db.add_springer("K2", "sekretariat", "2026-01-01")
        html = client.get("/springer").data.decode()
        assert "K1" in html and "K2" in html

    def test_therapist_filter_default_own(self, client):
        _login(client, "mueller")
        db.add_springer("Meins", "mueller", "2026-01-01")
        db.add_springer("Fremd", "sekretariat", "2026-01-01")
        html = client.get("/springer").data.decode()
        assert "Meins" in html
        assert "Fremd" not in html

    def test_empty_name_rejected(self, client):
        _login(client)
        resp = self._add(client, client_name="")
        assert "Pflichtfeld" in resp.data.decode()


# --- Warteliste mit Terminzeit ---


class TestWarteliste:
    def test_add_with_appointment_time(self, client):
        _login(client)
        resp = client.post(
            "/warteliste/add",
            data={"name": "Neuer Klient", "appointment_time": "nachmittags"},
            follow_redirects=True,
        )
        html = resp.data.decode()
        assert "Neuer Klient" in html and "nachmittags" in html

    def test_edit_loads_contact(self, client):
        _login(client)
        cid = db.add_contact("Maria", "0171", "m@test.de", "Notiz", "mittags")
        html = client.get(f"/warteliste/edit/{cid}").data.decode()
        assert "Maria" in html and "0171" in html

    def test_empty_list_hint(self, client):
        _login(client)
        assert "Warteliste ist leer" in client.get("/warteliste").data.decode()

    def test_import_mode_selection(self, client):
        _login(client)
        html = client.get("/warteliste/import").data.decode()
        assert 'value="replace"' in html and 'value="merge"' in html

    def test_invalid_json_rejected(self, client):
        _login(client)
        data = {"file": (io.BytesIO(b"kein json"), "bad.json"), "mode": "replace"}
        resp = client.post(
            "/warteliste/import", data=data,
            content_type="multipart/form-data", follow_redirects=True,
        )
        assert "JSON" in resp.data.decode()


# --- Nutzerverwaltung ---


class TestUsers:
    def test_add_user(self, client):
        _login(client)
        client.post(
            "/users/add",
            data={"username": "neu", "password": "pw", "role": "therapist"},
            follow_redirects=True,
        )
        assert db.get_user_by_username("neu") is not None

    def test_duplicate_username_rejected(self, client):
        _login(client)
        resp = client.post(
            "/users/add",
            data={"username": "mueller", "password": "pw", "role": "therapist"},
            follow_redirects=True,
        )
        assert "vergeben" in resp.data.decode()

    def test_delete_user_keeps_springer_entries(self, client):
        _login(client)
        db.add_springer("Bleibt", "mueller", "2026-01-01")
        user = db.get_user_by_username("mueller")
        client.post(f"/users/delete/{user['id']}", follow_redirects=True)
        # Nutzer weg, Springer-Eintrag bleibt
        assert db.get_user_by_username("mueller") is None
        assert len(db.list_springer(therapist="mueller", include_expired=True)) == 1

    def test_german_ui(self, client):
        _login(client)
        html = client.get("/springer").data.decode()
        assert "Therapeutin" in html and "Terminzeit" in html
