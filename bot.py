import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from utils.database import connect

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

EXTENSIONS = (
    "cogs.community",
    "cogs.moderation",
    "cogs.automod",
    "cogs.antiraid",
    "cogs.server_backup",
    "cogs.economy",
    "cogs.server",
    "cogs.verification",
    "cogs.welcome",
    "cogs.tickets",
    "cogs.birthday",
    "cogs.reviews",
    "cogs.introduction",
    "cogs.utility",
    "cogs.community_tools",
    "cogs.fun",
)


def command_prefix(bot: commands.Bot, message: discord.Message):
    """Use '/' as the only message-command prefix."""
    return "/"


class AishuBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix=command_prefix, intents=intents)

    async def setup_hook(self):
        connection = connect()
        connection.close()

        # Existing legacy commands keep their current implementation while
        # standalone commands are also registered as Discord slash commands.
        # Groups with nested subcommands remain message commands until they are
        # flattened into Discord's one-level application-command structure.
        original_command = commands.command
        commands.command = commands.hybrid_command
        try:
            for extension in EXTENSIONS:
                await self.load_extension(extension)
        finally:
            commands.command = original_command

        synced = await self.tree.sync()
        print(f"Synced {len(synced)} application command(s).")

    async def on_ready(self):
        print(f"Logged in as {self.user} ({self.user.id})")
        print(f"Connected to {len(self.guilds)} server(s).")

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
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
