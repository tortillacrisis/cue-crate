import unittest

import cue_crate as app
from scripts.serve_demo import demo_workspace


class DemoTests(unittest.TestCase):
    def test_demo_is_temporary_and_never_uses_real_provider_credentials(self):
        original_catalog, original_config = app.CATALOG_PATH, app.PROFILES_CONFIG_PATH
        with demo_workspace() as root:
            self.assertTrue(app.CATALOG_PATH.is_relative_to(root))
            self.assertTrue(app.PROFILES_CONFIG_PATH.is_relative_to(root))
            self.assertEqual(len(app.load_catalog()["records"]), 3)
            self.assertIsNone(app.read_token(None, "DJ One"))
            self.assertIsNone(app.read_spotify_client_id())
            self.assertIsNone(app.read_opencode_go_key())
            with self.assertRaisesRegex(ValueError, "disabled"):
                app.discogs_request("/oauth/identity")
        self.assertFalse(root.exists())
        self.assertEqual(app.CATALOG_PATH, original_catalog)
        self.assertEqual(app.PROFILES_CONFIG_PATH, original_config)


if __name__ == "__main__":
    unittest.main()
