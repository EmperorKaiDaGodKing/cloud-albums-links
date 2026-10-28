"""Save album files locally without putting them in git."""

from __future__ import annotations

import re
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
