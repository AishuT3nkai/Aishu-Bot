import discord
from discord import app_commands
from discord.ext import commands
from utils.database import (
    get_introduction, add_suggestion, add_report, get_guild_config,
    get_language, set_language, save_introduction,
)
from utils.language import LANGUAGES, TEXT, interaction_language
from datetime import datetime, timezone


class IntroductionModal(discord.ui.Modal):
    def __init__(self, language: str):
        t = TEXT[language]
        super().__init__(title=t["profile"][:45])
        self.language = language
        self.name = discord.ui.TextInput(label=t["name"], placeholder="Your name", max_length=100)
        self.birthdate = discord.ui.TextInput(label=t["birthdate"], placeholder="21 June 2011", max_length=50)
        self.age = discord.ui.TextInput(label=t["age"], placeholder="15", max_length=3)
        self.origin = discord.ui.TextInput(label=t["origin"], placeholder="Indonesia", max_length=100)
        self.city = discord.ui.TextInput(label=t["city"], placeholder="Your city", max_length=100)
        for item in (self.name, self.birthdate, self.age, self.origin, self.city):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        values = {
            "name": self.name.value.strip(),
            "birthdate": self.birthdate.value.strip(),
            "age": self.age.value.strip(),
            "origin": self.origin.value.strip(),
            "city": self.city.value.strip(),
        }
        save_introduction(interaction.guild_id, interaction.user.id, values)
        t = TEXT[self.language]
        embed = discord.Embed(
            title=t["profile"].format(user=interaction.user.display_name),
            color=discord.Color.blurple(),
        )
        for key in ("name", "birthdate", "age", "origin", "city"):
            embed.add_field(name=t[key], value=values[key] or "-", inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(content=t["saved"], embed=embed)


class SuggestionModal(discord.ui.Modal, title="Community Suggestion"):
    content = discord.ui.TextInput(
        label="Suggestion",
        placeholder="Tell the community team what you want to improve.",
        style=discord.TextStyle.paragraph,
        max_length=1500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        suggestion_id = add_suggestion(
            interaction.guild_id,
            interaction.user.id,
            self.content.value.strip(),
            datetime.now(timezone.utc).isoformat(),
        )
        config = get_guild_config(interaction.guild_id)
        channel = interaction.guild.get_channel(config.get("suggestion_channel_id") or 0)
        if channel:
            embed = discord.Embed(title=f"Suggestion #{suggestion_id}", description=self.content.value, color=discord.Color.blurple())
            embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
            embed.set_footer(text=f"Submitted by {interaction.user.id}")
            try:
                await channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass
        await interaction.response.send_message(f"Suggestion #{suggestion_id} submitted.", ephemeral=True)


class ReportModal(discord.ui.Modal, title="Community Report"):
    def __init__(self, target_id: int | None):
        super().__init__(title="Community Report")
        self.target_id = target_id
        self.content = discord.ui.TextInput(
            label="Report details",
            placeholder="Describe the problem without sharing private information.",
            style=discord.TextStyle.paragraph,
            max_length=1500,
        )
        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction):
        report_id = add_report(
            interaction.guild_id,
            interaction.user.id,
            self.target_id,
            self.content.value.strip(),
            datetime.now(timezone.utc).isoformat(),
        )
        config = get_guild_config(interaction.guild_id)
        channel = interaction.guild.get_channel(config.get("report_channel_id") or 0)
        if channel:
            embed = discord.Embed(title=f"Report #{report_id}", description=self.content.value, color=discord.Color.orange())
            embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
            embed.set_footer(text=f"Reporter ID: {interaction.user.id}")
            try:
                await channel.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException):
                pass
        await interaction.response.send_message(f"Report #{report_id} submitted privately.", ephemeral=True)


class Community(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="language", description="Set your personal bot language")
    @app_commands.choices(language=[
        app_commands.Choice(name="Indonesia", value="id"),
        app_commands.Choice(name="Tagalog", value="tl"),
        app_commands.Choice(name="English", value="en"),
    ])
    async def language(self, interaction: discord.Interaction, language: app_commands.Choice[str]):
        if interaction.guild_id is None:
            await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
            return
        set_language(interaction.guild_id, interaction.user.id, language.value)
        await interaction.response.send_message(
            TEXT[language.value]["language_changed"].format(language=LANGUAGES[language.value]),
            ephemeral=True,
        )

    @app_commands.command(name="introduce", description="Create or update your community introduction")
    @app_commands.guild_only()
    async def introduce(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            await interaction.response.send_message("Use this command inside a server.", ephemeral=True)
            return
        await interaction.response.send_modal(IntroductionModal(interaction_language(interaction)))

    @app_commands.command(name="profile", description="View a member's introduction")
    @app_commands.describe(user="Member to inspect")
    @app_commands.guild_only()
    async def profile(self, interaction: discord.Interaction, user: discord.Member | None = None):
        user = user or interaction.user
        language = interaction_language(interaction)
        t = TEXT[language]
        row = get_introduction(interaction.guild_id, user.id)
        if not row:
            await interaction.response.send_message(t["no_profile"], ephemeral=True)
            return
        embed = discord.Embed(title=t["profile"].format(user=user.display_name), color=discord.Color.blurple())
        embed.set_thumbnail(url=user.display_avatar.url)
        for key in ("name", "birthdate", "age", "origin", "city"):
            embed.add_field(name=t[key], value=row[key], inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="View a member's avatar")
    @app_commands.describe(user="Member whose avatar you want to view")
    @app_commands.guild_only()
    async def avatar(self, interaction: discord.Interaction, user: discord.User | None = None):
        user = user or interaction.user
        embed = discord.Embed(title=f"{user.display_name}'s Avatar", color=discord.Color.blurple())
        embed.set_image(url=user.display_avatar.replace(size=1024).url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="View useful public Discord account information")
    @app_commands.describe(user="Member to inspect")
    @app_commands.guild_only()
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member | None = None):
        user = user or interaction.user
        embed = discord.Embed(title=f"User Info — {user.display_name}", color=discord.Color.blurple())
        embed.set_thumbnail(url=user.display_avatar.url)
        created = discord.utils.format_dt(user.created_at, "F")
        joined = discord.utils.format_dt(user.joined_at, "F") if isinstance(user, discord.Member) and user.joined_at else "Unknown"
        embed.add_field(name="Account created", value=f"{created}\n{discord.utils.format_dt(user.created_at, 'R')}", inline=False)
        embed.add_field(name="Joined server", value=joined, inline=False)
        embed.add_field(name="Bot", value="Yes" if user.bot else "No", inline=True)
        embed.add_field(name="User ID", value=str(user.id), inline=True)
        if isinstance(user, discord.Member):
            roles = [role.mention for role in user.roles[1:]]
            embed.add_field(name="Roles", value=", ".join(roles[-10:]) or "None", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="View server information")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner", value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Boosts", value=str(guild.premium_subscription_count), inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, "F"), inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="suggest", description="Submit a community suggestion")
    @app_commands.guild_only()
    async def suggest(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SuggestionModal())

    @app_commands.command(name="report", description="Submit a private community report")
    @app_commands.describe(user="Optional member this report concerns")
    @app_commands.guild_only()
    async def report(self, interaction: discord.Interaction, user: discord.Member | None = None):
        await interaction.response.send_modal(ReportModal(user.id if user else None))


async def setup(bot: commands.Bot):
    await bot.add_cog(Community(bot))
