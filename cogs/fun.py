import random
from datetime import datetime, timezone

import discord
from discord.ext import commands


class Fun(commands.Cog):
    @staticmethod
    def _embed(title: str, description: str) -> discord.Embed:
        return discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )

    @commands.command(name="8ball", description="Ask the magic 8-ball a question.")
    async def eightball(self, ctx: commands.Context, *, question: str):
        answers = [
            "Yes.", "No.", "Probably.", "Probably not.",
            "Ask again later.", "The signs point to yes.", "The signs point to no.",
        ]
        embed = self._embed("Magic 8-Ball", f"**Question**\n{question}\n\n**Answer**\n{random.choice(answers)}")
        embed.set_footer(text=f"Asked by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.command(description="Flip a coin.")
    async def coinflip(self, ctx: commands.Context):
        result = random.choice(["Heads", "Tails"])
        await ctx.send(embed=self._embed("Coin Flip", f"The result is **{result}**."))

    @commands.command(description="Roll a six-sided die.")
    async def dice(self, ctx: commands.Context):
        result = random.randint(1, 6)
        await ctx.send(embed=self._embed("Dice Roll", f"You rolled **{result}**."))

    @commands.command(description="Choose one option from a comma-separated list.")
    async def choose(self, ctx: commands.Context, *, options: str):
        choices = [item.strip() for item in options.split(",") if item.strip()]
        if len(choices) < 2:
            await ctx.send("Give me at least two options separated by commas.", delete_after=8)
            return
        if len(choices) > 20:
            await ctx.send("Keep the list to 20 options or fewer.", delete_after=8)
            return
        await ctx.send(embed=self._embed("Choice", f"I choose **{random.choice(choices)}**."))

    @commands.command(description="Calculate compatibility between two members.")
    @commands.guild_only()
    async def ship(self, ctx: commands.Context, first: discord.Member, second: discord.Member):
        low, high = sorted((first.id, second.id))
        score = random.Random((low << 32) ^ high).randint(0, 100)
        embed = self._embed(
            "Compatibility",
            f"**{first.display_name} × {second.display_name}**\n\nCompatibility: **{score}%**",
        )
        await ctx.send(embed=embed)

    @commands.command(description="Rate something from 1 to 10.")
    async def rate(self, ctx: commands.Context, *, thing: str):
        score = random.randint(1, 10)
        await ctx.send(embed=self._embed("Rating", f"**{thing}**\n\nScore: **{score}/10**"))

    @commands.command(description="Play rock, paper, scissors.")
    @commands.guild_only()
    async def rps(self, ctx: commands.Context, choice: str):
        choice = choice.casefold()
        if choice not in {"rock", "paper", "scissors"}:
            await ctx.send("Choose rock, paper, or scissors.", delete_after=8)
            return
        bot_choice = random.choice(["rock", "paper", "scissors"])
        if choice == bot_choice:
            result = "Draw."
        elif (choice, bot_choice) in {
            ("rock", "scissors"),
            ("paper", "rock"),
            ("scissors", "paper"),
        }:
            result = "You win."
        else:
            result = "I win."
        embed = self._embed(
            "Rock, Paper, Scissors",
            f"**You:** {choice.title()}\n**Aishu:** {bot_choice.title()}\n\n**{result}**",
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
