"""Find the album links the owner has configured.

The search order is fixed:

1. The PHOTO_FEED_URL environment variable (a Codespaces secret uses this name).
2. A local config file. PHOTO_FEED_CONFIG can point at that file. Otherwise
   it is photo-feed.local.json in the project folder (git-ignored).
3. Text files under shared-album-link-storage/.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from photo_feed.errors import AlbumError

Provider = Literal["google-photos", "terabox", "unknown"]

NO_ALBUMS_NOTE = (
    "No album link found. Set the PHOTO_FEED_URL secret, "
    "or create photo-feed.local.json (it stays off GitHub), "
    "or set PHOTO_FEED_CONFIG to a config file outside this folder, "
    "or put a link in a file under shared-album-link-storage/."
)

_URL_RE = re.compile(r"https?://[^\s<>'\"`]+")
_GENERIC_NAME = re.compile(r"^(link|url|test)( \d+)?$", re.IGNORECASE)
_SKIP_FILE_NAMES = {"readme", "readme.md", "readme.txt"}


@dataclass
class Album:
    id: str
    name: str
    url: str
    provider: Provider
    source: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Discovery:
    source: str | None
    albums: list[Album]
    note: str | None = None


def discover_albums(root: Path) -> Discovery:
    """Return albums from the first place that has a link."""
    root = Path(root)
    raw_env = os.environ.get("PHOTO_FEED_URL")
    if raw_env is not None and raw_env.strip():
        urls = extract_urls(raw_env)
        if not urls:
            raise AlbumError("PHOTO_FEED_URL is set, but it is not a web link.")
        return Discovery("env", _albums_from_urls(urls, source="env", default_name="Photo feed"))

    config_path = config_file_path(root)
    if config_path.is_file():
        configured = _albums_from_config(config_path)
        if configured:
            return Discovery("config", configured)

    stored = _albums_from_storage(root / "shared-album-link-storage")
    if stored:
        return Discovery("storage", stored)
    return Discovery(None, [], NO_ALBUMS_NOTE)


def config_file_path(root: Path) -> Path:
    """Where the local album list lives.

    PHOTO_FEED_CONFIG, when set, is that path. A relative path is inside the
    project folder. ``~`` is the home folder. When the variable is unset, the
    file is photo-feed.local.json next to the program.
    """
    override = os.environ.get("PHOTO_FEED_CONFIG")
    if override is not None and override.strip():
        path = Path(override.strip()).expanduser()
        if not path.is_absolute():
            path = Path(root) / path
        return path
    return Path(root) / "photo-feed.local.json"


def provider_for(url: str) -> Provider:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host in {"photos.app.goo.gl", "photos.google.com"}:
        return "google-photos"
    if (
        "terabox" in host
        or "1024tera" in host
        or host.endswith("4funbox.com")
        or host.endswith("mirrobox.com")
        or host.endswith("nephobox.com")
        or host.endswith("dubox.com")
    ):
        return "terabox"
    return "unknown"


def extract_urls(text: str) -> list[str]:
    """Pull web links out of a note. Lines that start with # are comments."""
    found: list[str] = []
    lines = text.splitlines() or [text]
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for match in _URL_RE.findall(stripped):
            cleaned = match.rstrip(").,]}>\"'")
            if cleaned:
                found.append(cleaned)
    return found


def slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._/-]+", "-", text.strip()).strip("-").lower()
    cleaned = cleaned.replace("/", "-")
    return cleaned or "album"


def _albums_from_urls(urls: list[str], source: str, default_name: str) -> list[Album]:
    albums: list[Album] = []
    used: set[str] = set()
    for index, url in enumerate(urls, start=1):
        name = default_name if index == 1 else f"{default_name} {index}"
        base_id = "photo-feed" if source == "env" and index == 1 else slug(name)
        albums.append(
            Album(
                id=_unique(base_id, used),
                name=name,
                url=url,
                provider=provider_for(url),
                source=source,
            )
        )
    return albums


def _albums_from_config(path: Path) -> list[Album]:
    label = path.name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise AlbumError(
            f"{label} is not valid JSON. "
            "Copy photo-feed.local.json.example and edit that."
        ) from None
    except OSError:
        raise AlbumError(f"Could not read {label}.") from None
    if not isinstance(data, dict) or not isinstance(data.get("albums"), list):
        raise AlbumError(
            f"{label} must be an object with an albums list. "
            "Copy photo-feed.local.json.example and edit that."
        )
    albums: list[Album] = []
    used: set[str] = set()
    for entry in data["albums"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("url"), str):
            raise AlbumError(f"Each album in {label} needs a url.")
        urls = extract_urls(entry["url"])
        if len(urls) != 1:
            raise AlbumError(f"Each album in {label} needs a url that starts with http.")
        name = str(entry.get("name") or "Album").strip() or "Album"
        base_id = str(entry.get("id") or slug(name)).strip() or slug(name)
        albums.append(
            Album(
                id=_unique(slug(base_id), used),
                name=name,
                url=urls[0],
                provider=provider_for(urls[0]),
                source="config",
            )
        )
    return albums


def _albums_from_storage(storage: Path) -> list[Album]:
    if not storage.is_dir():
        return []
    albums: list[Album] = []
    used: set[str] = set()
    files = [path for path in storage.rglob("*") if path.is_file() and not path.is_symlink()]
    for path in sorted(files):
        if path.name.startswith(".") or path.name.lower() in _SKIP_FILE_NAMES:
            continue
        if path.stat().st_size > 64_000:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        urls = extract_urls(text)
        if not urls:
            continue
        name = _name_from_storage_path(path, storage)
        base_id = "/".join(slug(part) for part in path.relative_to(storage).parts)
        for index, url in enumerate(urls):
            item_name = name if index == 0 else f"{name} {index + 1}"
            item_id = base_id if index == 0 else f"{base_id}-{index + 1}"
            albums.append(
                Album(
                    id=_unique(item_id, used),
                    name=item_name,
                    url=url,
                    provider=provider_for(url),
                    source="storage",
                )
            )
    return albums


def _name_from_storage_path(path: Path, storage: Path) -> str:
    if _GENERIC_NAME.match(path.stem) and path.parent != storage:
        return path.parent.name
    return path.stem


def _unique(base: str, used: set[str]) -> str:
    candidate = base or "album"
    if candidate not in used:
        used.add(candidate)
        return candidate
    number = 2
    while f"{candidate}-{number}" in used:
        number += 1
    result = f"{candidate}-{number}"
    used.add(result)
    return result
