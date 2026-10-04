import discord
from discord import app_commands
from discord.ext import commands

class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Show Aishu's latency")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Pong — {self.bot.latency * 1000:.0f} ms.", ephemeral=True)

    @app_commands.command(name="botinfo", description="Show Aishu runtime information")
    async def botinfo(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Aishu Bot", color=discord.Color.blurple())
        embed.add_field(name="Version", value="Community build", inline=True)
        embed.add_field(name="discord.py", value=discord.__version__, inline=True)
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Latency", value=f"{self.bot.latency * 1000:.0f} ms", inline=True)
        embed.add_field(name="Commands", value=str(len(self.bot.tree.get_commands())), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="membercount", description="Show human, bot and total member counts")
    @app_commands.guild_only()
    async def membercount(self, interaction: discord.Interaction):
        guild = interaction.guild
        humans = sum(not member.bot for member in guild.members)
        bots = sum(member.bot for member in guild.members)
        await interaction.response.send_message(
            f"Humans: {humans}\nBots: {bots}\nTotal: {guild.member_count or 0}"
        )

    @app_commands.command(name="channelinfo", description="Show information about a channel")
    @app_commands.guild_only()
    async def channelinfo(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        channel = channel or interaction.channel
        embed = discord.Embed(title=f"Channel Info — #{channel.name}", color=discord.Color.blurple())
        embed.add_field(name="ID", value=str(channel.id))
        embed.add_field(name="Type", value=str(channel.type))
        embed.add_field(name="Created", value=discord.utils.format_dt(channel.created_at, "F"), inline=False)
        embed.add_field(name="Slowmode", value=f"{channel.slowmode_delay}s", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roleinfo", description="Show information about a role")
    @app_commands.guild_only()
    async def roleinfo(self, interaction: discord.Interaction, role: discord.Role):
        embed = discord.Embed(title=f"Role Info — {role.name}", color=role.color or discord.Color.blurple())
        embed.add_field(name="ID", value=str(role.id), inline=True)
        embed.add_field(name="Position", value=str(role.position), inline=True)
        embed.add_field(name="Members", value=str(len(role.members)), inline=True)
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True)
        embed.add_field(name="Managed", value="Yes" if role.managed else "No", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="permissions", description="Show your effective server permissions")
    @app_commands.guild_only()
    async def permissions(self, interaction: discord.Interaction, member: discord.Member | None = None):
        member = member or interaction.user
        perms = member.guild_permissions
        important = [
            "administrator", "manage_guild", "manage_channels", "manage_roles",
            "manage_messages", "moderate_members", "kick_members", "ban_members",
            "mention_everyone", "manage_webhooks"
        ]
        lines = [f"{name.replace('_', ' ').title()}: {'Yes' if getattr(perms, name) else 'No'}" for name in important]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Utility(bot))
