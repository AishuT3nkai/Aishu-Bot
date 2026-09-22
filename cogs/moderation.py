import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone, timedelta
from utils.database import (
    add_warning, get_warnings, clear_warnings, get_guild_config
)


async def send_modlog(guild: discord.Guild, title: str, description: str, color: discord.Color):
    config = get_guild_config(guild.id)
    channel = guild.get_channel(config.get("modlog_channel_id") or 0)
    if not isinstance(channel, discord.TextChannel):
        return
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
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

    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(user="Member to warn", reason="Reason for the warning")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
        ok, error = can_act(interaction.user, user)
        if not ok:
            await interaction.response.send_message(error, ephemeral=True)
            return
        warning_id = add_warning(
            interaction.guild_id, user.id, interaction.user.id, reason,
            datetime.now(timezone.utc).isoformat(),
        )
        await send_modlog(
            interaction.guild,
            "Member Warned",
            f"**Member:** {user.mention}\n**Moderator:** {interaction.user.mention}\n**Warning:** #{warning_id}\n**Reason:** {reason}",
            discord.Color.orange(),
        )
        await interaction.response.send_message(f"Warned {user.mention}. Warning #{warning_id}.", ephemeral=True)

    @app_commands.command(name="warnings", description="View a member's warnings")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(user="Member whose warnings you want to view")
    async def warnings(self, interaction: discord.Interaction, user: discord.Member):
        rows = get_warnings(interaction.guild_id, user.id)
        if not rows:
            await interaction.response.send_message(f"{user.mention} has no warnings.", ephemeral=True)
            return
        lines = [
            f"**#{row['id']}** — <@{row['moderator_id']}> — {row['reason']} "
            f"({row['created_at'][:10]})"
            for row in rows[:15]
        ]
        embed = discord.Embed(title=f"Warnings — {user.display_name}", description="\n".join(lines), color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Clear all warnings for a member")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(user="Member whose warnings should be cleared")
    async def clearwarnings(self, interaction: discord.Interaction, user: discord.Member):
        count = clear_warnings(interaction.guild_id, user.id)
        await send_modlog(
            interaction.guild,
            "Warnings Cleared",
            f"**Member:** {user.mention}\n**Moderator:** {interaction.user.mention}\n**Removed:** {count}",
            discord.Color.green(),
        )
        await interaction.response.send_message(f"Cleared {count} warning(s) for {user.mention}.", ephemeral=True)

    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(user="Member to timeout", minutes="Timeout duration in minutes", reason="Reason")
    async def timeout(self, interaction: discord.Interaction, user: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "No reason provided"):
        ok, error = can_act(interaction.user, user)
        if not ok:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await user.timeout(discord.utils.utcnow() + timedelta(minutes=minutes), reason=reason)
        await send_modlog(
            interaction.guild,
            "Member Timed Out",
            f"**Member:** {user.mention}\n**Moderator:** {interaction.user.mention}\n**Duration:** {minutes} minute(s)\n**Reason:** {reason}",
            discord.Color.red(),
        )
        await interaction.response.send_message(f"Timed out {user.mention} for {minutes} minute(s).", ephemeral=True)

    @app_commands.command(name="untimeout", description="Remove a member's timeout")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(user="Member whose timeout should be removed")
    @app_commands.guild_only()
    async def untimeout(self, interaction: discord.Interaction, user: discord.Member):
        ok, error = can_act(interaction.user, user)
        if not ok:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await user.timeout(None, reason=f"Timeout removed by {interaction.user}")
        await interaction.response.send_message(f"Removed timeout from {user.mention}.", ephemeral=True)

    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(user="Member to kick", reason="Reason")
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
        ok, error = can_act(interaction.user, user)
        if not ok:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await user.kick(reason=reason)
        await send_modlog(interaction.guild, "Member Kicked", f"**Member:** {user} ({user.id})\n**Moderator:** {interaction.user.mention}\n**Reason:** {reason}", discord.Color.red())
        await interaction.response.send_message(f"Kicked {user}.", ephemeral=True)

    @app_commands.command(name="ban", description="Ban a member")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(user="Member to ban", reason="Reason")
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
        ok, error = can_act(interaction.user, user)
        if not ok:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await user.ban(reason=reason, delete_message_seconds=0)
        await send_modlog(interaction.guild, "Member Banned", f"**Member:** {user} ({user.id})\n**Moderator:** {interaction.user.mention}\n**Reason:** {reason}", discord.Color.dark_red())
        await interaction.response.send_message(f"Banned {user}.", ephemeral=True)

    @app_commands.command(name="unban", description="Unban a user by Discord ID")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.describe(user_id="Discord user ID", reason="Reason")
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        if not user_id.isdigit():
            await interaction.response.send_message("User ID must contain only numbers.", ephemeral=True)
            return
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=reason)
        except (discord.NotFound, discord.HTTPException):
            await interaction.response.send_message("That user is not banned or could not be unbanned.", ephemeral=True)
            return
        await send_modlog(interaction.guild, "User Unbanned", f"**User:** {user} ({user.id})\n**Moderator:** {interaction.user.mention}\n**Reason:** {reason}", discord.Color.green())
        await interaction.response.send_message(f"Unbanned {user}.", ephemeral=True)

    @app_commands.command(name="purge", description="Delete recent messages from the current channel")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(amount="Number of messages to delete")
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("This command needs a text channel.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await send_modlog(
            interaction.guild,
            "Messages Purged",
            f"**Channel:** {interaction.channel.mention}\n**Moderator:** {interaction.user.mention}\n**Deleted:** {len(deleted)}",
            discord.Color.orange(),
        )
        await interaction.followup.send(f"Deleted {len(deleted)} message(s).", ephemeral=True)

    @app_commands.command(name="slowmode", description="Set the current channel slowmode")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.describe(seconds="Slowmode in seconds, 0 to disable")
    async def slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("This command needs a text channel.", ephemeral=True)
            return
        await interaction.channel.edit(slowmode_delay=seconds)
        await interaction.response.send_message(f"Slowmode set to {seconds} second(s).", ephemeral=True)

    @app_commands.command(name="lock", description="Lock the current channel")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    async def lock(self, interaction: discord.Interaction):
        channel = interaction.channel
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Locked by {interaction.user}")
        await interaction.response.send_message("Channel locked.", ephemeral=False)

    @app_commands.command(name="unlock", description="Unlock the current channel")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_channels=True)
    async def unlock(self, interaction: discord.Interaction):
        channel = interaction.channel
        overwrite = channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Unlocked by {interaction.user}")
        await interaction.response.send_message("Channel unlocked.", ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
