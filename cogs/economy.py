import random
import time
import discord
from discord.ext import commands
from utils.database import get_economy, update_economy, get_economy_leaderboard

class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._xp_cooldown: dict[tuple[int, int], float] = {}

    @staticmethod
    def level_for_xp(xp: int) -> int:
        level = 0
        while xp >= 100 * (level + 1) * (level + 1):
            level += 1
        return level

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot or not message.content.strip():
            return
        member = message.author
        if not isinstance(member, discord.Member):
            return
        key = (message.guild.id, member.id)
        now = time.time()
        if now - self._xp_cooldown.get(key, 0) < 60:
            return
        self._xp_cooldown[key] = now

        profile = get_economy(message.guild.id, member.id)
        gained = random.randint(5, 10)
        new_xp = int(profile["xp"]) + gained
        new_level = self.level_for_xp(new_xp)
        update_economy(
            message.guild.id,
            member.id,
            xp=new_xp,
            level=new_level,
            last_xp_at=now,
        )
        if new_level > int(profile["level"]):
            await message.channel.send(
                f"{member.mention} reached **Level {new_level}**.",
                delete_after=10,
            )

    @commands.command()
    @commands.guild_only()
    async def level(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        profile = get_economy(ctx.guild.id, member.id)
        level = int(profile["level"])
        xp = int(profile["xp"])
        next_xp = 100 * (level + 1) * (level + 1)
        await ctx.send(
            f"**{member.display_name}** — Level **{level}** | XP **{xp}/{next_xp}**"
        )

    @commands.command()
    @commands.guild_only()
    async def balance(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        profile = get_economy(ctx.guild.id, member.id)
        await ctx.send(f"**{member.display_name}** has **{int(profile['coins'])}** coins.")

    @commands.command()
    @commands.guild_only()
    async def daily(self, ctx: commands.Context):
        profile = get_economy(ctx.guild.id, ctx.author.id)
        now = time.time()
        remaining = 86400 - (now - float(profile["daily_at"]))
        if remaining > 0:
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            await ctx.send(f"Daily reward is ready again in **{hours}h {minutes}m**.", delete_after=8)
            return
        reward = random.randint(100, 250)
        update_economy(
            ctx.guild.id,
            ctx.author.id,
            coins=int(profile["coins"]) + reward,
            daily_at=now,
        )
        await ctx.send(f"You received **{reward}** coins from your daily reward.")

    @commands.command(name="leaderboard")
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context):
        rows = get_economy_leaderboard(ctx.guild.id, 10)
        if not rows:
            await ctx.send("No economy data yet.")
            return
        lines = []
        for index, row in enumerate(rows, 1):
            lines.append(
                f"**{index}.** <@{row['user_id']}> — Level {row['level']} | {row['xp']} XP | {row['coins']} coins"
            )
        await ctx.send(embed=discord.Embed(
            title="Aishu Leaderboard",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        ))

async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
