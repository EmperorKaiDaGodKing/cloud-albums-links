"""List albums and the photos inside them.

Callers pass a fetch function in tests. The command line uses the real network.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Callable, Never
from urllib.parse import urlparse

from photo_feed.albums import Album, discover_albums, extract_urls, provider_for, slug
from photo_feed.download import ensure_safe_download_dir, file_path_for
from photo_feed.errors import AlbumError
from photo_feed.google_photos import looks_like_google_album, parse_album_html, parse_photo_html
from photo_feed.net import download_to_file, fetch_text as default_fetch_text
from photo_feed.terabox import TERABOX_ERROR

FetchText = Callable[[str], str]
FetchDownload = Callable[[str, Path], str]

SIGN_IN_ERROR = (
    "Google asked for a sign-in, so this is not a public album link. "
    "In Google Photos, open the album, tap Share, then Create link, "
    "and set it so anyone with the link can view. This tool does not log in."
)
CONSENT_ERROR = (
    "Google showed a cookie consent page instead of the album. "
    "Try the command again. If it keeps happening, open the link in a private "
    "browser window and check that anyone with the link can view it."
)
EMPTY_ERROR = (
    "No photos were found. Share the album so anyone with the link can view it "
    "(Google Photos: Share, then Create link). "
    "If the link already works in a browser, Google may have changed the page and this tool needs an update."
)
SHORT_LINK_ERROR = (
    "Google returned the short-link page instead of the album. "
    "Run the command again. If it still happens, open the link in a browser, "
    "copy the long photos.google.com/share address from the address bar, and use that."
)
UNKNOWN_ERROR = (
    "This link is not a Google Photos or TeraBox share link. "
    "Use a photos.app.goo.gl link or a photos.google.com/share link."
)


def list_albums(root: Path) -> dict:
    found = discover_albums(root)
    return {
        "source": found.source,
        "albums": [album.to_dict() for album in found.albums],
        "note": found.note,
    }


def list_album_photos(
    root: Path,
    album_id: str | None = None,
    url: str | None = None,
    limit: int | None = None,
    download_dir: Path | None = None,
    download: bool = False,
    fetch_text: FetchText | None = None,
    fetch_download: FetchDownload | None = None,
    max_photo_pages: int = 40,
) -> dict:
    """Return JSON-ready details for one album."""
    root = Path(root)
    album = _select_album(root, album_id, url)
    if download and download_dir is None:
        download_dir = root / "downloads" / album.id.replace("/", "__")
    if download_dir is not None:
        download_dir = ensure_safe_download_dir(root, Path(download_dir))

    provider = album.provider
    if provider == "terabox":
        return _error_payload(album, TERABOX_ERROR)
    if provider == "unknown":
        page_html = _fetch(fetch_text, album.url)
        if looks_like_google_album(page_html):
            album = replace(album, provider="google-photos")
            return _read_google(
                album,
                page_html,
                limit=limit,
                download_dir=download_dir,
                fetch_text=fetch_text,
                fetch_download=fetch_download,
                max_photo_pages=max_photo_pages,
            )
        return _error_payload(album, UNKNOWN_ERROR)
    if provider == "google-photos":
        page_html = _fetch(fetch_text, album.url)
        return _read_google(
            album,
            page_html,
            limit=limit,
            download_dir=download_dir,
            fetch_text=fetch_text,
            fetch_download=fetch_download,
            max_photo_pages=max_photo_pages,
        )
    _never: Never = provider
    raise RuntimeError(_never)


def _read_google(
    album: Album,
    page_html: str,
    limit: int | None,
    download_dir: Path | None,
    fetch_text: FetchText | None,
    fetch_download: FetchDownload | None,
    max_photo_pages: int,
) -> dict:
    parsed = parse_album_html(page_html, album.url)
    items = list(parsed.items)
    notes: list[str] = []
    partial = parsed.partial
    if parsed.partial:
        notes.append(
            "Google only included the first batch of this album on the public page. There may be more photos."
        )
    if not items and parsed.photo_pages:
        pages = parsed.photo_pages
        if max_photo_pages >= 0 and len(pages) > max_photo_pages:
            pages = pages[:max_photo_pages]
            partial = True
            notes.append(
                f"Opened the first {max_photo_pages} photo pages. The album page listed more."
            )
        for page_url in pages:
            item = parse_photo_html(_fetch(fetch_text, page_url), page_url)
            if item is not None:
                items.append(item)
    if limit is not None:
        if limit < 0:
            raise AlbumError("Limit has to be zero or more.")
        if len(items) > limit:
            items = items[:limit]
            partial = True
            notes.append(f"Stopped after {limit} items because a limit was set.")

    if not items:
        if parsed.sign_in_required:
            return _error_payload(album, SIGN_IN_ERROR, parsed.title)
        if "consent.google.com" in page_html.lower():
            return _error_payload(album, CONSENT_ERROR, parsed.title)
        if "photos.app.goo.gl" in page_html and "googleusercontent.com" not in page_html:
            return _error_payload(album, SHORT_LINK_ERROR, parsed.title)
        return _error_payload(album, EMPTY_ERROR, parsed.title)

    if download_dir is not None:
        _download_items(items, download_dir, fetch_download)

    payload = {
        "album": {**album.to_dict(), "title": parsed.title},
        "count": len(items),
        "partial": partial,
        "note": " ".join(notes) if notes else None,
        "items": items,
    }
    if download_dir is not None:
        manifest = download_dir / "album.json"
        manifest.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        payload = {**payload, "manifest": str(manifest)}
    return payload


def _download_items(items: list[dict], dest: Path, fetch_download: FetchDownload | None) -> None:
    saver = fetch_download or download_to_file
    used: set[str] = set()
    for item in items:
        target = file_path_for(dest, item["filename"], used)
        try:
            saver(item["original_url"], target)
        except AlbumError as exc:
            item["saved_path"] = None
            item["download_error"] = str(exc)
            continue
        item["saved_path"] = str(target)


def _select_album(root: Path, album_id: str | None, url: str | None) -> Album:
    if url:
        urls = extract_urls(url)
        if len(urls) != 1:
            raise AlbumError("That album link is not a web link.")
        chosen = urls[0]
        host = urlparse(chosen).netloc or "album"
        return Album(
            id=slug(host),
            name="Album",
            url=chosen,
            provider=provider_for(chosen),
            source="argument",
        )
    found = discover_albums(root)
    if album_id:
        for album in found.albums:
            if album.id == album_id:
                return album
        raise AlbumError(f"No album with id {album_id}. Run list-albums to see the ids.")
    if len(found.albums) == 1:
        return found.albums[0]
    if not found.albums:
        raise AlbumError(found.note or "No album link found.")
    ids = ", ".join(album.id for album in found.albums)
    raise AlbumError(f"More than one album is configured. Pass an album id. Available ids: {ids}")


def _fetch(fetch_text: FetchText | None, url: str) -> str:
    fetcher = fetch_text or default_fetch_text
    page = fetcher(url)
    if not isinstance(page, str):
        raise AlbumError("Could not open the album link.")
    return page


def _error_payload(album: Album, message: str, title: str | None = None) -> dict:
    return {
        "album": {**album.to_dict(), "title": title},
        "count": 0,
        "partial": False,
        "note": None,
        "items": [],
        "error": message,
    }
