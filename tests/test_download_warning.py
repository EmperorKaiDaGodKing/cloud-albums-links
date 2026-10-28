import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from photo_feed.download import download_commit_warning
from photo_feed.mcp_server import handle_message
from photo_feed.service import list_album_photos

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "google_album.html").read_text(encoding="utf-8")
ALBUM_URL = "https://photos.google.com/share/FixtureAlbum?key=fixture-key"


def git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True, capture_output=True)


def fetch_fixture(url: str) -> str:
    return FIXTURE


def save_fake(url: str, path: Path) -> str:
    path.write_bytes(b"not-a-real-photo")
    return "image/jpeg"


class DownloadWarningTest(unittest.TestCase):
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

    def test_default_downloads_folder_in_this_repo_is_ignored(self):
        warning = download_commit_warning(ROOT / "downloads" / "photo-feed" / "pic.jpg")
        self.assertIsNone(warning)

    def test_gitignored_folder_has_no_warning(self):
        git_init(self.root)
        (self.root / ".gitignore").write_text("downloads/\noutput/\n", encoding="utf-8")
        dest = self.root / "downloads" / "album"
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = list_album_photos(
                self.root,
                url=ALBUM_URL,
                download_dir=dest,
                fetch_text=fetch_fixture,
                fetch_download=save_fake,
            )
        self.assertNotIn("warning", result)
        self.assertEqual(stderr.getvalue(), "")
        self.assertTrue((dest / "fixture-photo-1.jpg").is_file())

    def test_folder_git_does_not_ignore_warns(self):
        git_init(self.root)
        dest = self.root / "downloads" / "album"
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = list_album_photos(
                self.root,
                url=ALBUM_URL,
                download_dir=dest,
                fetch_text=fetch_fixture,
                fetch_download=save_fake,
            )
        warning = result.get("warning") or ""
        self.assertIn("Do not commit", warning)
        self.assertIn("public", warning.lower())
        self.assertIn(str(dest), warning)
        self.assertIn(warning, stderr.getvalue())
        self.assertNotIn("lh3.googleusercontent.com", warning)

    def test_outside_a_git_repo_still_downloads(self):
        dest = self.root / "downloads" / "album"
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = list_album_photos(
                self.root,
                url=ALBUM_URL,
                download_dir=dest,
                fetch_text=fetch_fixture,
                fetch_download=save_fake,
            )
        self.assertNotIn("error", result)
        self.assertEqual(result["count"], 2)
        self.assertNotIn("warning", result)
        self.assertEqual(stderr.getvalue(), "")
        self.assertTrue((dest / "fixture-photo-1.jpg").is_file())

    def test_mcp_download_warns_only_when_git_would_commit_the_folder(self):
        git_init(self.root)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            plain = handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "list_album_photos",
                        "arguments": {"url": ALBUM_URL, "download_dir": "downloads/album"},
                    },
                },
                root=self.root,
                fetch_text=fetch_fixture,
                fetch_download=save_fake,
            )
        plain_text = plain["result"]["content"][0]["text"]
        self.assertIn("Do not commit", plain_text)
        self.assertIn("Do not commit", stderr.getvalue())
        self.assertFalse(plain["result"]["isError"])

        (self.root / ".gitignore").write_text("downloads/\n", encoding="utf-8")
        quiet_err = io.StringIO()
        with redirect_stderr(quiet_err):
            quiet = handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "list_album_photos",
                        "arguments": {"url": ALBUM_URL, "download_dir": "downloads/album"},
                    },
                },
                root=self.root,
                fetch_text=fetch_fixture,
                fetch_download=save_fake,
            )
        quiet_text = quiet["result"]["content"][0]["text"]
        self.assertNotIn("Do not commit", quiet_text)
        self.assertNotIn("warning", json.loads(quiet_text))
        self.assertEqual(quiet_err.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
