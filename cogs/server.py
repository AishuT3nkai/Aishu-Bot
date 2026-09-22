import discord
from discord import app_commands
from discord.ext import commands
from utils.database import get_guild_config, update_guild_config


class Server(commands.Cog):
    config = app_commands.Group(name="config", description="Configure Aishu community systems")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @config.command(name="channel", description="Set a channel used by a community system")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(system="System to configure", channel="Target channel")
    @app_commands.choices(system=[
        app_commands.Choice(name="Moderation logs", value="modlog"),
        app_commands.Choice(name="Suggestions", value="suggestion"),
        app_commands.Choice(name="Reports", value="report"),
    ])
    async def channel(self, interaction: discord.Interaction, system: app_commands.Choice[str], channel: discord.TextChannel):
        field = {
            "modlog": "modlog_channel_id",
            "suggestion": "suggestion_channel_id",
            "report": "report_channel_id",
        }[system.value]
        update_guild_config(interaction.guild_id, **{field: channel.id})
        await interaction.response.send_message(f"{system.name} channel set to {channel.mention}.", ephemeral=True)

    @config.command(name="autorole", description="Configure the automatic role for new members")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(role="Role to give new members", enabled="Enable or disable autorole")
    async def autorole(self, interaction: discord.Interaction, role: discord.Role, enabled: bool = True):
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message("That role must be below my highest role.", ephemeral=True)
            return
        update_guild_config(
            interaction.guild_id,
            autorole_id=role.id,
            autorole_enabled=1 if enabled else 0,
        )
        await interaction.response.send_message(
            f"Autorole {'enabled' if enabled else 'disabled'}: {role.mention}",
            ephemeral=True,
        )

    @config.command(name="view", description="View current community configuration")
    @app_commands.default_permissions(manage_guild=True)
    async def view(self, interaction: discord.Interaction):
        config = get_guild_config(interaction.guild_id)
        def channel_name(key: str) -> str:
            channel = interaction.guild.get_channel(config.get(key) or 0)
            return channel.mention if channel else "Not set"
        def role_name(key: str) -> str:
            role = interaction.guild.get_role(config.get(key) or 0)
            return role.mention if role else "Not set"

        embed = discord.Embed(title=f"Aishu Configuration — {interaction.guild.name}", color=discord.Color.blurple())
        embed.add_field(name="Welcome", value=f"{'ON' if config.get('welcome_enabled') else 'OFF'} · {channel_name('welcome_channel_id')}", inline=False)
        embed.add_field(name="Goodbye", value=f"{'ON' if config.get('goodbye_enabled') else 'OFF'} · {channel_name('goodbye_channel_id')}", inline=False)
        embed.add_field(name="Verification", value=f"{'ON' if config.get('verification_enabled') else 'OFF'} · min {config.get('min_account_age_days', 7)} days", inline=False)
        embed.add_field(name="Verified role", value=role_name("verification_role_id"), inline=True)
        embed.add_field(name="Unverified role", value=role_name("unverified_role_id"), inline=True)
        embed.add_field(name="Autorole", value=f"{'ON' if config.get('autorole_enabled') else 'OFF'} · {role_name('autorole_id')}", inline=False)
        embed.add_field(name="Moderation logs", value=channel_name("modlog_channel_id"), inline=True)
        embed.add_field(name="Suggestions", value=channel_name("suggestion_channel_id"), inline=True)
        embed.add_field(name="Reports", value=channel_name("report_channel_id"), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="stats", description="Show server statistics")
    async def stats(self, interaction: discord.Interaction):
        guild = interaction.guild
        humans = sum(1 for member in guild.members if not member.bot)
        bots = sum(1 for member in guild.members if member.bot)
        online = sum(1 for member in guild.members if member.status != discord.Status.offline)
        embed = discord.Embed(title=f"Server Stats — {guild.name}", color=discord.Color.blurple())
        embed.add_field(name="Members", value=str(guild.member_count or 0), inline=True)
        embed.add_field(name="Humans", value=str(humans), inline=True)
        embed.add_field(name="Bots", value=str(bots), inline=True)
        embed.add_field(name="Online", value=str(online), inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Boosts", value=str(guild.premium_subscription_count), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="Show Aishu community commands")
    async def help(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Aishu Bot — Community",
            description="Aishu is built for moderation, verification and community management.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Member", value="/introduce\n/profile\n/language\n/avatar\n/userinfo\n/serverinfo\n/stats\n/suggest\n/report\n/verify\n/verificationinfo", inline=False)
        embed.add_field(name="Moderation", value="/warn\n/warnings\n/clearwarnings\n/timeout\n/untimeout\n/kick\n/ban\n/unban\n/purge\n/slowmode\n/lock\n/unlock", inline=False)
        embed.add_field(name="Setup", value="/config ...\n/welcome ...\n/goodbye ...\n/verification ...", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Server(bot))
