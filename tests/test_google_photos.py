"""Parse a saved Google Photos share page that contains no real album."""

import gzip
import unittest
from pathlib import Path

from photo_feed.errors import PhotoFeedError
from photo_feed.google_photos import fetch_html, parse_shared_album_html

FIXTURE = Path(__file__).parent / "fixtures" / "google_share_page.html"


class ParseSharedAlbumTests(unittest.TestCase):
    def test_fixture_page_lists_photo_and_video(self):
        listing = parse_shared_album_html(FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(listing.album_id, "fixture-album")
        self.assertEqual(listing.title, "Picnic")
        self.assertFalse(listing.truncated)
        self.assertEqual(
            [item.as_dict() for item in listing.items],
            [
                {
                    "id": "fixture-photo-1",
                    "filename": "picnic.jpg",
                    "kind": "photo",
                    "url": "https://cdn.example.test/picnic.jpg",
                    "width": 800,
                    "height": 600,
                    "created_at": "2023-11-14T22:13:20Z",
                    "added_at": "2023-11-15T22:13:20Z",
                    "size_bytes": 2048,
                },
                {
                    "id": "fixture-video-1",
                    "filename": "clip.mp4",
                    "kind": "video",
                    "url": "https://cdn.example.test/clip.mp4",
                    "width": 1920,
                    "height": 1080,
                    "created_at": "2023-11-14T23:13:20Z",
                    "added_at": "2023-11-15T22:13:20Z",
                    "size_bytes": None,
                },
            ],
        )

    def test_continuation_token_marks_the_list_as_truncated(self):
        html = """
        <script>AF_initDataCallback({key: 'ds:1', hash: '1', data:[null,[
          ["only",["https://cdn.example.test/one.jpg",10,10],1700000000000,"t",0,1700086400000]
        ],"more-items",["alb","Day"]], sideChannel: {}});</script>
        """
        listing = parse_shared_album_html(html)
        self.assertTrue(listing.truncated)
        self.assertEqual(listing.title, "Day")
        self.assertEqual(len(listing.items), 1)

    def test_function_return_wrapper_is_parsed(self):
        html = """
        AF_initDataCallback({key: 'ds:1', hash: '1', data:function(){return [null,[
          ["wrapped",["https://cdn.example.test/wrapped.jpg",4,5],1700000000000,"t",0,1700086400000]
        ],"",["alb","Wrapped"]]}, sideChannel: {}});
        """
        listing = parse_shared_album_html(html)
        self.assertEqual(listing.items[0].id, "wrapped")
        self.assertEqual(listing.title, "Wrapped")

    def test_plain_image_url_fallback_uses_a_direct_file_link(self):
        # Token is made up. It is not a photo from anyone's album.
        html = "<html>https://lh3.googleusercontent.com/pw/synthetic-fixture-token=w100-h100</html>"
        listing = parse_shared_album_html(html)
        self.assertEqual(len(listing.items), 1)
        item = listing.items[0]
        self.assertEqual(item.kind, "photo")
        self.assertEqual(
            item.url,
            "https://lh3.googleusercontent.com/pw/synthetic-fixture-token=d",
        )
        self.assertTrue(item.id)

    def test_empty_page_explains_link_sharing(self):
        with self.assertRaises(PhotoFeedError) as caught:
            parse_shared_album_html("<html><body>Sign in to Google Photos</body></html>")
        message = str(caught.exception)
        self.assertIn("Create link", message)
        self.assertNotIn("Sign in to Google Photos", message)

    def test_fetch_html_reads_the_response_body(self):
        seen = {}

        class Response:
            status = 200

            def read(self):
                return b"<html>ok</html>"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def open_url(request, timeout):
            seen["url"] = request.full_url
            seen["timeout"] = timeout
            seen["user_agent"] = request.get_header("User-agent")
            return Response()

        body = fetch_html("https://photos.app.goo.gl/example", open_url=open_url, timeout=5)
        self.assertEqual(body, "<html>ok</html>")
        self.assertEqual(seen["url"], "https://photos.app.goo.gl/example")
        self.assertEqual(seen["timeout"], 5)
        self.assertIn("Mozilla", seen["user_agent"])

    def test_fetch_html_turns_http_errors_into_a_short_message(self):
        class Response:
            status = 404

            def read(self):
                return b"secret page body"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def open_url(request, timeout):
            return Response()

        with self.assertRaises(PhotoFeedError) as caught:
            fetch_html("https://photos.app.goo.gl/missing", open_url=open_url)
        self.assertIn("404", str(caught.exception))
        self.assertNotIn("secret page body", str(caught.exception))

    def test_fetch_html_unzips_gzip(self):
        payload = b"<html>plain page</html>"

        class Response:
            status = 200
            headers = {"Content-Encoding": "gzip"}

            def read(self):
                return gzip.compress(payload)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def open_url(request, timeout):
            self.assertIn("gzip", request.get_header("Accept-encoding").lower())
            return Response()

        body = fetch_html("https://photos.app.goo.gl/example", open_url=open_url)
        self.assertEqual(body, payload.decode("utf-8"))

    def test_fetch_html_refuses_brotli_without_echoing_the_body(self):
        class Response:
            status = 200
            headers = {"Content-Encoding": "br"}

            def read(self):
                return b"compressed-album-body"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with self.assertRaises(PhotoFeedError) as caught:
            fetch_html("https://photos.app.goo.gl/example", open_url=lambda request, timeout: Response())
        self.assertNotIn("compressed-album-body", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
