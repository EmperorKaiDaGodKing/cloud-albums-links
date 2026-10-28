import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from photo_feed.albums import discover_albums
from photo_feed.errors import AlbumError


FIXTURE_GOOGLE = "https://photos.google.com/share/FixtureFromEnv"
FIXTURE_TERABOX = "https://www.terabox.com/s/fixture-share"


class DiscoverAlbumsTest(unittest.TestCase):
    def setUp(self):
        self._previous = os.environ.get("PHOTO_FEED_URL")
        self._config = os.environ.get("PHOTO_FEED_CONFIG")
        os.environ.pop("PHOTO_FEED_URL", None)
        os.environ.pop("PHOTO_FEED_CONFIG", None)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.storage = self.root / "shared-album-link-storage"
        self.storage.mkdir()

    def tearDown(self):
        if self._previous is None:
            os.environ.pop("PHOTO_FEED_URL", None)
        else:
            os.environ["PHOTO_FEED_URL"] = self._previous
        if self._config is None:
            os.environ.pop("PHOTO_FEED_CONFIG", None)
        else:
            os.environ["PHOTO_FEED_CONFIG"] = self._config
        self.tmp.cleanup()

    def test_env_var_wins_over_config_and_storage(self):
        os.environ["PHOTO_FEED_URL"] = FIXTURE_GOOGLE
        (self.root / "photo-feed.local.json").write_text(
            '{"albums":[{"name":"From file","url":"https://photos.example.test/from-file"}]}',
            encoding="utf-8",
        )
        (self.storage / "MCP-Photo-Feed").write_text(
            "https://photos.example.test/from-storage\n",
            encoding="utf-8",
        )

        found = discover_albums(self.root)

        self.assertEqual(found.source, "env")
        self.assertEqual(len(found.albums), 1)
        album = found.albums[0]
        self.assertEqual(album.id, "photo-feed")
        self.assertEqual(album.name, "Photo feed")
        self.assertEqual(album.url, FIXTURE_GOOGLE)
        self.assertEqual(album.provider, "google-photos")
        self.assertEqual(album.source, "env")

    def test_blank_env_var_falls_through_to_config(self):
        os.environ["PHOTO_FEED_URL"] = "   \n"
        (self.root / "photo-feed.local.json").write_text(
            '{"albums":[{"name":"Trip","url":"https://photos.google.com/share/FixtureAlbum?key=fixture-key"}]}',
            encoding="utf-8",
        )

        found = discover_albums(self.root)

        self.assertEqual(found.source, "config")
        self.assertEqual(found.albums[0].name, "Trip")
        self.assertEqual(found.albums[0].provider, "google-photos")
        self.assertEqual(found.albums[0].id, "trip")

    def test_photo_feed_config_is_used_instead_of_the_default_file(self):
        custom = self.root / "kept-off-github" / "albums.json"
        custom.parent.mkdir()
        custom.write_text(
            '{"albums":[{"name":"Desk","url":"https://photos.google.com/share/FixtureFromConfig"}]}',
            encoding="utf-8",
        )
        (self.root / "photo-feed.local.json").write_text(
            '{"albums":[{"name":"Ignored","url":"https://photos.google.com/share/FixtureDefault"}]}',
            encoding="utf-8",
        )
        os.environ["PHOTO_FEED_CONFIG"] = str(custom)

        found = discover_albums(self.root)

        self.assertEqual(found.source, "config")
        self.assertEqual(found.albums[0].name, "Desk")
        self.assertEqual(found.albums[0].url, "https://photos.google.com/share/FixtureFromConfig")

    def test_photo_feed_url_wins_over_photo_feed_config(self):
        os.environ["PHOTO_FEED_URL"] = FIXTURE_GOOGLE
        custom = self.root / "albums.json"
        custom.write_text(
            '{"albums":[{"name":"Desk","url":"https://photos.google.com/share/FixtureFromConfig"}]}',
            encoding="utf-8",
        )
        os.environ["PHOTO_FEED_CONFIG"] = str(custom)

        found = discover_albums(self.root)

        self.assertEqual(found.source, "env")
        self.assertEqual(found.albums[0].url, FIXTURE_GOOGLE)

    def test_relative_photo_feed_config_stays_inside_the_project(self):
        os.environ["PHOTO_FEED_CONFIG"] = "secret/albums.json"
        custom = self.root / "secret" / "albums.json"
        custom.parent.mkdir()
        custom.write_text(
            '{"albums":[{"name":"Side","url":"https://photos.google.com/share/FixtureSide"}]}',
            encoding="utf-8",
        )

        found = discover_albums(self.root)

        self.assertEqual(found.albums[0].name, "Side")

    def test_missing_photo_feed_config_skips_the_default_file(self):
        os.environ["PHOTO_FEED_CONFIG"] = str(self.root / "missing.json")
        (self.root / "photo-feed.local.json").write_text(
            '{"albums":[{"name":"Ignored","url":"https://photos.google.com/share/FixtureDefault"}]}',
            encoding="utf-8",
        )
        (self.storage / "summer-trip").write_text(FIXTURE_GOOGLE + "\n", encoding="utf-8")

        found = discover_albums(self.root)

        self.assertEqual(found.source, "storage")
        self.assertEqual(found.albums[0].id, "summer-trip")

    def test_empty_config_list_falls_through_to_storage(self):
        (self.root / "photo-feed.local.json").write_text('{"albums":[]}', encoding="utf-8")
        (self.storage / "summer-trip").write_text(FIXTURE_GOOGLE + "\n", encoding="utf-8")
        nested = self.storage / "terabox-link-album" / "terabox-test-photo-album"
        nested.mkdir(parents=True)
        (nested / "Link 1").write_text(FIXTURE_TERABOX + "\n", encoding="utf-8")
        (self.storage / "google-photos-link-album").mkdir()
        (self.storage / "google-photos-link-album" / "test 2").write_text("\n", encoding="utf-8")
        (self.storage / "notes.txt").write_text("# moved to the secret\n", encoding="utf-8")

        found = discover_albums(self.root)

        self.assertEqual(found.source, "storage")
        by_id = {album.id: album for album in found.albums}
        self.assertEqual(set(by_id), {
            "summer-trip",
            "terabox-link-album/terabox-test-photo-album/link-1",
        })
        self.assertEqual(by_id["summer-trip"].provider, "google-photos")
        self.assertEqual(by_id["terabox-link-album/terabox-test-photo-album/link-1"].name, "terabox-test-photo-album")
        self.assertEqual(by_id["terabox-link-album/terabox-test-photo-album/link-1"].provider, "terabox")

    def test_broken_config_is_an_error_without_its_contents(self):
        (self.root / "photo-feed.local.json").write_text(
            "{not json https://photos.example.test/secret-in-file}",
            encoding="utf-8",
        )

        with self.assertRaises(AlbumError) as caught:
            discover_albums(self.root)

        message = str(caught.exception)
        self.assertIn("photo-feed.local.json", message)
        self.assertNotIn("photos.example.test", message)

    def test_env_set_to_text_that_is_not_a_link(self):
        os.environ["PHOTO_FEED_URL"] = "not a link"

        with self.assertRaises(AlbumError) as caught:
            discover_albums(self.root)

        self.assertIn("PHOTO_FEED_URL", str(caught.exception))

    def test_no_links_anywhere_returns_an_empty_list_and_a_note(self):
        found = discover_albums(self.root)

        self.assertEqual(found.albums, [])
        self.assertIsNone(found.source)
        self.assertIn("PHOTO_FEED_URL", found.note or "")


if __name__ == "__main__":
    unittest.main()
