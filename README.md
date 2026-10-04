# Aishu Bot

Aishu Bot is a multilingual Discord Community bot focused on moderation, verification, member profiles and server management.

## Supported languages

Member language is personal, not server-wide:
- Indonesia
- Tagalog
- English

Members choose with /language. Users with Manage Server receive administrative command responses in English.

## Community commands

Aishu is organized around four practical areas: **community, moderation, utility, and fun**. The goal is to cover common server needs without turning the bot into a command dump.

### Member
- /introduce — create or update Name, Date of birth, Age, Origin and City.
- /profile — view a member's self-declared introduction.
- /language — choose your personal bot language.
- /avatar — view a member avatar.
- /userinfo — useful public Discord account metadata.
- /serverinfo — basic server information.
- /stats — member/channel/role/boost statistics.
- /suggest — submit a community suggestion.
- /report — submit a private community report.
- /verify — run the configured verification check.
- /verificationinfo — public verification/account-age information.

### Utility
- /ping — bot latency.
- /botinfo — runtime and bot information.
- /membercount — human, bot and total member counts.
- /channelinfo — text-channel information.
- /roleinfo — role information.
- /permissions — inspect important effective permissions.

### Fun
- .8ball
- .coinflip
- .dice
- .choose
- .ship
- .rate
- .rps

### Leveling and Economy
- .level
- .balance
- .daily
- .leaderboard
- XP has a 60-second per-user cooldown.
- Daily rewards have a 24-hour cooldown.

### Moderation
- ,warn
- ,warnings
- ,clearwarnings
- ,timeout
- ,untimeout
- ,kick
- ,ban
- ,unban
- ,purge
- ,slowmode
- ,lock
- ,unlock
- ,automod
- ,antiraid

Moderation currently uses Discord command permissions plus hierarchy checks. The bot refuses to act on the server owner, equal/higher roles, or members above the bot's highest role.

Moderation actions can be written to the configured moderation-log channel.

### Verification
- /verification setup
- /verification panel
- /verification status

The verification system can check useful Discord metadata such as account creation time, account age, server join time and bot status. It does not request private information such as email, phone number, IP address or passwords.

Administrators can configure:
- verified role
- unverified role
- minimum account age
- enabled/disabled state

### Welcome and Goodbye
- /welcome setup
- /welcome test
- /goodbye setup
- /goodbye test

Supported placeholders:
- {user}
- {username}
- {server}
- {member_count}

New members can also receive a configured autorole.

### Tickets
- /ticket setup
- /ticket panel
- /ticket close
- /ticket claim
- /ticket rename
- /ticket add
- /ticket remove

Ticket channels are private and can use a support role.

### Birthday
- /birthday set
- /birthday view
- /birthday remove
- /birthday channel
- /birthday today

Only month and day are stored for birthdays.

### Suggestions and reports
- /suggestion approve
- /suggestion deny
- /reports close

## Server configuration
- /config channel
- /config autorole
- /config view

Complex administration is intended to move to the private web dashboard later.

## Custom Automod

- ,automod — show current configuration.
- ,automod enable / disable
- ,automod spam on|off [messages] [seconds]
- ,automod duplicates on|off [messages] [seconds]
- ,automod mentions on|off [maximum]
- ,automod links on|off
- ,automod invites on|off
- ,automod keywords add/remove
- ,automod action delete|warn|timeout [minutes]

Custom automod is disabled by default per server. Rule configuration is stored in SQLite; rate tracking stays in memory.

## Anti-Raid

- ,antiraid — show status.
- ,antiraid enable / disable
- ,antiraid threshold [joins] [seconds]
- ,antiraid duration [seconds]
- ,antiraid lock / unlock

Anti-raid is disabled by default per server. Automatic lockdown only changes channels whose @everyone send_messages overwrite is unset, so pre-existing explicit channel rules are not overwritten.

## Community Tools

- /rolepanel — create a persistent role-selection panel.
- /announcement — open an embed announcement builder with optional image URL.

## Quality and safety

- / commands are used for simple utility and community tools.
- , commands are reserved for moderation and security controls.
- . commands are used for games, fun, leveling and economy.
- Bot responses disable automatic mention parsing to reduce mention-injection risk.
- Moderation actions are protected by Discord permissions and role-hierarchy checks.
- Important moderation actions can be sent to a configured log channel.
- User-submitted reports and suggestions are routed to configured staff channels.
- No passwords, tokens, IP addresses, email addresses, or other Discord credentials are requested.
- Discord's native AutoMod can still be used alongside Aishu as an additional safety layer.
- Message Content Intent is required for prefix commands and custom message automod.
- Server Members Intent is required for member join detection and other member-based features.

## Verification

CI runs on pushes and pull requests and currently performs dependency installation plus Python compilation checks.

## Permissions

Member commands are available to normal members.

Moderation and configuration commands use Discord permissions such as:
- Manage Messages
- Moderate Members
- Kick Members
- Ban Members
- Manage Channels
- Manage Server

The future web dashboard will be restricted to two explicitly authorized Discord user IDs.

## Requirements

- Python 3.10+
- discord.py 2.6+
- python-dotenv

Install:

    pip install -r requirements.txt

Copy .env.example to .env and set DISCORD_TOKEN.

For member join/leave events and autorole/verification handling, enable the Server Members Intent in the Discord Developer Portal.

Never commit .env or a bot token.

## Run

    python bot.py

Aishu creates a local SQLite database named aishu.db automatically.

## Private web dashboard

The dashboard lives in dashboard/ and is designed for Vercel.

Vercel project settings:
- Root Directory: dashboard
- Framework: Next.js

Configure dashboard/.env using the Discord OAuth application values and the two authorized Discord user IDs.

Required dashboard variables:
- DISCORD_CLIENT_ID
- DISCORD_CLIENT_SECRET
- DISCORD_REDIRECT_URI
- ADMIN_USER_ID_1
- ADMIN_USER_ID_2
- ADMIN_GUILD_ID
- DASHBOARD_SESSION_SECRET

In the Discord Developer Portal, add the exact DISCORD_REDIRECT_URI as an OAuth2 redirect URL and request the identify and guilds scopes.

The dashboard currently provides the secure login and admin UI shell. A bot API bridge will connect the dashboard controls to the live Discord configuration; until that bridge is added, the dashboard does not pretend to change server settings.

## Project structure

    bot.py
    cogs/
    utils/
    .env.example
    requirements.txt

The bot is intentionally split into cogs so Community features can grow without turning bot.py into one large file.


## Security / Disaster Recovery

### Automod v2
- Role/channel exemptions
- Moderator exemptions
- Escalation mode: delete -> warn -> timeout
- Safer keyword matching
- Action cooldown and detailed mod-log

### Anti-Raid v2
- Join-spike detection
- New-account threshold
- Bot-join burst detection
- User whitelist
- Permission-preserving lockdown

### Moderation Cases
- Case IDs for moderation actions
- `,case <id>`
- `,history @member`
- Persistent SQLite case history

### Server Backup / Nuke Recovery
- Rolling pre-raid snapshots every 15 minutes
- Server name, roles, role permissions/hierarchy, channels/categories, overwrites
- Member role assignments for members still present
- Recent message/embed backup per text channel
- Automatic nuke marker after rapid channel/role deletion
- `,server backups`
- `,server backup`
- `,server restore <backup_id>`

Discord does not allow a bot to forcibly move members to another server. Members who are no longer present cannot have their roles restored there automatically. Message attachments and original message timestamps are also not guaranteed to be reproducible.
