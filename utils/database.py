import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path("aishu.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_settings (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    language TEXT NOT NULL DEFAULT 'id',
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS introductions (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    birthdate TEXT NOT NULL,
    age TEXT NOT NULL,
    origin TEXT NOT NULL,
    city TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id INTEGER PRIMARY KEY,
    welcome_channel_id INTEGER,
    goodbye_channel_id INTEGER,
    verification_channel_id INTEGER,
    verification_role_id INTEGER,
    unverified_role_id INTEGER,
    modlog_channel_id INTEGER,
    suggestion_channel_id INTEGER,
    report_channel_id INTEGER,
    ticket_category_id INTEGER,
    ticket_support_role_id INTEGER,
    autorole_id INTEGER,
    min_account_age_days INTEGER NOT NULL DEFAULT 7,
    verification_enabled INTEGER NOT NULL DEFAULT 0,
    welcome_enabled INTEGER NOT NULL DEFAULT 0,
    goodbye_enabled INTEGER NOT NULL DEFAULT 0,
    autorole_enabled INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    reporter_id INTEGER NOT NULL,
    target_id INTEGER,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL
);
"""

def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    connection.commit()
    return connection

def ensure_guild(guild_id: int) -> None:
    connection = connect()
    connection.execute("INSERT OR IGNORE INTO guild_config (guild_id) VALUES (?)", (guild_id,))
    connection.commit()
    connection.close()

def get_guild_config(guild_id: int) -> dict[str, Any]:
    ensure_guild(guild_id)
    connection = connect()
    row = connection.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,)).fetchone()
    connection.close()
    return dict(row) if row else {}

def update_guild_config(guild_id: int, **values: Any) -> None:
    ensure_guild(guild_id)
    allowed = {
        "welcome_channel_id", "goodbye_channel_id", "verification_channel_id",
        "verification_role_id", "unverified_role_id", "modlog_channel_id",
        "suggestion_channel_id", "report_channel_id", "ticket_category_id",
        "ticket_support_role_id", "autorole_id", "min_account_age_days",
        "verification_enabled", "welcome_enabled", "goodbye_enabled", "autorole_enabled",
    }
    values = {key: value for key, value in values.items() if key in allowed}
    if not values:
        return
    assignments = ", ".join(f"{key} = ?" for key in values)
    params = list(values.values()) + [guild_id]
    connection = connect()
    connection.execute(f"UPDATE guild_config SET {assignments} WHERE guild_id = ?", params)
    connection.commit()
    connection.close()

def get_language(guild_id: int, user_id: int) -> str:
    connection = connect()
    row = connection.execute(
        "SELECT language FROM user_settings WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ).fetchone()
    connection.close()
    return row["language"] if row else "id"

def set_language(guild_id: int, user_id: int, language: str) -> None:
    connection = connect()
    connection.execute(
        """
        INSERT INTO user_settings (guild_id, user_id, language)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET language = excluded.language
        """,
        (guild_id, user_id, language),
    )
    connection.commit()
    connection.close()

def save_introduction(guild_id: int, user_id: int, values: dict[str, str]) -> None:
    connection = connect()
    connection.execute(
        """
        INSERT INTO introductions
        (guild_id, user_id, name, birthdate, age, origin, city)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            name = excluded.name,
            birthdate = excluded.birthdate,
            age = excluded.age,
            origin = excluded.origin,
            city = excluded.city
        """,
        (
            guild_id, user_id, values["name"], values["birthdate"],
            values["age"], values["origin"], values["city"],
        ),
    )
    connection.commit()
    connection.close()

def get_introduction(guild_id: int, user_id: int):
    connection = connect()
    row = connection.execute(
        "SELECT * FROM introductions WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ).fetchone()
    connection.close()
    return row

def add_warning(guild_id: int, user_id: int, moderator_id: int, reason: str, created_at: str) -> int:
    connection = connect()
    cursor = connection.execute(
        "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
        (guild_id, user_id, moderator_id, reason, created_at),
    )
    connection.commit()
    warning_id = int(cursor.lastrowid)
    connection.close()
    return warning_id

def get_warnings(guild_id: int, user_id: int):
    connection = connect()
    rows = connection.execute(
        "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
        (guild_id, user_id),
    ).fetchall()
    connection.close()
    return rows

def clear_warnings(guild_id: int, user_id: int) -> int:
    connection = connect()
    cursor = connection.execute(
        "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    connection.commit()
    deleted = cursor.rowcount
    connection.close()
    return deleted

def add_suggestion(guild_id: int, user_id: int, content: str, created_at: str) -> int:
    connection = connect()
    cursor = connection.execute(
        "INSERT INTO suggestions (guild_id, user_id, content, created_at) VALUES (?, ?, ?, ?)",
        (guild_id, user_id, content, created_at),
    )
    connection.commit()
    suggestion_id = int(cursor.lastrowid)
    connection.close()
    return suggestion_id

def set_suggestion_status(guild_id: int, suggestion_id: int, status: str) -> bool:
    connection = connect()
    cursor = connection.execute(
        "UPDATE suggestions SET status = ? WHERE guild_id = ? AND id = ?",
        (status, guild_id, suggestion_id),
    )
    connection.commit()
    updated = cursor.rowcount > 0
    connection.close()
    return updated

def add_report(guild_id: int, reporter_id: int, target_id: int | None, content: str, created_at: str) -> int:
    connection = connect()
    cursor = connection.execute(
        "INSERT INTO reports (guild_id, reporter_id, target_id, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (guild_id, reporter_id, target_id, content, created_at),
    )
    connection.commit()
    report_id = int(cursor.lastrowid)
    connection.close()
    return report_id
