import argparse
import copy
import io
import json
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

import cue_crate as app
import photo_analysis as photos


def model(model_id="kimi-k3.1-pro", images=True):
    return {
        "id": model_id, "name": model_id,
        "modalities": {"input": ["text", "image/jpeg"] if images else ["text"]},
        "capabilities": {"temperature": False, "structured_output": True, "reasoning": {"effort": ["low", "high", "max"]}},
        "api": {"chat-completions": {"base_url": photos.GO_CHAT_BASE_URL}},
        "limit": {"output": 65536},
    }


class PhotoSettingsTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"data": [model(), model("mimo-v2.6-flash"), model("text-only", images=False)]}

    def test_default_uses_current_go_model(self):
        settings = photos.photo_model_settings(self.catalog, {})
        self.assertEqual(settings["model"], "mimo-v2.6-flash")
        self.assertEqual(settings["max_tokens"], 8192)
        self.assertEqual(settings["max_image_dimension"], 2048)

    def test_local_config_and_explicit_overrides(self):
        config = {"provider": "mimo", "max_tokens": 12000, "max_image_dimension": 3072}
        settings = photos.photo_model_settings(self.catalog, config)
        self.assertEqual(settings["model"], "mimo-v2.6-flash")
        explicit = photos.photo_model_settings(self.catalog, config, provider="kimi", max_tokens=4096)
        self.assertEqual(explicit["model"], "kimi-k3.1-pro")
        self.assertEqual(explicit["max_tokens"], 4096)

    def test_retired_model_fails_before_upload(self):
        with self.assertRaisesRegex(photos.PhotoProviderError, "not in the current Go catalog"):
            photos.photo_model_settings(self.catalog, {}, model_id="kimi-k2.6")

    def test_text_only_model_is_rejected(self):
        with self.assertRaisesRegex(photos.PhotoProviderError, "does not advertise image input"):
            photos.photo_model_settings(self.catalog, {}, model_id="text-only")

    def test_no_pay_as_you_go_or_third_party_endpoint(self):
        unsafe = copy.deepcopy(self.catalog)
        unsafe["data"][0]["api"]["chat-completions"]["base_url"] = "https://opencode.ai/inference/openai/v1"
        with self.assertRaisesRegex(photos.PhotoProviderError, "will not silently change routes"):
            photos.photo_model_settings(unsafe, {}, provider="kimi")

    def test_native_only_models_are_not_silently_translated(self):
        native = model()
        native["api"] = {"messages": {"base_url": "https://opencode.ai/inference/go/anthropic/v1"}}
        with self.assertRaises(photos.PhotoProviderError):
            photos.photo_model_settings({"data": [native]}, {}, provider="kimi")

    def test_reasoning_model_does_not_get_unsupported_temperature(self):
        settings = photos.photo_model_settings(self.catalog, {}, provider="kimi")
        options = photos.completion_options(settings, "JSON only", [{"type": "text", "text": "read label"}])
        self.assertNotIn("temperature", options)
        self.assertEqual(options["reasoning_effort"], "low")
        self.assertEqual(options["response_format"], {"type": "json_object"})

    def test_only_advertised_request_options_are_sent(self):
        supported = model()
        supported["capabilities"] = {"temperature": True, "reasoning": {"supported": True}}
        settings = photos.photo_model_settings({"data": [supported]}, {}, provider="kimi")
        options = photos.completion_options(settings, "JSON only", [])
        self.assertEqual(options["temperature"], 0)
        self.assertNotIn("reasoning_effort", options)
        self.assertNotIn("response_format", options)

    def test_bad_settings_fail_cleanly(self):
        for config in ({"provider": []}, {"max_tokens": 1}, {"max_tokens": "wrong"}, {"max_image_dimension": 400}):
            with self.subTest(config=config), self.assertRaises(photos.PhotoProviderError):
                photos.photo_model_settings(self.catalog, config)


