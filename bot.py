import os
import sqlite3
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DB_PATH = "aishu.db"

LANGUAGES = {
    "id": "Indonesia",
    "tl": "Tagalog",
    "en": "English",
}

TEXT = {
    "id": {
        "language_set": "Bahasa bot untuk server ini diubah ke **{language}**.",
        "introduce_title": "Perkenalan",
        "name": "Nama",
        "birthdate": "Tanggal lahir",
        "age": "Umur",
        "origin": "Asal",
        "city": "Kota",
        "saved": "Perkenalan kamu berhasil disimpan.",
        "profile": "Perkenalan {user}",
    },
    "tl": {
        "language_set": "Ang wika ng bot para sa server na ito ay itinakda sa **{language}**.",
        "introduce_title": "Pagpapakilala",
        "name": "Pangalan",
        "birthdate": "Petsa ng kapanganakan",
        "age": "Edad",
        "origin": "Pinagmulan",
        "city": "Lungsod",
        "saved": "Matagumpay na na-save ang iyong pagpapakilala.",
        "profile": "Pagpapakilala ni {user}",
    },
    "en": {
        "language_set": "The bot language for this server is now **{language}**.",
        "introduce_title": "Introduction",
        "name": "Name",
        "birthdate": "Date of birth",
        "age": "Age",
        "origin": "Origin",
        "city": "City",
        "saved": "Your introduction has been saved.",
        "profile": "{user}'s Introduction",
    },
}


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            language TEXT NOT NULL DEFAULT 'id',
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS introductions (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            birthdate TEXT NOT NULL,
            age TEXT NOT NULL,
            origin TEXT NOT NULL,
            city TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        )
        """
    )
    connection.commit()
    return connection


def get_language(guild_id: int, user_id: int) -> str:
    # Admins always receive English so administrative commands stay consistent.
    connection = db()
    row = connection.execute(
        "SELECT language FROM user_settings WHERE guild_id = ? AND user_id = ?",
        (guild_id, user_id),
    ).fetchone()
    connection.close()
    return row[0] if row else "id"


def set_language(guild_id: int, user_id: int, language: str):
    connection = db()
    connection.execute(
        """
        INSERT INTO user_settings (guild_id, user_id, language)
        VALUES (?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET language=excluded.language
        """,
        (guild_id, user_id, language),
    )
    connection.commit()
    connection.close()


def get_interaction_language(interaction: discord.Interaction) -> str:
    if interaction.guild and interaction.user.guild_permissions.manage_guild:
        return "en"
    return get_language(interaction.guild_id, interaction.user.id)


def save_introduction(guild_id: int, user_id: int, values: dict):
    connection = db()
    connection.execute(
        """
        INSERT INTO introductions
        (guild_id, user_id, name, birthdate, age, origin, city)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            name=excluded.name,
            birthdate=excluded.birthdate,
            age=excluded.age,
            origin=excluded.origin,
            city=excluded.city
        """,
        (
            guild_id,
            user_id,
            values["name"],
            values["birthdate"],
            values["age"],
            values["origin"],
            values["city"],
        ),
    )
    connection.commit()
    connection.close()


class IntroductionModal(discord.ui.Modal):
    def __init__(self, language: str):
        t = TEXT[language]
        super().__init__(title=t["introduce_title"])
        self.language = language

        self.name = discord.ui.TextInput(
            label=t["name"], placeholder="Ratman", max_length=100
        )
        self.birthdate = discord.ui.TextInput(
            label=t["birthdate"], placeholder="21 June 2011", max_length=50
        )
        self.age = discord.ui.TextInput(
            label=t["age"], placeholder="15", max_length=3
        )
        self.origin = discord.ui.TextInput(
            label=t["origin"], placeholder="Indonesia", max_length=100
        )
        self.city = discord.ui.TextInput(
            label=t["city"], placeholder="Lamongan", max_length=100
        )

        for field in (
            self.name,
            self.birthdate,
            self.age,
            self.origin,
            self.city,
        ):
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        values = {
            "name": self.name.value,
            "birthdate": self.birthdate.value,
            "age": self.age.value,
            "origin": self.origin.value,
            "city": self.city.value,
        }

        save_introduction(interaction.guild_id, interaction.user.id, values)
        t = TEXT[self.language]

        embed = discord.Embed(
            title=t["profile"].format(user=interaction.user.display_name),
            color=discord.Color.blurple(),
        )
        embed.add_field(name=t["name"], value=values["name"], inline=True)
        embed.add_field(name=t["birthdate"], value=values["birthdate"], inline=True)
        embed.add_field(name=t["age"], value=values["age"], inline=True)
        embed.add_field(name=t["origin"], value=values["origin"], inline=True)
        embed.add_field(name=t["city"], value=values["city"], inline=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        await interaction.response.send_message(
            content=t["saved"], embed=embed, ephemeral=False
        )


class AishuBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        db().close()
        await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id})")


bot = AishuBot()


@bot.tree.command(name="introduce", description="Create or update your server introduction")
async def introduce(interaction: discord.Interaction):
    language = get_interaction_language(interaction)
    await interaction.response.send_modal(IntroductionModal(language))


@bot.tree.command(name="language", description="Set your personal bot language")
@app_commands.describe(language="Choose your personal language: Indonesia, Tagalog, or English")
@app_commands.choices(
    language=[
        app_commands.Choice(name="Indonesia", value="id"),
        app_commands.Choice(name="Tagalog", value="tl"),
        app_commands.Choice(name="English", value="en"),
    ]
)
async def language(interaction: discord.Interaction, language: app_commands.Choice[str]):
    set_language(interaction.guild_id, interaction.user.id, language.value)
    # The setting confirmation itself follows the language just selected.
    t = TEXT[language.value]
    await interaction.response.send_message(
        t["language_set"].replace("server", "your personal setting").format(
            language=LANGUAGES[language.value]
        )
    )


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing from the environment.")

bot.run(TOKEN)
