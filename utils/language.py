from utils.database import get_language, set_language

LANGUAGES = {"id": "Indonesia", "tl": "Tagalog", "en": "English"}

TEXT = {
    "id": {
        "language_changed": "Bahasa pribadi kamu sekarang **{language}**.",
        "no_profile": "Kamu belum membuat perkenalan. Gunakan /introduce.",
        "profile": "Perkenalan {user}",
        "name": "Nama", "birthdate": "Tanggal lahir", "age": "Umur",
        "origin": "Asal", "city": "Kota", "saved": "Perkenalan kamu berhasil disimpan.",
        "not_in_server": "Command ini hanya bisa digunakan di server.",
    },
    "tl": {
        "language_changed": "Ang personal mong wika ay **{language}** na ngayon.",
        "no_profile": "Wala ka pang pagpapakilala. Gamitin ang /introduce.",
        "profile": "Pagpapakilala ni {user}",
        "name": "Pangalan", "birthdate": "Petsa ng kapanganakan", "age": "Edad",
        "origin": "Pinagmulan", "city": "Lungsod", "saved": "Matagumpay na na-save ang iyong pagpapakilala.",
        "not_in_server": "Magagamit lang ang command na ito sa server.",
    },
    "en": {
        "language_changed": "Your personal language is now **{language}**.",
        "no_profile": "You do not have an introduction yet. Use /introduce.",
        "profile": "{user}'s Introduction",
        "name": "Name", "birthdate": "Date of birth", "age": "Age",
        "origin": "Origin", "city": "City", "saved": "Your introduction has been saved.",
        "not_in_server": "This command can only be used in a server.",
    },
}

def interaction_language(interaction) -> str:
    if interaction.guild is not None and interaction.user.guild_permissions.manage_guild:
        return "en"
    if interaction.guild_id is None:
        return "en"
    return get_language(interaction.guild_id, interaction.user.id)
