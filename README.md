# Aishu Bot

Aishu Bot is a multilingual Discord Community bot focused on moderation, verification, member profiles and server management.

## Supported languages

Member language is personal, not server-wide:
- Indonesia
- Tagalog
- English

Members choose with /language. Users with Manage Server receive administrative command responses in English.

## Community commands

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

### Moderation
- /warn
- /warnings
- /clearwarnings
- /timeout
- /untimeout
- /kick
- /ban
- /unban
- /purge
- /slowmode
- /lock
- /unlock

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
