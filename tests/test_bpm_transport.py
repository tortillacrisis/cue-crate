import io
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import cue_crate as app


class BPMTransportTests(unittest.TestCase):
    def test_key_is_a_header_not_a_query_parameter(self):
        with patch.object(app, "urlopen", return_value=io.BytesIO(b'{"search": []}')) as opened:
            self.assertEqual(app.getsongbpm_request("/search/", "example-key", {"lookup": "Example Song", "api_key": "do-not-include"}), {"search": []})
        request = opened.call_args.args[0]
        self.assertNotIn("api_key", request.full_url)
        self.assertNotIn("example-key", request.full_url)
        self.assertEqual(request.get_header("X-api-key"), "example-key")

    def test_error_responses_cannot_echo_a_credential(self):
        error = HTTPError("https://api.getsong.co/search/", 401, "Unauthorized", {}, io.BytesIO(b'echoed example-key'))
        with patch.object(app, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 401") as caught:
                app.getsongbpm_request("/search/", "example-key", {})
        self.assertNotIn("example-key", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    def test_transport_error_details_are_not_exposed(self):
        with patch.object(app, "urlopen", side_effect=URLError("echoed example-key")):
            with self.assertRaises(RuntimeError) as caught:
                app.getsongbpm_request("/search/", "example-key", {})
        self.assertNotIn("example-key", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
