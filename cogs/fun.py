import random
import discord
from discord.ext import commands

class Fun(commands.Cog):
    @commands.command(name="8ball")
    async def eightball(self, ctx: commands.Context, *, question: str):
        answers = ["Yes.", "No.", "Probably.", "Probably not.", "Ask again later.", "The signs point to yes.", "The signs point to no."]
        await ctx.send(f"Question: {question}\nAnswer: {random.choice(answers)}")

    @commands.command()
    async def coinflip(self, ctx: commands.Context):
        await ctx.send(random.choice(["Heads.", "Tails."]))

    @commands.command()
    async def dice(self, ctx: commands.Context):
        await ctx.send(f"You rolled **{random.randint(1, 6)}**.")

    @commands.command()
    async def choose(self, ctx: commands.Context, *, options: str):
        choices = [item.strip() for item in options.split(",") if item.strip()]
        if len(choices) < 2:
            await ctx.send("Give me at least two options separated by commas.", delete_after=8); return
        if len(choices) > 20:
            await ctx.send("Keep the list to 20 options or fewer.", delete_after=8); return
        await ctx.send(f"I choose **{random.choice(choices)}**.")

    @commands.command()
    @commands.guild_only()
    async def ship(self, ctx: commands.Context, first: discord.Member, second: discord.Member):
        low, high = sorted((first.id, second.id))
        score = random.Random((low << 32) ^ high).randint(0, 100)
        await ctx.send(f"**{first.display_name} × {second.display_name}** — {score}% compatibility.")

    @commands.command()
    async def rate(self, ctx: commands.Context, *, thing: str):
        await ctx.send(f"I rate **{thing}**: **{random.randint(1, 10)}/10**.")

    @commands.command()
    @commands.guild_only()
    async def rps(self, ctx: commands.Context, choice: str):
        choice = choice.casefold()
        if choice not in {"rock", "paper", "scissors"}:
            await ctx.send("Choose rock, paper, or scissors.", delete_after=8); return
        bot_choice = random.choice(["rock", "paper", "scissors"])
        if choice == bot_choice:
            result = "Draw."
        elif (choice, bot_choice) in {("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")}:
            result = "You win."
        else:
            result = "I win."
        await ctx.send(f"You: **{choice.title()}**\nMe: **{bot_choice.title()}**\n**{result}**")

async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
