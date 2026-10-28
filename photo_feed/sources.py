"""Find the shared-album links this tool should read.

The first place that actually contains a link wins:

1. The ``PHOTO_FEED_URL`` environment variable.
2. A local config file (``photo-feed.local.json`` by default).
3. Text files under ``shared-album-link-storage/``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s<>\"']+")

# Hosts that serve a TeraBox share page. Listing those pages needs a
# signed-in session, so they are recognized here and refused later.
_TERABOX_HOSTS = (
    "terabox.com",
    "1024terabox.com",
    "1024tera.com",
    "4funbox.com",
    "mirrobox.com",
    "nephobox.com",
    "teraboxapp.com",
    "freeterabox.com",
    "terasharelink.com",
)

_MAX_LINK_FILE_BYTES = 1_000_000


@dataclass(frozen=True)
class AlbumRef:
    """One shared-album link and where it came from."""

    name: str
    url: str
    provider: str
    source: str
    readable: bool


def load_albums(env: dict[str, str], config_path: Path, storage_dir: Path) -> list[AlbumRef]:
    """Return albums from the first source that has at least one link."""

    env_url = (env.get("PHOTO_FEED_URL") or "").strip()
    if env_url:
        url = _require_one_url(env_url, "PHOTO_FEED_URL")
        return [_album("PHOTO_FEED_URL", url, "env")]

    if config_path.is_file():
        from_config = _albums_from_config(config_path)
        if from_config:
            return from_config

    return _albums_from_storage(storage_dir)


def resolve_album(
    albums: list[AlbumRef],
    url: str | None = None,
    name: str | None = None,
) -> AlbumRef:
    """Pick one album from a stored list, or from a link passed in directly."""

    if url and url.strip():
        cleaned = _require_one_url(url, "The album link")
        for album in albums:
            if album.url == cleaned:
                return AlbumRef(album.name, cleaned, album.provider, "argument", album.readable)
        return _album(_name_from_url(cleaned), cleaned, "argument")

    if name and name.strip():
        wanted = name.strip().casefold()
        matches = [album for album in albums if album.name.casefold() == wanted]
        if len(matches) == 1:
            return matches[0]
        known = ", ".join(album.name for album in albums) or "(none)"
        if not matches:
            raise ValueError(f"No album named {name.strip()!r}. Known albums: {known}.")
        raise ValueError(f"More than one album is named {name.strip()!r}. Known albums: {known}.")

    if len(albums) == 1:
        return albums[0]
    if not albums:
        raise ValueError(
            "No album links found. Set PHOTO_FEED_URL, create photo-feed.local.json, "
            "or put a link in shared-album-link-storage/."
        )
    known = ", ".join(album.name for album in albums)
    raise ValueError(
        "More than one album link is saved. Pass a link or a name. Known albums: " + known + "."
    )


def provider_for(url: str) -> str:
    """Classify a link by its host name."""

    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if host == "photos.app.goo.gl" or host == "photos.google.com" or host.endswith(".photos.google.com"):
        return "google-photos"
    for suffix in _TERABOX_HOSTS:
        if host == suffix or host.endswith("." + suffix):
            return "terabox"
    return "unknown"


def repo_root() -> Path:
    """Folder that holds this project.

    Prefers the current working directory when it looks like the project,
    so a Codespace terminal opened at the repo root just works. Falls back
    to the folder that contains the ``photo_feed`` package.
    """

    packaged = Path(__file__).resolve().parent.parent
    cwd = Path.cwd()
    for candidate in (cwd, packaged):
        if (candidate / "shared-album-link-storage").is_dir() or (candidate / "photo_feed").is_dir():
            return candidate
    return packaged


def default_config_path(root: Path | None = None, env: dict[str, str] | None = None) -> Path:
    """Local config file. ``PHOTO_FEED_CONFIG`` can point outside the repo."""

    env = env if env is not None else {}
    override = (env.get("PHOTO_FEED_CONFIG") or "").strip()
    if override:
        return Path(override).expanduser()
    base = root if root is not None else repo_root()
    return base / "photo-feed.local.json"


def _album(name: str, url: str, source: str) -> AlbumRef:
    provider = provider_for(url)
    return AlbumRef(
        name=name,
        url=url,
        provider=provider,
        source=source,
        readable=provider == "google-photos",
    )


def _require_one_url(value: str, label: str) -> str:
    stripped = value.strip()
    urls = _extract_urls(stripped)
    if len(urls) != 1 or urls[0] != stripped:
        raise ValueError(
            f"{label} should be one album link, like https://photos.app.goo.gl/..."
        )
    return urls[0]


def _extract_urls(text: str) -> list[str]:
    found: list[str] = []
    for match in _URL_RE.findall(text):
        url = match.rstrip(".,);]")
        if url not in found:
            found.append(url)
    return found


def _name_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return urlparse(url).hostname or "album"
    return path.split("/")[-1] or "album"


def _albums_from_config(config_path: Path) -> list[AlbumRef]:
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{config_path.name} is not valid JSON ({exc.msg} on line {exc.lineno}). "
            "Copy photo-feed.local.json.example and edit that."
        ) from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("albums"), list):
        raise ValueError(
            f"{config_path.name} should be an object with an \"albums\" list. "
            "See photo-feed.local.json.example."
        )
    albums: list[AlbumRef] = []
    used_names: set[str] = set()
    for index, entry in enumerate(raw["albums"], start=1):
        if isinstance(entry, str):
            url = _require_one_url(entry, f"Album {index} in {config_path.name}")
            name = _name_from_url(url)
        elif isinstance(entry, dict) and isinstance(entry.get("url"), str):
            url = _require_one_url(entry["url"], f"Album {index} in {config_path.name}")
            custom = entry.get("name")
            name = custom.strip() if isinstance(custom, str) and custom.strip() else _name_from_url(url)
        else:
            raise ValueError(
                f"Album {index} in {config_path.name} should be a link string "
                "or an object with a url."
            )
        albums.append(_album(_unique_name(name, used_names), url, "config"))
    return albums


def _albums_from_storage(storage_dir: Path) -> list[AlbumRef]:
    if not storage_dir.is_dir():
        return []
    albums: list[AlbumRef] = []
    seen_urls: set[str] = set()
    used_names: set[str] = set()
    files = [path for path in storage_dir.rglob("*") if path.is_file() and not _is_hidden(path, storage_dir)]
    for path in sorted(files, key=lambda item: item.relative_to(storage_dir).as_posix()):
        if path.stat().st_size > _MAX_LINK_FILE_BYTES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        urls = _extract_urls(text)
        if not urls:
            continue
        rel = path.relative_to(storage_dir).as_posix()
        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            albums.append(_album(_unique_name(rel, used_names), url, "file"))
    return albums


def _is_hidden(path: Path, root: Path) -> bool:
    return any(part.startswith(".") for part in path.relative_to(root).parts)


def _unique_name(base: str, used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    number = 2
    while f"{base} ({number})" in used:
        number += 1
    name = f"{base} ({number})"
    used.add(name)
    return name
