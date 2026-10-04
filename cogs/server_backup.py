import asyncio
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import discord
from discord.ext import commands, tasks

from utils.database import create_server_backup, get_latest_server_backup, get_server_backups

SNAPSHOT_INTERVAL = 900
MESSAGE_LIMIT = 100
NUKE_DELETE_THRESHOLD = 3
NUKE_WINDOW = 15


def _overwrite_data(channel: discord.abc.GuildChannel, guild: discord.Guild) -> list[dict]:
    result = []
    for target, overwrite in channel.overwrites.items():
        if isinstance(target, discord.Role):
            target_id = target.id
            target_type = "role"
        elif isinstance(target, discord.Member):
            target_id = target.id
            target_type = "member"
        else:
            continue
        result.append({
            "type": target_type,
            "id": target_id,
            "allow": overwrite.pair()[0].value,
            "deny": overwrite.pair()[1].value,
        })
    return result


def _channel_type(channel: discord.abc.GuildChannel) -> str | None:
    if isinstance(channel, discord.CategoryChannel):
        return "category"
    if isinstance(channel, discord.TextChannel):
        return "text"
    if isinstance(channel, discord.VoiceChannel):
        return "voice"
    if isinstance(channel, discord.StageChannel):
        return "stage"
    if isinstance(channel, discord.ForumChannel):
        return "forum"
    return None


