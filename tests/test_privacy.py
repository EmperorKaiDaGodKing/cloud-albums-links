"""The public repo must not gain a second copy of a saved album link."""

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "downloads", "output"}


class PrivacyTests(unittest.TestCase):
    def test_gitignore_covers_config_and_download_folders(self):
        for relative in (
            "photo-feed.local.json",
            "downloads/photo.jpg",
            "output/album.json",
            "photo-feed-downloads/clip.mp4",
            "photo-feed-out/list.json",
        ):
            completed = subprocess.run(
                ["git", "check-ignore", "-q", "--", relative],
                cwd=ROOT,
                check=False,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, relative)

    def test_saved_share_link_is_not_copied_into_other_files(self):
        link_path = ROOT / "shared-album-link-storage" / "MCP-Photo-Feed"
        link = link_path.read_text(encoding="utf-8").strip()
        self.assertTrue(link.startswith("https://"), "the stored link file should contain one URL")
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.resolve() == link_path.resolve():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if link in text:
                self.fail(f"{path.relative_to(ROOT)} repeats the shared album link. Remove it.")


if __name__ == "__main__":
    unittest.main()
