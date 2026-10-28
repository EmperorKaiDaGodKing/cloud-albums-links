"""Turn saved links into the JSON documents the CLI and the MCP server share."""

from __future__ import annotations

import subprocess
from pathlib import Path

from photo_feed.download import download_items
from photo_feed.download import fetch_bytes as default_fetch_bytes
from photo_feed.errors import PhotoFeedError
from photo_feed.google_photos import fetch_html as default_fetch_html
from photo_feed.google_photos import parse_shared_album_html
from photo_feed.sources import default_config_path, load_albums, resolve_album
from photo_feed.terabox import list_share

_BATCH_NOTE = (
    "This is the first batch from the public share page, about 300 items. "
    "Google loads the rest only when someone scrolls, so a bigger album is cut off."
)
_TRUNCATED_NOTE = (
    "This album has more items than the public page included. "
    "Only the first batch is listed (about 300)."
)
_DOWNLOAD_WARNING = (
    "Warning: that download folder is not git-ignored. "
    "Do not commit it. This repo is public, so committed photos would be visible to everyone."
)


def albums_document(root: Path, env: dict[str, str]) -> dict:
    """Albums from the first source that has a link."""

    albums = _load(root, env)
    return {
        "albums": [
            {
                "name": album.name,
                "url": album.url,
                "provider": album.provider,
                "source": album.source,
                "readable": album.readable,
            }
            for album in albums
        ],
        "note": _source_note(albums),
    }


def photos_document(
    root: Path,
    env: dict[str, str],
    *,
    url: str | None = None,
    name: str | None = None,
    download_dir: Path | None = None,
    fetch_html=default_fetch_html,
    fetch_file=None,
) -> dict:
    """List the photos and videos in one album."""

    albums = _load(root, env)
    album = resolve_album(albums, url=_blank_to_none(url), name=_blank_to_none(name))
    if album.provider == "terabox":
        list_share(album.url)
    if not album.readable:
        raise PhotoFeedError(
            "This tool reads public Google Photos share links "
            "(photos.app.goo.gl or photos.google.com). That link is a different site."
        )
    html = fetch_html(album.url)
    listing = parse_shared_album_html(html)
    document = {
        "album": {
            "name": album.name,
            "url": album.url,
            "provider": album.provider,
            "source": album.source,
            "title": listing.title,
            "id": listing.album_id,
        },
        "items": [item.as_dict() for item in listing.items],
        "truncated": listing.truncated,
        "note": _TRUNCATED_NOTE if listing.truncated else _BATCH_NOTE,
    }
    if download_dir is not None:
        document["downloaded"] = download_items(
            listing.items,
            download_dir,
            fetch_bytes=fetch_file or default_fetch_bytes,
        )
        if path_is_gitignored(download_dir, cwd=root) is False:
            document["warning"] = _DOWNLOAD_WARNING
    return document


def path_is_gitignored(path: Path, *, cwd: Path) -> bool | None:
    """True when git would ignore ``path``. None when git cannot say."""

    try:
        completed = subprocess.run(
            ["git", "check-ignore", "-q", "--", str(path)],
            cwd=cwd,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    return None


def _load(root: Path, env: dict[str, str]):
    return load_albums(
        env,
        default_config_path(root, env),
        root / "shared-album-link-storage",
    )


def _source_note(albums) -> str:
    if not albums:
        return (
            "No album links found. Set PHOTO_FEED_URL, create photo-feed.local.json, "
            "or put a link in shared-album-link-storage/."
        )
    source = albums[0].source
    if source == "env":
        return "Using PHOTO_FEED_URL. Other saved links were left unused."
    if source == "config":
        return (
            "Using photo-feed.local.json. "
            "Link files in shared-album-link-storage were left unused."
        )
    if source == "file":
        return (
            "Using link files in shared-album-link-storage. "
            "Set PHOTO_FEED_URL or photo-feed.local.json to override them."
        )
    return "Using the album link you passed in."


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None
