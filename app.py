from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "database.db"
VALID_STATUSES = {"Todo", "In Progress", "Done"}
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 5_000
MAX_PASSWORD_LENGTH = 256
MAX_IMPORT_TASKS = 1_000
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("TASK_MANAGER_SECRET_KEY", secrets.token_hex(32)),
    MAX_CONTENT_LENGTH=512 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)


def get_db_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    """Create the current schema and safely move pre-account tasks aside."""
    with get_db_connection() as connection:
        task_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
        }
        if task_columns and "user_id" not in task_columns:
            connection.execute("ALTER TABLE tasks RENAME TO legacy_tasks")

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'Todo'
                    CHECK (status IN ('Todo', 'In Progress', 'Done')),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )


def create_user(email: str, password: str) -> int:
    with get_db_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email, generate_password_hash(password)),
        )
    return cursor.lastrowid


def get_user_by_email(email: str) -> dict | None:
    with get_db_connection() as connection:
        row = connection.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with get_db_connection() as connection:
        row = connection.execute(
            "SELECT id, email, password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return dict(row) if row else None


def change_password(user_id: int, password: str) -> None:
    with get_db_connection() as connection:
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (generate_password_hash(password), user_id),
        )


def create_task(user_id: int, title: str, description: str = "", status: str = "Todo") -> dict:
    with get_db_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO tasks (user_id, title, description, status) VALUES (?, ?, ?, ?)",
            (user_id, title, description, status),
        )
        row = connection.execute(
            "SELECT id, title, description, status FROM tasks WHERE id = ? AND user_id = ?",
            (cursor.lastrowid, user_id),
        ).fetchone()
    return dict(row)


def get_all_tasks(user_id: int) -> list[dict]:
    with get_db_connection() as connection:
        rows = connection.execute(
            "SELECT id, title, description, status FROM tasks WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_task(user_id: int, task_id: int, title: str, description: str, status: str) -> dict | None:
    with get_db_connection() as connection:
        cursor = connection.execute(
            "UPDATE tasks SET title = ?, description = ?, status = ? WHERE id = ? AND user_id = ?",
            (title, description, status, task_id, user_id),
        )
        if cursor.rowcount == 0:
            return None
        row = connection.execute(
            "SELECT id, title, description, status FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, user_id),
        ).fetchone()
    return dict(row)


def delete_task(user_id: int, task_id: int) -> bool:
    with get_db_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)
        )
    return cursor.rowcount > 0


def normalize_email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        return None
    return email


def validate_password(value: object) -> str | None:
    if not isinstance(value, str) or not 8 <= len(value) <= MAX_PASSWORD_LENGTH:
        return None
    return value


def validate_task_data(data: object, require_status: bool = False) -> tuple[dict | None, str | None]:
    if not isinstance(data, dict):
        return None, "A JSON object is required."

    title = data.get("title")
    description = data.get("description", "")
    status = data.get("status")
    if not isinstance(title, str) or not title.strip():
        return None, "Title is required."
    if not isinstance(description, str):
        return None, "Description must be a string."
    if require_status and not isinstance(status, str):
        return None, "Status is required."
    if status is not None and (not isinstance(status, str) or status.strip() not in VALID_STATUSES):
        return None, "Status must be Todo, In Progress, or Done."

    title, description = title.strip(), description.strip()
    if len(title) > MAX_TITLE_LENGTH:
        return None, f"Title must be at most {MAX_TITLE_LENGTH} characters."
    if len(description) > MAX_DESCRIPTION_LENGTH:
        return None, f"Description must be at most {MAX_DESCRIPTION_LENGTH} characters."
    return {
        "title": title,
        "description": description,
        "status": status.strip() if isinstance(status, str) else "Todo",
    }, None


def current_user_id() -> int:
    return session["user_id"]


def csrf_token() -> str:
    return session.setdefault("csrf_token", secrets.token_urlsafe(32))


def csrf_is_valid(token: object) -> bool:
    expected = session.get("csrf_token")
    return isinstance(token, str) and isinstance(expected, str) and secrets.compare_digest(token, expected)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session or get_user_by_id(session["user_id"]) is None:
            session.clear()
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session or get_user_by_id(session["user_id"]) is None:
            session.clear()
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def api_csrf_is_valid() -> bool:
    return csrf_is_valid(request.headers.get("X-CSRF-Token"))


@app.context_processor
def inject_template_values():
    return {"csrf_token": csrf_token}


