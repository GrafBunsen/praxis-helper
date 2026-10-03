"""Flask-Anwendung für Praxis Helper.

Zwei Listen (Springer-Einträge und Warteliste-Neuanmeldungen) hinter einem
einfachen Login. Serverseitig gerenderte Jinja2-Templates mit Auto-Escaping
(XSS-Schutz). Rollen (`therapist`/`office`) steuern nur Vorbelegungen, keine
harten Zugriffssperren — Sicherheit kommt aus dem geschlossenen Praxis-LAN.
"""

import json
import os
from datetime import date, datetime
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from src import db
from src import validators
from src.validators import APPOINTMENT_TIMES

_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = Flask(
    __name__,
    template_folder=os.path.join(_base_dir, "templates"),
    static_folder=os.path.join(_base_dir, "static"),
)

# Secret-Key zwingend aus der Umgebung – kein unsicherer Default im Code.
_secret = os.environ.get("PRAXIS_SECRET_KEY")
if not _secret:
    raise RuntimeError(
        "PRAXIS_SECRET_KEY ist nicht gesetzt. Die Anwendung startet ohne "
        "diese Umgebungsvariable nicht."
    )
app.secret_key = _secret

VISIBILITY_DAYS = 28

# Deutsche Anzeige-Labels für die Rollen (eine Stelle für Auswahl + Anzeige).
ROLE_LABELS = {"therapist": "Therapeutin", "office": "Sekretariat"}


# ---------------------------------------------------------------------------
# Initialisierung & Seeding
# ---------------------------------------------------------------------------

def seed_initial_user() -> None:
    """Legt beim allerersten Start ein office-Konto aus der Umgebung an.

    Nur wenn noch kein Nutzer existiert und PRAXIS_ADMIN_PASSWORD gesetzt ist.
    So kommt beim ersten Start jemand rein, um weitere Nutzer zu pflegen.
    """
    admin_password = os.environ.get("PRAXIS_ADMIN_PASSWORD")
    if admin_password and not db.list_users():
        admin_user = os.environ.get("PRAXIS_ADMIN_USER", "admin")
        db.add_user(
            username=admin_user,
            password_hash=generate_password_hash(admin_password),
            role="office",
        )


# ---------------------------------------------------------------------------
# Login & Zugriffsschutz
# ---------------------------------------------------------------------------

def login_required(view):
    """Decorator: leitet nicht angemeldete Nutzer auf die Anmeldeseite um.

    Einzige harte Sperre – nur "angemeldet ja/nein", keine Rollenprüfung.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


_last_purge_date = None


@app.before_request
def _maybe_purge():
    """Räumt abgelaufene Einträge höchstens einmal pro Tag auf (Dauerbetrieb)."""
    global _last_purge_date
    today = date.today()
    if _last_purge_date != today:
        db.purge_expired()
        _last_purge_date = today


# ---------------------------------------------------------------------------
# Template-Filter & Hilfsfunktionen
# ---------------------------------------------------------------------------

@app.template_filter("format_date")
def format_date(value: str) -> str:
    """Formatiert ein Datum von 'YYYY-MM-DD HH:MM:SS' oder 'YYYY-MM-DD' zu 'DD.MM.YY'."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%d.%m.%y")
        except (ValueError, TypeError):
            continue
    return value


def _waiting_days(created_at: str) -> int:
    """Berechnet die Wartedauer in Tagen seit dem Erstellungsdatum."""
    created = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
    return (datetime.now() - created).days


