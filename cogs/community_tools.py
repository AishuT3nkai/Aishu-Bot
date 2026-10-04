import discord
from discord import app_commands
from discord.ext import commands

from utils.database import add_reaction_role, get_reaction_role, get_role_panels, remove_reaction_role, save_role_panel

class RoleSelect(discord.ui.Select):
    def __init__(self, guild_id: int, roles: list[discord.Role]):
        self.guild_id = guild_id
        options = [
            discord.SelectOption(label=role.name[:100], value=str(role.id))
            for role in roles
        ]
        super().__init__(
            custom_id=f"aishu:roles:{guild_id}",
            placeholder="Select your roles",
            min_values=0,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message("This role menu belongs to another server.", ephemeral=True)
            return
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return
        selected = {int(value) for value in self.values}
        changed = []
        for option in self.options:
            role = interaction.guild.get_role(int(option.value))
            if role is None or role.is_default() or role.managed:
                continue
            if role >= interaction.guild.me.top_role:
                continue
            try:
                if role.id in selected and role not in member.roles:
                    await member.add_roles(role, reason="Aishu role menu")
                    changed.append(f"Added {role.mention}")
                elif role.id not in selected and role in member.roles:
                    await member.remove_roles(role, reason="Aishu role menu")
                    changed.append(f"Removed {role.mention}")
            except (discord.Forbidden, discord.HTTPException):
                continue
        await interaction.response.send_message(
            "\n".join(changed) if changed else "No role changes were made.",
            ephemeral=True,
        )

class RolePanelView(discord.ui.View):
    def __init__(self, guild_id: int, roles: list[discord.Role]):
        super().__init__(timeout=None)
        self.add_item(RoleSelect(guild_id, roles))

class AnnouncementModal(discord.ui.Modal, title="Create Announcement"):
    title_input = discord.ui.TextInput(label="Title", max_length=256, placeholder="Announcement title")
    description = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        placeholder="Write the announcement...",
    )
    image_url = discord.ui.TextInput(
        label="Image URL (optional)",
        required=False,
        max_length=1000,
        placeholder="https://example.com/image.png",
    )

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=self.title_input.value.strip(),
            description=self.description.value.strip(),
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        image_url = self.image_url.value.strip()
        if image_url:
            if not image_url.startswith(("https://", "http://")):
                await interaction.response.send_message("Image URL must start with http:// or https://.", ephemeral=True)
                return
            embed.set_image(url=image_url)
        embed.set_footer(text=f"Posted by {interaction.user.display_name}")
        try:
            await self.channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message("I could not post the announcement in that channel.", ephemeral=True)
            return
        await interaction.response.send_message(f"Announcement sent to {self.channel.mention}.", ephemeral=True)

