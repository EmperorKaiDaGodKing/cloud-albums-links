import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from photo_feed.google_photos import parse_album_html, parse_photo_html

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ALBUM_URL = "https://photos.google.com/share/FixtureAlbum?key=fixture-key"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ParseAlbumHtmlTest(unittest.TestCase):
    def test_structured_page_returns_photo_and_video(self):
        parsed = parse_album_html(read_fixture("google_album.html"), ALBUM_URL)

        self.assertEqual(parsed.title, "Fixture Picnic & Games")
        self.assertEqual(parsed.photo_pages, [])
        self.assertEqual([item["id"] for item in parsed.items], ["fixture-photo-1", "fixture-video-1"])

        photo = parsed.items[0]
        self.assertEqual(photo["kind"], "image")
        self.assertEqual(photo["filename"], "fixture-photo-1.jpg")
        self.assertEqual(photo["url"], "https://lh3.googleusercontent.com/pw/FIXTURE_PHOTO_ONE=s2048")
        self.assertEqual(photo["original_url"], "https://lh3.googleusercontent.com/pw/FIXTURE_PHOTO_ONE=d")
        self.assertEqual(photo["width"], 800)
        self.assertEqual(photo["height"], 600)
        self.assertEqual(photo["date"], "2024-03-09T16:00:00Z")
        self.assertIsNone(photo["size_bytes"])

        video = parsed.items[1]
        self.assertEqual(video["kind"], "video")
        self.assertEqual(video["filename"], "fixture-video-1.mp4")
        self.assertEqual(video["url"], "https://lh3.googleusercontent.com/pw/FIXTURE_VIDEO_ONE=s2048")
        self.assertEqual(video["original_url"], "https://lh3.googleusercontent.com/pw/FIXTURE_VIDEO_ONE=d")
        self.assertEqual(video["width"], 1920)
        self.assertEqual(video["height"], 1080)
        self.assertEqual(video["date"], "2024-03-09T16:00:02Z")
        self.assertFalse(parsed.partial)

    def test_a_continuation_token_marks_the_batch_partial(self):
        html = """
        <html><head><meta property="og:title" content="Fixture More"></head>
        <script>AF_initDataCallback({key: 'ds:0', hash: '1', data:[null, [
          ["fixture-photo-1", ["https://lh3.googleusercontent.com/pw/FIXTURE_PHOTO_ONE", 10, 10], 1710000000000]
        ], "FIXTURE_NEXT_PAGE_TOKEN_NOT_REAL_123456"], sideChannel: {}});</script>
        </html>
        """
        parsed = parse_album_html(html, ALBUM_URL)
        self.assertEqual(len(parsed.items), 1)
        self.assertTrue(parsed.partial)

    def test_links_only_page_keeps_photo_pages_and_skips_cover(self):
        parsed = parse_album_html(read_fixture("google_album_links_only.html"), ALBUM_URL)

        self.assertEqual(parsed.title, "Fixture Links Album")
        self.assertEqual(parsed.items, [])
        self.assertEqual(parsed.photo_pages, [
            "https://photos.google.com/share/FixtureAlbum/photo/FixturePhotoA?key=fixture-key",
            "https://photos.google.com/share/FixtureAlbum/photo/FixturePhotoB?key=fixture-key",
        ])
        self.assertFalse(parsed.sign_in_required)
        joined = " ".join(parsed.photo_pages)
        self.assertNotIn("FIXTURE_COVER", joined)

    def test_loose_url_is_used_when_the_page_has_no_items_or_links(self):
        parsed = parse_album_html(read_fixture("google_loose_url.html"), ALBUM_URL)

        self.assertEqual(len(parsed.items), 1)
        self.assertEqual(parsed.items[0]["id"], "FIXTURE_LOOSE_URL")
        self.assertEqual(parsed.items[0]["kind"], "image")
        self.assertEqual(parsed.photo_pages, [])

    def test_sign_in_page_is_flagged(self):
        parsed = parse_album_html(read_fixture("google_sign_in.html"), ALBUM_URL)

        self.assertTrue(parsed.sign_in_required)
        self.assertEqual(parsed.items, [])
        self.assertEqual(parsed.photo_pages, [])

    def test_photo_page_parser_reads_one_item(self):
        item = parse_photo_html(
            read_fixture("google_photo_page_a.html"),
            "https://photos.google.com/share/FixtureAlbum/photo/FixturePhotoA?key=fixture-key",
        )

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["id"], "fixture-photo-a")
        self.assertEqual(item["width"], 640)
        self.assertEqual(item["url"], "https://lh3.googleusercontent.com/pw/FIXTURE_PAGE_A=s2048")


if __name__ == "__main__":
    unittest.main()
