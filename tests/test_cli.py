"""The command line prints JSON and does not need a real album."""

import json
import os
import subprocess
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from photo_feed.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "google_share_page.html"
ALBUM = "https://photos.app.goo.gl/example"


def _fetch(_url, **_kwargs):
    return FIXTURE.read_text(encoding="utf-8")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.stdout = StringIO()
        self.stderr = StringIO()

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, argv, env=None, fetch_html=_fetch, fetch_file=None):
        return main(
            argv,
            root=self.root,
            env={} if env is None else env,
            stdout=self.stdout,
            stderr=self.stderr,
            fetch_html=fetch_html,
            fetch_file=fetch_file,
        )

    def test_list_albums_reads_photo_feed_url_from_the_process_environment(self):
        previous = os.environ.get("PHOTO_FEED_URL")
        os.environ["PHOTO_FEED_URL"] = ALBUM
        try:
            code = main(
                ["list-albums"],
                root=self.root,
                stdout=self.stdout,
                stderr=self.stderr,
                fetch_html=_fetch,
            )
        finally:
            if previous is None:
                os.environ.pop("PHOTO_FEED_URL", None)
            else:
                os.environ["PHOTO_FEED_URL"] = previous
        self.assertEqual(code, 0)
        payload = json.loads(self.stdout.getvalue())
        self.assertEqual(payload["albums"][0]["url"], ALBUM)
        self.assertEqual(payload["albums"][0]["source"], "env")

    def test_list_albums_uses_the_env_link_only(self):
        storage = self.root / "shared-album-link-storage"
        storage.mkdir()
        (storage / "MCP-Photo-Feed").write_text("https://photos.app.goo.gl/fromfile\n", encoding="utf-8")

        code = self._run(["list-albums"], env={"PHOTO_FEED_URL": ALBUM})

        self.assertEqual(code, 0)
        payload = json.loads(self.stdout.getvalue())
        self.assertEqual(payload["albums"], [
            {
                "name": "PHOTO_FEED_URL",
                "url": ALBUM,
                "provider": "google-photos",
                "source": "env",
                "readable": True,
            }
        ])
        self.assertIn("PHOTO_FEED_URL", payload["note"])
        self.assertNotIn("fromfile", self.stdout.getvalue())

    def test_list_albums_explains_when_nothing_is_saved(self):
        code = self._run(["list-albums"])
        self.assertEqual(code, 0)
        payload = json.loads(self.stdout.getvalue())
        self.assertEqual(payload["albums"], [])
        self.assertIn("PHOTO_FEED_URL", payload["note"])

    def test_list_photos_parses_the_fixture_page(self):
        code = self._run(["list-photos"], env={"PHOTO_FEED_URL": ALBUM})
        self.assertEqual(code, 0)
        payload = json.loads(self.stdout.getvalue())
        self.assertEqual(payload["album"]["title"], "Picnic")
        self.assertEqual(payload["album"]["url"], ALBUM)
        self.assertEqual(payload["items"][0]["filename"], "picnic.jpg")
        self.assertEqual(payload["items"][1]["kind"], "video")
        self.assertIn("first batch", payload["note"])
        self.assertFalse(payload["truncated"])

    def test_unknown_site_is_refused_before_fetch(self):
        def boom(*_args, **_kwargs):
            raise AssertionError("should not fetch an unknown site")

        code = self._run(
            ["list-photos", "--url", "https://example.test/album"],
            fetch_html=boom,
        )
        self.assertEqual(code, 1)
        self.assertIn("Google Photos", json.loads(self.stdout.getvalue())["error"])

    def test_list_photos_refuses_terabox_without_fetching(self):
        def boom(*_args, **_kwargs):
            raise AssertionError("should not fetch a TeraBox page")

        code = self._run(
            ["list-photos", "--url", "https://terabox.com/s/1privateExample"],
            fetch_html=boom,
        )
        self.assertEqual(code, 1)
        payload = json.loads(self.stdout.getvalue())
        self.assertIn("captcha", payload["error"].lower())
        self.assertNotIn("1privateExample", payload["error"])
        self.assertIn("captcha", self.stderr.getvalue().lower())

    def test_download_flag_writes_files_and_warns_if_not_ignored(self):
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        dest = self.root / "saved"

        def fetch_file(url):
            return f"bytes:{url}".encode("utf-8"), {}

        code = self._run(
            ["list-photos", "--download", str(dest)],
            env={"PHOTO_FEED_URL": ALBUM},
            fetch_file=fetch_file,
        )
        self.assertEqual(code, 0)
        self.assertTrue((dest / "picnic.jpg").is_file())
        self.assertTrue((dest / "clip.mp4").is_file())
        self.assertIn("not git-ignored", self.stderr.getvalue())
        payload = json.loads(self.stdout.getvalue())
        self.assertEqual(len(payload["downloaded"]), 2)
        self.assertIn("not git-ignored", payload["warning"])

    def test_download_is_quiet_when_gitignore_covers_the_folder(self):
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        (self.root / ".gitignore").write_text("saved/\n", encoding="utf-8")
        dest = self.root / "saved"

        code = self._run(
            ["list-photos", "--download", str(dest)],
            env={"PHOTO_FEED_URL": ALBUM},
            fetch_file=lambda url: (b"abc", {}),
        )
        self.assertEqual(code, 0)
        self.assertNotIn("not git-ignored", self.stderr.getvalue())
        self.assertEqual((dest / "picnic.jpg").read_bytes(), b"abc")

    def test_mcp_command_speaks_json_rpc_on_stdout(self):
        stdin = StringIO(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05"},
                }
            )
            + "\n"
        )
        code = main(
            ["mcp"],
            root=self.root,
            env={},
            stdout=self.stdout,
            stderr=self.stderr,
            stdin=stdin,
            fetch_html=_fetch,
        )
        self.assertEqual(code, 0)
        response = json.loads(self.stdout.getvalue())
        self.assertEqual(response["result"]["serverInfo"]["name"], "photo-feed")


if __name__ == "__main__":
    unittest.main()
