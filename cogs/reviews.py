import discord
from discord import app_commands
from discord.ext import commands
from utils.database import set_report_status, set_suggestion_status


class Reviews(commands.Cog):
    suggestion = app_commands.Group(name="suggestion", description="Moderate community suggestions")
    report = app_commands.Group(name="reports", description="Manage community reports")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @suggestion.command(name="approve", description="Approve a suggestion by its ID")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(suggestion_id="Suggestion ID")
    async def suggestion_approve(self, interaction: discord.Interaction, suggestion_id: int):
        ok = set_suggestion_status(interaction.guild_id, suggestion_id, "approved")
        await interaction.response.send_message(
            f"Suggestion #{suggestion_id} {'approved.' if ok else 'was not found.'}",
            ephemeral=True,
        )

    @suggestion.command(name="deny", description="Deny a suggestion by its ID")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(suggestion_id="Suggestion ID")
    async def suggestion_deny(self, interaction: discord.Interaction, suggestion_id: int):
        ok = set_suggestion_status(interaction.guild_id, suggestion_id, "denied")
        await interaction.response.send_message(
            f"Suggestion #{suggestion_id} {'denied.' if ok else 'was not found.'}",
            ephemeral=True,
        )

    @report.command(name="close", description="Close a community report by its ID")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(report_id="Report ID")
    async def report_close(self, interaction: discord.Interaction, report_id: int):
        ok = set_report_status(interaction.guild_id, report_id, "closed")
        await interaction.response.send_message(
            f"Report #{report_id} {'closed.' if ok else 'was not found.'}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Reviews(bot))
