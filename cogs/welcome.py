import discord
from discord import app_commands
from discord.ext import commands
from utils.database import get_guild_config, update_guild_config


def render_message(template: str, member: discord.Member) -> str:
    guild = member.guild
    return template.format(
        user=member.mention,
        username=member.display_name,
        server=guild.name,
        member_count=guild.member_count or 0,
    )


class Welcome(commands.Cog):
    welcome = app_commands.Group(name="welcome", description="Configure welcome messages")
    goodbye = app_commands.Group(name="goodbye", description="Configure goodbye messages")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def send_configured(self, member: discord.Member, key_channel: str, key_enabled: str, default_template: str):
        config = get_guild_config(member.guild.id)
        if not config.get(key_enabled):
            return
        channel = member.guild.get_channel(config.get(key_channel) or 0)
        if channel:
            await channel.send(render_message(default_template, member))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = get_guild_config(member.guild.id)
        if config.get("unverified_role_id"):
            role = member.guild.get_role(config["unverified_role_id"])
            if role and role < member.guild.me.top_role:
                try:
                    await member.add_roles(role, reason="Aishu default unverified role")
                except discord.Forbidden:
                    pass

        if config.get("autorole_enabled") and config.get("autorole_id"):
            role = member.guild.get_role(config["autorole_id"])
            if role and role < member.guild.me.top_role:
                try:
                    await member.add_roles(role, reason="Aishu autorole")
                except discord.Forbidden:
                    pass

        if config.get("welcome_enabled"):
            await self.send_configured(
                member, "welcome_channel_id", "welcome_enabled",
                "Welcome {user} to **{server}**! You are member #{member_count}.",
            )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        config = get_guild_config(member.guild.id)
        if config.get("goodbye_enabled"):
            channel = member.guild.get_channel(config.get("goodbye_channel_id") or 0)
            if channel:
                await channel.send(
                    render_message(
                        "Goodbye **{username}**. Thanks for being part of {server}.",
                        member,
                    )
                )

    @welcome.command(name="setup", description="Set the welcome channel and enable welcome messages")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(channel="Channel for welcome messages", enabled="Enable welcome messages")
    async def welcome_setup(self, interaction: discord.Interaction, channel: discord.TextChannel, enabled: bool = True):
        update_guild_config(
            interaction.guild_id,
            welcome_channel_id=channel.id,
            welcome_enabled=1 if enabled else 0,
        )
        await interaction.response.send_message(
            f"Welcome messages {'enabled' if enabled else 'disabled'} in {channel.mention}.",
            ephemeral=True,
        )

    @welcome.command(name="test", description="Send a sample welcome message")
    @app_commands.default_permissions(manage_guild=True)
    async def welcome_test(self, interaction: discord.Interaction):
        config = get_guild_config(interaction.guild_id)
        channel = interaction.guild.get_channel(config.get("welcome_channel_id") or 0)
        if not channel:
            await interaction.response.send_message("Set a welcome channel first with /welcome setup.", ephemeral=True)
            return
        await channel.send(render_message("Welcome {user} to **{server}**! You are member #{member_count}.", interaction.user))
        await interaction.response.send_message("Welcome test sent.", ephemeral=True)

    @goodbye.command(name="setup", description="Set the goodbye channel and enable goodbye messages")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(channel="Channel for goodbye messages", enabled="Enable goodbye messages")
    async def goodbye_setup(self, interaction: discord.Interaction, channel: discord.TextChannel, enabled: bool = True):
        update_guild_config(
            interaction.guild_id,
            goodbye_channel_id=channel.id,
            goodbye_enabled=1 if enabled else 0,
        )
        await interaction.response.send_message(
            f"Goodbye messages {'enabled' if enabled else 'disabled'} in {channel.mention}.",
            ephemeral=True,
        )

    @goodbye.command(name="test", description="Send a sample goodbye message")
    @app_commands.default_permissions(manage_guild=True)
    async def goodbye_test(self, interaction: discord.Interaction):
        config = get_guild_config(interaction.guild_id)
        channel = interaction.guild.get_channel(config.get("goodbye_channel_id") or 0)
        if not channel:
            await interaction.response.send_message("Set a goodbye channel first with /goodbye setup.", ephemeral=True)
            return
        await channel.send(render_message("Goodbye **{username}**. Thanks for being part of {server}.", interaction.user))
        await interaction.response.send_message("Goodbye test sent.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
