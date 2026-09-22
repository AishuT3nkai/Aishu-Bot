import discord
from discord import app_commands
from discord.ext import commands
from utils.database import get_guild_config, update_guild_config


async def create_ticket(guild: discord.Guild, member: discord.Member):
    config = get_guild_config(guild.id)
    category = guild.get_channel(config.get("ticket_category_id") or 0)
    if not isinstance(category, discord.CategoryChannel):
        return None, False

    existing = discord.utils.find(
        lambda c: isinstance(c, discord.TextChannel) and c.topic == f"aishu-ticket:{member.id}",
        guild.text_channels,
    )
    if existing:
        return existing, False

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }
    support_role = guild.get_role(config.get("ticket_support_role_id") or 0)
    if support_role:
        overwrites[support_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        )

    safe_name = "-".join(member.display_name.lower().split())[:70] or "member"
    try:
        channel = await category.create_text_channel(
            name=f"ticket-{safe_name}",
            overwrites=overwrites,
            topic=f"aishu-ticket:{member.id}",
            reason=f"Ticket opened by {member}",
        )
    except (discord.Forbidden, discord.HTTPException):
        return None, False
    return channel, True


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Create Ticket",
        style=discord.ButtonStyle.primary,
        emoji="🎫",
        custom_id="aishu:ticket:create",
    )
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel, created = await create_ticket(interaction.guild, interaction.user)
        if channel is None:
            await interaction.response.send_message(
                "Ticket system is not configured. Ask an administrator to configure it.",
                ephemeral=True,
            )
            return
        if created:
            await channel.send(
                f"{interaction.user.mention}, welcome. Please describe your issue. "
                "A support member will help you here."
            )
            await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)
        else:
            await interaction.response.send_message(f"You already have a ticket: {channel.mention}", ephemeral=True)


class Ticket(commands.Cog):
    ticket = app_commands.Group(name="ticket", description="Community support ticket system")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @ticket.command(name="setup", description="Configure the ticket category and support role")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        category="Category where ticket channels will be created",
        support_role="Role that can see tickets",
    )
    @app_commands.guild_only()
    async def setup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        support_role: discord.Role | None = None,
    ):
        if support_role and support_role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                "The support role must be below my highest role.", ephemeral=True
            )
            return
        update_guild_config(
            interaction.guild_id,
            ticket_category_id=category.id,
            ticket_support_role_id=support_role.id if support_role else None,
        )
        await interaction.response.send_message(
            f"Ticket system configured for {category.name}.", ephemeral=True
        )

    @ticket.command(name="panel", description="Post the ticket creation panel")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def panel(self, interaction: discord.Interaction):
        config = get_guild_config(interaction.guild_id)
        if not config.get("ticket_category_id"):
            await interaction.response.send_message("Run /ticket setup first.", ephemeral=True)
            return
        embed = discord.Embed(
            title="Community Support",
            description="Need help? Click the button below to create a private support ticket.",
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, view=TicketView())

    @ticket.command(name="close", description="Close the current ticket")
    @app_commands.guild_only()
    async def close(self, interaction: discord.Interaction):
        channel = interaction.channel
        if (
            not isinstance(channel, discord.TextChannel)
            or not channel.topic
            or not channel.topic.startswith("aishu-ticket:")
        ):
            await interaction.response.send_message(
                "This command can only be used inside an Aishu ticket.", ephemeral=True
            )
            return
        config = get_guild_config(interaction.guild_id)
        support_role = interaction.guild.get_role(config.get("ticket_support_role_id") or 0)
        is_support = interaction.user.guild_permissions.manage_channels or (
            support_role is not None and support_role in interaction.user.roles
        )
        if not is_support:
            await interaction.response.send_message(
                "You do not have permission to close this ticket.", ephemeral=True
            )
            return
        await interaction.response.send_message("Closing ticket...", ephemeral=True)
        await channel.delete(reason=f"Ticket closed by {interaction.user}")

    @ticket.command(name="claim", description="Claim the current ticket")
    @app_commands.guild_only()
    async def claim(self, interaction: discord.Interaction):
        if (
            not isinstance(interaction.channel, discord.TextChannel)
            or not interaction.channel.topic
            or not interaction.channel.topic.startswith("aishu-ticket:")
        ):
            await interaction.response.send_message("Use this inside a ticket.", ephemeral=True)
            return
        config = get_guild_config(interaction.guild_id)
        support_role = interaction.guild.get_role(config.get("ticket_support_role_id") or 0)
        is_support = interaction.user.guild_permissions.manage_channels or (
            support_role is not None and support_role in interaction.user.roles
        )
        if not is_support:
            await interaction.response.send_message("You do not have permission to claim this ticket.", ephemeral=True)
            return
        await interaction.channel.send(f"🎫 Ticket claimed by {interaction.user.mention}.")
        await interaction.response.send_message("Ticket claimed.", ephemeral=True)

    @ticket.command(name="rename", description="Rename the current ticket")
    @app_commands.describe(name="New channel name")
    @app_commands.guild_only()
    async def rename(self, interaction: discord.Interaction, name: str):
        if (
            not isinstance(interaction.channel, discord.TextChannel)
            or not interaction.channel.topic
            or not interaction.channel.topic.startswith("aishu-ticket:")
        ):
            await interaction.response.send_message("Use this inside a ticket.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message("You need Manage Channels to rename tickets.", ephemeral=True)
            return
        safe_name = "-".join(name.lower().split())[:90]
        await interaction.channel.edit(name=safe_name, reason=f"Renamed by {interaction.user}")
        await interaction.response.send_message(f"Ticket renamed to {safe_name}.", ephemeral=True)

    @ticket.command(name="add", description="Add a member to the current ticket")
    @app_commands.describe(user="Member to add")
    @app_commands.guild_only()
    async def add(self, interaction: discord.Interaction, user: discord.Member):
        if (
            not isinstance(interaction.channel, discord.TextChannel)
            or not interaction.channel.topic
            or not interaction.channel.topic.startswith("aishu-ticket:")
        ):
            await interaction.response.send_message("Use this inside a ticket.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "You need Manage Channels to modify ticket access.", ephemeral=True
            )
            return
        await interaction.channel.set_permissions(
            user, view_channel=True, send_messages=True, read_message_history=True
        )
        await interaction.response.send_message(f"Added {user.mention} to the ticket.")

    @ticket.command(name="remove", description="Remove a member from the current ticket")
    @app_commands.describe(user="Member to remove")
    @app_commands.guild_only()
    async def remove(self, interaction: discord.Interaction, user: discord.Member):
        if (
            not isinstance(interaction.channel, discord.TextChannel)
            or not interaction.channel.topic
            or not interaction.channel.topic.startswith("aishu-ticket:")
        ):
            await interaction.response.send_message("Use this inside a ticket.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.manage_channels:
            await interaction.response.send_message(
                "You need Manage Channels to modify ticket access.", ephemeral=True
            )
            return
        await interaction.channel.set_permissions(user, overwrite=None)
        await interaction.response.send_message(f"Removed {user.mention} from the ticket.")


async def setup(bot: commands.Bot):
    bot.add_view(TicketView())
    await bot.add_cog(Ticket(bot))
