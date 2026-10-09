import hmac
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

import discord
from aiohttp import web

from utils.database import connect, ensure_guild, get_automod_config, get_guild_config, set_automod_config, update_guild_config


def _json(request: web.Request, status: int = 200, **data: Any) -> web.Response:
    return web.json_response(data, status=status)


def _rows(rows) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


class Bridge:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.secret = os.getenv("BOT_API_SHARED_SECRET", "")
        self.host = os.getenv("BOT_API_HOST", "0.0.0.0")
        self.port = int(os.getenv("BOT_API_PORT", "8080"))
        self.runner: web.AppRunner | None = None
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        connection = connect()
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS dashboard_configs (
                guild_id INTEGER NOT NULL,
                config_key TEXT NOT NULL,
                config_json TEXT NOT NULL,
                PRIMARY KEY (guild_id, config_key)
            )
            """
        )
        connection.commit()
        connection.close()

    def _get_config(self, guild_id: int, key: str, default: Any) -> Any:
        connection = connect()
        row = connection.execute(
            "SELECT config_json FROM dashboard_configs WHERE guild_id = ? AND config_key = ?",
            (guild_id, key),
        ).fetchone()
        connection.close()
        if not row:
            return default
        try:
            return json.loads(row["config_json"])
        except (TypeError, ValueError):
            return default

    def _set_config(self, guild_id: int, key: str, value: Any) -> None:
        connection = connect()
        connection.execute(
            """
            INSERT INTO dashboard_configs (guild_id, config_key, config_json)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, config_key)
            DO UPDATE SET config_json = excluded.config_json
            """,
            (guild_id, key, json.dumps(value, ensure_ascii=False)),
        )
        connection.commit()
        connection.close()

    def _guild(self, request: web.Request) -> discord.Guild:
        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            raise web.HTTPBadRequest(text="Invalid guild ID.")
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise web.HTTPNotFound(text="Guild is not available to this bot.")
        return guild

    @staticmethod
    def _id(value: Any) -> str | None:
        return str(value) if value is not None else None

    def _validate_id(self, value: Any, kind: str, guild: discord.Guild) -> str | None:
        if value is None:
            return None
        value = str(value)
        try:
            snowflake = int(value)
        except ValueError:
            raise web.HTTPBadRequest(text=f"Invalid {kind} ID.")
        if kind == "channel" and guild.get_channel(snowflake) is None:
            raise web.HTTPBadRequest(text=f"Channel {value} is not in this guild.")
        if kind == "role" and guild.get_role(snowflake) is None:
            raise web.HTTPBadRequest(text=f"Role {value} is not in this guild.")
        return value

    @web.middleware
    async def auth(self, request: web.Request, handler):
        if not self.secret:
            raise web.HTTPServiceUnavailable(text="Bridge secret is not configured.")
        header = request.headers.get("Authorization", "")
        expected = f"Bearer {self.secret}"
        if not hmac.compare_digest(header, expected):
            raise web.HTTPUnauthorized(text="Unauthorized.")
        return await handler(request)

    async def health(self, request: web.Request):
        return _json(request, ok=True, botOnline=not self.bot.is_closed(), guildCount=len(self.bot.guilds))

    async def guilds(self, request: web.Request):
        result = [
            {"id": str(guild.id), "name": guild.name, "memberCount": guild.member_count or 0}
            for guild in self.bot.guilds
        ]
        return web.json_response(result)

    async def overview(self, request: web.Request):
        guild = self._guild(request)
        config = get_guild_config(guild.id)
        connection = connect()
        suggestions = connection.execute(
            "SELECT COUNT(*) AS count FROM suggestions WHERE guild_id = ? AND status = 'pending'",
            (guild.id,),
        ).fetchone()["count"]
        reports = connection.execute(
            "SELECT COUNT(*) AS count FROM reports WHERE guild_id = ? AND status = 'open'",
            (guild.id,),
        ).fetchone()["count"]
        connection.close()
        return web.json_response({
            "botOnline": not self.bot.is_closed(),
            "botLatencyMs": round(self.bot.latency * 1000) if self.bot.latency is not None else None,
            "guildName": guild.name,
            "memberCount": guild.member_count or len(guild.members),
            "onlineCount": sum(1 for m in guild.members if m.status != discord.Status.offline),
            "verificationEnabled": bool(config.get("verification_enabled")),
            "welcomeEnabled": bool(config.get("welcome_enabled")),
            "goodbyeEnabled": bool(config.get("goodbye_enabled")),
            "ticketsEnabled": bool(self._get_config(guild.id, "tickets", {}).get("enabled", False)),
            "levelingEnabled": bool(self._get_config(guild.id, "leveling", {}).get("enabled", False)),
            "openSuggestions": suggestions,
            "openReports": reports,
        })

    async def verification_get(self, request: web.Request):
        guild = self._guild(request)
        c = get_guild_config(guild.id)
        return _json(request,
            enabled=bool(c.get("verification_enabled")),
            channelId=self._id(c.get("verification_channel_id")),
            verifiedRoleId=self._id(c.get("verification_role_id")),
            unverifiedRoleId=self._id(c.get("unverified_role_id")),
            minAccountAgeDays=int(c.get("min_account_age_days") or 0),
        )

    async def verification_put(self, request: web.Request):
        guild = self._guild(request)
        data = await request.json()
        channel = self._validate_id(data.get("channelId"), "channel", guild)
        verified = self._validate_id(data.get("verifiedRoleId"), "role", guild)
        unverified = self._validate_id(data.get("unverifiedRoleId"), "role", guild)
        update_guild_config(
            guild.id,
            verification_enabled=int(bool(data.get("enabled"))),
            verification_channel_id=_int_or_none(channel),
            verification_role_id=_int_or_none(verified),
            unverified_role_id=_int_or_none(unverified),
            min_account_age_days=max(0, min(365, int(data.get("minAccountAgeDays", 7)))),
        )
        return await self.verification_get(request)

    async def welcome_get(self, request: web.Request):
        guild = self._guild(request)
        c = get_guild_config(guild.id)
        stored = self._get_config(guild.id, "welcome", {})
        return _json(request,
            welcomeEnabled=bool(c.get("welcome_enabled")),
            welcomeChannelId=self._id(c.get("welcome_channel_id")),
            welcomeMessage=stored.get("welcomeMessage", "Welcome {user} to {server}!"),
            goodbyeEnabled=bool(c.get("goodbye_enabled")),
            goodbyeChannelId=self._id(c.get("goodbye_channel_id")),
            goodbyeMessage=stored.get("goodbyeMessage", "Goodbye {user}!"),
        )

    async def welcome_put(self, request: web.Request):
        guild = self._guild(request)
        data = await request.json()
        welcome_channel = self._validate_id(data.get("welcomeChannelId"), "channel", guild)
        goodbye_channel = self._validate_id(data.get("goodbyeChannelId"), "channel", guild)
        update_guild_config(
            guild.id,
            welcome_enabled=int(bool(data.get("welcomeEnabled"))),
            welcome_channel_id=_int_or_none(welcome_channel),
            goodbye_enabled=int(bool(data.get("goodbyeEnabled"))),
            goodbye_channel_id=_int_or_none(goodbye_channel),
        )
        self._set_config(guild.id, "welcome", {
            "welcomeMessage": str(data.get("welcomeMessage", "")),
            "goodbyeMessage": str(data.get("goodbyeMessage", "")),
        })
        return await self.welcome_get(request)

    async def moderation_get(self, request: web.Request):
        guild = self._guild(request)
        c = get_guild_config(guild.id)
        stored = self._get_config(guild.id, "moderation", {})
        return _json(request,
            logChannelId=self._id(c.get("modlog_channel_id")),
            muteRoleId=self._id(stored.get("muteRoleId")),
        )

    async def moderation_put(self, request: web.Request):
        guild = self._guild(request)
        data = await request.json()
        log_channel = self._validate_id(data.get("logChannelId"), "channel", guild)
        mute_role = self._validate_id(data.get("muteRoleId"), "role", guild)
        update_guild_config(guild.id, modlog_channel_id=_int_or_none(log_channel))
        self._set_config(guild.id, "moderation", {"muteRoleId": mute_role})
        return await self.moderation_get(request)

    async def warnings_get(self, request: web.Request):
        guild = self._guild(request)
        connection = connect()
        rows = connection.execute(
            "SELECT id, user_id, moderator_id, reason, created_at FROM warnings WHERE guild_id = ? ORDER BY id DESC",
            (guild.id,),
        ).fetchall()
        connection.close()
        result = []
        for row in rows:
            member = guild.get_member(row["user_id"])
            moderator = guild.get_member(row["moderator_id"])
            result.append({
                "id": str(row["id"]),
                "userId": str(row["user_id"]),
                "username": member.display_name if member else str(row["user_id"]),
                "moderatorId": str(row["moderator_id"]),
                "reason": row["reason"],
                "createdAt": row["created_at"],
            })
        return web.json_response(result)

    async def warning_delete(self, request: web.Request):
        guild = self._guild(request)
        try:
            warning_id = int(request.match_info["warning_id"])
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid warning ID.")
        connection = connect()
        cursor = connection.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND id = ?",
            (guild.id, warning_id),
        )
        connection.commit()
        connection.close()
        if cursor.rowcount == 0:
            raise web.HTTPNotFound(text="Warning not found.")
        return web.Response(status=204)

    async def tickets_get(self, request: web.Request):
        guild = self._guild(request)
        c = get_guild_config(guild.id)
        stored = self._get_config(guild.id, "tickets", {})
        return _json(request,
            categoryId=self._id(c.get("ticket_category_id")),
            supportRoleId=self._id(c.get("ticket_support_role_id")),
            namingPattern=stored.get("namingPattern", "ticket-{username}"),
            openMessage=stored.get("openMessage", "Thanks for opening a ticket!"),
        )

    async def tickets_put(self, request: web.Request):
        guild = self._guild(request)
        data = await request.json()
        category = self._validate_id(data.get("categoryId"), "channel", guild)
        support = self._validate_id(data.get("supportRoleId"), "role", guild)
        update_guild_config(
            guild.id,
            ticket_category_id=_int_or_none(category),
            ticket_support_role_id=_int_or_none(support),
        )
        self._set_config(guild.id, "tickets", {
            "namingPattern": str(data.get("namingPattern", "ticket-{username}")),
            "openMessage": str(data.get("openMessage", "")),
        })
        return await self.tickets_get(request)

    async def suggestion_config_get(self, request: web.Request):
        guild = self._guild(request)
        c = get_guild_config(guild.id)
        return _json(request, channelId=self._id(c.get("suggestion_channel_id")))

    async def suggestion_config_put(self, request: web.Request):
        guild = self._guild(request)
        data = await request.json()
        channel = self._validate_id(data.get("channelId"), "channel", guild)
        update_guild_config(guild.id, suggestion_channel_id=_int_or_none(channel))
        return await self.suggestion_config_get(request)

    async def suggestions_get(self, request: web.Request):
        guild = self._guild(request)
        connection = connect()
        rows = connection.execute(
            "SELECT id, user_id, content, status, created_at FROM suggestions WHERE guild_id = ? ORDER BY id DESC",
            (guild.id,),
        ).fetchall()
        connection.close()
        return web.json_response([{
            "id": str(row["id"]),
            "userId": str(row["user_id"]),
            "username": (guild.get_member(row["user_id"]).display_name if guild.get_member(row["user_id"]) else str(row["user_id"])),
            "content": row["content"],
            "status": row["status"],
            "note": self._get_config(guild.id, f"suggestion_note:{row['id']}", None),
            "createdAt": row["created_at"],
        } for row in rows])

    async def suggestion_decide(self, request: web.Request):
        guild = self._guild(request)
        try:
            suggestion_id = int(request.match_info["suggestion_id"])
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid suggestion ID.")
        data = await request.json()
        decision = data.get("decision")
        if decision not in {"approved", "denied"}:
            raise web.HTTPBadRequest(text="Decision must be approved or denied.")
        connection = connect()
        cursor = connection.execute(
            "UPDATE suggestions SET status = ? WHERE guild_id = ? AND id = ?",
            (decision, guild.id, suggestion_id),
        )
        connection.commit()
        connection.close()
        if cursor.rowcount == 0:
            raise web.HTTPNotFound(text="Suggestion not found.")
        self._set_config(guild.id, f"suggestion_note:{suggestion_id}", data.get("note"))
        return _json(request, ok=True)

    async def report_config_get(self, request: web.Request):
        guild = self._guild(request)
        c = get_guild_config(guild.id)
        return _json(request, channelId=self._id(c.get("report_channel_id")))

    async def report_config_put(self, request: web.Request):
        guild = self._guild(request)
        data = await request.json()
        channel = self._validate_id(data.get("channelId"), "channel", guild)
        update_guild_config(guild.id, report_channel_id=_int_or_none(channel))
        return await self.report_config_get(request)

    async def reports_get(self, request: web.Request):
        guild = self._guild(request)
        connection = connect()
        rows = connection.execute(
            "SELECT id, reporter_id, target_id, content, status, created_at FROM reports WHERE guild_id = ? ORDER BY id DESC",
            (guild.id,),
        ).fetchall()
        connection.close()
        result = []
        for row in rows:
            member = guild.get_member(row["reporter_id"])
            result.append({
                "id": str(row["id"]),
                "userId": str(row["reporter_id"]),
                "username": member.display_name if member else str(row["reporter_id"]),
                "content": row["content"],
                "status": row["status"],
                "createdAt": row["created_at"],
            })
        return web.json_response(result)

    async def report_close(self, request: web.Request):
        guild = self._guild(request)
        try:
            report_id = int(request.match_info["report_id"])
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid report ID.")
        connection = connect()
        cursor = connection.execute(
            "UPDATE reports SET status = 'closed' WHERE guild_id = ? AND id = ?",
            (guild.id, report_id),
        )
        connection.commit()
        connection.close()
        if cursor.rowcount == 0:
            raise web.HTTPNotFound(text="Report not found.")
        return _json(request, ok=True)

    async def birthday_get(self, request: web.Request):
        guild = self._guild(request)
        c = get_guild_config(guild.id)
        stored = self._get_config(guild.id, "birthday", {})
        return _json(request,
            enabled=bool(stored.get("enabled", bool(c.get("birthday_channel_id")))),
            channelId=self._id(c.get("birthday_channel_id")),
            announcementFormat=stored.get("announcementFormat", "Happy birthday, {user}!"),
        )

    async def birthday_put(self, request: web.Request):
        guild = self._guild(request)
        data = await request.json()
        channel = self._validate_id(data.get("channelId"), "channel", guild)
        update_guild_config(guild.id, birthday_channel_id=_int_or_none(channel))
        self._set_config(guild.id, "birthday", {
            "enabled": bool(data.get("enabled")),
            "announcementFormat": str(data.get("announcementFormat", "")),
        })
        return await self.birthday_get(request)

    async def autorole_get(self, request: web.Request):
        guild = self._guild(request)
        c = get_guild_config(guild.id)
        return _json(request, enabled=bool(c.get("autorole_enabled")), roleId=self._id(c.get("autorole_id")))

    async def autorole_put(self, request: web.Request):
        guild = self._guild(request)
        data = await request.json()
        role = self._validate_id(data.get("roleId"), "role", guild)
        update_guild_config(guild.id, autorole_enabled=int(bool(data.get("enabled"))), autorole_id=_int_or_none(role))
        return await self.autorole_get(request)

    async def leveling_get(self, request: web.Request):
        guild = self._guild(request)
        return web.json_response(self._get_config(guild.id, "leveling", {
            "enabled": False,
            "xpPerMessage": {"min": 10, "max": 20},
            "xpCooldownSeconds": 60,
            "xpMultiplier": 1,
            "levelUpChannelId": None,
            "levelUpMessage": "GG {user}, you reached level {level}!",
            "excludedChannelIds": [],
            "excludedRoleIds": [],
            "antiSpamEnabled": True,
        }))

    async def leveling_put(self, request: web.Request):
        guild = self._guild(request)
        data = await request.json()
        if data.get("levelUpChannelId") is not None:
            data["levelUpChannelId"] = self._validate_id(data["levelUpChannelId"], "channel", guild)
        for key in ("excludedChannelIds",):
            data[key] = [self._validate_id(value, "channel", guild) for value in data.get(key, [])]
        for key in ("excludedRoleIds",):
            data[key] = [self._validate_id(value, "role", guild) for value in data.get(key, [])]
        self._set_config(guild.id, "leveling", data)
        return await self.leveling_get(request)

    async def level_rewards_get(self, request: web.Request):
        guild = self._guild(request)
        return web.json_response(self._get_config(guild.id, "level_rewards", []))

    async def level_rewards_put(self, request: web.Request):
        guild = self._guild(request)
        data = await request.json()
        if not isinstance(data, list):
            raise web.HTTPBadRequest(text="Rewards must be an array.")
        for item in data:
            if not isinstance(item, dict):
                raise web.HTTPBadRequest(text="Invalid reward.")
            role = self._validate_id(item.get("roleId"), "role", guild)
            item["roleId"] = role
        self._set_config(guild.id, "level_rewards", data)
        return web.json_response(data)

    async def leveling_users_get(self, request: web.Request):
        guild = self._guild(request)
        search = request.query.get("search", "").strip().lower()
        connection = connect()
        rows = connection.execute(
            "SELECT user_id, xp, level FROM economy WHERE guild_id = ? ORDER BY level DESC, xp DESC, coins DESC",
            (guild.id,),
        ).fetchall()
        connection.close()
        result = []
        rank = 0
        for row in rows:
            member = guild.get_member(row["user_id"])
            username = member.display_name if member else str(row["user_id"])
            if search and search not in username.lower() and search not in str(row["user_id"]):
                continue
            rank += 1
            result.append({
                "userId": str(row["user_id"]),
                "username": username,
                "xp": int(row["xp"]),
                "level": int(row["level"]),
                "rank": rank,
            })
        return web.json_response(result)

    async def leveling_user_put(self, request: web.Request):
        guild = self._guild(request)
        user_id = int(request.match_info["user_id"])
        data = await request.json()
        xp = int(data.get("xp", 0))
        if xp < 0:
            raise web.HTTPBadRequest(text="XP cannot be negative.")
        connection = connect()
        connection.execute(
            "INSERT OR IGNORE INTO economy (guild_id, user_id) VALUES (?, ?)",
            (guild.id, user_id),
        )
        connection.execute(
            "UPDATE economy SET xp = ? WHERE guild_id = ? AND user_id = ?",
            (xp, guild.id, user_id),
        )
        connection.commit()
        connection.close()
        return _json(request, ok=True, xp=xp)

    async def leveling_user_reset(self, request: web.Request):
        guild = self._guild(request)
        user_id = int(request.match_info["user_id"])
        connection = connect()
        connection.execute(
            "INSERT OR IGNORE INTO economy (guild_id, user_id) VALUES (?, ?)",
            (guild.id, user_id),
        )
        connection.execute(
            "UPDATE economy SET xp = 0, level = 0 WHERE guild_id = ? AND user_id = ?",
            (guild.id, user_id),
        )
        connection.commit()
        connection.close()
        return _json(request, ok=True)

    async def languages(self, request: web.Request):
        guild = self._guild(request)
        connection = connect()
        rows = connection.execute(
            "SELECT language, COUNT(*) AS count FROM user_settings WHERE guild_id = ? GROUP BY language",
            (guild.id,),
        ).fetchall()
        total = sum(int(row["count"]) for row in rows)
        counts = {row["language"]: int(row["count"]) for row in rows}
        connection.close()
        labels = {"id": "Indonesia", "tl": "Tagalog", "en": "English"}
        return _json(request,
            totalMembersWithPreference=total,
            breakdown=[{"code": code, "label": labels[code], "count": counts.get(code, 0)} for code in ("id", "tl", "en")],
        )

    async def server_get(self, request: web.Request):
        guild = self._guild(request)
        c = get_guild_config(guild.id)
        stored = self._get_config(guild.id, "server", {})
        return _json(request,
            prefix=stored.get("prefix", "/"),
            moderationLogChannelId=self._id(c.get("modlog_channel_id")),
        )

    async def server_put(self, request: web.Request):
        guild = self._guild(request)
        data = await request.json()
        channel = self._validate_id(data.get("moderationLogChannelId"), "channel", guild)
        prefix = str(data.get("prefix", "/"))
        if not 1 <= len(prefix) <= 5:
            raise web.HTTPBadRequest(text="Prefix must be 1-5 characters.")
        update_guild_config(guild.id, modlog_channel_id=_int_or_none(channel))
        self._set_config(guild.id, "server", {"prefix": prefix})
        return await self.server_get(request)

    async def automod_get(self, request: web.Request):
        guild = self._guild(request)
        config = get_automod_config(guild.id)
        defaults = {
            "enabled": True, "spam_enabled": True, "spam_messages": 5, "spam_window": 8,
            "duplicate_enabled": True, "duplicate_messages": 3, "duplicate_window": 10,
            "mention_enabled": True, "max_mentions": 5, "links_enabled": False,
            "invites_enabled": False, "keywords": ["anjing", "bangsat", "bajingan", "kontol", "memek", "ngentot", "goblok", "tolol", "fuck", "fucking", "shit", "bitch", "asshole"], "action": "delete",
            "timeout_minutes": 5, "escalation": True, "exempt_roles": [],
            "exempt_channels": [], "action_cooldown": 5,
        }
        defaults.update(config)
        if not defaults.get("keywords"):
            defaults["keywords"] = ["anjing", "bangsat", "bajingan", "kontol", "memek", "ngentot", "goblok", "tolol", "fuck", "fucking", "shit", "bitch", "asshole"]
        defaults["exempt_roles"] = [str(value) for value in defaults.get("exempt_roles", [])]
        defaults["exempt_channels"] = [str(value) for value in defaults.get("exempt_channels", [])]
        return web.json_response(defaults)

    async def automod_put(self, request: web.Request):
        guild = self._guild(request)
        data = await request.json()
        current = get_automod_config(guild.id)
        allowed = {
            "enabled", "spam_enabled", "duplicate_enabled", "mention_enabled",
            "links_enabled", "invites_enabled", "escalation",
        }
        config = dict(current)
        for key in allowed:
            if key in data:
                config[key] = bool(data[key])
        for key, low, high in (
            ("spam_messages", 2, 20), ("spam_window", 2, 60),
            ("duplicate_messages", 2, 20), ("duplicate_window", 2, 60),
            ("max_mentions", 1, 20), ("timeout_minutes", 1, 60),
            ("action_cooldown", 0, 60),
        ):
            if key in data:
                try:
                    value = int(data[key])
                except (TypeError, ValueError):
                    raise web.HTTPBadRequest(text=f"Invalid {key}.")
                if not low <= value <= high:
                    raise web.HTTPBadRequest(text=f"{key} must be between {low} and {high}.")
                config[key] = value
        if "action" in data:
            action = str(data["action"]).casefold()
            if action not in {"delete", "warn", "timeout"}:
                raise web.HTTPBadRequest(text="Action must be delete, warn, or timeout.")
            config["action"] = action
        if "keywords" in data:
            keywords = data["keywords"]
            if not isinstance(keywords, list) or len(keywords) > 100:
                raise web.HTTPBadRequest(text="Keywords must be a list of at most 100 items.")
            cleaned = []
            for item in keywords:
                word = str(item).strip()
                if not word or len(word) > 100:
                    raise web.HTTPBadRequest(text="Each keyword must be 1-100 characters.")
                if word.casefold() not in {x.casefold() for x in cleaned}:
                    cleaned.append(word)
            config["keywords"] = cleaned
        for key, kind in (("exempt_roles", "role"), ("exempt_channels", "channel")):
            if key in data:
                values = data[key]
                if not isinstance(values, list) or len(values) > 100:
                    raise web.HTTPBadRequest(text=f"{key} must be a list of at most 100 IDs.")
                config[key] = []
                for value in values:
                    valid = self._validate_id(value, kind, guild)
                    if valid is not None:
                        config[key].append(int(valid))
        set_automod_config(guild.id, config)
        return await self.automod_get(request)

    def app(self) -> web.Application:
        app = web.Application(middlewares=[self.auth])
        app.router.add_get("/health", self.health)
        app.router.add_get("/api/guilds", self.guilds)
        app.router.add_get("/api/guilds/{guild_id}/overview", self.overview)
        app.router.add_get("/api/guilds/{guild_id}/verification", self.verification_get)
        app.router.add_put("/api/guilds/{guild_id}/verification", self.verification_put)
        app.router.add_get("/api/guilds/{guild_id}/welcome", self.welcome_get)
        app.router.add_put("/api/guilds/{guild_id}/welcome", self.welcome_put)
        app.router.add_get("/api/guilds/{guild_id}/moderation", self.moderation_get)
        app.router.add_get("/api/guilds/{guild_id}/automod", self.automod_get)
        app.router.add_put("/api/guilds/{guild_id}/automod", self.automod_put)
        app.router.add_put("/api/guilds/{guild_id}/moderation", self.moderation_put)
        app.router.add_get("/api/guilds/{guild_id}/moderation/warnings", self.warnings_get)
        app.router.add_delete("/api/guilds/{guild_id}/moderation/warnings/{warning_id}", self.warning_delete)
        app.router.add_get("/api/guilds/{guild_id}/tickets", self.tickets_get)
        app.router.add_put("/api/guilds/{guild_id}/tickets", self.tickets_put)
        app.router.add_get("/api/guilds/{guild_id}/suggestions/config", self.suggestion_config_get)
        app.router.add_put("/api/guilds/{guild_id}/suggestions/config", self.suggestion_config_put)
        app.router.add_get("/api/guilds/{guild_id}/suggestions", self.suggestions_get)
        app.router.add_post("/api/guilds/{guild_id}/suggestions/{suggestion_id}/decide", self.suggestion_decide)
        app.router.add_get("/api/guilds/{guild_id}/reports/config", self.report_config_get)
        app.router.add_put("/api/guilds/{guild_id}/reports/config", self.report_config_put)
        app.router.add_get("/api/guilds/{guild_id}/reports", self.reports_get)
        app.router.add_post("/api/guilds/{guild_id}/reports/{report_id}/close", self.report_close)
        app.router.add_get("/api/guilds/{guild_id}/birthday", self.birthday_get)
        app.router.add_put("/api/guilds/{guild_id}/birthday", self.birthday_put)
        app.router.add_get("/api/guilds/{guild_id}/autorole", self.autorole_get)
        app.router.add_put("/api/guilds/{guild_id}/autorole", self.autorole_put)
        app.router.add_get("/api/guilds/{guild_id}/leveling/config", self.leveling_get)
        app.router.add_put("/api/guilds/{guild_id}/leveling/config", self.leveling_put)
        app.router.add_get("/api/guilds/{guild_id}/leveling/rewards", self.level_rewards_get)
        app.router.add_put("/api/guilds/{guild_id}/leveling/rewards", self.level_rewards_put)
        app.router.add_get("/api/guilds/{guild_id}/leveling/users", self.leveling_users_get)
        app.router.add_put("/api/guilds/{guild_id}/leveling/users/{user_id}", self.leveling_user_put)
        app.router.add_post("/api/guilds/{guild_id}/leveling/users/{user_id}/reset", self.leveling_user_reset)
        app.router.add_get("/api/guilds/{guild_id}/languages", self.languages)
        app.router.add_get("/api/guilds/{guild_id}/server", self.server_get)
        app.router.add_put("/api/guilds/{guild_id}/server", self.server_put)
        return app

    async def start(self) -> None:
        if not self.secret:
            print("Bridge disabled: BOT_API_SHARED_SECRET is missing.")
            return
        self.runner = web.AppRunner(self.app())
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        print(f"Dashboard bridge listening on {self.host}:{self.port}")

    async def close(self) -> None:
        if self.runner is not None:
            await self.runner.cleanup()
            self.runner = None
