import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from photo_feed.errors import AlbumError
from photo_feed.service import list_album_photos, list_albums

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ALBUM_URL = "https://photos.google.com/share/FixtureAlbum?key=fixture-key"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self._previous = os.environ.get("PHOTO_FEED_URL")
        os.environ.pop("PHOTO_FEED_URL", None)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("PHOTO_FEED_URL", None)
        else:
            os.environ["PHOTO_FEED_URL"] = self._previous
        self.tmp.cleanup()

    def test_list_photos_uses_the_fixture_page_fetcher(self):
        os.environ["PHOTO_FEED_URL"] = ALBUM_URL
        calls = []

        def fetch_text(url: str) -> str:
            calls.append(url)
            self.assertEqual(url, ALBUM_URL)
            return fixture("google_album.html")

        result = list_album_photos(self.root, fetch_text=fetch_text)

        self.assertNotIn("error", result)
        self.assertEqual(result["count"], 2)
        self.assertFalse(result["partial"])
        self.assertEqual(result["album"]["title"], "Fixture Picnic & Games")
        self.assertEqual(result["album"]["provider"], "google-photos")
        self.assertEqual([item["id"] for item in result["items"]], ["fixture-photo-1", "fixture-video-1"])
        self.assertEqual(calls, [ALBUM_URL])

    def test_links_only_album_fetches_each_photo_page(self):
        pages = {
            ALBUM_URL: fixture("google_album_links_only.html"),
            "https://photos.google.com/share/FixtureAlbum/photo/FixturePhotoA?key=fixture-key": fixture("google_photo_page_a.html"),
            "https://photos.google.com/share/FixtureAlbum/photo/FixturePhotoB?key=fixture-key": fixture("google_photo_page_b.html"),
        }

        result = list_album_photos(self.root, url=ALBUM_URL, fetch_text=pages.get)

        self.assertEqual([item["id"] for item in result["items"]], ["fixture-photo-a", "fixture-photo-b"])
        self.assertNotIn("FIXTURE_COVER", str(result))
        self.assertFalse(result["partial"])

    def test_photo_page_cap_marks_the_list_partial(self):
        pages = {
            ALBUM_URL: fixture("google_album_links_only.html"),
            "https://photos.google.com/share/FixtureAlbum/photo/FixturePhotoA?key=fixture-key": fixture("google_photo_page_a.html"),
        }

        def fetch_text(url: str) -> str:
            if url not in pages:
                raise AssertionError("fetched a page past the cap")
            return pages[url]

        result = list_album_photos(self.root, url=ALBUM_URL, fetch_text=fetch_text, max_photo_pages=1)

        self.assertEqual([item["id"] for item in result["items"]], ["fixture-photo-a"])
        self.assertTrue(result["partial"])
        self.assertIn("photo pages", result["note"] or "")

    def test_limit_stops_early(self):
        os.environ["PHOTO_FEED_URL"] = ALBUM_URL

        result = list_album_photos(
            self.root,
            limit=1,
            fetch_text=lambda url: fixture("google_album.html"),
        )

        self.assertEqual(result["count"], 1)
        self.assertTrue(result["partial"])
        self.assertEqual(result["items"][0]["id"], "fixture-photo-1")

    def test_short_link_shell_asks_for_the_long_link(self):
        shell = "<html><base href='https://photos.app.goo.gl/'><p>Loading</p></html>"
        result = list_album_photos(
            self.root,
            url="https://photos.app.goo.gl/fixtureExample",
            fetch_text=lambda url: shell,
        )
        self.assertIn("short-link", result["error"])
        self.assertEqual(result["items"], [])

    def test_sign_in_page_explains_link_sharing(self):
        result = list_album_photos(
            self.root,
            url="https://photos.google.com/share/PrivateFixture",
            fetch_text=lambda url: fixture("google_sign_in.html"),
        )

        self.assertIn("error", result)
        self.assertIn("anyone", result["error"].lower())
        self.assertEqual(result["items"], [])

    def test_consent_page_has_its_own_message(self):
        result = list_album_photos(
            self.root,
            url="https://photos.google.com/share/ConsentFixture",
            fetch_text=lambda url: fixture("google_consent.html"),
        )

        self.assertIn("consent", result["error"].lower())
        self.assertEqual(result["items"], [])

    def test_terabox_is_a_clear_stub(self):
        result = list_album_photos(
            self.root,
            url="https://terabox.com/s/fixture-share",
            fetch_text=lambda url: "this should not be fetched",
        )

        self.assertEqual(result["items"], [])
        self.assertEqual(result["album"]["provider"], "terabox")
        message = result["error"].lower()
        self.assertIn("terabox", message)
        self.assertIn("captcha", message)
        self.assertIn("sign", message)
        self.assertNotIn("this should not be fetched", message)

    def test_unknown_link_is_rejected(self):
        result = list_album_photos(
            self.root,
            url="https://example.test/not-an-album",
            fetch_text=lambda url: "",
        )

        self.assertIn("Google Photos", result["error"])
        self.assertEqual(result["items"], [])

    def test_download_writes_only_inside_downloads_and_records_the_path(self):
        os.environ["PHOTO_FEED_URL"] = ALBUM_URL
        dest = self.root / "downloads" / "photo-feed"

        def fetch_download(url: str, path: Path) -> str:
            self.assertTrue(str(url).startswith("https://lh3.googleusercontent.com/pw/FIXTURE_"))
            self.assertTrue(path.resolve().is_relative_to(dest.resolve()))
            path.write_bytes(b"not-a-real-photo")
            return "image/jpeg"

        result = list_album_photos(
            self.root,
            download_dir=dest,
            fetch_text=lambda url: fixture("google_album.html"),
            fetch_download=fetch_download,
        )

        saved = [item["saved_path"] for item in result["items"]]
        self.assertEqual(len(saved), 2)
        for path in saved:
            file_path = Path(path)
            self.assertTrue(file_path.is_file())
            self.assertEqual(file_path.read_bytes(), b"not-a-real-photo")
            self.assertTrue(file_path.resolve().is_relative_to((self.root / "downloads").resolve()))
        manifest = dest / "album.json"
        self.assertTrue(manifest.is_file())
        self.assertIn("FIXTURE_PHOTO_ONE", manifest.read_text(encoding="utf-8"))

    def test_download_refuses_the_source_tree(self):
        os.environ["PHOTO_FEED_URL"] = ALBUM_URL
        (self.root / "photo_feed").mkdir()

        with self.assertRaises(AlbumError) as caught:
            list_album_photos(
                self.root,
                download_dir=self.root / "photo_feed",
                fetch_text=lambda url: fixture("google_album.html"),
            )

        self.assertIn("downloads", str(caught.exception))
        self.assertFalse(any((self.root / "photo_feed").iterdir()))

    def test_list_albums_shape(self):
        os.environ["PHOTO_FEED_URL"] = "https://photos.app.goo.gl/fixtureExample"

        result = list_albums(self.root)

        self.assertEqual(result["source"], "env")
        self.assertEqual(result["albums"][0]["id"], "photo-feed")
        self.assertNotIn("items", result)


if __name__ == "__main__":
    unittest.main()
