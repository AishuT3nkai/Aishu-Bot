import random
import discord
from discord import app_commands
from discord.ext import commands

class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="8ball", description="Ask the magic 8-ball")
    async def eightball(self, interaction: discord.Interaction, question: str):
        answers = [
            "Yes.", "No.", "Probably.", "Probably not.",
            "Ask again later.", "The signs point to yes.", "The signs point to no."
        ]
        await interaction.response.send_message(
            f"Question: {question}\nAnswer: {random.choice(answers)}"
        )

    @app_commands.command(name="coinflip", description="Flip a coin")
    async def coinflip(self, interaction: discord.Interaction):
        await interaction.response.send_message(random.choice(["Heads.", "Tails."]))

    @app_commands.command(name="dice", description="Roll a six-sided die")
    async def dice(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"You rolled **{random.randint(1, 6)}**.")

    @app_commands.command(name="choose", description="Choose from comma-separated options")
    async def choose(self, interaction: discord.Interaction, options: str):
        choices = [item.strip() for item in options.split(",") if item.strip()]
        if len(choices) < 2:
            await interaction.response.send_message(
                "Give me at least two options separated by commas.", ephemeral=True
            )
            return
        if len(choices) > 20:
            await interaction.response.send_message(
                "Keep the list to 20 options or fewer.", ephemeral=True
            )
            return
        await interaction.response.send_message(f"I choose **{random.choice(choices)}**.")

    @app_commands.command(name="ship", description="Calculate a playful compatibility score")
    @app_commands.guild_only()
    async def ship(self, interaction: discord.Interaction, first: discord.Member, second: discord.Member):
        rng = random.Random((first.id << 32) ^ second.id)
        score = rng.randint(0, 100)
        await interaction.response.send_message(
            f"**{first.display_name} × {second.display_name}** — {score}% compatibility."
        )

    @app_commands.command(name="rate", description="Give something a playful rating")
    async def rate(self, interaction: discord.Interaction, thing: str):
        score = random.randint(1, 10)
        await interaction.response.send_message(f"I rate **{thing}**: **{score}/10**.")

    @app_commands.command(name="rps", description="Play rock paper scissors")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Rock", value="rock"),
        app_commands.Choice(name="Paper", value="paper"),
        app_commands.Choice(name="Scissors", value="scissors"),
    ])
    async def rps(self, interaction: discord.Interaction, choice: app_commands.Choice[str]):
        bot_choice = random.choice(["rock", "paper", "scissors"])
        if choice.value == bot_choice:
            result = "Draw."
        elif (choice.value, bot_choice) in {("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")}:
            result = "You win."
        else:
            result = "I win."
        await interaction.response.send_message(
            f"You: **{choice.name}**\nMe: **{bot_choice.title()}**\n**{result}**"
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
