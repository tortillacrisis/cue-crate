"""Real HTTP routing with fictional data and mocked mutation/provider boundaries."""

from contextlib import ExitStack
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import cue_crate as app
from local_http import CSRF_HEADER, LocalHTTPServer, MAX_JSON_BODY_BYTES


class LocalHTTPSecurityTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.object(app, "WORKSPACE_DIR", Path(root)))
        self.stack.enter_context(patch.object(app, "INBOX_DIR", Path(root) / "inbox"))
        self.stack.enter_context(patch.object(app, "load_profiles_config", return_value={}))
        self.stack.enter_context(patch.object(app, "load_catalog", return_value={"records": [
            {"id": "example-copy", "owner": "Example DJ", "artist": "Example Artist", "title": "Example Record"},
        ]}))
        self.saved = self.stack.enter_context(patch.object(app, "save_library_playback_source", return_value={"ok": True}))
        self.stack.enter_context(patch.object(app, "write_json", side_effect=AssertionError("No real writes in HTTP tests")))
        self.stack.enter_context(patch.object(app, "discogs_request", side_effect=AssertionError("No provider calls in HTTP tests")))
        self.stack.enter_context(patch.object(app, "spotify_api_request", side_effect=AssertionError("No provider calls in HTTP tests")))
        self.server = self.start_server(app.make_cue_crate_handler("Example DJ", "http://192.0.2.5", "phone-test-token", None))

    def start_server(self, handler, remote=False):
        class QuietHandler(handler):
            def log_message(self, *args): pass
            if remote:
                def is_loopback_client(self): return False
        server = LocalHTTPServer(("127.0.0.1", 0), QuietHandler)
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        def stop():
            server.shutdown()
            server.server_close()
            thread.join()
        self.addCleanup(stop)
        return server

    def request(self, method="GET", path="/api/library/catalog", headers=None, body=None, server=None):
        server = server or self.server
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def write(self, extra=None, body=None):
        headers = {CSRF_HEADER: self.server.desktop_csrf_token, "Content-Type": "application/json"}
        headers.update(extra or {})
        return self.request("POST", "/api/library/playback-sources", headers,
                            body if body is not None else json.dumps({"release_id": 10, "spotify_url": ""}))

    def test_local_bootstrap_is_uncached_and_read_requests_work(self):
        self.assertEqual(self.request()[0], 200)
        status, headers, body = self.request(path="/api/session")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(json.loads(body)["csrf_token"], self.server.desktop_csrf_token)

    def test_foreign_and_malformed_hosts_are_rejected(self):
        for host in ("untrusted.example", f"localhost.evil:{self.server.server_port}", "127.0.0.1:1", "user@127.0.0.1"):
            with self.subTest(host=host):
                self.assertEqual(self.request(headers={"Host": host})[0], 421)

    def test_explicit_localhost_alias_is_supported(self):
        host = f"localhost:{self.server.server_port}"
        self.assertEqual(self.request(headers={"Host": host, "Origin": f"http://{host}"})[0], 200)

    def test_foreign_origin_and_fetch_metadata_are_rejected(self):
        for headers in ({"Origin": "https://untrusted.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request(headers=headers)[0], 403)
                self.assertEqual(self.request(path="/api/session", headers=headers)[0], 403)

    def test_foreign_origin_write_never_reaches_mutation(self):
        self.assertEqual(self.write({"Origin": "https://untrusted.example"})[0], 403)
        self.saved.assert_not_called()

    def test_writes_require_current_desktop_capability(self):
        for token in ("", "wrong-token", "é"):
            with self.subTest(token=token):
                self.assertEqual(self.write({CSRF_HEADER: token})[0], 403)
        self.saved.assert_not_called()

    def test_verified_json_write_reaches_only_mocked_boundary(self):
        self.assertEqual(self.write({"Origin": f"http://127.0.0.1:{self.server.server_port}"})[0], 200)
        self.saved.assert_called_once_with(10, "")

    def test_simple_content_type_is_rejected_even_with_token(self):
        self.assertEqual(self.write({"Content-Type": "text/plain"})[0], 415)
        self.saved.assert_not_called()

    def test_json_size_and_framing_are_bounded_before_read(self):
        for extra, status in (({"Content-Length": "0"}, 413), ({"Content-Length": str(MAX_JSON_BODY_BYTES + 1)}, 413), ({"Content-Length": "-1"}, 400), ({"Transfer-Encoding": "chunked"}, 400)):
            with self.subTest(extra=extra):
                self.assertEqual(self.write(extra)[0], status)
        self.saved.assert_not_called()

    def test_restart_invalidates_old_capability(self):
        other = self.start_server(app.make_cue_crate_handler("Example DJ", "http://127.0.0.1", "other-phone-token", None))
        headers = {CSRF_HEADER: self.server.desktop_csrf_token, "Content-Type": "application/json"}
        self.assertEqual(self.request("POST", "/api/library/playback-sources", headers, "{}", server=other)[0], 403)

    def test_phone_scope_stays_separate_from_desktop(self):
        remote = self.start_server(app.make_cue_crate_handler("Example DJ", "http://192.0.2.5", "phone-test-token", None), remote=True)
        self.assertEqual(self.request(server=remote)[0], 403)
        self.assertEqual(self.request(path="/api/session", server=remote)[0], 403)
        self.assertEqual(self.request(path="/connect.html", server=remote)[0], 403)
        self.assertEqual(self.request(path="/api/mobile/catalog", server=remote)[0], 401)
        self.assertEqual(self.request(path="/api/mobile/catalog", headers={"X-Cue-Crate-Session": "phone-test-token"}, server=remote)[0], 200)
        # A desktop capability does not authenticate a phone request.
        self.assertEqual(self.request(path="/api/mobile/catalog", headers={CSRF_HEADER: remote.desktop_csrf_token}, server=remote)[0], 401)

    def test_authorized_phone_upload_needs_no_desktop_csrf_token(self):
        remote = self.start_server(app.make_cue_crate_handler("Example DJ", "http://192.0.2.5", "phone-test-token", None), remote=True)
        body = (b'--fixture-boundary\r\nContent-Disposition: form-data; name="upload_id"\r\n\r\nexample-upload\r\n'
                b'--fixture-boundary\r\nContent-Disposition: form-data; name="role"\r\n\r\nevidence\r\n'
                b'--fixture-boundary\r\nContent-Disposition: form-data; name="photo"; filename="fixture.jpg"\r\nContent-Type: image/jpeg\r\n\r\nfixture-image\r\n'
                b'--fixture-boundary--\r\n')
        headers = {
            "Host": f"192.0.2.5:{remote.server_port}", "Origin": f"http://192.0.2.5:{remote.server_port}",
            "X-Cue-Crate-Session": "phone-test-token", "Content-Type": "multipart/form-data; boundary=fixture-boundary",
        }
        with patch.object(app, "write_json", return_value=None):
            self.assertEqual(self.request("POST", "/api/mobile/upload", headers, body, server=remote)[0], 200)
        self.assertEqual((app.INBOX_DIR / "example-dj/example-upload/evidence.jpg").read_bytes(), b"fixture-image")

    def test_raw_files_and_head_cannot_bypass_static_allowlist(self):
        for path in ("/data/library/catalog.json", "/config/profiles.local.json", "/.git/config", "/cue_crate.py"):
            self.assertEqual(self.request(path=path)[0], 404)
            self.assertEqual(self.request("HEAD", path)[0], 405)

    def test_oauth_callback_allows_cross_site_navigation_but_still_checks_state(self):
        headers = {"Sec-Fetch-Site": "cross-site", "Origin": "https://accounts.spotify.com"}
        self.assertEqual(self.request(path="/api/spotify/callback?state=invalid&code=example", headers=headers)[0], 400)
        with patch.object(app, "complete_spotify_authorization", return_value="Example DJ") as complete:
            self.assertEqual(self.request(path="/api/spotify/callback?state=example&code=example", headers=headers)[0], 302)
            complete.assert_called_once()

    def test_legacy_services_have_bootstrap_and_filesystem_guards(self):
        for handler in (app.make_review_handler("Example DJ"), app.make_youtube_review_handler("Example DJ"), app.make_mobile_handler("Example DJ", "http://192.0.2.5", "phone-test-token")):
            server = self.start_server(handler)
            self.assertEqual(self.request(path="/api/session", server=server)[0], 200)
            self.assertEqual(self.request(path="/.git/config", server=server)[0], 404)
            self.assertEqual(self.request(headers={"Host": "untrusted.example"}, server=server)[0], 421)


if __name__ == "__main__":
    unittest.main()
