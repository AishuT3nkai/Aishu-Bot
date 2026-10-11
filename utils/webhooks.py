import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
from datetime import datetime, timezone
from urllib.parse import urlsplit
from typing import Any

import aiohttp
from aiohttp import web
from cryptography.fernet import Fernet, InvalidToken

from utils.database import connect

ALLOWED_EVENTS = {
    "member.joined",
    "member.verified",
    "member.quarantined",
    "raid.detected",
    "raid.cleared",
    "moderation.action",
}
MAX_ENDPOINT_LENGTH = 2048
MAX_EVENTS = len(ALLOWED_EVENTS)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_resolve_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not results:
        raise OSError("Webhook destination did not resolve.")
    for result in results:
        try:
            address = ipaddress.ip_address(result["host"])
        except ValueError as exc:
            raise OSError("Webhook destination resolved to an invalid address.") from exc
        if not address.is_global:
            raise OSError("Webhook destinations must resolve only to public IP addresses.")
    return results


class PublicOnlyResolver(aiohttp.abc.AbstractResolver):
    """Resolver that rejects private, loopback, link-local, and reserved targets at connect time."""

    def __init__(self):
        self._resolver = aiohttp.resolver.DefaultResolver()

    async def resolve(self, host: str, port: int = 0, family: int = socket.AF_INET):
        results = await self._resolver.resolve(host, port, family)
        return safe_resolve_results(results)

    async def close(self):
        await self._resolver.close()