@app.after_request
def add_security_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(error):
    if request.path.startswith("/api/"):
        return jsonify(error="Request body is too large."), 413
    flash("Request body is too large.", "error")
    return redirect(request.referrer or url_for("index")), 413


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("index"))
    if request.method == "POST":
        if not csrf_is_valid(request.form.get("csrf_token")):
            flash("Invalid form token. Please try again.", "error")
            return redirect(url_for("register"))
        email = normalize_email(request.form.get("email"))
        password = validate_password(request.form.get("password"))
        if not email:
            flash("Enter a valid email address.", "error")
        elif not password:
            flash("Password must be between 8 and 256 characters.", "error")
        else:
            try:
                user_id = create_user(email, password)
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "error")
            else:
                session.clear()
                session["user_id"] = user_id
                csrf_token()
                return redirect(url_for("index"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))
    if request.method == "POST":
        if not csrf_is_valid(request.form.get("csrf_token")):
            flash("Invalid form token. Please try again.", "error")
            return redirect(url_for("login"))
        email = normalize_email(request.form.get("email"))
        password = request.form.get("password")
        user = get_user_by_email(email) if email else None
        if not user or not isinstance(password, str) or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            csrf_token()
            return redirect(url_for("index"))
    return render_template("login.html")


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
@login_required
def index():
    user = get_user_by_id(current_user_id())
    return render_template("index.html", email=user["email"])


@app.get("/settings")
@login_required
def settings():
    user = get_user_by_id(current_user_id())
    return render_template("settings.html", email=user["email"])


@app.post("/settings/password")
@login_required
def update_password():
    if not csrf_is_valid(request.form.get("csrf_token")):
        flash("Invalid form token. Please try again.", "error")
        return redirect(url_for("settings"))
    user = get_user_by_id(current_user_id())
    current_password = request.form.get("current_password")
    new_password = validate_password(request.form.get("new_password"))
    if not isinstance(current_password, str) or not check_password_hash(user["password_hash"], current_password):
        flash("Current password is incorrect.", "error")
    elif not new_password:
        flash("New password must be between 8 and 256 characters.", "error")
    else:
        change_password(current_user_id(), new_password)
        flash("Password updated.", "success")
    return redirect(url_for("settings"))


@app.get("/privacy")
def privacy():
    return render_template("privacy.html")


@app.get("/terms")
def terms():
    return render_template("terms.html")


@app.get("/api/tasks")
@api_login_required
def list_tasks():
    return jsonify(get_all_tasks(current_user_id()))


@app.post("/api/tasks")
@api_login_required
def add_task():
    if not api_csrf_is_valid():
        return jsonify(error="Invalid CSRF token."), 400
    data, error = validate_task_data(request.get_json(silent=True))
    if error:
        return jsonify(error=error), 400
    return jsonify(create_task(current_user_id(), data["title"], data["description"])), 201


@app.put("/api/tasks/<int:task_id>")
@api_login_required
def edit_task(task_id: int):
    if not api_csrf_is_valid():
        return jsonify(error="Invalid CSRF token."), 400
    data, error = validate_task_data(request.get_json(silent=True), require_status=True)
    if error:
        return jsonify(error=error), 400
    task = update_task(current_user_id(), task_id, data["title"], data["description"], data["status"])
    if task is None:
        return jsonify(error="Task not found."), 404
    return jsonify(task)


@app.delete("/api/tasks/<int:task_id>")
@api_login_required
def remove_task(task_id: int):
    if not api_csrf_is_valid():
        return jsonify(error="Invalid CSRF token."), 400
    if not delete_task(current_user_id(), task_id):
        return jsonify(error="Task not found."), 404
    return jsonify(message="Task deleted.")


@app.get("/api/tasks/export")
@api_login_required
def export_tasks():
    response = Response(json.dumps(get_all_tasks(current_user_id()), indent=2), mimetype="application/json")
    response.headers["Content-Disposition"] = 'attachment; filename="tasks.json"'
    return response


@app.post("/api/tasks/import")
@api_login_required
def import_tasks():
    if not api_csrf_is_valid():
        return jsonify(error="Invalid CSRF token."), 400
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify(error="Choose a JSON file to import."), 400
    try:
        imported = json.load(upload.stream)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonify(error="The uploaded file is not valid JSON."), 400
    if not isinstance(imported, list) or len(imported) > MAX_IMPORT_TASKS:
        return jsonify(error=f"Import a JSON array with at most {MAX_IMPORT_TASKS} tasks."), 400

    validated = []
    for item in imported:
        task, error = validate_task_data(item, require_status=True)
        if error:
            return jsonify(error=f"Invalid imported task: {error}"), 400
        validated.append(task)

    with get_db_connection() as connection:
        connection.executemany(
            "INSERT INTO tasks (user_id, title, description, status) VALUES (?, ?, ?, ?)",
            [(current_user_id(), task["title"], task["description"], task["status"]) for task in validated],
        )
    return jsonify(message=f"Imported {len(validated)} tasks.", count=len(validated)), 201


init_db()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
