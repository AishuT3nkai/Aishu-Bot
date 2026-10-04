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
    birthday_channel_id INTEGER,
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
CREATE TABLE IF NOT EXISTS antiraid_config (
    guild_id INTEGER PRIMARY KEY,
    config_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS economy (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    level INTEGER NOT NULL DEFAULT 0,
    coins INTEGER NOT NULL DEFAULT 0,
    last_xp_at REAL NOT NULL DEFAULT 0,
    daily_at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);
CREATE TABLE IF NOT EXISTS role_panels (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    role_ids_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reaction_roles (
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    emoji TEXT NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (guild_id, message_id, emoji)
);
CREATE TABLE IF NOT EXISTS automod_config (
    guild_id INTEGER PRIMARY KEY,
    config_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS server_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    reason TEXT NOT NULL,
    snapshot_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mod_cases (
    guild_id INTEGER NOT NULL,
    case_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    target_id INTEGER,
    moderator_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    duration INTEGER,
    metadata_json TEXT,
    PRIMARY KEY (guild_id, case_id)
);
CREATE TABLE IF NOT EXISTS birthdays (
    guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    month INTEGER NOT NULL,
    day INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);
"""

def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)

    # Lightweight migrations for databases created before newer config fields existed.
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(guild_config)").fetchall()}
    if "birthday_channel_id" not in columns:
        connection.execute("ALTER TABLE guild_config ADD COLUMN birthday_channel_id INTEGER")

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
        "suggestion_channel_id", "report_channel_id", "birthday_channel_id", "ticket_category_id",
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


def set_birthday(guild_id: int, user_id: int, month: int, day: int) -> None:
    connection = connect()
    connection.execute(
        """
        INSERT INTO birthdays (guild_id, user_id, month, day)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            month = excluded.month,
            day = excluded.day
        """,
        (guild_id, user_id, month, day),
    )
    connection.commit()
    connection.close()


def get_birthday(guild_id: int, user_id: int):
    connection = connect()
    row = connection.execute(
        "SELECT * FROM birthdays WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ).fetchone()
    connection.close()
    return row


def remove_birthday(guild_id: int, user_id: int) -> bool:
    connection = connect()
    cursor = connection.execute(
        "DELETE FROM birthdays WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    )
    connection.commit()
    removed = cursor.rowcount > 0
    connection.close()
    return removed


def get_birthdays(guild_id: int, month: int, day: int):
    connection = connect()
    rows = connection.execute(
        "SELECT * FROM birthdays WHERE guild_id = ? AND month = ? AND day = ?",
        (guild_id, month, day),
    ).fetchall()
    connection.close()
    return rows


def set_report_status(guild_id: int, report_id: int, status: str) -> bool:
    connection = connect()
    cursor = connection.execute(
        "UPDATE reports SET status = ? WHERE guild_id = ? AND id = ?",
        (status, guild_id, report_id),
    )
    connection.commit()
    updated = cursor.rowcount > 0
    connection.close()
    return updated


def get_automod_config(guild_id: int) -> dict[str, Any]:
    import json
    connection = connect()
    row = connection.execute("SELECT config_json FROM automod_config WHERE guild_id = ?", (guild_id,)).fetchone()
    connection.close()
    if not row:
        return {}
    try:
        value = json.loads(row["config_json"])
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def set_automod_config(guild_id: int, config: dict[str, Any]) -> None:
    import json
    connection = connect()
    connection.execute(
        """INSERT INTO automod_config (guild_id, config_json)
        VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET config_json = excluded.config_json""",
        (guild_id, json.dumps(config, ensure_ascii=False)),
    )
    connection.commit()
    connection.close()


def get_antiraid_config(guild_id: int) -> dict[str, Any]:
    import json
    connection = connect()
    row = connection.execute("SELECT config_json FROM antiraid_config WHERE guild_id = ?", (guild_id,)).fetchone()
    connection.close()
    if not row:
        return {}
    try:
        value = json.loads(row["config_json"])
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def set_antiraid_config(guild_id: int, config: dict[str, Any]) -> None:
    import json
    connection = connect()
    connection.execute(
        """INSERT INTO antiraid_config (guild_id, config_json)
        VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET config_json = excluded.config_json""",
        (guild_id, json.dumps(config, ensure_ascii=False)),
    )
    connection.commit()
    connection.close()


def get_economy(guild_id: int, user_id: int) -> dict[str, Any]:
    connection = connect()
    row = connection.execute(
        "SELECT * FROM economy WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ).fetchone()
    if row is None:
        connection.execute(
            "INSERT INTO economy (guild_id, user_id) VALUES (?, ?)",
            (guild_id, user_id),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM economy WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).fetchone()
    connection.close()
    return dict(row)


def update_economy(guild_id: int, user_id: int, **values: Any) -> None:
    allowed = {"xp", "level", "coins", "last_xp_at", "daily_at"}
    values = {key: value for key, value in values.items() if key in allowed}
    if not values:
        return
    assignments = ", ".join(f"{key} = ?" for key in values)
    params = list(values.values()) + [guild_id, user_id]
    connection = connect()
    connection.execute(
        f"UPDATE economy SET {assignments} WHERE guild_id = ? AND user_id = ?",
        params,
    )
    connection.commit()
    connection.close()


def get_economy_leaderboard(guild_id: int, limit: int = 10):
    connection = connect()
    rows = connection.execute(
        "SELECT * FROM economy WHERE guild_id = ? ORDER BY level DESC, xp DESC, coins DESC LIMIT ?",
        (guild_id, limit),
    ).fetchall()
    connection.close()
    return rows


def save_role_panel(guild_id: int, channel_id: int, message_id: int, role_ids: list[int]) -> None:
    import json
    connection = connect()
    connection.execute(
        """INSERT INTO role_panels (guild_id, channel_id, message_id, role_ids_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET
            channel_id = excluded.channel_id,
            message_id = excluded.message_id,
            role_ids_json = excluded.role_ids_json""",
        (guild_id, channel_id, message_id, json.dumps(role_ids)),
    )
    connection.commit()
    connection.close()


def get_role_panels():
    import json
    connection = connect()
    rows = connection.execute("SELECT * FROM role_panels").fetchall()
    connection.close()
    result = []
    for row in rows:
        try:
            role_ids = json.loads(row["role_ids_json"])
        except (TypeError, ValueError):
            role_ids = []
        result.append((row["guild_id"], row["channel_id"], row["message_id"], role_ids))
    return result


def create_server_backup(guild_id: int, reason: str, snapshot: dict[str, Any]) -> int:
    import json
    connection = connect()
    cursor = connection.execute(
        "INSERT INTO server_backups (guild_id, created_at, reason, snapshot_json) VALUES (?, ?, ?, ?)",
        (guild_id, __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), reason, json.dumps(snapshot, ensure_ascii=False)),
    )
    connection.commit()
    backup_id = int(cursor.lastrowid)
    connection.close()
    return backup_id


def get_server_backups(guild_id: int, limit: int = 10):
    import json
    connection = connect()
    rows = connection.execute(
        "SELECT id, guild_id, created_at, reason, snapshot_json FROM server_backups WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
        (guild_id, limit),
    ).fetchall()
    connection.close()
    result = []
    for row in rows:
        try:
            snapshot = json.loads(row["snapshot_json"])
        except (TypeError, ValueError):
            snapshot = {}
        result.append((row["id"], row["created_at"], row["reason"], snapshot))
    return result


def get_latest_server_backup(guild_id: int):
    backups = get_server_backups(guild_id, 1)
    return backups[0] if backups else None


def create_case(
    guild_id: int,
    action: str,
    target_id: int | None,
    moderator_id: int,
    reason: str,
    created_at: str,
    duration: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    import json
    connection = connect()
    row = connection.execute(
        "SELECT COALESCE(MAX(case_id), 0) + 1 AS next_id FROM mod_cases WHERE guild_id = ?",
        (guild_id,),
    ).fetchone()
    case_id = int(row["next_id"])
    connection.execute(
        """INSERT INTO mod_cases
        (guild_id, case_id, action, target_id, moderator_id, reason, created_at, duration, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            guild_id, case_id, action, target_id, moderator_id, reason, created_at,
            duration, json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    connection.commit()
    connection.close()
    return case_id


def get_case(guild_id: int, case_id: int):
    connection = connect()
    row = connection.execute(
        "SELECT * FROM mod_cases WHERE guild_id = ? AND case_id = ?",
        (guild_id, case_id),
    ).fetchone()
    connection.close()
    return row


def get_member_cases(guild_id: int, user_id: int, limit: int = 15):
    connection = connect()
    rows = connection.execute(
        "SELECT * FROM mod_cases WHERE guild_id = ? AND target_id = ? ORDER BY case_id DESC LIMIT ?",
        (guild_id, user_id, limit),
    ).fetchall()
    connection.close()
    return rows


def add_reaction_role(guild_id: int, channel_id: int, message_id: int, emoji: str, role_id: int) -> None:
    connection = connect()
    connection.execute(
        """INSERT INTO reaction_roles (guild_id, channel_id, message_id, emoji, role_id)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, message_id, emoji) DO UPDATE SET
            channel_id = excluded.channel_id, role_id = excluded.role_id""",
        (guild_id, channel_id, message_id, emoji, role_id),
    )
    connection.commit()
    connection.close()


def get_reaction_role(guild_id: int, message_id: int, emoji: str):
    connection = connect()
    row = connection.execute(
        "SELECT * FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
        (guild_id, message_id, emoji),
    ).fetchone()
    connection.close()
    return dict(row) if row else None


def get_reaction_roles():
    connection = connect()
    rows = connection.execute("SELECT * FROM reaction_roles").fetchall()
    connection.close()
    return [dict(row) for row in rows]


def remove_reaction_role(guild_id: int, message_id: int, emoji: str) -> bool:
    connection = connect()
    cursor = connection.execute(
        "DELETE FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?",
        (guild_id, message_id, emoji),
    )
    connection.commit()
    removed = cursor.rowcount > 0
    connection.close()
    return removed
