import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from photo_feed.errors import AlbumError
from photo_feed.net import download_to_file, fetch_text

FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "google_album.html").read_bytes()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        if self.path == "/browser-shell":
            agent = self.headers.get("User-Agent") or ""
            if agent.startswith("Mozilla"):
                body = b"<html><base href='https://photos.app.goo.gl/'></html>"
                self._send(body, "text/html")
                return
            self.send_response(302)
            location = f"http://127.0.0.1:{self.server.server_address[1]}/album"
            self.send_header("Location", location)
            self.end_headers()
            return
        if self.path == "/short":
            self.send_response(302)
            location = f"http://127.0.0.1:{self.server.server_address[1]}/album"
            self.send_header("Location", location)
            self.end_headers()
            return
        if self.path == "/consent":
            cookie = self.headers.get("Cookie") or ""
            if "CONSENT=" not in cookie:
                body = b"<html>https://consent.google.com/ml?continue=1</html>"
            else:
                body = FIXTURE
            self._send(body, "text/html; charset=utf-8")
            return
        if self.path == "/album":
            self._send(FIXTURE, "text/html; charset=utf-8")
            return
        if self.path == "/missing":
            self.send_error(404, "missing")
            return
        if self.path == "/file":
            body = b"not-a-real-photo"
            self._send(body, "image/jpeg")
            return
        if self.path == "/big":
            self._send(b"x" * 50, "image/jpeg")
            return
        self.send_error(404, "nope")

    def _send(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class NetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def test_plain_client_gets_the_album_instead_of_a_browser_shell(self):
        html = fetch_text(self.url("/browser-shell"))
        self.assertIn("FIXTURE_PHOTO_ONE", html)
        self.assertNotIn("photos.app.goo.gl", html)

    def test_fetch_follows_a_short_link_redirect(self):
        html = fetch_text(self.url("/short"))
        self.assertIn("FIXTURE_PHOTO_ONE", html)

    def test_fetch_retries_a_consent_page_once(self):
        html = fetch_text(self.url("/consent"))
        self.assertIn("FIXTURE_PHOTO_ONE", html)
        self.assertNotIn("consent.google.com", html)

    def test_missing_page_does_not_include_the_response_body(self):
        with self.assertRaises(AlbumError) as caught:
            fetch_text(self.url("/missing"))
        message = str(caught.exception)
        self.assertIn("404", message)
        self.assertNotIn("<html", message.lower())
        self.assertNotIn(self.url("/missing"), message)

    def test_download_writes_bytes_and_stops_when_the_file_is_too_large(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "photo.bin"
            content_type = download_to_file(self.url("/file"), dest)
            self.assertEqual(content_type, "image/jpeg")
            self.assertEqual(dest.read_bytes(), b"not-a-real-photo")

            too_big = Path(tmp) / "big.bin"
            with self.assertRaises(AlbumError):
                download_to_file(self.url("/big"), too_big, max_bytes=10)
            self.assertFalse(too_big.exists())


if __name__ == "__main__":
    unittest.main()
