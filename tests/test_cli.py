import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from photo_feed.cli import main

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def stored_album_urls():
    storage = ROOT / "shared-album-link-storage"
    urls = []
    if not storage.exists():
        return urls
    for path in storage.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in text.split():
                if token.startswith("http://") or token.startswith("https://"):
                    urls.append(token.strip())
    return urls


def assert_no_stored_links(test, text):
    for url in stored_album_urls():
        if url and url in text:
            test.fail("output contained a link stored in shared-album-link-storage")


class CliHelpTest(unittest.TestCase):
    def test_help_mentions_the_secret_and_does_not_read_albums(self):
        env = os.environ.copy()
        env.pop("PHOTO_FEED_URL", None)
        completed = subprocess.run(
            [sys.executable, "-m", "photo_feed", "--help"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("PHOTO_FEED_URL", completed.stdout)
        assert_no_stored_links(self, completed.stdout + completed.stderr)
        self.assertEqual(completed.stderr, "")


class CliFixtureTest(unittest.TestCase):
    def test_list_photos_reads_a_local_fixture_server(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading

        album = (FIXTURES / "google_album.html").read_bytes()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(album)))
                self.end_headers()
                self.wfile.write(album)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = os.environ.copy()
            env["PHOTO_FEED_URL"] = f"http://127.0.0.1:{port}/album"
            completed = subprocess.run(
                [sys.executable, "-m", "photo_feed", "list-photos"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual([item["id"] for item in payload["items"]], ["fixture-photo-1", "fixture-video-1"])
        assert_no_stored_links(self, completed.stdout + completed.stderr)

    def test_main_list_albums_with_env(self):
        previous = os.environ.get("PHOTO_FEED_URL")
        os.environ["PHOTO_FEED_URL"] = "https://photos.example.test/album"
        held = io.StringIO()
        try:
            with redirect_stdout(held):
                code = main(["list-albums"])
        finally:
            if previous is None:
                os.environ.pop("PHOTO_FEED_URL", None)
            else:
                os.environ["PHOTO_FEED_URL"] = previous
        self.assertEqual(code, 0)
        self.assertIn("photos.example.test", held.getvalue())
        assert_no_stored_links(self, held.getvalue())


if __name__ == "__main__":
    unittest.main()
