import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]


def stored_album_urls():
    storage = ROOT / "shared-album-link-storage"
    urls = []
    for path in storage.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in text.split():
            if token.startswith("http://") or token.startswith("https://"):
                urls.append(token.strip())
    return [url for url in urls if len(url) > 12]


class PrivacyTest(unittest.TestCase):
    def test_download_config_and_output_paths_are_gitignored(self):
        paths = [
            "downloads/pic.jpg",
            "downloads/photo-feed/album.json",
            "output/result.json",
            "photo-feed.local.json",
            ".env",
        ]
        completed = subprocess.run(
            ["git", "check-ignore", "--", *paths],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        ignored = set(completed.stdout.splitlines())
        for path in paths:
            self.assertIn(path, ignored)

    def test_there_is_no_workflow_that_could_fetch_albums(self):
        workflows = ROOT / ".github" / "workflows"
        self.assertFalse(workflows.exists())

    def test_stored_links_are_not_copied_outside_the_storage_folder(self):
        urls = stored_album_urls()
        self.assertTrue(urls, "expected the existing storage folder to hold at least one link")
        storage = (ROOT / "shared-album-link-storage").resolve()
        skip = {".git", "__pycache__", ".venv", "downloads", "output"}
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(part in skip for part in path.parts):
                continue
            resolved = path.resolve()
            if resolved == storage or storage in resolved.parents:
                continue
            if path.stat().st_size > 2_000_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for url in urls:
                if url in text:
                    self.fail(f"{path.relative_to(ROOT)} repeats a stored album link")

    def test_fixtures_are_labeled_and_not_real_hosts(self):
        fixtures = ROOT / "tests" / "fixtures"
        for path in fixtures.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            self.assertIn("synthetic fixture", text)
            self.assertNotIn("photos.app.goo.gl", text)
            self.assertNotIn("terabox.com/s/", text.lower())


if __name__ == "__main__":
    unittest.main()
