"""Trusted-local HTTP boundaries shared by the unified and legacy servers."""

import http.server
import ipaddress
import json
import secrets
from urllib.parse import urlparse


CSRF_HEADER = "X-Cue-Crate-CSRF"
MAX_JSON_BODY_BYTES = 2 * 1024 * 1024
STATIC_ASSETS = {
    "/viewer.html", "/quick-crate.html", "/review.html", "/taste-profile.html",
    "/youtube-review.html", "/playlists.html", "/mobile.html", "/connect.html",
    "/app.css", "/app.js",
}


class LocalHTTPServer(http.server.ThreadingHTTPServer):
    def __init__(self, *args, **kwargs):
        self.desktop_csrf_token = secrets.token_urlsafe(32)
        super().__init__(*args, **kwargs)


class LocalRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Reject rebinding/cross-origin traffic before any application dispatch."""

    advertised_host = ""
    timeout = 15

    def is_loopback_client(self):
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:
            return False

    def reject_request(self, message, status=403):
        body = json.dumps({"error": message}).encode("utf-8")
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        return False

    def parse_request(self):
        if not super().parse_request():
            return False
        try:
            target = urlparse(self.path)
        except ValueError:
            return self.reject_request("Invalid local request URL.", 400)
        if target.scheme or target.netloc or not self.path.startswith("/"):
            return self.reject_request("Use a local Cue Crate URL.", 400)
        port = self.server.server_port
        hosts = {"127.0.0.1", "localhost", "[::1]"}
        if self.advertised_host:
            hosts.add(self.advertised_host.lower())
        allowed = {f"{host}:{port}" for host in hosts}
        if port == 80:
            allowed.update(hosts)
        host_headers = self.headers.get_all("Host", [])
        if len(host_headers) != 1 or host_headers[0].lower() not in allowed:
            return self.reject_request("This Host is not a Cue Crate address.", 421)
        origins = self.headers.get_all("Origin", [])
        if len(origins) > 1:
            return self.reject_request("Use a single request origin.", 400)
        origin = self.headers.get("Origin")
        callback = target.path == "/api/spotify/callback" and self.command == "GET"
        if not callback:
            if origin is not None and origin != f"http://{host_headers[0].lower()}":
                return self.reject_request("Cross-origin Cue Crate requests are not allowed.")
            if target.path.startswith("/api/") and self.headers.get("Sec-Fetch-Site") not in (None, "same-origin", "none"):
                return self.reject_request("Open this API from Cue Crate itself.")
        mobile = target.path.startswith("/api/mobile/")
        if target.path.startswith("/api/") and not mobile and not self.is_loopback_client():
            return self.reject_request("This API is available only on the serving computer.")
        if self.command == "POST" and not mobile:
            supplied = self.headers.get(CSRF_HEADER, "")
            expected = getattr(self.server, "desktop_csrf_token", "")
            if not expected or not supplied.isascii() or not secrets.compare_digest(supplied, expected):
                return self.reject_request("Local session expired or missing. Reload Cue Crate before saving.")
            if self.headers.get_content_type() != "application/json":
                return self.reject_request("Desktop writes require application/json.", 415)
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
                return self.reject_request("A single valid Content-Length is required.", 400)
            length = int(lengths[0])
            if not 0 < length <= MAX_JSON_BODY_BYTES:
                return self.reject_request("JSON request is empty or too large.", 413)
        return True

    def serve_desktop_session(self):
        if urlparse(self.path).path != "/api/session":
            return False
        # parse_request already enforces loopback, Host, Origin, and Fetch Metadata.
        body = json.dumps({"csrf_token": self.server.desktop_csrf_token}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)
        return True

    def do_GET(self):
        if self.serve_desktop_session():
            return
        path = urlparse(self.path).path
        if path not in STATIC_ASSETS or (path == "/connect.html" and not self.is_loopback_client()):
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):
        # Never inherit SimpleHTTPRequestHandler's unrestricted filesystem route.
        self.send_error(405, "Use GET for Cue Crate resources.")
