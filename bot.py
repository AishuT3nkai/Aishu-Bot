import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from utils.database import connect, get_dashboard_config
from bridge import Bridge

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
    """Read the per-guild message-command prefix configured by the dashboard."""
    if message.guild is None:
        return "/"
    config = get_dashboard_config(message.guild.id, "server", {})
    prefix = config.get("prefix", "/") if isinstance(config, dict) else "/"
    return prefix if isinstance(prefix, str) and 1 <= len(prefix) <= 5 else "/"


class AishuBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.bridge = Bridge(self)

    async def setup_hook(self):
        connection = connect()
        connection.close()

        original_command = commands.command
        commands.command = commands.hybrid_command
        try:
            for extension in EXTENSIONS:
                await self.load_extension(extension)
        finally:
            commands.command = original_command

        synced = await self.tree.sync()
        print(f"Synced {len(synced)} application command(s).")
        await self.bridge.start()

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

    async def close(self):
        await self.bridge.close()
        await super().close()


async def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing from the environment.")
    async with AishuBot() as bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
