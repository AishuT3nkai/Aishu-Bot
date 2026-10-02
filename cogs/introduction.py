import os
import sqlite3
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

DB_PATH = os.getenv("AISHU_INTRO_DB", "data/introductions.db")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


def db_connect():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS introductions (
            guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            name TEXT NOT NULL, age INTEGER NOT NULL,
            birth_month INTEGER NOT NULL, birth_day INTEGER NOT NULL,
            city TEXT NOT NULL, country TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        )
    """)
    return conn


class IntroductionModal(discord.ui.Modal, title="Member Introduction"):
    name = discord.ui.TextInput(label="Name", placeholder="What should people call you?", min_length=1, max_length=50)
    age = discord.ui.TextInput(label="Age", placeholder="Your current age", min_length=1, max_length=3)
    birthday = discord.ui.TextInput(label="Birthday", placeholder="MM/DD (example: 06/21)", min_length=5, max_length=5)
    city = discord.ui.TextInput(label="City", placeholder="Your city", min_length=1, max_length=60)
    country = discord.ui.TextInput(label="Country", placeholder="Your country", min_length=1, max_length=60)

    def __init__(self, cog, interaction):
        super().__init__()
        self.cog = cog
        self.guild_id = interaction.guild_id
        self.user_id = interaction.user.id

    async def on_submit(self, interaction):
        try:
            age = int(str(self.age.value).strip())
        except ValueError:
            await interaction.response.send_message("Age must be a whole number.", ephemeral=True)
            return
        if not 1 <= age <= 120:
            await interaction.response.send_message("Please enter a valid age.", ephemeral=True)
            return

        try:
            month, day = map(int, str(self.birthday.value).strip().split("/"))
            datetime(2000, month, day)
        except (ValueError, TypeError):
            await interaction.response.send_message("Birthday must use MM/DD, for example 06/21.", ephemeral=True)
            return

        values = (
            self.guild_id, self.user_id, str(self.name.value).strip(), age,
            month, day, str(self.city.value).strip(), str(self.country.value).strip(),
            datetime.now(timezone.utc).isoformat()
        )
        conn = db_connect()
        conn.execute("""
            INSERT INTO introductions
            (guild_id, user_id, name, age, birth_month, birth_day, city, country, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
            name=excluded.name, age=excluded.age, birth_month=excluded.birth_month,
            birth_day=excluded.birth_day, city=excluded.city, country=excluded.country,
            updated_at=excluded.updated_at
        """, values)
        conn.commit()
        conn.close()

        embed = self.cog.build_embed(interaction.user, *values[2:8])
        await interaction.response.send_message("Your introduction has been saved.", embed=embed, ephemeral=True)


class IntroductionPanel(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Introduce Yourself", style=discord.ButtonStyle.primary, custom_id="aishu:introduction:start")
    async def start(self, interaction, button):
        if interaction.guild is None:
            await interaction.response.send_message("This can only be used inside a server.", ephemeral=True)
            return
        await interaction.response.send_modal(IntroductionModal(self.cog, interaction))


class IntroductionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        db_connect().close()

    def build_embed(self, member, name, age, month, day, city, country):
        embed = discord.Embed(
            title="Member Introduction",
            description=f"Getting to know **{discord.utils.escape_markdown(str(name))}**.",
            colour=discord.Colour.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Name", value=str(name), inline=True)
        embed.add_field(name="Age", value=str(age), inline=True)
        embed.add_field(name="Birthday", value=f"{MONTHS[int(month) - 1]} {day}", inline=True)
        embed.add_field(name="City", value=str(city), inline=True)
        embed.add_field(name="Country", value=str(country), inline=True)
        embed.set_footer(text="Aishu Introduction System")
        return embed

    def get_intro(self, guild_id, user_id):
        conn = db_connect()
        row = conn.execute(
            "SELECT name, age, birth_month, birth_day, city, country FROM introductions WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        ).fetchone()
        conn.close()
        return row

    intro_group = app_commands.Group(name="intro", description="Manage your member introduction.")

    @intro_group.command(name="set", description="Create or update your introduction.")
    async def intro_set(self, interaction):
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
            return
        await interaction.response.send_modal(IntroductionModal(self, interaction))

    @intro_group.command(name="view", description="View a member's introduction.")
    @app_commands.describe(member="The member whose introduction you want to view.")
    async def intro_view(self, interaction, member: discord.Member = None):
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
            return
        target = member or interaction.user
        row = self.get_intro(interaction.guild.id, target.id)
        if row is None:
            await interaction.response.send_message(f"{target.mention} has not completed an introduction yet.", ephemeral=True)
            return
        await interaction.response.send_message(embed=self.build_embed(target, *row))

    @intro_group.command(name="delete", description="Delete your saved introduction.")
    async def intro_delete(self, interaction):
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used inside a server.", ephemeral=True)
            return
        conn = db_connect()
        cursor = conn.execute("DELETE FROM introductions WHERE guild_id=? AND user_id=?", (interaction.guild.id, interaction.user.id))
        conn.commit()
        conn.close()
        await interaction.response.send_message(
            "Your introduction has been deleted." if cursor.rowcount else "You do not have a saved introduction.",
            ephemeral=True,
        )

    @intro_group.command(name="setup", description="Create an introduction setup panel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def intro_setup(self, interaction):
        embed = discord.Embed(
            title="Member Introduction",
            description="Tell the community a little about yourself.\n\nClick the button below to create or update your introduction.",
            colour=discord.Colour.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=IntroductionPanel(self))

    async def cog_app_command_error(self, interaction, error):
        message = "You need Manage Server to use this command." if isinstance(error, app_commands.MissingPermissions) else "Something went wrong while processing the introduction."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot):
    cog = IntroductionCog(bot)
    await bot.add_cog(cog)
    bot.add_view(IntroductionPanel(cog))