class ServerBackup(commands.Cog):
    """Rolling disaster-recovery snapshots and nuke recovery."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._delete_events: dict[int, deque[float]] = defaultdict(deque)
        self._snapshot_lock: set[int] = set()
        self._ready = False
        self.snapshot_loop.start()

    def cog_unload(self):
        self.snapshot_loop.cancel()

    async def _snapshot(self, guild: discord.Guild, reason: str) -> int | None:
        if guild.id in self._snapshot_lock:
            return None
        self._snapshot_lock.add(guild.id)
        try:
            snapshot = {
                "version": 1,
                "guild": {"name": guild.name, "description": guild.description or ""},
                "roles": [],
                "channels": [],
            }

            for role in sorted(guild.roles, key=lambda r: r.position):
                if role.is_default() or role.managed:
                    continue
                snapshot["roles"].append({
                    "id": role.id,
                    "name": role.name,
                    "colour": role.colour.value,
                    "hoist": role.hoist,
                    "mentionable": role.mentionable,
                    "permissions": role.permissions.value,
                    "position": role.position,
                })

            for channel in sorted(guild.channels, key=lambda c: (getattr(c, "position", 0), c.id)):
                kind = _channel_type(channel)
                if not kind:
                    continue
                item = {
                    "id": channel.id,
                    "type": kind,
                    "name": channel.name,
                    "position": channel.position,
                    "category_id": channel.category_id,
                    "overwrites": _overwrite_data(channel, guild),
                }
                if isinstance(channel, discord.TextChannel):
                    item.update({
                        "topic": channel.topic,
                        "nsfw": channel.nsfw,
                        "slowmode_delay": channel.slowmode_delay,
                    })
                    messages = []
                    try:
                        async for message in channel.history(limit=MESSAGE_LIMIT, oldest_first=False):
                            if message.author.bot and not message.embeds and not message.content:
                                continue
                            messages.append({
                                "author_id": message.author.id,
                                "content": message.content[:4000],
                                "embeds": [
                                    {
                                        "title": e.title,
                                        "description": e.description,
                                        "url": e.url,
                                        "colour": e.colour.value if e.colour else None,
                                        "fields": [
                                            {"name": f.name, "value": f.value, "inline": f.inline}
                                            for f in e.fields
                                        ],
                                        "footer": e.footer.text if e.footer else None,
                                        "image": e.image.url if e.image else None,
                                        "thumbnail": e.thumbnail.url if e.thumbnail else None,
                                    }
                                    for e in message.embeds[:5]
                                ],
                            })
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                    item["messages"] = list(reversed(messages))
                snapshot["channels"].append(item)

            return create_server_backup(guild.id, reason, snapshot)
        except (discord.Forbidden, discord.HTTPException):
            return None
        finally:
            self._snapshot_lock.discard(guild.id)

    @tasks.loop(seconds=SNAPSHOT_INTERVAL)
    async def snapshot_loop(self):
        for guild in list(self.bot.guilds):
            try:
                await self._snapshot(guild, "rolling-pre-raid snapshot")
            except Exception as error:
                print(f"[backup] snapshot failed for {guild.id}: {error!r}")

    @snapshot_loop.before_loop
    async def before_snapshot_loop(self):
        await self.bot.wait_until_ready()

    async def _record_delete(self, guild: discord.Guild, kind: str, object_id: int):
        now = time.monotonic()
        events = self._delete_events[guild.id]
        while events and now - events[0] > NUKE_WINDOW:
            events.popleft()
        events.append(now)
        if len(events) < NUKE_DELETE_THRESHOLD:
            return

        events.clear()
        backup = get_latest_server_backup(guild.id)
        if backup is None:
            await self._snapshot(guild, f"emergency {kind} deletion")
            return

        await self._announce(guild, f"Potential nuke detected: {event_count} rapid {kind} deletions. Latest safe snapshot is #{backup[0]}. ")
        await self._snapshot(guild, f"nuke detection marker: {event_count} {kind} deletions")

    async def _announce(self, guild: discord.Guild, text: str):
        me = guild.me
        if me is None:
            return
        for channel in guild.text_channels:
            perms = channel.permissions_for(me)
            if perms.send_messages:
                try:
                    await channel.send(
                        embed=discord.Embed(
                            title="Aishu Security — Nuke Detection",
                            description=text,
                            colour=discord.Colour.red(),
                            timestamp=discord.utils.utcnow(),
                        ),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass
                break

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self._record_delete(channel.guild, "channel", channel.id)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self._record_delete(role.guild, "role", role.id)

    @commands.group(name="server", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def server(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            latest = get_latest_server_backup(ctx.guild.id)
            await ctx.send(
                f"Latest server backup: **#{latest[0]}** ({latest[2]})"
                if latest else "No server backup exists yet."
            )

    @server.command(name="backup")
    async def backup(self, ctx: commands.Context):
        backup_id = await self._snapshot(ctx.guild, f"manual backup by {ctx.author.id}")
        await ctx.send(f"Server snapshot created: **#{backup_id}**." if backup_id else "Backup could not be created.")

    @server.command(name="backups")
    async def backups(self, ctx: commands.Context):
        rows = get_server_backups(ctx.guild.id, 10)
        if not rows:
            await ctx.send("No backups exist.")
            return
        lines = [f"**#{row[0]}** — {row[2]} — {row[1][:19]}" for row in rows]
        await ctx.send(embed=discord.Embed(title="Aishu Server Backups", description="\n".join(lines)))

    @server.command(name="restore")
    async def restore(self, ctx: commands.Context, backup_id: int | None = None):
        rows = get_server_backups(ctx.guild.id, 50)
        selected = next((row for row in rows if row[0] == backup_id), None) if backup_id else (rows[0] if rows else None)
        if not selected:
            await ctx.send("Backup not found.")
            return
        _, _, reason, snapshot = selected
        guild = ctx.guild
        role_map: dict[int, discord.Role] = {}
        category_map: dict[int, discord.CategoryChannel] = {}
        channel_map: dict[int, discord.abc.GuildChannel] = {}

        await ctx.send(f"Restoring server from backup **#{selected[0]}**. This may take some time.")

        if snapshot.get("guild", {}).get("name") and guild.me and guild.me.guild_permissions.manage_guild:
            try:
                await guild.edit(name=snapshot["guild"]["name"], reason="Aishu server recovery")
            except (discord.Forbidden, discord.HTTPException):
                pass

        for data in snapshot.get("roles", []):
            existing = discord.utils.get(guild.roles, name=data["name"])
            if existing and not existing.managed:
                role = existing
            else:
                try:
                    role = await guild.create_role(
                        name=data["name"],
                        colour=discord.Colour(data["colour"]),
                        hoist=bool(data["hoist"]),
                        mentionable=bool(data["mentionable"]),
                        permissions=discord.Permissions(data["permissions"]),
                        reason="Aishu server recovery",
                    )
                except (discord.Forbidden, discord.HTTPException):
                    continue
            role_map[int(data["id"])] = role

        ordered = sorted(snapshot.get("channels", []), key=lambda item: (item["type"] != "category", item.get("position", 0)))
        for data in ordered:
            existing = discord.utils.get(guild.channels, name=data["name"])
            if data["type"] == "category":
                if isinstance(existing, discord.CategoryChannel):
                    channel = existing
                else:
                    try:
                        channel = await guild.create_category(data["name"], reason="Aishu server recovery")
                    except (discord.Forbidden, discord.HTTPException):
                        continue
                category_map[int(data["id"])] = channel
                channel_map[int(data["id"])] = channel
                continue

            category = category_map.get(int(data["category_id"])) if data.get("category_id") else None
            if existing and _channel_type(existing) == data["type"]:
                channel = existing
            else:
                try:
                    if data["type"] == "text":
                        channel = await guild.create_text_channel(
                            data["name"], category=category, topic=data.get("topic"),
                            nsfw=bool(data.get("nsfw")), slowmode_delay=int(data.get("slowmode_delay", 0)),
                            reason="Aishu server recovery",
                        )
                    elif data["type"] == "voice":
                        channel = await guild.create_voice_channel(data["name"], category=category, reason="Aishu server recovery")
                    elif data["type"] == "stage":
                        channel = await guild.create_stage_channel(data["name"], category=category, reason="Aishu server recovery")
                    elif data["type"] == "forum":
                        channel = await guild.create_forum(data["name"], category=category, reason="Aishu server recovery")
                    else:
                        continue
                except (discord.Forbidden, discord.HTTPException):
                    continue
            channel_map[int(data["id"])] = channel

        for data in snapshot.get("channels", []):
            channel = channel_map.get(int(data["id"]))
            if not channel:
                continue
            for overwrite in data.get("overwrites", []):
                if overwrite["type"] != "role":
                    continue
                role = guild.default_role if int(overwrite["id"]) == guild.default_role.id else role_map.get(int(overwrite["id"]))
                if role is None:
                    continue
                permissions = discord.PermissionOverwrite.from_pair(
                    discord.Permissions(overwrite["allow"]),
                    discord.Permissions(overwrite["deny"]),
                )
                try:
                    await channel.set_permissions(role, overwrite=permissions, reason="Aishu server recovery")
                except (discord.Forbidden, discord.HTTPException):
                    pass

        for data in snapshot.get("channels", []):
            channel = channel_map.get(int(data["id"]))
            if not isinstance(channel, discord.TextChannel):
                continue
            messages = data.get("messages", [])
            if not messages:
                continue
            try:
                for message in messages:
                    embeds = []
                    for raw in message.get("embeds", []):
                        embed = discord.Embed(
                            title=raw.get("title"),
                            description=raw.get("description"),
                            url=raw.get("url"),
                            colour=raw.get("colour") or discord.Colour.default().value,
                        )
                        for field in raw.get("fields", []):
                            embed.add_field(name=field["name"], value=field["value"], inline=field["inline"])
                        if raw.get("footer"):
                            embed.set_footer(text=raw["footer"])
                        if raw.get("image"):
                            embed.set_image(url=raw["image"])
                        if raw.get("thumbnail"):
                            embed.set_thumbnail(url=raw["thumbnail"])
                        embeds.append(embed)
                    if message.get("content") or embeds:
                        await channel.send(
                            content=message.get("content") or None,
                            embeds=embeds[:10],
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
            except (discord.Forbidden, discord.HTTPException):
                pass

        await ctx.send(f"Recovery finished from backup **#{selected[0]}**. Original snapshot reason: {reason}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ServerBackup(bot))
