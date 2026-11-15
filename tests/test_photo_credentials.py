import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import cue_crate as app


class PhotoCredentialTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = self.root / "cue-crate-key"
        self.legacy = self.root / "legacy-key"
        self.auth = self.root / "auth.json"
        self.auth.write_text(json.dumps({"opencode-go": {"type": "api", "key": "shared-test-key"}}))
        self.original_auth = self.auth.read_bytes()
        self.patches = [
            patch.dict(os.environ, {}, clear=True),
            patch.object(app, "OPENCODE_GO_CONFIG_PATH", self.config),
            patch.object(app, "LEGACY_OPENCODE_GO_CONFIG_PATH", self.legacy),
            patch.object(app, "OPENCODE_AUTH_PATH", self.auth),
            patch.object(app.sys, "platform", "darwin"),
        ]
        for context in self.patches:
            context.start()
            self.addCleanup(context.stop)

    def tearDown(self):
        self.assertEqual(self.auth.read_bytes(), self.original_auth)

    def test_explicit_key_file_does_not_touch_keychain(self):
        self.config.write_text("dedicated-test-key\n")
        with patch.object(app.subprocess, "run") as keychain:
            self.assertEqual(app.read_opencode_go_key(str(self.config)), "dedicated-test-key")
            keychain.assert_not_called()

    def test_cue_specific_environment_has_priority(self):
        with patch.dict(os.environ, {"CUE_CRATE_OPENCODE_GO_API_KEY": "isolated-test-key", "OPENCODE_GO_API_KEY": "generic-test-key"}), patch.object(app.subprocess, "run") as keychain:
            self.assertEqual(app.read_opencode_go_key(), "isolated-test-key")
            keychain.assert_not_called()

    def test_dedicated_file_has_priority_over_shared_environment(self):
        self.config.write_text("dedicated-test-key\n")
        with patch.dict(os.environ, {"OPENCODE_GO_API_KEY": "generic-test-key"}), patch.object(app.subprocess, "run") as keychain:
            self.assertEqual(app.read_opencode_go_key(), "dedicated-test-key")
            keychain.assert_not_called()

    def test_dedicated_keychain_item_precedes_shared_auth(self):
        with patch.object(app.subprocess, "run", return_value=types.SimpleNamespace(returncode=0, stdout="keychain-test-key\n")) as keychain:
            self.assertEqual(app.read_opencode_go_key(), "keychain-test-key")
            self.assertIn("cue-crate.opencode-go-api-key", keychain.call_args.args[0])
            self.assertTrue(keychain.call_args.kwargs["capture_output"])

    def test_legacy_auth_is_only_read_when_no_dedicated_key_exists(self):
        with patch.object(app.subprocess, "run", return_value=types.SimpleNamespace(returncode=44, stdout="")):
            self.assertEqual(app.read_opencode_go_key(), "shared-test-key")


if __name__ == "__main__":
    unittest.main()
