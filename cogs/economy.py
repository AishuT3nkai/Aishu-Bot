import random
import re
import time
from datetime import datetime, timezone

import discord
from discord.ext import commands

from utils.database import get_economy, update_economy, get_economy_leaderboard

URL_ONLY_RE = re.compile(r"^(?:https?://|www\.)\S+$", re.IGNORECASE)
MIN_MESSAGE_LENGTH = 5
XP_COOLDOWN_SECONDS = 60
DAILY_XP_CAP = 300


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._recent_content: dict[tuple[int, int], tuple[str, float]] = {}

    @staticmethod
    def _embed(title: str, description: str) -> discord.Embed:
        return discord.Embed(
            title=title,
            description=description,
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )

    @staticmethod
    def level_for_xp(xp: int) -> int:
        level = 0
        while xp >= 100 * (level + 1) * (level + 1):
            level += 1
        return level

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot or not isinstance(message.author, discord.Member):
            return
        content = message.content.strip()
        if len(content) < MIN_MESSAGE_LENGTH or URL_ONLY_RE.fullmatch(content):
            return
        if content.startswith(("/", "!", "?")):
            return
        member = message.author
        key = (message.guild.id, member.id)
        now = time.time()
        profile = get_economy(message.guild.id, member.id)
        if now - float(profile["last_xp_at"]) < XP_COOLDOWN_SECONDS:
            return
        normalized = " ".join(content.casefold().split())
        recent = self._recent_content.get(key)
        if recent and recent[0] == normalized and now - recent[1] < 3600:
            return
        self._recent_content[key] = (normalized, now)

        utc_day = time.strftime("%Y-%m-%d", time.gmtime(now))
        earned_today = int(profile["xp_daily"]) if profile["xp_day"] == utc_day else 0
        if earned_today >= DAILY_XP_CAP:
            return
        gained = min(random.randint(5, 10), DAILY_XP_CAP - earned_today)
        new_xp = int(profile["xp"]) + gained
        new_level = self.level_for_xp(new_xp)
        update_economy(
            message.guild.id,
            member.id,
            xp=new_xp,
            level=new_level,
            last_xp_at=now,
            xp_day=utc_day,
            xp_daily=earned_today + gained,
        )
        if new_level > int(profile["level"]):
            embed = self._embed(
                "Level Up",
                f"{member.mention} reached **Level {new_level}**.",
            )
            embed.set_footer(text=f"{message.guild.name} • Aishu")
            await message.channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=[member]),
                delete_after=10,
            )

    @commands.command(description="View your or another member's level.")
    @commands.guild_only()
    async def level(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        profile = get_economy(ctx.guild.id, member.id)
        level = int(profile["level"])
        xp = int(profile["xp"])
        next_xp = 100 * (level + 1) * (level + 1)
        embed = self._embed(
            "Level",
            f"**Member:** {member.mention}\n**Level:** {level}\n**XP:** {xp}/{next_xp}",
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(description="View your or another member's coin balance.")
    @commands.guild_only()
    async def balance(self, ctx: commands.Context, member: discord.Member | None = None):
        member = member or ctx.author
        profile = get_economy(ctx.guild.id, member.id)
        embed = self._embed(
            "Balance",
            f"**Member:** {member.mention}\n**Coins:** {int(profile['coins']):,}",
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(description="Claim your daily coin reward.")
    @commands.guild_only()
    async def daily(self, ctx: commands.Context):
        profile = get_economy(ctx.guild.id, ctx.author.id)
        now = time.time()
        remaining = 86400 - (now - float(profile["daily_at"]))
        if remaining > 0:
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            await ctx.send(
                embed=self._embed(
                    "Daily Reward",
                    f"Your next reward is ready in **{hours}h {minutes}m**.",
                ),
                delete_after=8,
            )
            return
        reward = random.randint(100, 250)
        update_economy(
            ctx.guild.id,
            ctx.author.id,
            coins=int(profile["coins"]) + reward,
            daily_at=now,
        )
        await ctx.send(embed=self._embed("Daily Reward", f"You received **{reward:,} coins**."))

    @commands.command(name="leaderboard", description="View the server economy leaderboard.")
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context):
        rows = get_economy_leaderboard(ctx.guild.id, 10)
        if not rows:
            await ctx.send(embed=self._embed("Leaderboard", "No economy data yet."))
            return
        lines = []
        for index, row in enumerate(rows, 1):
            lines.append(
                f"**{index}.** <@{row['user_id']}> — Level **{row['level']}** · {row['xp']:,} XP · {row['coins']:,} coins"
            )
        embed = self._embed("Economy Leaderboard", "\n".join(lines))
        embed.set_footer(text=f"Top {len(rows)} members • {ctx.guild.name}")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
