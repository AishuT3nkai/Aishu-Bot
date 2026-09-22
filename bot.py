import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from utils.database import connect

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DEFAULT_PREFIX = "!"

EXTENSIONS = (
    "cogs.community",
    "cogs.moderation",
    "cogs.server",
    "cogs.verification",
    "cogs.welcome",
    "cogs.tickets",
    "cogs.birthday",
    "cogs.reviews",
)

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing from the environment.")


class AishuBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix=DEFAULT_PREFIX, intents=intents)

    async def setup_hook(self):
        connection = connect()
        connection.close()
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id})")
        print(f"Connected to {len(self.guilds)} server(s).")


async def main():
    async with AishuBot() as bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
