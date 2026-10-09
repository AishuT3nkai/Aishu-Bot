import re
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands

from utils.database import add_warning, create_case, get_automod_config, get_guild_config, set_automod_config

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
INVITE_RE = re.compile(r"discord\.(?:gg|com/invite)/[A-Za-z0-9-]+", re.IGNORECASE)

DEFAULT_CONFIG = {
    "enabled": True,
    "spam_enabled": True, "spam_messages": 5, "spam_window": 8,
    "duplicate_enabled": True, "duplicate_messages": 3, "duplicate_window": 10,
    "mention_enabled": True, "max_mentions": 5,
    "links_enabled": False, "invites_enabled": False,
    "keywords": ["anjing", "bangsat", "bajingan", "kontol", "memek", "ngentot", "goblok", "tolol", "fuck", "fucking", "shit", "bitch", "asshole"], "action": "delete", "timeout_minutes": 5,
    "escalation": True, "exempt_roles": [], "exempt_channels": [], "action_cooldown": 5,
}

class Automod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._messages = defaultdict(deque)
        self._violations = defaultdict(deque)
        self._action_times = {}

    def _config(self, guild_id: int) -> dict:
        config = DEFAULT_CONFIG.copy()
        config.update(get_automod_config(guild_id))
        config["exempt_roles"] = list(config.get("exempt_roles") or [])
        config["exempt_channels"] = list(config.get("exempt_channels") or [])
        config["keywords"] = list(config.get("keywords") or [])
        return config

    def _exempt(self, message, config):
        if not isinstance(message.author, discord.Member):
            return True
        role_ids = {int(x) for x in config["exempt_roles"]}
        channel_ids = {int(x) for x in config["exempt_channels"]}
        if message.channel.id in channel_ids or any(role.id in role_ids for role in message.author.roles):
            return True
        perms = message.author.guild_permissions
        return perms.manage_messages or perms.manage_guild or perms.administrator

    async def _modlog(self, guild, message, reason, action):
        config = get_guild_config(guild.id)
        channel = guild.get_channel(config.get("modlog_channel_id") or 0)
        if not isinstance(channel, discord.TextChannel):
            return
        content = message.content.strip().replace("\n", " ")[:500] or "(no text)"
        embed = discord.Embed(
            title="Automod Action",
            description=(
                f"Member: {message.author.mention} ({message.author.id})\n"
                f"Channel: {message.channel.mention}\n"
                f"Rule: {reason}\nAction: {action}\nContent: {content}"
            ),
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            pass

    def _record(self, message, config):
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
                if text.strip().casefold() == message.content.strip().casefold()
                and now - timestamp <= window
            )
            if duplicate_count >= int(config["duplicate_messages"]):
                return f"duplicate messages ({duplicate_count}/{int(window)}s)"
        return None

    def _keyword_match(self, content, keywords):
        lowered = content.casefold()
        for keyword in keywords:
            value = str(keyword).strip().casefold()
            if value and re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", lowered):
                return True
        return False

    def _escalated_action(self, guild_id, user_id, reason, config):
        if not config.get("escalation"):
            return str(config.get("action", "delete"))
        key = (guild_id, user_id, reason.split(" (", 1)[0])
        now = time.monotonic()
        history = self._violations[key]
        while history and now - history[0] > 600:
            history.popleft()
        history.append(now)
        if len(history) >= 2:
            return "timeout"
        return "warn"

    async def _take_action(self, message, reason, config):
        action = self._escalated_action(message.guild.id, message.author.id, reason, config)
        key = (message.guild.id, message.author.id, reason.split(" (", 1)[0])
        now = time.monotonic()
        if now - self._action_times.get(key, 0) < max(0, int(config.get("action_cooldown", 5))):
            return
        self._action_times[key] = now
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

        case_id = None
        if action == "warn" and isinstance(message.author, discord.Member):
            warning_id = add_warning(
                message.guild.id, message.author.id,
                self.bot.user.id if self.bot.user else 0,
                f"Automod: {reason}", discord.utils.utcnow().isoformat(),
            )
            case_id = create_case(
                message.guild.id, "automod_warn", message.author.id,
                self.bot.user.id if self.bot.user else 0, reason,
                discord.utils.utcnow().isoformat(), metadata={"warning_id": warning_id},
            )
            try:
                await message.channel.send(
                    f"{message.author.mention}, pesanmu dihapus karena melanggar aturan ({reason}). "
                    "Ini peringatan pertama—silakan baca #rules. Pelanggaran berikutnya dapat membuatmu timeout.",
                    delete_after=12,
                    allowed_mentions=discord.AllowedMentions(users=True),
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
        elif action == "timeout" and isinstance(message.author, discord.Member):
            try:
                minutes = max(1, min(60, int(config.get("timeout_minutes", 5))))
                await message.author.timeout(
                    discord.utils.utcnow() + timedelta(minutes=minutes),
                    reason=f"Automod: {reason}",
                )
                case_id = create_case(
                    message.guild.id, "automod_timeout", message.author.id,
                    self.bot.user.id if self.bot.user else 0, reason,
                    discord.utils.utcnow().isoformat(), duration=minutes,
                )
            except (discord.Forbidden, discord.HTTPException):
                pass
        await self._modlog(message.guild, message, reason, action + (f" / Case #{case_id}" if case_id else ""))

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot or not message.content:
            return
        config = self._config(message.guild.id)
        if not config["enabled"] or self._exempt(message, config):
            return
        reason = self._record(message, config)
        if reason is None and config["mention_enabled"] and len(message.mentions) > int(config["max_mentions"]):
            reason = f"mention spam ({len(message.mentions)} mentions)"
        if reason is None and config["invites_enabled"] and INVITE_RE.search(message.content):
            reason = "Discord invite link"
        if reason is None and config["links_enabled"] and URL_RE.search(message.content):
            reason = "link filtering"
        if reason is None and config["keywords"] and self._keyword_match(message.content, config["keywords"]):
            reason = "blocked keyword"
        if reason:
            await self._take_action(message, reason, config)

    @commands.group(name="automod", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx):
        if ctx.invoked_subcommand is None:
            config = self._config(ctx.guild.id)
            embed = discord.Embed(title="Aishu Automod", color=discord.Color.blurple())
            embed.add_field(name="Enabled", value="Yes" if config["enabled"] else "No")
            embed.add_field(name="Action", value=f"{config['action']} / escalation={'on' if config['escalation'] else 'off'}")
            embed.add_field(name="Exempt roles", value=str(len(config["exempt_roles"])))
            embed.add_field(name="Exempt channels", value=str(len(config["exempt_channels"])))
            embed.add_field(name="Keywords", value=", ".join(config["keywords"][:20]) or "None", inline=False)
            await ctx.send(embed=embed)

    @automod.command(name="enable")
    async def enable(self, ctx):
        config = self._config(ctx.guild.id); config["enabled"] = True
        set_automod_config(ctx.guild.id, config); await ctx.send("Automod enabled.")

    @automod.command(name="disable")
    async def disable(self, ctx):
        config = self._config(ctx.guild.id); config["enabled"] = False
        set_automod_config(ctx.guild.id, config); await ctx.send("Automod disabled.")

    @automod.command(name="spam")
    async def spam(self, ctx, enabled: str | None = None, messages: int | None = None, window: int | None = None):
        config = self._config(ctx.guild.id)
        if enabled is None:
            await ctx.send(f"Spam: {'on' if config['spam_enabled'] else 'off'} — {config['spam_messages']} messages/{config['spam_window']}s"); return
        if enabled.casefold() not in {"on", "off"} or (messages is not None and not 2 <= messages <= 20) or (window is not None and not 2 <= window <= 60):
            await ctx.send("Usage: ,automod spam on|off [messages] [seconds]"); return
        config["spam_enabled"] = enabled.casefold() == "on"
        if messages is not None: config["spam_messages"] = messages
        if window is not None: config["spam_window"] = window
        set_automod_config(ctx.guild.id, config); await ctx.send("Spam automod updated.")

    @automod.command(name="duplicates")
    async def duplicates(self, ctx, enabled: str | None = None, messages: int | None = None, window: int | None = None):
        config = self._config(ctx.guild.id)
        if enabled is None:
            await ctx.send(f"Duplicates: {'on' if config['duplicate_enabled'] else 'off'} — {config['duplicate_messages']} messages/{config['duplicate_window']}s"); return
        if enabled.casefold() not in {"on", "off"} or (messages is not None and not 2 <= messages <= 20) or (window is not None and not 2 <= window <= 60):
            await ctx.send("Usage: ,automod duplicates on|off [messages] [seconds]"); return
        config["duplicate_enabled"] = enabled.casefold() == "on"
        if messages is not None: config["duplicate_messages"] = messages
        if window is not None: config["duplicate_window"] = window
        set_automod_config(ctx.guild.id, config); await ctx.send("Duplicate-message automod updated.")

    @automod.command(name="mentions")
    async def mentions(self, ctx, enabled: str | None = None, maximum: int | None = None):
        config = self._config(ctx.guild.id)
        if enabled is None:
            await ctx.send(f"Mentions: {'on' if config['mention_enabled'] else 'off'} — max {config['max_mentions']}"); return
        if enabled.casefold() not in {"on", "off"} or (maximum is not None and not 1 <= maximum <= 20):
            await ctx.send("Usage: ,automod mentions on|off [maximum]"); return
        config["mention_enabled"] = enabled.casefold() == "on"
        if maximum is not None: config["max_mentions"] = maximum
        set_automod_config(ctx.guild.id, config); await ctx.send("Mention automod updated.")

    @automod.command(name="links")
    async def links(self, ctx, enabled: str | None = None):
        config = self._config(ctx.guild.id)
        if enabled is None: await ctx.send(f"Links: {'on' if config['links_enabled'] else 'off'}"); return
        if enabled.casefold() not in {"on", "off"}: await ctx.send("Usage: ,automod links on|off"); return
        config["links_enabled"] = enabled.casefold() == "on"
        set_automod_config(ctx.guild.id, config); await ctx.send("Link filtering updated.")

    @automod.command(name="invites")
    async def invites(self, ctx, enabled: str | None = None):
        config = self._config(ctx.guild.id)
        if enabled is None: await ctx.send(f"Invites: {'on' if config['invites_enabled'] else 'off'}"); return
        if enabled.casefold() not in {"on", "off"}: await ctx.send("Usage: ,automod invites on|off"); return
        config["invites_enabled"] = enabled.casefold() == "on"
        set_automod_config(ctx.guild.id, config); await ctx.send("Invite filtering updated.")

    @automod.group(name="keywords", invoke_without_command=True)
    async def keywords(self, ctx):
        await ctx.send(", ".join(self._config(ctx.guild.id)["keywords"][:30]) or "No blocked keywords configured.")

    @keywords.command(name="add")
    async def keyword_add(self, ctx, *, keyword: str):
        keyword = keyword.strip()
        if not 1 <= len(keyword) <= 100:
            await ctx.send("Keyword must be between 1 and 100 characters."); return
        config = self._config(ctx.guild.id)
        if keyword.casefold() not in {item.casefold() for item in config["keywords"]}:
            config["keywords"] = (config["keywords"] + [keyword])[:100]
            set_automod_config(ctx.guild.id, config)
        await ctx.send("Blocked keyword added.")

    @keywords.command(name="remove")
    async def keyword_remove(self, ctx, *, keyword: str):
        config = self._config(ctx.guild.id)
        before = len(config["keywords"])
        config["keywords"] = [item for item in config["keywords"] if item.casefold() != keyword.strip().casefold()]
        set_automod_config(ctx.guild.id, config)
        await ctx.send("Keyword removed." if len(config["keywords"]) < before else "Keyword was not configured.")

    @automod.command(name="action")
    async def action(self, ctx, action: str | None = None, timeout_minutes: int | None = None):
        config = self._config(ctx.guild.id)
        if action is None: await ctx.send(f"Automod action: {config['action']}"); return
        action = action.casefold()
        if action not in {"delete", "warn", "timeout"} or (timeout_minutes is not None and not 1 <= timeout_minutes <= 60):
            await ctx.send("Action must be delete, warn, or timeout."); return
        config["action"] = action
        if timeout_minutes is not None: config["timeout_minutes"] = timeout_minutes
        set_automod_config(ctx.guild.id, config); await ctx.send("Automod action updated.")

    @automod.command(name="escalation")
    async def escalation(self, ctx, enabled: str | None = None):
        config = self._config(ctx.guild.id)
        if enabled is None: await ctx.send(f"Escalation: {'on' if config['escalation'] else 'off'}"); return
        if enabled.casefold() not in {"on", "off"}: await ctx.send("Usage: ,automod escalation on|off"); return
        config["escalation"] = enabled.casefold() == "on"
        set_automod_config(ctx.guild.id, config); await ctx.send("Automod escalation updated.")

    @automod.group(name="exempt", invoke_without_command=True)
    async def exempt(self, ctx):
        config = self._config(ctx.guild.id)
        await ctx.send(f"Exempt roles: {len(config['exempt_roles'])} | Exempt channels: {len(config['exempt_channels'])}")

    @exempt.command(name="role")
    async def exempt_role(self, ctx, role: discord.Role):
        config = self._config(ctx.guild.id)
        if role.id not in config["exempt_roles"]:
            config["exempt_roles"].append(role.id); set_automod_config(ctx.guild.id, config)
        await ctx.send(f"Automod exemption added for {role.mention}.")

    @exempt.command(name="channel")
    async def exempt_channel(self, ctx, channel: discord.TextChannel):
        config = self._config(ctx.guild.id)
        if channel.id not in config["exempt_channels"]:
            config["exempt_channels"].append(channel.id); set_automod_config(ctx.guild.id, config)
        await ctx.send(f"Automod exemption added for {channel.mention}.")

    @exempt.command(name="unrole")
    async def unexempt_role(self, ctx, role: discord.Role):
        config = self._config(ctx.guild.id)
        config["exempt_roles"] = [x for x in config["exempt_roles"] if int(x) != role.id]
        set_automod_config(ctx.guild.id, config); await ctx.send("Role exemption removed.")

    @exempt.command(name="unchannel")
    async def unexempt_channel(self, ctx, channel: discord.TextChannel):
        config = self._config(ctx.guild.id)
        config["exempt_channels"] = [x for x in config["exempt_channels"] if int(x) != channel.id]
        set_automod_config(ctx.guild.id, config); await ctx.send("Channel exemption removed.")

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You do not have permission to configure automod.", delete_after=8)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument. Use ,help {ctx.command.qualified_name} for help.", delete_after=8)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("I could not understand the argument.", delete_after=8)
        else:
            raise error

async def setup(bot):
    await bot.add_cog(Automod(bot))
