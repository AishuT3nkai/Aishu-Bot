import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import date
from utils.database import set_birthday, remove_birthday, get_birthday, get_birthdays, get_guild_config, update_guild_config


class Birthday(commands.Cog):
    birthday = app_commands.Group(name="birthday", description="Community birthday settings")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sent: set[str] = set()
        self.daily_birthdays.start()

    def cog_unload(self):
        self.daily_birthdays.cancel()

    @birthday.command(name="set", description="Set your birthday month and day")
    @app_commands.describe(month="Birthday month (1-12)", day="Birthday day")
    @app_commands.guild_only()
    async def set(self, interaction: discord.Interaction, month: app_commands.Range[int, 1, 12], day: app_commands.Range[int, 1, 31]):
        try:
            date(2000, month, day)
        except ValueError:
            await interaction.response.send_message("That is not a valid month/day combination.", ephemeral=True)
            return
        set_birthday(interaction.guild_id, interaction.user.id, month, day)
        await interaction.response.send_message(
            f"Birthday saved as {month:02d}/{day:02d}. Only the month and day are stored.",
            ephemeral=True,
        )

    @birthday.command(name="view", description="View your saved birthday")
    @app_commands.guild_only()
    async def view(self, interaction: discord.Interaction):
        row = get_birthday(interaction.guild_id, interaction.user.id)
        if not row:
            await interaction.response.send_message("You have no birthday saved.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Your saved birthday is {row['month']:02d}/{row['day']:02d}.",
            ephemeral=True,
        )

    @birthday.command(name="remove", description="Remove your saved birthday")
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction):
        remove_birthday(interaction.guild_id, interaction.user.id)
        await interaction.response.send_message("Your birthday has been removed.", ephemeral=True)

    @birthday.command(name="channel", description="Set the birthday announcement channel")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(channel="Channel for birthday announcements")
    @app_commands.guild_only()
    async def channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        update_guild_config(interaction.guild_id, birthday_channel_id=channel.id)
        await interaction.response.send_message(
            f"Birthday announcements will be sent to {channel.mention}.",
            ephemeral=True,
        )

    @birthday.command(name="today", description="See today's saved birthdays")
    @app_commands.guild_only()
    async def today(self, interaction: discord.Interaction):
        today = date.today()
        rows = get_birthdays(interaction.guild_id, today.month, today.day)
        if not rows:
            await interaction.response.send_message("No birthdays saved for today.", ephemeral=True)
            return
        mentions = [f"<@{row['user_id']}>" for row in rows]
        await interaction.response.send_message("Today's birthdays: " + ", ".join(mentions))

    @tasks.loop(minutes=5)
    async def daily_birthdays(self):
        now = date.today()
        for guild in self.bot.guilds:
            config = get_guild_config(guild.id)
            channel = guild.get_channel(config.get("birthday_channel_id") or 0)
            if not channel:
                continue
            # A lightweight duplicate guard: this only runs once per date per process.
            key = f"{guild.id}:{now.isoformat()}"
            if key in self._sent:
                continue
            rows = get_birthdays(guild.id, now.month, now.day)
            if rows:
                mentions = [f"<@{row['user_id']}>" for row in rows]
                try:
                    await channel.send("🎂 Happy birthday to " + ", ".join(mentions) + "!")
                except (discord.Forbidden, discord.HTTPException):
                    continue
            self._sent.add(key)

        # Keep the in-memory guard bounded to the current date.
        today_prefix = f":{now.isoformat()}"
        self._sent = {item for item in self._sent if item.endswith(today_prefix)}

    @daily_birthdays.before_loop
    async def before_birthdays(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Birthday(bot))