class CommunityTools(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._views_restored = False

    async def restore_role_panels(self):
        if self._views_restored:
            return
        self._views_restored = True
        for guild_id, channel_id, message_id, role_ids in get_role_panels():
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue
            roles = [guild.get_role(role_id) for role_id in role_ids]
            roles = [role for role in roles if role and not role.is_default() and not role.managed]
            if not roles:
                continue
            try:
                self.bot.add_view(RolePanelView(guild.id, roles), message_id=message_id)
            except (discord.HTTPException, discord.ClientException):
                continue

    @commands.Cog.listener()
    async def on_ready(self):
        await self.restore_role_panels()

    @app_commands.command(name="rolepanel", description="Create or replace the server role selection panel")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_roles=True)
    async def rolepanel(
        self,
        interaction: discord.Interaction,
        role1: discord.Role,
        role2: discord.Role | None = None,
        role3: discord.Role | None = None,
        role4: discord.Role | None = None,
        role5: discord.Role | None = None,
        role6: discord.Role | None = None,
        role7: discord.Role | None = None,
        role8: discord.Role | None = None,
        role9: discord.Role | None = None,
        role10: discord.Role | None = None,
    ):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("You need Manage Roles permission.", ephemeral=True)
            return
        roles = [role for role in (role1, role2, role3, role4, role5, role6, role7, role8, role9, role10) if role]
        bot_member = interaction.guild.me
        if bot_member is None:
            await interaction.response.send_message("I am not ready to manage roles yet.", ephemeral=True)
            return
        invalid = [role.name for role in roles if role.is_default() or role.managed or role >= bot_member.top_role]
        if invalid:
            await interaction.response.send_message(
                "I cannot manage these roles: " + ", ".join(invalid),
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="Choose your roles",
            description="Select the roles you want. Selecting again updates your choices.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Available roles", value="\n".join(role.mention for role in roles), inline=False)
        view = RolePanelView(interaction.guild.id, roles)
        await interaction.response.send_message(embed=embed, view=view)
        message = await interaction.original_response()
        save_role_panel(interaction.guild.id, interaction.channel_id, message.id, [role.id for role in roles])


    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or payload.member is None or payload.member.bot:
            return
        mapping = get_reaction_role(payload.guild_id, payload.message_id, str(payload.emoji))
        if not mapping:
            return
        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        role = guild.get_role(int(mapping["role_id"])) if guild else None
        if not member or not role or role.is_default() or role.managed:
            return
        if not guild.me or role >= guild.me.top_role:
            return
        try:
            await member.add_roles(role, reason="Aishu reaction role")
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None:
            return
        mapping = get_reaction_role(payload.guild_id, payload.message_id, str(payload.emoji))
        if not mapping:
            return
        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        role = guild.get_role(int(mapping["role_id"])) if guild else None
        if not member or member.bot or not role or role.is_default() or role.managed:
            return
        if not guild.me or role >= guild.me.top_role:
            return
        try:
            await member.remove_roles(role, reason="Aishu reaction role")
        except (discord.Forbidden, discord.HTTPException):
            pass


    @app_commands.command(name="reactionrole", description="Bind a reaction on an existing message to a role")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_roles=True)
    @app_commands.describe(channel="Channel containing the target message", message_id="ID of the target message", emoji="Unicode emoji or custom emoji markup", role="Role to assign")
    async def reactionrole(self, interaction: discord.Interaction, channel: discord.TextChannel, message_id: str, emoji: str, role: discord.Role):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("You need Manage Roles permission.", ephemeral=True)
            return
        if not message_id.isdigit():
            await interaction.response.send_message("Message ID must be numeric.", ephemeral=True)
            return
        bot_member = interaction.guild.me
        if role.is_default() or role.managed or bot_member is None or role >= bot_member.top_role:
            await interaction.response.send_message("I cannot manage that role. Move my role above it and choose a normal role.", ephemeral=True)
            return
        try:
            message = await channel.fetch_message(int(message_id))
            reaction_emoji = discord.PartialEmoji.from_str(emoji.strip())
            await message.add_reaction(reaction_emoji)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError):
            await interaction.response.send_message("I could not access that message or add that emoji reaction.", ephemeral=True)
            return
        add_reaction_role(interaction.guild_id, channel.id, message.id, str(reaction_emoji), role.id)
        await interaction.response.send_message("Reaction " + str(reaction_emoji) + " on that message now grants " + role.mention + ".", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())

    @app_commands.command(name="reactionrole_remove", description="Remove a reaction-role mapping")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_roles=True)
    async def reactionrole_remove(self, interaction: discord.Interaction, message_id: str, emoji: str):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_roles:
            await interaction.response.send_message("You need Manage Roles permission.", ephemeral=True)
            return
        if not message_id.isdigit():
            await interaction.response.send_message("Message ID must be numeric.", ephemeral=True)
            return
        try:
            normalized_emoji = str(discord.PartialEmoji.from_str(emoji.strip()))
        except ValueError:
            await interaction.response.send_message("Invalid emoji.", ephemeral=True)
            return
        removed = remove_reaction_role(interaction.guild_id, int(message_id), normalized_emoji)
        await interaction.response.send_message("Reaction-role mapping removed." if removed else "No matching reaction-role mapping was found.", ephemeral=True)

    @app_commands.command(name="announcement", description="Open the announcement builder")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(channel="Channel where the announcement will be posted")
    async def announcement(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("You need Manage Server permission.", ephemeral=True)
            return
        bot_member = interaction.guild.me
        if bot_member is None or not channel.permissions_for(bot_member).send_messages or not channel.permissions_for(bot_member).embed_links:
            await interaction.response.send_message("I need Send Messages and Embed Links permissions in that channel.", ephemeral=True)
            return
        await interaction.response.send_modal(AnnouncementModal(channel))

async def setup(bot: commands.Bot):
    await bot.add_cog(CommunityTools(bot))
