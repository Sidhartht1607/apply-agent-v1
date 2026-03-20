"""Database-backed authentication helpers for ResumeForge.

Supports:
- SQLite for local development
- Postgres via DATABASE_URL for Railway/production
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - only relevant when Postgres deps are missing
    psycopg = None
    dict_row = None


REPO_ROOT = Path(__file__).resolve().parents[1]
SQLITE_DB_PATH = REPO_ROOT / "backend" / "resumeforge.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))


def _normalized_database_url() -> str:
    if DATABASE_URL.startswith("postgres://"):
        return DATABASE_URL.replace("postgres://", "postgresql://", 1)
    return DATABASE_URL


def _ensure_postgres_driver() -> None:
    if psycopg is None:
        raise RuntimeError(
            "Postgres support requires 'psycopg[binary]'. Add it to requirements before deploying."
        )


@contextmanager
def get_connection():
    if IS_POSTGRES:
        _ensure_postgres_driver()
        conn = psycopg.connect(_normalized_database_url(), row_factory=dict_row)
        try:
            yield conn
        finally:
            conn.close()
        return

    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _row_to_dict(row) -> dict | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def _fetchone_dict(cursor) -> dict | None:
    row = cursor.fetchone()
    return _row_to_dict(row)


def init_db() -> None:
    with get_connection() as conn:
        if IS_POSTGRES:
            _postgres_init(conn)
        else:
            _sqlite_init(conn)


def _sqlite_init(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            password_salt TEXT NOT NULL,
            resume_build_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    user_columns = {row[1] for row in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "name" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN name TEXT NOT NULL DEFAULT ''")
    if "resume_build_count" not in user_columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN resume_build_count INTEGER NOT NULL DEFAULT 0"
        )
    conn.commit()


def _postgres_init(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                resume_build_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT ''")
        cur.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS resume_build_count INTEGER NOT NULL DEFAULT 0"
        )
    conn.commit()


def database_backend_label() -> str:
    if IS_POSTGRES:
        parsed = urlparse(_normalized_database_url())
        return f"postgres ({parsed.hostname or 'remote'})"
    return f"sqlite ({SQLITE_DB_PATH})"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    )
    return derived.hex(), salt


def verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    computed_hash, _ = hash_password(password, password_salt)
    return hmac.compare_digest(computed_hash, password_hash)


def create_user(name: str, username: str, email: str, password: str) -> dict:
    password_hash, password_salt = hash_password(password)
    created_at = _utc_now()
    with get_connection() as conn:
        cursor = conn.cursor()
        if IS_POSTGRES:
            cursor.execute(
                """
                INSERT INTO users (
                    name, username, email, password_hash, password_salt, resume_build_count, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id, name, username, email, resume_build_count, created_at
                """,
                (name, username, email, password_hash, password_salt, 0, created_at),
            )
            user = _fetchone_dict(cursor)
        else:
            cursor.execute(
                """
                INSERT INTO users (name, username, email, password_hash, password_salt, resume_build_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (name, username, email, password_hash, password_salt, 0, created_at),
            )
            user = {
                "id": cursor.lastrowid,
                "name": name,
                "username": username,
                "email": email,
                "resume_build_count": 0,
                "created_at": created_at,
            }
        conn.commit()
        return user


def get_user_by_username(username: str) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        if IS_POSTGRES:
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        else:
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        return _fetchone_dict(cursor)


def get_user_by_email(email: str) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        if IS_POSTGRES:
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        else:
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        return _fetchone_dict(cursor)


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with get_connection() as conn:
        cursor = conn.cursor()
        if IS_POSTGRES:
            cursor.execute(
                "INSERT INTO sessions (user_id, token, created_at) VALUES (%s, %s, %s)",
                (user_id, token, _utc_now()),
            )
        else:
            cursor.execute(
                "INSERT INTO sessions (user_id, token, created_at) VALUES (?, ?, ?)",
                (user_id, token, _utc_now()),
            )
        conn.commit()
    return token


def get_user_by_token(token: str) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        query = """
            SELECT u.id, u.name, u.username, u.email, u.resume_build_count, u.created_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = {placeholder}
        """
        if IS_POSTGRES:
            cursor.execute(query.format(placeholder="%s"), (token,))
        else:
            cursor.execute(query.format(placeholder="?"), (token,))
        return _fetchone_dict(cursor)


def increment_resume_build_count(user_id: int) -> dict | None:
    with get_connection() as conn:
        cursor = conn.cursor()
        if IS_POSTGRES:
            cursor.execute(
                "UPDATE users SET resume_build_count = resume_build_count + 1 WHERE id = %s",
                (user_id,),
            )
            cursor.execute(
                "SELECT id, name, username, email, resume_build_count, created_at FROM users WHERE id = %s",
                (user_id,),
            )
        else:
            cursor.execute(
                "UPDATE users SET resume_build_count = resume_build_count + 1 WHERE id = ?",
                (user_id,),
            )
            cursor.execute(
                "SELECT id, name, username, email, resume_build_count, created_at FROM users WHERE id = ?",
                (user_id,),
            )
        conn.commit()
        return _fetchone_dict(cursor)


def delete_session(token: str) -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        if IS_POSTGRES:
            cursor.execute("DELETE FROM sessions WHERE token = %s", (token,))
        else:
            cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
