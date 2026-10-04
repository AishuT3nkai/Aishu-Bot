import re
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands

from utils.database import add_warning, get_automod_config, get_guild_config, set_automod_config

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
INVITE_RE = re.compile(r"discord\.(?:gg|com/invite)/[A-Za-z0-9-]+", re.IGNORECASE)
DEFAULT_CONFIG = {
    "enabled": False, "spam_enabled": True, "spam_messages": 5, "spam_window": 8,
    "duplicate_enabled": True, "duplicate_messages": 3, "duplicate_window": 10,
    "mention_enabled": True, "max_mentions": 5, "links_enabled": False,
    "invites_enabled": False, "keywords": [], "action": "delete", "timeout_minutes": 5,
}

class Automod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._messages: dict[tuple[int, int], deque[tuple[float, str]]] = defaultdict(deque)

    def _config(self, guild_id: int) -> dict:
        config = DEFAULT_CONFIG.copy()
        config.update(get_automod_config(guild_id))
        return config

    async def _modlog(self, guild: discord.Guild, message: discord.Message, reason: str):
        config = get_guild_config(guild.id)
        channel = guild.get_channel(config.get("modlog_channel_id") or 0)
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(
            title="Automod Action",
            description=f"**Member:** {message.author.mention}\n**Channel:** {message.channel.mention}\n**Reason:** {reason}",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _take_action(self, message: discord.Message, reason: str, config: dict):
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass
        action = str(config.get("action", "delete"))
        if action == "warn" and isinstance(message.author, discord.Member):
            add_warning(
                message.guild.id, message.author.id,
                self.bot.user.id if self.bot.user else 0,
                f"Automod: {reason}", discord.utils.utcnow().isoformat(),
            )
        elif action == "timeout" and isinstance(message.author, discord.Member):
            try:
                await message.author.timeout(
                    discord.utils.utcnow() + timedelta(minutes=int(config.get("timeout_minutes", 5))),
                    reason=f"Automod: {reason}",
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
        await self._modlog(message.guild, message, reason)

    def _record(self, message: discord.Message, config: dict) -> str | None:
        now = time.monotonic()
        key = (message.guild.id, message.author.id)
        history = self._messages[key]
        max_window = max(int(config["spam_window"]), int(config["duplicate_window"]))
        while history and now - history[0][0] > max_window:
            history.popleft()
        history.append((now, message.content))
        if config["spam_enabled"]:
            window = float(config["spam_window"])
            recent = sum(1 for timestamp, _ in history if now - timestamp <= window)
            if recent >= int(config["spam_messages"]):
                return f"spam ({recent} messages/{int(window)}s)"
        if config["duplicate_enabled"] and message.content.strip():
            window = float(config["duplicate_window"])
            duplicate_count = sum(
                1 for timestamp, text in history
                if text.strip() == message.content.strip() and now - timestamp <= window
            )
            if duplicate_count >= int(config["duplicate_messages"]):
                return f"duplicate messages ({duplicate_count}/{int(window)}s)"
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot or not message.content:
            return
        if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_messages:
            return
        config = self._config(message.guild.id)
        if not config["enabled"]:
            return
        reason = self._record(message, config)
        if reason is None and config["mention_enabled"] and len(message.mentions) > int(config["max_mentions"]):
            reason = f"mention spam ({len(message.mentions)} mentions)"
        if reason is None and config["invites_enabled"] and INVITE_RE.search(message.content):
            reason = "Discord invite link"
        if reason is None and config["links_enabled"] and URL_RE.search(message.content):
            reason = "link filtering"
        if reason is None and config["keywords"]:
            lowered = message.content.casefold()
            if any(keyword.casefold() in lowered for keyword in config["keywords"]):
                reason = "blocked keyword"
        if reason:
            await self._take_action(message, reason, config)

    @commands.group(name="automod", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await self._send_status(ctx)

    async def _send_status(self, ctx: commands.Context):
        config = self._config(ctx.guild.id)
        embed = discord.Embed(title="Aishu Automod", color=discord.Color.blurple())
        embed.add_field(name="Enabled", value="Yes" if config["enabled"] else "No", inline=True)
        embed.add_field(name="Spam", value=f"{'On' if config['spam_enabled'] else 'Off'} — {config['spam_messages']} / {config['spam_window']}s", inline=True)
        embed.add_field(name="Duplicates", value=f"{'On' if config['duplicate_enabled'] else 'Off'} — {config['duplicate_messages']} / {config['duplicate_window']}s", inline=True)
        embed.add_field(name="Mentions", value=f"{'On' if config['mention_enabled'] else 'Off'} — max {config['max_mentions']}", inline=True)
        embed.add_field(name="Links", value="On" if config["links_enabled"] else "Off", inline=True)
        embed.add_field(name="Invites", value="On" if config["invites_enabled"] else "Off", inline=True)
        embed.add_field(name="Action", value=f"{config['action']} ({config['timeout_minutes']}m timeout)", inline=True)
        embed.add_field(name="Keywords", value=", ".join(config["keywords"][:20]) or "None", inline=False)
        await ctx.send(embed=embed)

    @automod.command(name="enable")
    async def enable(self, ctx: commands.Context):
        config = self._config(ctx.guild.id)
        config["enabled"] = True
        set_automod_config(ctx.guild.id, config)
        await ctx.send("Automod enabled.")

    @automod.command(name="disable")
    async def disable(self, ctx: commands.Context):
        config = self._config(ctx.guild.id)
        config["enabled"] = False
        set_automod_config(ctx.guild.id, config)
        await ctx.send("Automod disabled.")

    @automod.command(name="spam")
    async def spam(self, ctx: commands.Context, enabled: str | None = None, messages: int | None = None, window: int | None = None):
        config = self._config(ctx.guild.id)
        if enabled is None:
            await ctx.send(f"Spam: {'on' if config['spam_enabled'] else 'off'} — {config['spam_messages']} messages/{config['spam_window']}s")
            return
        if enabled.casefold() not in {"on", "off"}:
            await ctx.send("Usage: ,automod spam on|off [messages] [seconds]")
            return
        if messages is not None and not 2 <= messages <= 20:
            await ctx.send("Messages must be between 2 and 20.")
            return
        if window is not None and not 2 <= window <= 60:
            await ctx.send("Window must be between 2 and 60 seconds.")
            return
        config["spam_enabled"] = enabled.casefold() == "on"
        if messages is not None:
            config["spam_messages"] = messages
        if window is not None:
            config["spam_window"] = window
        set_automod_config(ctx.guild.id, config)
        await ctx.send("Spam automod updated.")

    @automod.command(name="duplicates")
    async def duplicates(self, ctx: commands.Context, enabled: str | None = None, messages: int | None = None, window: int | None = None):
        config = self._config(ctx.guild.id)
        if enabled is None:
            await ctx.send(f"Duplicates: {'on' if config['duplicate_enabled'] else 'off'} — {config['duplicate_messages']} messages/{config['duplicate_window']}s")
            return
        if enabled.casefold() not in {"on", "off"}:
            await ctx.send("Usage: ,automod duplicates on|off [messages] [seconds]")
            return
        if messages is not None and not 2 <= messages <= 20:
            await ctx.send("Messages must be between 2 and 20.")
            return
        if window is not None and not 2 <= window <= 60:
            await ctx.send("Window must be between 2 and 60 seconds.")
            return
        config["duplicate_enabled"] = enabled.casefold() == "on"
        if messages is not None:
            config["duplicate_messages"] = messages
        if window is not None:
            config["duplicate_window"] = window
        set_automod_config(ctx.guild.id, config)
        await ctx.send("Duplicate-message automod updated.")

    @automod.command(name="mentions")
    async def mentions(self, ctx: commands.Context, enabled: str | None = None, maximum: int | None = None):
        config = self._config(ctx.guild.id)
        if enabled is None:
            await ctx.send(f"Mentions: {'on' if config['mention_enabled'] else 'off'} — max {config['max_mentions']}")
            return
        if enabled.casefold() not in {"on", "off"}:
            await ctx.send("Usage: ,automod mentions on|off [maximum]")
            return
        if maximum is not None and not 1 <= maximum <= 20:
            await ctx.send("Maximum mentions must be between 1 and 20.")
            return
        config["mention_enabled"] = enabled.casefold() == "on"
        if maximum is not None:
            config["max_mentions"] = maximum
        set_automod_config(ctx.guild.id, config)
        await ctx.send("Mention automod updated.")

    @automod.command(name="links")
    async def links(self, ctx: commands.Context, enabled: str | None = None):
        config = self._config(ctx.guild.id)
        if enabled is None:
            await ctx.send(f"Links: {'on' if config['links_enabled'] else 'off'}")
            return
        if enabled.casefold() not in {"on", "off"}:
            await ctx.send("Usage: ,automod links on|off")
            return
        config["links_enabled"] = enabled.casefold() == "on"
        set_automod_config(ctx.guild.id, config)
        await ctx.send("Link filtering updated.")

    @automod.command(name="invites")
    async def invites(self, ctx: commands.Context, enabled: str | None = None):
        config = self._config(ctx.guild.id)
        if enabled is None:
            await ctx.send(f"Invites: {'on' if config['invites_enabled'] else 'off'}")
            return
        if enabled.casefold() not in {"on", "off"}:
            await ctx.send("Usage: ,automod invites on|off")
            return
        config["invites_enabled"] = enabled.casefold() == "on"
        set_automod_config(ctx.guild.id, config)
        await ctx.send("Invite filtering updated.")

    @automod.group(name="keywords", invoke_without_command=True)
    async def keywords(self, ctx: commands.Context):
        await ctx.send(", ".join(self._config(ctx.guild.id)["keywords"][:30]) or "No blocked keywords configured.")

    @keywords.command(name="add")
    async def keyword_add(self, ctx: commands.Context, *, keyword: str):
        keyword = keyword.strip()
        if not 1 <= len(keyword) <= 100:
            await ctx.send("Keyword must be between 1 and 100 characters.")
            return
        config = self._config(ctx.guild.id)
        if keyword.casefold() not in {item.casefold() for item in config["keywords"]}:
            config["keywords"] = (config["keywords"] + [keyword])[:100]
            set_automod_config(ctx.guild.id, config)
        await ctx.send("Blocked keyword added.")

    @keywords.command(name="remove")
    async def keyword_remove(self, ctx: commands.Context, *, keyword: str):
        config = self._config(ctx.guild.id)
        before = len(config["keywords"])
        config["keywords"] = [item for item in config["keywords"] if item.casefold() != keyword.strip().casefold()]
        set_automod_config(ctx.guild.id, config)
        await ctx.send("Keyword removed." if len(config["keywords"]) < before else "Keyword was not configured.")

    @automod.command(name="action")
    async def action(self, ctx: commands.Context, action: str | None = None, timeout_minutes: int | None = None):
        config = self._config(ctx.guild.id)
        if action is None:
            await ctx.send(f"Automod action: {config['action']}")
            return
        action = action.casefold()
        if action not in {"delete", "warn", "timeout"}:
            await ctx.send("Action must be delete, warn, or timeout.")
            return
        if timeout_minutes is not None and not 1 <= timeout_minutes <= 60:
            await ctx.send("Timeout duration must be between 1 and 60 minutes.")
            return
        config["action"] = action
        if timeout_minutes is not None:
            config["timeout_minutes"] = timeout_minutes
        set_automod_config(ctx.guild.id, config)
        await ctx.send("Automod action updated.")

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You do not have permission to configure automod.", delete_after=8)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument. Use ,help {ctx.command.qualified_name} for help.", delete_after=8)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("I could not understand the argument.", delete_after=8)
        else:
            raise error

async def setup(bot: commands.Bot):
    await bot.add_cog(Automod(bot))