class ModelCatalogTests(unittest.TestCase):
    def test_fresh_cache_requires_no_network_or_key(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "models.json"
            path.write_text(json.dumps({"fetched_at": time.time(), "data": [model()]}))
            with patch.object(photos, "urlopen") as request:
                self.assertEqual(photos.load_model_catalog(path)["data"][0]["id"], "kimi-k3.1-pro")
                request.assert_not_called()

    def test_refresh_uses_public_go_catalog_and_user_agent(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "models.json"
            body = io.BytesIO(json.dumps({"data": [model()]}).encode())
            with patch.object(photos, "urlopen", return_value=body) as request:
                photos.load_model_catalog(path, refresh=True)
                outgoing = request.call_args.args[0]
                self.assertEqual(outgoing.full_url, photos.GO_MODELS_URL)
                self.assertIn("User-agent", outgoing.headers)
                self.assertNotIn("Authorization", outgoing.headers)
            self.assertTrue(path.exists())

    def test_malformed_catalog_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with patch.object(photos, "urlopen", return_value=io.BytesIO(b"[]")):
                with self.assertRaises(photos.PhotoProviderError):
                    photos.load_model_catalog(Path(root) / "models.json", refresh=True)


class IntakeSafetyTests(unittest.TestCase):
    def test_one_label_photo_without_cover_or_identifiers_is_valid_intake(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root / "a-label.jpg").write_bytes(b"fixture")
            metadata = {"upload_id": "label-only", "files": {"evidence": {"filename": "a-label.jpg"}}}
            settings = {"provider": "mimo", "model": "mimo-v2.6-flash", "max_image_dimension": 2048}
            args = argparse.Namespace(owner="test-owner", api_key_file=None, upload_id="label-only", refresh=False)
            response = json.dumps({"artist": "Example Artist", "title": "Example Side", "catalog_number": None, "barcode": None, "confidence": "medium"})
            with patch.object(app, "intake_bundle_for", return_value=(root, metadata)), patch.object(app, "person_workspace_path", side_effect=lambda owner, name: root / name), patch.object(app, "read_opencode_go_key", return_value="fixture-key"), patch.object(app, "configured_photo_settings", return_value=settings), patch.object(app, "image_data_url", return_value="data:image/jpeg;base64,AA=="), patch.object(app, "photo_completion", return_value=response) as complete, patch.object(app, "load_catalog", return_value={"records": []}), patch.object(app, "build_review", return_value={"items": []}):
                app.analyse_one_intake(args)
                images = [part for part in complete.call_args.args[3] if part["type"] == "image_url"]
                self.assertEqual(len(images), 1)
            saved = json.loads((root / "intake-review.json").read_text())["items"]
            self.assertEqual(len(saved), 1)
            self.assertEqual(list(saved[0]["views"]), ["evidence"])
            self.assertIsNone(saved[0]["observed"]["catalog_number"])
            self.assertEqual(saved[0]["status"], "unreviewed")

    def test_pending_mode_skips_existing_analysis_and_obeys_limit(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            inbox = root / "inbox"
            for name in ("a-old", "b-new", "c-new"):
                (inbox / name).mkdir(parents=True)
                (inbox / name / "intake.json").write_text("{}")
            review_path = root / "review.json"
            review_path.write_text(json.dumps({"items": [{"upload_id": "a-old", "status": "confirmed"}]}))
            args = argparse.Namespace(owner="test-owner", all_pending=True, upload_id=None, refresh=False, limit=1)
            with patch.object(app, "person_inbox_dir", return_value=inbox), patch.object(app, "person_workspace_path", return_value=review_path), patch.object(app, "analyse_one_intake") as analyse:
                app.command_analyse_intake(args)
                self.assertEqual(analyse.call_count, 1)
                self.assertEqual(analyse.call_args.args[0].upload_id, "b-new")

    def test_pending_and_refresh_cannot_be_combined(self):
        args = argparse.Namespace(owner="test-owner", all_pending=True, upload_id=None, refresh=True, limit=None)
        with self.assertRaisesRegex(SystemExit, "cannot be combined"):
            app.command_analyse_intake(args)

    def test_legacy_photo_command_cannot_overwrite_existing_drafts(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            candidates = root / "photo-candidates.json"
            candidates.write_text('{"photos": [{"path": "saved.jpg"}]}')
            args = argparse.Namespace(owner="test-owner", photo_dir=str(root), resume=False, replace_candidates=False)
            with patch.object(app, "person_workspace_path", return_value=candidates), patch.object(app, "read_opencode_go_key") as key:
                with self.assertRaisesRegex(SystemExit, "Existing photo candidates are protected"):
                    app.command_analyse_photos(args)
                key.assert_not_called()
            self.assertIn("saved.jpg", candidates.read_text())

    def test_non_object_json_fails_with_clear_message(self):
        with self.assertRaisesRegex(SystemExit, "did not contain a record object"):
            app.parse_model_json("[]", "test-bundle")


class PhotoRequestTests(unittest.TestCase):
    def setUp(self):
        self.settings = photos.photo_model_settings({"data": [model()]}, {}, provider="kimi")
        self.client = Mock()
        self.sdk = types.ModuleType("openai")
        self.sdk.APIError = type("APIError", (Exception,), {})
        self.sdk.APITimeoutError = type("APITimeoutError", (self.sdk.APIError,), {})
        self.sdk.OpenAI = Mock(return_value=self.client)

    def test_truthful_user_agent_and_stable_session_header(self):
        self.client.chat.completions.create.return_value = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='{"artist":"Example"}'), finish_reason="stop")]
        )
        with patch.dict("sys.modules", {"openai": self.sdk}):
            for _ in range(2):
                self.assertIn("Example", photos.complete_photo("test-key", self.settings, "JSON only", []))
        for call in self.sdk.OpenAI.call_args_list:
            headers = call.kwargs["default_headers"]
            self.assertIn("cue-crate/", headers["User-Agent"])
            self.assertEqual(headers["x-opencode-session"], self.settings["session_id"])
            self.assertEqual(call.kwargs["max_retries"], 0)
            self.assertEqual(call.kwargs["base_url"], photos.GO_CHAT_BASE_URL)

    def test_expired_key_is_actionable_without_automatic_fallback(self):
        error = self.sdk.APIError("expired")
        error.status_code = 401
        error.body = {"code": "api_key_expired"}
        self.client.chat.completions.create.side_effect = error
        with patch.dict("sys.modules", {"openai": self.sdk}):
            with self.assertRaisesRegex(photos.PhotoProviderError, "Create a replacement key"):
                photos.complete_photo("test-key", self.settings, "JSON only", [])
        self.assertEqual(self.client.chat.completions.create.call_count, 1)

    def test_empty_reasoning_only_response_does_not_become_candidate(self):
        self.client.chat.completions.create.return_value = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=None), finish_reason="length")]
        )
        with patch.dict("sys.modules", {"openai": self.sdk}):
            with self.assertRaisesRegex(photos.PhotoProviderError, "No candidate was saved"):
                photos.complete_photo("test-key", self.settings, "JSON only", [])


if __name__ == "__main__":
    unittest.main()
