"""Save album files locally without putting them in git."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from photo_feed.errors import AlbumError

_ALLOWED_TOP_FOLDERS = {"downloads", "output"}


def ensure_safe_download_dir(root: Path, dest: Path) -> Path:
    """Allow downloads outside the project, or only in downloads/ and output/ inside it."""
    root = root.resolve()
    dest = dest.resolve()
    if ".git" in dest.parts:
        raise AlbumError("Refusing to save photos into a .git folder.")
    try:
        relative = dest.relative_to(root)
    except ValueError:
        return dest
    if not relative.parts or relative.parts[0] not in _ALLOWED_TOP_FOLDERS:
        raise AlbumError(
            "Inside this project, photos can only be saved to the downloads or output folders. "
            "Those folders are git-ignored so the photos stay off GitHub."
        )
    return dest


def download_commit_warning(path: Path) -> str | None:
    """Warn when a saved photo would be committable in a public repo.

    ``path`` is a file path inside the download folder (it does not have to exist).
    Git is asked with ``check-ignore``. Outside a git repo, or if git cannot
    answer, there is no warning and no error.
    """
    path = Path(path)
    if _git_ignores(path) is not False:
        return None
    folder = path.parent if path.suffix else path
    return (
        f"Warning: photos were saved to {folder}. "
        "Git is not ignoring that folder. This repo is public. "
        "Do not commit these photos."
    )


def _git_ignores(path: Path) -> bool | None:
    """True if git ignores path, False if it does not, None if git cannot say."""
    start = path if path.is_dir() else path.parent
    while not start.exists():
        if start.parent == start:
            return None
        start = start.parent
    toplevel = _git(["rev-parse", "--show-toplevel"], start)
    if toplevel is None:
        return None
    repo = toplevel.stdout.strip()
    if not repo:
        return None
    checked = _git(["check-ignore", "-q", "--", str(path)], Path(repo))
    if checked is None:
        return None
    if checked.returncode == 0:
        return True
    if checked.returncode == 1:
        return False
    return None


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def file_path_for(dest: Path, filename: str, used: set[str]) -> Path:
    """Build a file path that stays inside dest, even if the name tries to climb out."""
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._") or "photo"
    candidate_name = safe
    number = 2
    while candidate_name.lower() in used:
        stem = Path(safe).stem
        suffix = Path(safe).suffix
        candidate_name = f"{stem}-{number}{suffix}"
        number += 1
    used.add(candidate_name.lower())
    candidate = (dest / candidate_name).resolve()
    candidate.relative_to(dest)
    return candidate
