import tempfile
import unittest
from pathlib import Path

from utils import database


class DatabaseFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_path = database.DB_PATH
        database.DB_PATH = Path(self.temp_dir.name) / "test.db"
        connection = database.connect()
        connection.close()

    def tearDown(self):
        database.DB_PATH = self.original_path
        self.temp_dir.cleanup()

    def test_per_guild_automod_and_antiraid_configs(self):
        database.set_automod_config(101, {"enabled": True, "keywords": ["example"]})
        database.set_antiraid_config(101, {"enabled": True, "joins": 8})
        self.assertEqual(database.get_automod_config(101)["keywords"], ["example"])
        self.assertEqual(database.get_antiraid_config(101)["joins"], 8)
        self.assertEqual(database.get_automod_config(202), {})

    def test_economy_persists_xp_cooldown_and_daily_cap(self):
        profile = database.get_economy(101, 303)
        self.assertEqual(profile["xp"], 0)
        database.update_economy(101, 303, xp=25, level=1, last_xp_at=123.0, xp_day="2026-10-04", xp_daily=25)
        profile = database.get_economy(101, 303)
        self.assertEqual(profile["xp"], 25)
        self.assertEqual(profile["last_xp_at"], 123.0)
        self.assertEqual(profile["xp_daily"], 25)

    def test_reaction_role_mapping_round_trip(self):
        database.add_reaction_role(101, 404, 505, "🔥", 606)
        mapping = database.get_reaction_role(101, 505, "🔥")
        self.assertEqual(mapping["role_id"], 606)
        self.assertTrue(database.remove_reaction_role(101, 505, "🔥"))
        self.assertIsNone(database.get_reaction_role(101, 505, "🔥"))

    def test_case_and_server_backup_storage(self):
        case_id = database.create_case(101, "warn", 303, 707, "test", "2026-10-04T00:00:00+00:00")
        self.assertEqual(database.get_case(101, case_id)["action"], "warn")
        backup_id = database.create_server_backup(101, "test snapshot", {"guild": {"name": "test"}})
        backup = database.get_latest_server_backup(101)
        self.assertEqual(backup[0], backup_id)
        self.assertEqual(backup[3]["guild"]["name"], "test")


if __name__ == "__main__":
    unittest.main()
