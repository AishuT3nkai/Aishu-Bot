import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from utils.database import connect

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

MODERATION_COMMANDS = {"warn", "warnings", "clearwarnings", "timeout", "untimeout", "kick", "ban", "unban", "purge", "slowmode", "lock", "unlock", "automod", "antiraid"}
FUN_COMMANDS = {"8ball", "coinflip", "dice", "choose", "ship", "rate", "rps", "level", "balance", "daily", "leaderboard"}

EXTENSIONS = (
    "cogs.community",
    "cogs.moderation",
    "cogs.automod",
    "cogs.antiraid",
    "cogs.economy",
    "cogs.server",
    "cogs.verification",
    "cogs.welcome",
    "cogs.tickets",
    "cogs.birthday",
    "cogs.reviews",
    "cogs.introduction",
    "cogs.utility",
    "cogs.fun",
)

def command_prefix(bot: commands.Bot, message: discord.Message):
    content = message.content.lstrip()
    if content.startswith(","):
        name = content[1:].split(maxsplit=1)[0].casefold()
        return "," if name in MODERATION_COMMANDS else "\x00"
    if content.startswith("."):
        name = content[1:].split(maxsplit=1)[0].casefold()
        return "." if name in FUN_COMMANDS else "\x00"
    return "\x00"

class AishuBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix=command_prefix, intents=intents)

    async def setup_hook(self):
        connection = connect()
        connection.close()
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        await self.tree.sync()

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id})")
        print(f"Connected to {len(self.guilds)} server(s).")

    async def on_message(self, message: discord.Message):
        await self.process_commands(message)

    async def on_app_command_error(self, interaction, error):
        print(f"App command error: {error!r}")
        message = "Something went wrong while processing that command."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            pass

async def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing from the environment.")
    async with AishuBot() as bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
