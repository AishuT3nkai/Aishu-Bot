import asyncio
import time
from collections import defaultdict, deque

import discord
from discord.ext import commands

from utils.database import get_antiraid_config, set_antiraid_config, get_guild_config

DEFAULT_CONFIG = {
    "enabled": False,
    "joins": 8,
    "window": 10,
    "lockdown_seconds": 60,
}

class AntiRaid(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._joins: dict[int, deque[float]] = defaultdict(deque)
        self._locked_channels: dict[int, set[int]] = defaultdict(set)
        self._unlock_tasks: dict[int, asyncio.Task] = {}

    def _config(self, guild_id: int) -> dict:
        config = DEFAULT_CONFIG.copy()
        config.update(get_antiraid_config(guild_id))
        return config

    async def _modlog(self, guild: discord.Guild, title: str, description: str):
        config = get_guild_config(guild.id)
        channel = guild.get_channel(config.get("modlog_channel_id") or 0)
        if not isinstance(channel, discord.TextChannel):
            return
        embed = discord.Embed(title=title, description=description, color=discord.Color.red(), timestamp=discord.utils.utcnow())
        try:
            await channel.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _lockdown(self, guild: discord.Guild, reason: str):
        locked = self._locked_channels[guild.id]
        for channel in guild.text_channels:
            overwrite = channel.overwrites_for(guild.default_role)
            if overwrite.send_messages is not None:
                continue
            try:
                overwrite.send_messages = False
                await channel.set_permissions(
                    guild.default_role,
                    overwrite=overwrite,
                    reason=f"Anti-raid lockdown: {reason}",
                )
                locked.add(channel.id)
            except (discord.Forbidden, discord.HTTPException):
                continue

        config = self._config(guild.id)
        await self._modlog(
            guild,
            "Anti-Raid Lockdown",
            f"Join burst detected. Locked {len(locked)} channel(s) for {config['lockdown_seconds']} seconds.\n**Reason:** {reason}",
        )

        old_task = self._unlock_tasks.get(guild.id)
        if old_task and not old_task.done():
            old_task.cancel()
        self._unlock_tasks[guild.id] = asyncio.create_task(self._unlock_later(guild, int(config["lockdown_seconds"])))

    async def _unlock_later(self, guild: discord.Guild, seconds: int):
        await asyncio.sleep(seconds)
        await self._unlock(guild, automatic=True)

    async def _unlock(self, guild: discord.Guild, automatic: bool = False):
        locked = self._locked_channels.get(guild.id, set())
        restored = 0
        for channel_id in list(locked):
            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue
            overwrite = channel.overwrites_for(guild.default_role)
            if overwrite.send_messages is not False:
                continue
            try:
                overwrite.send_messages = None
                await channel.set_permissions(
                    guild.default_role,
                    overwrite=overwrite,
                    reason="Anti-raid lockdown ended",
                )
                restored += 1
            except (discord.Forbidden, discord.HTTPException):
                continue
        locked.clear()
        if not automatic:
            await self._modlog(guild, "Anti-Raid Unlocked", f"Restored {restored} channel(s).")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = self._config(member.guild.id)
        if not config["enabled"] or member.bot:
            return
        now = time.monotonic()
        joins = self._joins[member.guild.id]
        window = int(config["window"])
        while joins and now - joins[0] > window:
            joins.popleft()
        joins.append(now)
        if len(joins) >= int(config["joins"]):
            joins.clear()
            await self._lockdown(member.guild, f"{len(joins)} joins detected within {window} seconds.")

    @commands.group(name="antiraid", invoke_without_command=True)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def antiraid(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            config = self._config(ctx.guild.id)
            embed = discord.Embed(title="Aishu Anti-Raid", color=discord.Color.blurple())
            embed.add_field(name="Enabled", value="Yes" if config["enabled"] else "No", inline=True)
            embed.add_field(name="Threshold", value=f"{config['joins']} joins / {config['window']}s", inline=True)
            embed.add_field(name="Lockdown", value=f"{config['lockdown_seconds']}s", inline=True)
            embed.add_field(name="Active", value="Yes" if self._locked_channels.get(ctx.guild.id) else "No", inline=True)
            await ctx.send(embed=embed)

    @antiraid.command(name="enable")
    async def enable(self, ctx: commands.Context):
        config = self._config(ctx.guild.id)
        config["enabled"] = True
        set_antiraid_config(ctx.guild.id, config)
        await ctx.send("Anti-raid enabled.")

    @antiraid.command(name="disable")
    async def disable(self, ctx: commands.Context):
        config = self._config(ctx.guild.id)
        config["enabled"] = False
        set_antiraid_config(ctx.guild.id, config)
        await ctx.send("Anti-raid disabled.")

    @antiraid.command(name="threshold")
    async def threshold(self, ctx: commands.Context, joins: int, window: int):
        if not 3 <= joins <= 100:
            await ctx.send("Join threshold must be between 3 and 100.")
            return
        if not 3 <= window <= 120:
            await ctx.send("Join window must be between 3 and 120 seconds.")
            return
        config = self._config(ctx.guild.id)
        config["joins"] = joins
        config["window"] = window
        set_antiraid_config(ctx.guild.id, config)
        await ctx.send(f"Anti-raid threshold set to {joins} joins/{window}s.")

    @antiraid.command(name="duration")
    async def duration(self, ctx: commands.Context, seconds: int):
        if not 10 <= seconds <= 3600:
            await ctx.send("Lockdown duration must be between 10 and 3600 seconds.")
            return
        config = self._config(ctx.guild.id)
        config["lockdown_seconds"] = seconds
        set_antiraid_config(ctx.guild.id, config)
        await ctx.send(f"Lockdown duration set to {seconds} seconds.")

    @antiraid.command(name="lock")
    async def lock(self, ctx: commands.Context):
        await self._lockdown(ctx.guild, "Manual moderator lockdown.")

    @antiraid.command(name="unlock")
    async def unlock(self, ctx: commands.Context):
        task = self._unlock_tasks.get(ctx.guild.id)
        if task and not task.done():
            task.cancel()
        await self._unlock(ctx.guild)
        await ctx.send("Anti-raid lockdown released.")

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You do not have permission to configure anti-raid.", delete_after=8)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument. Use ,help {ctx.command.qualified_name} for help.", delete_after=8)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("I could not understand the argument.", delete_after=8)
        else:
            raise error

async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))
