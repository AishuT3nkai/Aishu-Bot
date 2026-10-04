import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
from utils.database import add_warning, get_warnings, clear_warnings, get_guild_config, create_case, get_case, get_member_cases

async def send_modlog(guild: discord.Guild, title: str, description: str, color: discord.Color):
    config = get_guild_config(guild.id)
    channel = guild.get_channel(config.get("modlog_channel_id") or 0)
    if not isinstance(channel, discord.TextChannel):
        return
    embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(timezone.utc))
    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass

def can_act(moderator: discord.Member, target: discord.Member) -> tuple[bool, str]:
    if moderator.id == target.id:
        return False, "You cannot use moderation actions on yourself."
    if target == moderator.guild.owner:
        return False, "You cannot moderate the server owner."
    if target.top_role >= moderator.top_role and moderator != moderator.guild.owner:
        return False, "That member has an equal or higher role than you."
    bot_member = moderator.guild.me
    if bot_member is None:
        return False, "I am not ready to manage members in this server yet."
    if target.top_role >= bot_member.top_role:
        return False, "That member is at or above my highest role."
    return True, ""

class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx: commands.Context, user: discord.Member, *, reason: str = "No reason provided"):
        ok, error = can_act(ctx.author, user)
        if not ok:
            await ctx.send(error, delete_after=8); return
        warning_id = add_warning(ctx.guild.id, user.id, ctx.author.id, reason, datetime.now(timezone.utc).isoformat())
        case_id = create_case(ctx.guild.id, "warn", user.id, ctx.author.id, reason, datetime.now(timezone.utc).isoformat(), metadata={"warning_id": warning_id})
        await send_modlog(ctx.guild, "Member Warned", f"**Member:** {user.mention}\n**Moderator:** {ctx.author.mention}\n**Warning:** #{warning_id}\n**Case:** #{case_id}\n**Reason:** {reason}", discord.Color.orange())
        await ctx.send(f"Warned {user.mention}. Warning #{warning_id} | Case #{case_id}.", delete_after=10)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def warnings(self, ctx: commands.Context, user: discord.Member):
        rows = get_warnings(ctx.guild.id, user.id)
        if not rows:
            await ctx.send(f"{user.mention} has no warnings.", delete_after=8); return
        lines = [f"**#{row['id']}** — <@{row['moderator_id']}> — {row['reason']} ({row['created_at'][:10]})" for row in rows[:15]]
        await ctx.send(embed=discord.Embed(title=f"Warnings — {user.display_name}", description="\n".join(lines), color=discord.Color.orange()))

    @commands.command(name="clearwarnings")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def clearwarnings(self, ctx: commands.Context, user: discord.Member):
        count = clear_warnings(ctx.guild.id, user.id)
        await send_modlog(ctx.guild, "Warnings Cleared", f"**Member:** {user.mention}\n**Moderator:** {ctx.author.mention}\n**Removed:** {count}", discord.Color.green())
        await ctx.send(f"Cleared {count} warning(s) for {user.mention}.", delete_after=10)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx: commands.Context, user: discord.Member, minutes: int, *, reason: str = "No reason provided"):
        if not 1 <= minutes <= 40320:
            await ctx.send("Timeout must be between 1 and 40320 minutes.", delete_after=8); return
        ok, error = can_act(ctx.author, user)
        if not ok:
            await ctx.send(error, delete_after=8); return
        try:
            await user.timeout(discord.utils.utcnow() + timedelta(minutes=minutes), reason=reason)
        except (discord.Forbidden, discord.HTTPException) as error:
            await ctx.send(f"I could not timeout that member: {error}", delete_after=8); return
        case_id = create_case(ctx.guild.id, "timeout", user.id, ctx.author.id, reason, datetime.now(timezone.utc).isoformat(), duration=minutes)\n        await send_modlog(ctx.guild, "Member Timed Out", f"**Member:** {user.mention}\\n**Moderator:** {ctx.author.mention}\\n**Duration:** {minutes} minute(s)\\n**Case:** #{case_id}\\n**Reason:** {reason}", discord.Color.red())
        await ctx.send(f"Timed out {user.mention} for {minutes} minute(s) | Case #{case_id}.", delete_after=10)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def untimeout(self, ctx: commands.Context, user: discord.Member):
        ok, error = can_act(ctx.author, user)
        if not ok:
            await ctx.send(error, delete_after=8); return
        try:
            await user.timeout(None, reason=f"Timeout removed by {ctx.author}")
        except (discord.Forbidden, discord.HTTPException) as error:
            await ctx.send(f"I could not remove that timeout: {error}", delete_after=8); return
        case_id = create_case(ctx.guild.id, "untimeout", user.id, ctx.author.id, "Timeout removed", datetime.now(timezone.utc).isoformat())
        await send_modlog(ctx.guild, "Timeout Removed", f"**Member:** {user.mention}\n**Moderator:** {ctx.author.mention}\n**Case:** #{case_id}", discord.Color.green())
        await ctx.send(f"Removed timeout from {user.mention}. Case #{case_id}.", delete_after=10)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, user: discord.Member, *, reason: str = "No reason provided"):
        ok, error = can_act(ctx.author, user)
        if not ok:
            await ctx.send(error, delete_after=8); return
        try:
            await user.kick(reason=reason)
        except (discord.Forbidden, discord.HTTPException) as error:
            await ctx.send(f"I could not kick that member: {error}", delete_after=8); return
        case_id = create_case(ctx.guild.id, "kick", user.id, ctx.author.id, reason, datetime.now(timezone.utc).isoformat())\n        await send_modlog(ctx.guild, "Member Kicked", f"**Member:** {user} ({user.id})\\n**Moderator:** {ctx.author.mention}\\n**Case:** #{case_id}\\n**Reason:** {reason}", discord.Color.red())
        await ctx.send(f"Kicked {user}. Case #{case_id}.", delete_after=10)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, user: discord.Member, *, reason: str = "No reason provided"):
        ok, error = can_act(ctx.author, user)
        if not ok:
            await ctx.send(error, delete_after=8); return
        try:
            await user.ban(reason=reason, delete_message_seconds=0)
        except (discord.Forbidden, discord.HTTPException) as error:
            await ctx.send(f"I could not ban that member: {error}", delete_after=8); return
        case_id = create_case(ctx.guild.id, "ban", user.id, ctx.author.id, reason, datetime.now(timezone.utc).isoformat())\n        await send_modlog(ctx.guild, "Member Banned", f"**Member:** {user} ({user.id})\\n**Moderator:** {ctx.author.mention}\\n**Case:** #{case_id}\\n**Reason:** {reason}", discord.Color.dark_red())
        await ctx.send(f"Banned {user}. Case #{case_id}.", delete_after=10)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: str, *, reason: str = "No reason provided"):
        if not user_id.isdigit():
            await ctx.send("User ID must contain only numbers.", delete_after=8); return
        try:
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user, reason=reason)
        except (discord.NotFound, discord.HTTPException):
            await ctx.send("That user is not banned or could not be unbanned.", delete_after=8); return
        case_id = create_case(ctx.guild.id, "unban", user.id, ctx.author.id, reason, datetime.now(timezone.utc).isoformat())\n        await send_modlog(ctx.guild, "User Unbanned", f"**User:** {user} ({user.id})\\n**Moderator:** {ctx.author.mention}\\n**Case:** #{case_id}\\n**Reason:** {reason}", discord.Color.green())
        await ctx.send(f"Unbanned {user}. Case #{case_id}.", delete_after=10)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int):
        if not 1 <= amount <= 100:
            await ctx.send("Purge amount must be between 1 and 100.", delete_after=8); return
        if not isinstance(ctx.channel, discord.TextChannel):
            return
        deleted = await ctx.channel.purge(limit=amount + 1)
        count = max(0, len(deleted) - 1)
        case_id = create_case(ctx.guild.id, "purge", None, ctx.author.id, f"Purged {count} messages in #{ctx.channel.name}", datetime.now(timezone.utc).isoformat(), metadata={"channel_id": ctx.channel.id, "count": count})\n        await send_modlog(ctx.guild, "Messages Purged", f"**Channel:** {ctx.channel.mention}\\n**Moderator:** {ctx.author.mention}\\n**Deleted:** {count}\\n**Case:** #{case_id}", discord.Color.orange())
        await ctx.send(f"Deleted {count} message(s). Case #{case_id}.", delete_after=5)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: int):
        if not 0 <= seconds <= 21600:
            await ctx.send("Slowmode must be between 0 and 21600 seconds.", delete_after=8); return
        if isinstance(ctx.channel, discord.TextChannel):
            await ctx.channel.edit(slowmode_delay=seconds)
        case_id = create_case(ctx.guild.id, "slowmode", None, ctx.author.id, f"Slowmode set to {seconds}s", datetime.now(timezone.utc).isoformat(), metadata={"channel_id": ctx.channel.id, "seconds": seconds})
        await ctx.send(f"Slowmode set to {seconds} second(s). Case #{case_id}.", delete_after=8)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Locked by {ctx.author}")
        case_id = create_case(ctx.guild.id, "lock", None, ctx.author.id, "Channel locked", datetime.now(timezone.utc).isoformat(), metadata={"channel_id": ctx.channel.id})
        await ctx.send(f"Channel locked. Case #{case_id}.")

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Unlocked by {ctx.author}")
        case_id = create_case(ctx.guild.id, "unlock", None, ctx.author.id, "Channel unlocked", datetime.now(timezone.utc).isoformat(), metadata={"channel_id": ctx.channel.id})
        await ctx.send(f"Channel unlocked. Case #{case_id}.")



    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(view_audit_log=True)
    async def case(self, ctx: commands.Context, case_id: int):
        row = get_case(ctx.guild.id, case_id)
        if not row:
            await ctx.send("Case not found.", delete_after=8)
            return
        embed = discord.Embed(title=f"Moderation Case #{case_id}", color=discord.Color.blurple())
        embed.add_field(name="Action", value=row["action"])
        embed.add_field(name="Target", value=f"<@{row['target_id']}>" if row["target_id"] else "Server/channel")
        embed.add_field(name="Moderator", value=f"<@{row['moderator_id']}>")
        embed.add_field(name="Reason", value=row["reason"][:1024], inline=False)
        embed.add_field(name="Created", value=row["created_at"][:19])
        if row["duration"] is not None:
            embed.add_field(name="Duration", value=f"{row['duration']} minute(s)")
        await ctx.send(embed=embed)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(view_audit_log=True)
    async def history(self, ctx: commands.Context, user: discord.Member):
        rows = get_member_cases(ctx.guild.id, user.id)
        if not rows:
            await ctx.send(f"No moderation cases found for {user.mention}.")
            return
        lines = [
            f"Case #{row['case_id']} — {row['action']} — <@{row['moderator_id']}> — {row['created_at'][:10]}"
            for row in rows
        ]
        await ctx.send(embed=discord.Embed(title=f"Moderation History — {user.display_name}", description="\n".join(lines)))

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You do not have permission to use this moderation command.", delete_after=8)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument. Use ,help {ctx.command.qualified_name} for help.", delete_after=8)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("I could not understand one of the arguments.", delete_after=8)
        else:
            raise error

async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