class WebhookManager:
    def __init__(self, bot):
        self.bot = bot
        self._ensure_schema()

    def _ensure_schema(self):
        connection = connect()
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS dashboard_webhooks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                endpoint_enc TEXT NOT NULL,
                signing_secret_enc TEXT NOT NULL,
                events_json TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_dashboard_webhooks_guild
                ON dashboard_webhooks(guild_id, id);
            CREATE TABLE IF NOT EXISTS webhook_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                webhook_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                event_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                http_status INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(webhook_id) REFERENCES dashboard_webhooks(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook
                ON webhook_deliveries(guild_id, webhook_id, id DESC);
            """
        )
        connection.commit()
        connection.close()

    def _fernet(self) -> Fernet:
        key = os.getenv("BOT_WEBHOOK_ENCRYPTION_KEY", "").strip()
        if not key:
            raise web.HTTPServiceUnavailable(
                text="Webhook encryption is not configured on the bot host."
            )
        try:
            return Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise web.HTTPServiceUnavailable(
                text="Webhook encryption key is invalid."
            ) from exc

    def _seal(self, value: str) -> str:
        return self._fernet().encrypt(value.encode("utf-8")).decode("ascii")

    def _open(self, value: str) -> str:
        try:
            return self._fernet().decrypt(value.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeEncodeError) as exc:
            raise web.HTTPServiceUnavailable(text="Stored webhook secret cannot be decrypted.") from exc

    async def _validate_endpoint(self, endpoint: Any) -> tuple[str, str]:
        if not isinstance(endpoint, str) or not endpoint.strip() or len(endpoint) > MAX_ENDPOINT_LENGTH:
            raise web.HTTPBadRequest(text="Endpoint must be a URL no longer than 2048 characters.")
        endpoint = endpoint.strip()
        try:
            parsed = urlsplit(endpoint)
            port = parsed.port
        except ValueError as exc:
            raise web.HTTPBadRequest(text="Invalid endpoint URL.") from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or parsed.hostname.endswith(".")
        ):
            raise web.HTTPBadRequest(text="Webhook endpoints must be valid HTTPS URLs without credentials or fragments.")
        if port is not None and not 1 <= port <= 65535:
            raise web.HTTPBadRequest(text="Invalid endpoint port.")
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                parsed.hostname, port or 443, type=socket.SOCK_STREAM
            )
            addresses = [{"host": info[4][0]} for info in infos]
            safe_resolve_results(addresses)
        except (OSError, asyncio.TimeoutError):
            raise web.HTTPBadRequest(text="Endpoint host must resolve only to public IP addresses.")
        return endpoint, parsed.hostname

    def _guild(self, request: web.Request):
        try:
            guild_id = int(request.match_info["guild_id"])
        except (KeyError, ValueError):
            raise web.HTTPBadRequest(text="Invalid guild ID.")
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise web.HTTPNotFound(text="Guild is not available to this bot.")
        return guild

    def _owned_row(self, guild_id: int, webhook_id: int):
        connection = connect()
        row = connection.execute(
            "SELECT * FROM dashboard_webhooks WHERE guild_id = ? AND id = ?",
            (guild_id, webhook_id),
        ).fetchone()
        connection.close()
        if row is None:
            raise web.HTTPNotFound(text="Webhook not found.")
        return row

    @staticmethod
    def _public_row(row) -> dict[str, Any]:
        try:
            endpoint_host = urlsplit(row["endpoint_enc"]).hostname
        except (TypeError, ValueError):
            endpoint_host = None
        return {
            "id": str(row["id"]),
            "events": json.loads(row["events_json"]),
            "enabled": bool(row["enabled"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    async def list_webhooks(self, request: web.Request):
        guild = self._guild(request)
        connection = connect()
        rows = connection.execute(
            "SELECT id, endpoint_enc, events_json, enabled, created_at, updated_at FROM dashboard_webhooks WHERE guild_id = ? ORDER BY id DESC",
            (guild.id,),
        ).fetchall()
        connection.close()
        result = []
        for row in rows:
            endpoint_host = urlsplit(self._open(row["endpoint_enc"])).hostname
            result.append({
                "id": str(row["id"]),
                "endpointHost": endpoint_host,
                "events": json.loads(row["events_json"]),
                "enabled": bool(row["enabled"]),
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            })
        return web.json_response(result)

    async def create_webhook(self, request: web.Request):
        guild = self._guild(request)
        try:
            data = await request.json()
        except (ValueError, json.JSONDecodeError):
            raise web.HTTPBadRequest(text="Body must be valid JSON.")
        endpoint, _ = await self._validate_endpoint(data.get("endpoint"))
        events = data.get("events")
        if not isinstance(events, list) or not events or len(events) > MAX_EVENTS:
            raise web.HTTPBadRequest(text="Select at least one supported event.")
        if any(not isinstance(event, str) or event not in ALLOWED_EVENTS for event in events):
            raise web.HTTPBadRequest(text="One or more event types are not supported.")
        events = sorted(set(events))
        signing_secret = secrets.token_urlsafe(32)
        now = utc_now()
        connection = connect()
        cursor = connection.execute(
            """INSERT INTO dashboard_webhooks
               (guild_id, endpoint_enc, signing_secret_enc, events_json, enabled, created_at, updated_at)
               VALUES (?, ?, ?, ?, 1, ?, ?)""",
            (guild.id, self._seal(endpoint), self._seal(signing_secret), json.dumps(events), now, now),
        )
        webhook_id = cursor.lastrowid
        connection.commit()
        connection.close()
        return web.json_response({
            "id": str(webhook_id),
            "events": events,
            "enabled": True,
            "createdAt": now,
            "signingSecret": signing_secret,
        }, status=201)

    async def update_webhook(self, request: web.Request):
        guild = self._guild(request)
        try:
            webhook_id = int(request.match_info["webhook_id"])
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid webhook ID.")
        row = self._owned_row(guild.id, webhook_id)
        try:
            data = await request.json()
        except (ValueError, json.JSONDecodeError):
            raise web.HTTPBadRequest(text="Body must be valid JSON.")
        endpoint_enc = row["endpoint_enc"]
        events_json = row["events_json"]
        enabled = int(row["enabled"])
        if "endpoint" in data:
            endpoint, _ = await self._validate_endpoint(data["endpoint"])
            endpoint_enc = self._seal(endpoint)
        if "events" in data:
            events = data["events"]
            if not isinstance(events, list) or not events or len(events) > MAX_EVENTS:
                raise web.HTTPBadRequest(text="Select at least one supported event.")
            if any(not isinstance(event, str) or event not in ALLOWED_EVENTS for event in events):
                raise web.HTTPBadRequest(text="One or more event types are not supported.")
            events_json = json.dumps(sorted(set(events)))
        if "enabled" in data:
            if not isinstance(data["enabled"], bool):
                raise web.HTTPBadRequest(text="enabled must be a boolean.")
            enabled = int(data["enabled"])
        now = utc_now()
        connection = connect()
        connection.execute(
            """UPDATE dashboard_webhooks
               SET endpoint_enc = ?, events_json = ?, enabled = ?, updated_at = ?
               WHERE guild_id = ? AND id = ?""",
            (endpoint_enc, events_json, enabled, now, guild.id, webhook_id),
        )
        connection.commit()
        connection.close()
        return web.json_response({
            "id": str(webhook_id),
            "events": json.loads(events_json),
            "enabled": bool(enabled),
            "updatedAt": now,
        })

    async def delete_webhook(self, request: web.Request):
        guild = self._guild(request)
        try:
            webhook_id = int(request.match_info["webhook_id"])
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid webhook ID.")
        self._owned_row(guild.id, webhook_id)
        connection = connect()
        connection.execute("DELETE FROM webhook_deliveries WHERE guild_id = ? AND webhook_id = ?", (guild.id, webhook_id))
        connection.execute("DELETE FROM dashboard_webhooks WHERE guild_id = ? AND id = ?", (guild.id, webhook_id))
        connection.commit()
        connection.close()
        return web.Response(status=204)

    async def test_webhook(self, request: web.Request):
        guild = self._guild(request)
        try:
            webhook_id = int(request.match_info["webhook_id"])
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid webhook ID.")
        row = self._owned_row(guild.id, webhook_id)
        if not row["enabled"]:
            raise web.HTTPConflict(text="Enable this webhook before testing.")
        event_id = "evt_" + secrets.token_hex(12)
        payload = {
            "id": event_id,
            "event": "webhook.test",
            "version": 1,
            "timestamp": utc_now(),
            "guild": {"id": str(guild.id), "name": guild.name},
            "test": True,
        }
        result = await self._deliver(row, guild.id, "webhook.test", payload)
        return web.json_response({
            "ok": result["status"] == "delivered",
            "status": result["status"],
            "attempts": result["attempts"],
            "httpStatus": result["httpStatus"],
        })

    async def list_deliveries(self, request: web.Request):
        guild = self._guild(request)
        try:
            webhook_id = int(request.match_info["webhook_id"])
        except ValueError:
            raise web.HTTPBadRequest(text="Invalid webhook ID.")
        self._owned_row(guild.id, webhook_id)
        connection = connect()
        rows = connection.execute(
            """SELECT event_id, event_type, status, attempts, http_status, created_at
               FROM webhook_deliveries WHERE guild_id = ? AND webhook_id = ?
               ORDER BY id DESC LIMIT 50""",
            (guild.id, webhook_id),
        ).fetchall()
        connection.close()
        return web.json_response([{
            "eventId": row["event_id"],
            "event": row["event_type"],
            "status": row["status"],
            "attempts": row["attempts"],
            "httpStatus": row["http_status"],
            "createdAt": row["created_at"],
        } for row in rows])

    async def emit(self, guild_id: int, event_type: str, details: dict[str, Any]):
        if event_type not in ALLOWED_EVENTS:
            return
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        connection = connect()
        rows = connection.execute(
            "SELECT * FROM dashboard_webhooks WHERE guild_id = ? AND enabled = 1",
            (guild_id,),
        ).fetchall()
        connection.close()
        for row in rows:
            try:
                events = json.loads(row["events_json"])
            except (TypeError, ValueError):
                continue
            if event_type not in events:
                continue
            payload = {
                "id": "evt_" + secrets.token_hex(12),
                "event": event_type,
                "version": 1,
                "timestamp": utc_now(),
                "guild": {"id": str(guild.id), "name": guild.name},
                **details,
            }
            try:
                await self._deliver(row, guild_id, event_type, payload)
            except Exception:
                # Delivery details are stored as redacted metadata; never log endpoint URLs or secrets.
                print(f"Webhook delivery failed for guild={guild_id} webhook={row['id']} event={event_type}.")

    async def _deliver(self, row, guild_id: int, event_type: str, payload: dict[str, Any]):
        event_id = str(payload["id"])
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        signing_secret = self._open(row["signing_secret_enc"])
        signature = hmac.new(
            signing_secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256
        ).hexdigest()
        endpoint = self._open(row["endpoint_enc"])
        status = "failed"
        attempts = 0
        http_status = None
        timeout = aiohttp.ClientTimeout(total=6, connect=3, sock_read=4)
        resolver = PublicOnlyResolver()
        connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False)
        try:
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                for attempt in range(1, 4):
                    attempts = attempt
                    try:
                        async with session.post(
                            endpoint,
                            data=body,
                            headers={
                                "Content-Type": "application/json",
                                "User-Agent": "Aishu-Webhooks/1.0",
                                "X-Aishu-Event": event_type,
                                "X-Aishu-Event-Id": event_id,
                                "X-Aishu-Timestamp": timestamp,
                                "X-Aishu-Signature": f"sha256={signature}",
                            },
                            allow_redirects=False,
                        ) as response:
                            http_status = response.status
                            await response.content.read(1024)
                            if 200 <= response.status < 300:
                                status = "delivered"
                                break
                            if response.status < 500 and response.status != 429:
                                break
                    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
                        http_status = None
                    if attempt < 3:
                        await asyncio.sleep(0.25 * (2 ** (attempt - 1)))
        finally:
            await resolver.close()
        connection = connect()
        connection.execute(
            """INSERT INTO webhook_deliveries
               (webhook_id, guild_id, event_id, event_type, status, attempts, http_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (row["id"], guild_id, event_id, event_type, status, attempts, http_status, utc_now()),
        )
        connection.commit()
        connection.close()
        return {"status": status, "attempts": attempts, "httpStatus": http_status}

    def register(self, app: web.Application):
        app.router.add_get("/api/guilds/{guild_id}/webhooks", self.list_webhooks)
        app.router.add_post("/api/guilds/{guild_id}/webhooks", self.create_webhook)
        app.router.add_patch("/api/guilds/{guild_id}/webhooks/{webhook_id}", self.update_webhook)
        app.router.add_delete("/api/guilds/{guild_id}/webhooks/{webhook_id}", self.delete_webhook)
        app.router.add_post("/api/guilds/{guild_id}/webhooks/{webhook_id}/test", self.test_webhook)
        app.router.add_get("/api/guilds/{guild_id}/webhooks/{webhook_id}/deliveries", self.list_deliveries)
