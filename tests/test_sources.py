"""How album links are found.

Order is a fallback, not a mix: the first place that has a link wins.
1. PHOTO_FEED_URL
2. photo-feed.local.json (or PHOTO_FEED_CONFIG)
3. text files under shared-album-link-storage/
"""

import json
import tempfile
import unittest
from pathlib import Path

from photo_feed.sources import AlbumRef, load_albums, resolve_album


class LoadAlbumsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.storage = self.root / "shared-album-link-storage"
        self.storage.mkdir()
        self.config_path = self.root / "photo-feed.local.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _write_link_file(self, relative, text):
        path = self.storage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_env_var_wins_over_config_and_files(self):
        self.config_path.write_text(
            json.dumps(
                {"albums": [{"name": "From config", "url": "https://photos.app.goo.gl/config"}]}
            ),
            encoding="utf-8",
        )
        self._write_link_file("MCP-Photo-Feed", "https://photos.app.goo.gl/fromfile\n")

        albums = load_albums(
            env={"PHOTO_FEED_URL": "https://photos.app.goo.gl/fromenv"},
            config_path=self.config_path,
            storage_dir=self.storage,
        )

        self.assertEqual(
            albums,
            [
                AlbumRef(
                    name="PHOTO_FEED_URL",
                    url="https://photos.app.goo.gl/fromenv",
                    provider="google-photos",
                    source="env",
                    readable=True,
                )
            ],
        )

    def test_blank_env_var_falls_through_to_config(self):
        self.config_path.write_text(
            json.dumps(
                {
                    "albums": [
                        "https://photos.app.goo.gl/onlyurl",
                        {"name": "Trip", "url": "https://www.terabox.com/s/1example"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        self._write_link_file("ignored.txt", "https://photos.app.goo.gl/ignored")

        albums = load_albums(
            env={"PHOTO_FEED_URL": "   "},
            config_path=self.config_path,
            storage_dir=self.storage,
        )

        self.assertEqual([album.source for album in albums], ["config", "config"])
        self.assertEqual(albums[0].name, "onlyurl")
        self.assertEqual(albums[0].provider, "google-photos")
        self.assertTrue(albums[0].readable)
        self.assertEqual(albums[1].name, "Trip")
        self.assertEqual(albums[1].provider, "terabox")
        self.assertFalse(albums[1].readable)

    def test_link_files_used_when_env_and_config_are_absent(self):
        self._write_link_file("MCP-Photo-Feed", "see https://photos.app.goo.gl/abcDEF123.\n")
        self._write_link_file("google-photos-link-album/test 2", "\n\n")
        self._write_link_file(
            "terabox-link-album/terabox-test-photo-album/Link 1",
            "not a link yet",
        )
        self._write_link_file("notes/extra.txt", "https://1024terabox.com/s/1zzzz")

        albums = load_albums(
            env={},
            config_path=self.config_path,
            storage_dir=self.storage,
        )

        by_name = {album.name: album for album in albums}
        self.assertEqual(set(by_name), {"MCP-Photo-Feed", "notes/extra.txt"})
        self.assertEqual(by_name["MCP-Photo-Feed"].url, "https://photos.app.goo.gl/abcDEF123")
        self.assertEqual(by_name["MCP-Photo-Feed"].provider, "google-photos")
        self.assertEqual(by_name["MCP-Photo-Feed"].source, "file")
        self.assertEqual(by_name["notes/extra.txt"].provider, "terabox")

    def test_missing_storage_dir_returns_empty(self):
        albums = load_albums(
            env={},
            config_path=self.config_path,
            storage_dir=self.root / "does-not-exist",
        )
        self.assertEqual(albums, [])

    def test_config_with_no_urls_falls_through_to_files(self):
        self.config_path.write_text('{"albums": []}', encoding="utf-8")
        self._write_link_file("one.txt", "https://photos.google.com/share/example?key=abc")

        albums = load_albums(
            env={},
            config_path=self.config_path,
            storage_dir=self.storage,
        )

        self.assertEqual(len(albums), 1)
        self.assertEqual(albums[0].source, "file")
        self.assertEqual(albums[0].provider, "google-photos")

    def test_bad_config_is_a_clear_error(self):
        self.config_path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError) as caught:
            load_albums(env={}, config_path=self.config_path, storage_dir=self.storage)
        self.assertIn("photo-feed.local.json", str(caught.exception))

    def test_duplicate_urls_in_one_file_are_kept_once(self):
        self._write_link_file(
            "twice.txt",
            "https://photos.app.goo.gl/same\nhttps://photos.app.goo.gl/same\n",
        )
        albums = load_albums(env={}, config_path=self.config_path, storage_dir=self.storage)
        self.assertEqual(len(albums), 1)


class ResolveAlbumTests(unittest.TestCase):
    def setUp(self):
        self.albums = [
            AlbumRef("Family", "https://photos.app.goo.gl/family", "google-photos", "config", True),
            AlbumRef("Box", "https://terabox.com/s/1box", "terabox", "config", False),
        ]

    def test_url_argument_is_used_even_if_it_was_not_stored(self):
        album = resolve_album(
            self.albums,
            url="https://photos.app.goo.gl/typed-in",
        )
        self.assertEqual(album.url, "https://photos.app.goo.gl/typed-in")
        self.assertEqual(album.provider, "google-photos")
        self.assertEqual(album.source, "argument")

    def test_name_match_is_case_insensitive(self):
        album = resolve_album(self.albums, name="family")
        self.assertEqual(album.url, "https://photos.app.goo.gl/family")

    def test_single_stored_album_is_the_default(self):
        only = [self.albums[0]]
        self.assertEqual(resolve_album(only).url, only[0].url)

    def test_several_albums_need_a_name_or_url(self):
        with self.assertRaises(ValueError) as caught:
            resolve_album(self.albums)
        self.assertIn("Family", str(caught.exception))
        self.assertIn("Box", str(caught.exception))

    def test_unknown_name_lists_what_exists(self):
        with self.assertRaises(ValueError) as caught:
            resolve_album(self.albums, name="nope")
        self.assertIn("nope", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
