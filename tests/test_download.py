"""Saving album files stays on this computer and inside the chosen folder."""

import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from photo_feed.download import download_items, fetch_bytes
from photo_feed.errors import PhotoFeedError
from photo_feed.google_photos import MediaItem


def _item(filename, url, media_id="fixture-photo-1"):
    return MediaItem(
        id=media_id,
        filename=filename,
        kind="photo",
        url=url,
        width=1,
        height=1,
        created_at=None,
        added_at=None,
        size_bytes=None,
    )


class DownloadItemsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self.tmp.name) / "downloads"

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_the_bytes_under_a_safe_filename(self):
        item = _item("../../picnic.jpg", "https://cdn.example.test/picnic.jpg")

        def fetch(url):
            self.assertEqual(url, item.url)
            return b"not-a-real-photo", {"Content-Type": "image/jpeg"}

        saved = download_items([item], self.dest, fetch_bytes=fetch)

        written = self.dest / "picnic.jpg"
        self.assertEqual(written.read_bytes(), b"not-a-real-photo")
        self.assertEqual(saved, [{"id": "fixture-photo-1", "path": str(written), "bytes": 16}])
        self.assertFalse((self.dest.parent / "picnic.jpg").exists())

    def test_content_disposition_name_is_used(self):
        item = _item("picnic.jpg", "https://cdn.example.test/picnic.jpg")

        def fetch(url):
            return b"xyz", {"Content-Disposition": "attachment; filename=\"from-server.png\""}

        download_items([item], self.dest, fetch_bytes=fetch)
        self.assertEqual((self.dest / "from-server.png").read_bytes(), b"xyz")
        self.assertFalse((self.dest / "picnic.jpg").exists())

    def test_duplicate_names_do_not_overwrite(self):
        items = [
            _item("picnic.jpg", "https://cdn.example.test/a", "a"),
            _item("picnic.jpg", "https://cdn.example.test/b", "b"),
        ]

        def fetch(url):
            return url.encode("utf-8"), {}

        download_items(items, self.dest, fetch_bytes=fetch)
        self.assertEqual((self.dest / "picnic.jpg").read_bytes(), b"https://cdn.example.test/a")
        self.assertEqual((self.dest / "picnic-2.jpg").read_bytes(), b"https://cdn.example.test/b")

    def test_non_web_link_is_refused(self):
        item = _item("picnic.jpg", "file:///tmp/picnic.jpg")
        with self.assertRaises(PhotoFeedError):
            download_items([item], self.dest, fetch_bytes=lambda url: (_ for _ in ()).throw(AssertionError("fetched")))
        self.assertFalse(self.dest.exists())


class FetchBytesTests(unittest.TestCase):
    def test_reads_a_local_http_response(self):
        payload = b"fixture-bytes"

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = payload
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, fmt, *args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            body, headers = fetch_bytes(f"http://127.0.0.1:{port}/picnic.jpg")
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(body, payload)
        self.assertEqual(headers["Content-Type"], "image/jpeg")


if __name__ == "__main__":
    unittest.main()
