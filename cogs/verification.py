import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from utils.database import get_guild_config, update_guild_config, get_introduction


async def run_verification(member: discord.Member, guild: discord.Guild) -> tuple[bool, str]:
    config = get_guild_config(guild.id)
    if not config.get("verification_enabled"):
        return True, "Verification is currently disabled."

    minimum_days = max(0, int(config.get("min_account_age_days") or 0))
    account_age_days = (datetime.now(timezone.utc) - member.created_at).days

    if account_age_days < minimum_days:
        return False, f"Your Discord account is {account_age_days} day(s) old. Minimum required: {minimum_days} day(s)."

    role_id = config.get("verification_role_id")
    role = guild.get_role(role_id or 0)
    if role is None:
        return False, "Verification is not configured correctly: verification role is missing."

    if role >= guild.me.top_role:
        return False, "I cannot assign the verification role because it is above my highest role."

    try:
        await member.add_roles(role, reason="Aishu verification")
        unverified = guild.get_role(config.get("unverified_role_id") or 0)
        if unverified and unverified in member.roles and unverified < guild.me.top_role:
            await member.remove_roles(unverified, reason="Aishu verification")
    except discord.Forbidden:
        return False, "I do not have permission to update your roles."

    return True, "Verification successful. You now have access to the community."


class VerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.success, emoji="✅", custom_id="aishu:verify")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("This button only works inside a server.", ephemeral=True)
            return

        passed, message = await run_verification(interaction.user, interaction.guild)
        await interaction.response.send_message(message, ephemeral=True)


class Verification(commands.Cog):
    verification = app_commands.Group(
        name="verification",
        description="Configure the Aishu account verification system",
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @verification.command(name="setup", description="Configure verification roles and minimum account age")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        verified_role="Role given after successful verification",
        unverified_role="Role removed after successful verification; optional",
        minimum_account_age_days="Minimum Discord account age in days",
        enabled="Enable or disable verification",
    )
    async def setup(
        self,
        interaction: discord.Interaction,
        verified_role: discord.Role,
        unverified_role: discord.Role | None = None,
        minimum_account_age_days: app_commands.Range[int, 0, 3650] = 7,
        enabled: bool = True,
    ):
        if verified_role >= interaction.guild.me.top_role:
            await interaction.response.send_message("The verified role must be below my highest role.", ephemeral=True)
            return
        if unverified_role and unverified_role >= interaction.guild.me.top_role:
            await interaction.response.send_message("The unverified role must be below my highest role.", ephemeral=True)
            return

        update_guild_config(
            interaction.guild_id,
            verification_role_id=verified_role.id,
            unverified_role_id=unverified_role.id if unverified_role else None,
            min_account_age_days=int(minimum_account_age_days),
            verification_enabled=1 if enabled else 0,
        )
        await interaction.response.send_message(
            f"Verification {'enabled' if enabled else 'disabled'}. Minimum account age: {minimum_account_age_days} day(s).",
            ephemeral=True,
        )

    @verification.command(name="panel", description="Post the verification panel in this channel")
    @app_commands.default_permissions(manage_guild=True)
    async def panel(self, interaction: discord.Interaction):
        config = get_guild_config(interaction.guild_id)
        if not config.get("verification_role_id"):
            await interaction.response.send_message("Run /verification setup first.", ephemeral=True)
            return
        update_guild_config(interaction.guild_id, verification_channel_id=interaction.channel_id)
        embed = discord.Embed(
            title="Aishu Verification",
            description=(
                "Click **Verify** to verify your Discord account.\n\n"
                "The system checks only useful Discord account information such as account age "
                "and server membership. It does not request private information."
            ),
            color=discord.Color.green(),
        )
        embed.add_field(name="Account check", value="Account creation date\nServer join date\nAccount age\nBot status", inline=False)
        await interaction.response.send_message(embed=embed, view=VerificationView())

    @verification.command(name="status", description="View verification settings")
    @app_commands.default_permissions(manage_guild=True)
    async def status(self, interaction: discord.Interaction):
        config = get_guild_config(interaction.guild_id)
        verified = interaction.guild.get_role(config.get("verification_role_id") or 0)
        unverified = interaction.guild.get_role(config.get("unverified_role_id") or 0)
        channel = interaction.guild.get_channel(config.get("verification_channel_id") or 0)
        embed = discord.Embed(title="Verification Status", color=discord.Color.blurple())
        embed.add_field(name="Enabled", value="Yes" if config.get("verification_enabled") else "No", inline=True)
        embed.add_field(name="Minimum account age", value=f"{config.get('min_account_age_days', 7)} day(s)", inline=True)
        embed.add_field(name="Verified role", value=verified.mention if verified else "Not set", inline=False)
        embed.add_field(name="Unverified role", value=unverified.mention if unverified else "Not set", inline=False)
        embed.add_field(name="Panel channel", value=channel.mention if channel else "Not set", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="verify", description="Run verification for yourself")
    async def verify(self, interaction: discord.Interaction):
        if not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
            return
        passed, message = await run_verification(interaction.user, interaction.guild)
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="verificationinfo", description="View public verification information about a member")
    @app_commands.describe(user="Member to inspect")
    async def verificationinfo(self, interaction: discord.Interaction, user: discord.Member | None = None):
        user = user or interaction.user
        account_age_days = max(0, (datetime.now(timezone.utc) - user.created_at).days)
        joined = discord.utils.format_dt(user.joined_at, "F") if user.joined_at else "Unknown"
        intro = get_introduction(interaction.guild_id, user.id)

        embed = discord.Embed(title=f"Verification Info — {user.display_name}", color=discord.Color.blurple())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Account created", value=f"{discord.utils.format_dt(user.created_at, 'F')}\n{account_age_days} day(s) old", inline=False)
        embed.add_field(name="Joined server", value=joined, inline=False)
        embed.add_field(name="Bot", value="Yes" if user.bot else "No", inline=True)
        embed.add_field(name="User ID", value=str(user.id), inline=True)
        if intro:
            embed.add_field(name="Self-declared origin", value=intro["origin"], inline=True)
            embed.add_field(name="Self-declared city", value=intro["city"], inline=True)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    bot.add_view(VerificationView())
    await bot.add_cog(Verification(bot))
