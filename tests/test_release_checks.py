import importlib.util
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("secret_guard", ROOT / "scripts/check_secrets.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class SecretGuardTests(unittest.TestCase):
    def test_credentials_are_reported_without_returning_their_values(self):
        value = "sk-" + "x" * 32
        found = guard.findings(value.encode())
        self.assertTrue(any(label == "provider key" for _line, label in found))
        self.assertNotIn(value, repr(found))

    def test_private_paths_and_safe_examples_are_distinguished(self):
        for name in (".env.local", "credentials.json", "spotify-oauth.json", "config/custom.local.json", "data/library/catalog.json"):
            self.assertTrue(guard.private_path(name), name)
        for name in (".env.example", "config/profiles.example.json", "data/README.md"):
            self.assertFalse(guard.private_path(name), name)

    def test_ignore_rules_cover_common_accidents_without_hiding_templates(self):
        for name in (".env.local", ".env.production", "spotify-oauth.json", "private-key.pem", "config/custom.local.json"):
            self.assertEqual(subprocess.run(["git", "check-ignore", "-q", "--no-index", name], cwd=ROOT).returncode, 0, name)
        for name in (".env.example", "config/profiles.example.json"):
            self.assertEqual(subprocess.run(["git", "check-ignore", "-q", "--no-index", name], cwd=ROOT).returncode, 1, name)


if __name__ == "__main__":
    unittest.main()