def _springer_is_expired(entry: dict) -> bool:
    """True, wenn der Eintrag ein valid_until hat, das vor heute liegt."""
    vu = entry.get("valid_until") or ""
    return bool(vu) and vu < datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Auth-Routes
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    """Anmeldeseite / Anmeldung."""
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = db.get_user_by_username(username)
        if user and check_password_hash(user["password_hash"], password):
            session["user"] = {
                "username": user["username"],
                "role": user["role"],
            }
            return redirect(url_for("springer_page"))
        flash("Benutzername oder Passwort ist falsch.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    """Abmelden: Sitzung beenden."""
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    """Startpunkt: auf die Springer-Seite leiten."""
    return redirect(url_for("springer_page"))


# ---------------------------------------------------------------------------
# Springer-Seite
# ---------------------------------------------------------------------------

@app.route("/springer")
@login_required
def springer_page():
    """Springer-Seite: Liste (mit Therapeutin-Filter) + Erfassen-Formular."""
    user = session["user"]
    show_hidden = request.args.get("show_hidden") == "1"

    # Filter-Default: office = alle, therapist = eigener Anzeigename.
    if "therapist" in request.args:
        therapist_filter = request.args.get("therapist") or None
    elif user["role"] == "therapist":
        therapist_filter = user["username"]
    else:
        therapist_filter = None

    entries = db.list_springer(therapist=therapist_filter, include_expired=show_hidden)
    for entry in entries:
        entry["is_expired"] = _springer_is_expired(entry)

    return render_template(
        "springer.html",
        entries=entries,
        therapists=db.list_users(),
        appointment_times=APPOINTMENT_TIMES,
        therapist_filter=therapist_filter,
        show_hidden=show_hidden,
        edit_entry=None,
        empty_hint=len(entries) == 0,
    )


@app.route("/springer/add", methods=["POST"])
@login_required
def springer_add():
    """Neuen Springer-Eintrag validieren und speichern."""
    is_valid, result = validators.validate_springer(_springer_form_data())
    if not is_valid:
        for error in result:
            flash(error, "error")
        return redirect(url_for("springer_page"))

    db.add_springer(**result)
    flash("Springer-Eintrag hinzugefügt.", "success")
    return redirect(url_for("springer_page"))


@app.route("/springer/edit/<int:springer_id>", methods=["GET"])
@login_required
def springer_edit(springer_id):
    """Springer-Eintrag zum Bearbeiten laden."""
    entry = db.get_springer(springer_id)
    if entry is None:
        abort(404)
    return render_template(
        "springer.html",
        entries=[],
        therapists=db.list_users(),
        appointment_times=APPOINTMENT_TIMES,
        therapist_filter=None,
        show_hidden=False,
        edit_entry=entry,
        empty_hint=False,
    )


@app.route("/springer/edit/<int:springer_id>", methods=["POST"])
@login_required
def springer_update(springer_id):
    """Bearbeiteten Springer-Eintrag validieren und aktualisieren."""
    if db.get_springer(springer_id) is None:
        abort(404)

    is_valid, result = validators.validate_springer(_springer_form_data())
    if not is_valid:
        for error in result:
            flash(error, "error")
        return redirect(url_for("springer_edit", springer_id=springer_id))

    db.update_springer(springer_id, **result)
    flash("Springer-Eintrag aktualisiert.", "success")
    return redirect(url_for("springer_page"))


@app.route("/springer/delete/<int:springer_id>", methods=["POST"])
@login_required
def springer_delete(springer_id):
    """Springer-Eintrag löschen."""
    if db.get_springer(springer_id) is None:
        abort(404)
    db.delete_springer(springer_id)
    flash("Springer-Eintrag gelöscht.", "success")
    return redirect(url_for("springer_page"))


def _springer_form_data() -> dict:
    """Liest die Springer-Formularfelder aus dem Request."""
    return {
        "client_name": request.form.get("client_name", ""),
        "therapist": request.form.get("therapist", ""),
        "valid_from": request.form.get("valid_from", ""),
        "valid_until": request.form.get("valid_until", ""),
        "appointment_time": request.form.get("appointment_time", ""),
        "notes": request.form.get("notes", ""),
    }


# ---------------------------------------------------------------------------
# Warteliste
# ---------------------------------------------------------------------------

@app.route("/warteliste")
@login_required
def warteliste_page():
    """Warteliste anzeigen (sichtbare oder alle Kontakte)."""
    show_hidden = request.args.get("show_hidden") == "1"

    if show_hidden:
        contacts = db.get_all_contacts()
    else:
        contacts = db.get_visible_contacts(VISIBILITY_DAYS)

    visible_ids = {c["id"] for c in db.get_visible_contacts(VISIBILITY_DAYS)}
    for contact in contacts:
        contact["waiting_days"] = _waiting_days(contact["created_at"])
        contact["is_hidden"] = contact["id"] not in visible_ids

    return render_template(
        "warteliste.html",
        contacts=contacts,
        appointment_times=APPOINTMENT_TIMES,
        show_hidden=show_hidden,
        empty_hint=len(contacts) == 0,
        edit_contact=None,
    )


@app.route("/warteliste/add", methods=["POST"])
@login_required
def warteliste_add():
    """Neuen Kontakt validieren und speichern."""
    is_valid, result = validators.validate_contact(_contact_form_data())
    if not is_valid:
        for error in result:
            flash(error, "error")
        return redirect(url_for("warteliste_page"))

    db.add_contact(**result)
    flash("Kontakt erfolgreich hinzugefügt.", "success")
    return redirect(url_for("warteliste_page"))


@app.route("/warteliste/edit/<int:contact_id>", methods=["GET"])
@login_required
def warteliste_edit(contact_id):
    """Kontaktdaten zum Bearbeiten laden."""
    contact = db.get_contact(contact_id)
    if contact is None:
        abort(404)
    return render_template(
        "warteliste.html",
        edit_contact=contact,
        contacts=_contacts_for_index(),
        appointment_times=APPOINTMENT_TIMES,
        show_hidden=False,
        empty_hint=False,
    )


@app.route("/warteliste/edit/<int:contact_id>", methods=["POST"])
@login_required
def warteliste_update(contact_id):
    """Bearbeiteten Kontakt validieren und aktualisieren."""
    if db.get_contact(contact_id) is None:
        abort(404)

    is_valid, result = validators.validate_contact(_contact_form_data())
    if not is_valid:
        for error in result:
            flash(error, "error")
        return redirect(url_for("warteliste_edit", contact_id=contact_id))

    db.update_contact(contact_id, **result)
    flash("Kontakt erfolgreich aktualisiert.", "success")
    return redirect(url_for("warteliste_page"))


@app.route("/warteliste/delete/<int:contact_id>", methods=["POST"])
@login_required
def warteliste_delete(contact_id):
    """Kontakt löschen."""
    if db.get_contact(contact_id) is None:
        abort(404)
    db.delete_contact(contact_id)
    flash("Kontakt erfolgreich gelöscht.", "success")
    return redirect(url_for("warteliste_page"))


@app.route("/warteliste/export")
@login_required
def warteliste_export():
    """Alle Kontakte als JSON-Datei zum Download anbieten."""
    data = db.export_contacts()
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    response = make_response(json_str)
    response.headers["Content-Type"] = "application/json; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=warteliste_export.json"
    return response


@app.route("/warteliste/import", methods=["GET"])
@login_required
def warteliste_import_page():
    """Import-Seite anzeigen."""
    return render_template("import.html")


@app.route("/warteliste/import", methods=["POST"])
@login_required
def warteliste_import():
    """JSON-Datei importieren mit Modus (ersetzen/zusammenführen)."""
    file = request.files.get("file")
    mode = request.form.get("mode", "replace")

    if not file or file.filename == "":
        flash("Bitte eine JSON-Datei auswählen.", "error")
        return redirect(url_for("warteliste_import_page"))

    try:
        data = json.loads(file.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        flash("Die Datei enthält kein gültiges JSON-Format.", "error")
        return redirect(url_for("warteliste_import_page"))

    is_valid, result = validators.validate_import_json(data)
    if not is_valid:
        for error in result:
            flash(error, "error")
        return redirect(url_for("warteliste_import_page"))

    count = db.import_contacts(data, mode=mode)
    flash(f"{count} Kontakt(e) erfolgreich importiert.", "success")
    return redirect(url_for("warteliste_page"))


def _contact_form_data() -> dict:
    """Liest die Kontakt-Formularfelder aus dem Request."""
    return {
        "name": request.form.get("name", ""),
        "phone": request.form.get("phone", ""),
        "email": request.form.get("email", ""),
        "notes": request.form.get("notes", ""),
        "appointment_time": request.form.get("appointment_time", "flexibel"),
    }


def _contacts_for_index() -> list[dict]:
    """Hilfsfunktion: sichtbare Kontaktliste mit Wartedauer."""
    contacts = db.get_visible_contacts(VISIBILITY_DAYS)
    for contact in contacts:
        contact["waiting_days"] = _waiting_days(contact["created_at"])
        contact["is_hidden"] = False
    return contacts


# ---------------------------------------------------------------------------
# Nutzerverwaltung
# ---------------------------------------------------------------------------

@app.route("/users")
@login_required
def users_page():
    """Nutzerverwaltung: Liste + Anlegen-Formular."""
    return render_template("users.html", users=db.list_users(), role_labels=ROLE_LABELS)


@app.route("/users/add", methods=["POST"])
@login_required
def users_add():
    """Neuen Nutzer validieren und anlegen."""
    data = {
        "username": request.form.get("username", ""),
        "password": request.form.get("password", ""),
        "role": request.form.get("role", ""),
    }
    is_valid, result = validators.validate_user(data)
    if not is_valid:
        for error in result:
            flash(error, "error")
        return redirect(url_for("users_page"))

    if db.get_user_by_username(result["username"]):
        flash("Benutzername ist bereits vergeben.", "error")
        return redirect(url_for("users_page"))

    db.add_user(
        username=result["username"],
        password_hash=generate_password_hash(result["password"]),
        role=result["role"],
    )
    flash("Nutzer angelegt.", "success")
    return redirect(url_for("users_page"))


@app.route("/users/delete/<int:user_id>", methods=["POST"])
@login_required
def users_delete(user_id):
    """Nutzer entfernen. Springer-Einträge der Person bleiben erhalten."""
    db.delete_user(user_id)
    flash("Nutzer entfernt.", "success")
    return redirect(url_for("users_page"))


# Datenbank beim Import initialisieren und ggf. Admin-Konto seeden.
db.init_db()
seed_initial_user()
