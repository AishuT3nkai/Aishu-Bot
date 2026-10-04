import asyncio
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import discord
from discord.ext import commands

from utils.database import create_case, get_antiraid_config, get_guild_config, set_antiraid_config

DEFAULT_CONFIG = {
    "enabled": False,
    "joins": 8,
    "window": 10,
    "lockdown_seconds": 60,
    "new_account_days": 3,
    "bot_join_threshold": 2,
    "whitelist_users": [],
}

class AntiRaid(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._joins = defaultdict(deque)
        self._bots = defaultdict(deque)
        self._locked_channels = defaultdict(dict)
        self._unlock_tasks = {}

    def _config(self, guild_id):
        config = DEFAULT_CONFIG.copy()
        config.update(get_antiraid_config(guild_id))
        config["whitelist_users"] = list(config.get("whitelist_users") or [])
        return config

    async def _modlog(self, guild, title, description):
        config = get_guild_config(guild.id)
        channel = guild.get_channel(config.get("modlog_channel_id") or 0)
        if not isinstance(channel, discord.TextChannel):
            return
        try:
            await channel.send(
                embed=discord.Embed(title=title, description=description, color=discord.Color.red(), timestamp=discord.utils.utcnow()),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _snapshot_before_lockdown(self, guild):
        cog = self.bot.get_cog("ServerBackup")
        if cog is not None and hasattr(cog, "_snapshot"):
            try:
                return await cog._snapshot(guild, "pre-lockdown raid snapshot")
            except Exception as error:
                print(f"[antiraid] backup failed for {guild.id}: {error!r}")
        return None

    async def _lockdown(self, guild, reason):
        await self._snapshot_before_lockdown(guild)
        locked = self._locked_channels[guild.id]
        for channel in guild.text_channels:
            if channel.id in locked:
                continue
            overwrite = channel.overwrites_for(guild.default_role)
            if overwrite.send_messages is False:
                continue
            previous = overwrite.send_messages
            overwrite.send_messages = False
            try:
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=f"Anti-raid lockdown: {reason}")
                locked[channel.id] = previous
            except (discord.Forbidden, discord.HTTPException):
                continue

        config = self._config(guild.id)
        case_id = create_case(
            guild.id, "raid_lockdown", None, self.bot.user.id if self.bot.user else 0,
            reason, discord.utils.utcnow().isoformat(),
            duration=int(config["lockdown_seconds"]),
        )
        await self._modlog(
            guild, "Anti-Raid Lockdown",
            f"Locked {len(locked)} channel(s) for {config['lockdown_seconds']} seconds.\nReason: {reason}\nCase: #{case_id}",
        )
        old_task = self._unlock_tasks.get(guild.id)
        if old_task and not old_task.done():
            old_task.cancel()
        self._unlock_tasks[guild.id] = asyncio.create_task(
            self._unlock_later(guild, int(config["lockdown_seconds"]))
        )

    async def _unlock_later(self, guild, seconds):
        try:
            await asyncio.sleep(seconds)
            await self._unlock(guild, automatic=True)
        except asyncio.CancelledError:
            pass

    async def _unlock(self, guild, automatic=False):
        locked = self._locked_channels.get(guild.id, {})
        restored = 0
        for channel_id, previous in list(locked.items()):
            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                locked.pop(channel_id, None)
                continue
            overwrite = channel.overwrites_for(guild.default_role)
            if overwrite.send_messages is not False:
                # Someone already changed the lockdown override; do not overwrite their change.
                locked.pop(channel_id, None)
                continue
            overwrite.send_messages = previous
            try:
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Anti-raid lockdown ended")
                restored += 1
                locked.pop(channel_id, None)
            except (discord.Forbidden, discord.HTTPException):
                # Keep failed entries so a moderator can retry unlocking them.
                continue
        if not automatic:
            await self._modlog(guild, "Anti-Raid Unlocked", f"Restored {restored} channel(s).")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        config = self._config(member.guild.id)
        if not config["enabled"] or member.id in {int(x) for x in config["whitelist_users"]}:
            return

        now = time.monotonic()
        guild_id = member.guild.id
        joins = self._joins[guild_id]
        window = int(config["window"])
        while joins and now - joins[0] > window:
            joins.popleft()
        joins.append(now)

        account_age = (datetime.now(timezone.utc) - member.created_at).total_seconds() / 86400
        suspicious = account_age < int(config["new_account_days"])

        if member.bot:
            bots = self._bots[guild_id]
            while bots and now - bots[0] > window:
                bots.popleft()
            bots.append(now)
            if len(bots) >= int(config["bot_join_threshold"]):
                await self._lockdown(member.guild, f"{len(bots)} bot joins detected within {window} seconds.")
                bots.clear()
                return

        if len(joins) >= int(config["joins"]):
            count = len(joins)
            joins.clear()
            reason = f"{count} joins detected within {window} seconds"
            if suspicious:
                reason += "; latest account is unusually new"
            await self._lockdown(member.guild, reason)

    @commands.group(name="antiraid", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def antiraid(self, ctx):
        if ctx.invoked_subcommand is None:
            config = self._config(ctx.guild.id)
            embed = discord.Embed(title="Aishu Anti-Raid", color=discord.Color.blurple())
            embed.add_field(name="Enabled", value="Yes" if config["enabled"] else "No")
            embed.add_field(name="Threshold", value=f"{config['joins']} joins / {config['window']}s")
            embed.add_field(name="Lockdown", value=f"{config['lockdown_seconds']}s")
            embed.add_field(name="New account threshold", value=f"{config['new_account_days']} days")
            embed.add_field(name="Bot threshold", value=f"{config['bot_join_threshold']} / window")
            embed.add_field(name="Active", value="Yes" if self._locked_channels.get(ctx.guild.id) else "No")
            await ctx.send(embed=embed)

    @antiraid.command(name="enable")
    async def enable(self, ctx):
        config = self._config(ctx.guild.id); config["enabled"] = True
        set_antiraid_config(ctx.guild.id, config); await ctx.send("Anti-raid enabled.")

    @antiraid.command(name="disable")
    async def disable(self, ctx):
        config = self._config(ctx.guild.id); config["enabled"] = False
        set_antiraid_config(ctx.guild.id, config); await ctx.send("Anti-raid disabled.")

    @antiraid.command(name="threshold")
    async def threshold(self, ctx, joins: int, window: int):
        if not 3 <= joins <= 100 or not 3 <= window <= 120:
            await ctx.send("Usage: ,antiraid threshold <joins 3-100> <seconds 3-120>"); return
        config = self._config(ctx.guild.id); config["joins"] = joins; config["window"] = window
        set_antiraid_config(ctx.guild.id, config); await ctx.send(f"Threshold set to {joins} joins/{window}s.")

    @antiraid.command(name="duration")
    async def duration(self, ctx, seconds: int):
        if not 10 <= seconds <= 3600:
            await ctx.send("Duration must be between 10 and 3600 seconds."); return
        config = self._config(ctx.guild.id); config["lockdown_seconds"] = seconds
        set_antiraid_config(ctx.guild.id, config); await ctx.send(f"Lockdown duration set to {seconds}s.")

    @antiraid.command(name="newaccount")
    async def newaccount(self, ctx, days: int):
        if not 0 <= days <= 30:
            await ctx.send("New-account threshold must be 0-30 days."); return
        config = self._config(ctx.guild.id); config["new_account_days"] = days
        set_antiraid_config(ctx.guild.id, config); await ctx.send(f"Suspicious-account threshold set to {days} days.")

    @antiraid.command(name="bots")
    async def bots(self, ctx, threshold: int):
        if not 1 <= threshold <= 20:
            await ctx.send("Bot threshold must be 1-20."); return
        config = self._config(ctx.guild.id); config["bot_join_threshold"] = threshold
        set_antiraid_config(ctx.guild.id, config); await ctx.send(f"Bot join threshold set to {threshold}.")

    @antiraid.group(name="whitelist", invoke_without_command=True)
    async def whitelist(self, ctx):
        config = self._config(ctx.guild.id)
        await ctx.send(f"Whitelisted users: {len(config['whitelist_users'])}")

    @whitelist.command(name="add")
    async def whitelist_add(self, ctx, user: discord.Member):
        config = self._config(ctx.guild.id)
        if user.id not in config["whitelist_users"]:
            config["whitelist_users"].append(user.id)
            set_antiraid_config(ctx.guild.id, config)
        await ctx.send(f"Added {user} to the anti-raid whitelist.")

    @whitelist.command(name="remove")
    async def whitelist_remove(self, ctx, user: discord.Member):
        config = self._config(ctx.guild.id)
        config["whitelist_users"] = [x for x in config["whitelist_users"] if int(x) != user.id]
        set_antiraid_config(ctx.guild.id, config); await ctx.send(f"Removed {user} from the anti-raid whitelist.")

    @antiraid.command(name="lock")
    async def lock(self, ctx):
        await self._lockdown(ctx.guild, "Manual moderator lockdown.")

    @antiraid.command(name="unlock")
    async def unlock(self, ctx):
        task = self._unlock_tasks.get(ctx.guild.id)
        if task and not task.done():
            task.cancel()
        await self._unlock(ctx.guild)
        await ctx.send("Anti-raid lockdown released.")

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You do not have permission to configure anti-raid.", delete_after=8)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument. Use ,help {ctx.command.qualified_name} for help.", delete_after=8)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("I could not understand the argument.", delete_after=8)
        else:
            raise error

async def setup(bot):
    await bot.add_cog(AntiRaid(bot))
