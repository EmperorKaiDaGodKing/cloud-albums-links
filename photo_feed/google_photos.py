"""Read a public Google Photos share page.

Google does not offer a login-free API for this. The public share page
(the one from Share → Create link) already contains the photo list in the
HTML, inside AF_initDataCallback data blocks. This module reads that HTML.
It does not log in.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

_PHOTO_LINK = re.compile(r"/share/([A-Za-z0-9_-]+)/photo/([A-Za-z0-9_-]+)(\?[^\"'\s<]*)?")
_LOOSE_URL = re.compile(r"https://lh3\.googleusercontent\.com/pw/[A-Za-z0-9_-]+")
_TITLE_PATTERNS = (
    re.compile(
        r'<meta\s+[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']*)["\']',
        re.IGNORECASE,
    ),
    re.compile(
        r'<meta\s+[^>]*content=["\']([^"\']*)["\'][^>]*property=["\']og:title["\']',
        re.IGNORECASE,
    ),
)
_VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv")


@dataclass
class ParsedPage:
    title: str | None
    items: list[dict]
    photo_pages: list[str]
    sign_in_required: bool
    partial: bool = False


def parse_album_html(page_html: str, album_url: str) -> ParsedPage:
    """Turn one album page into items, or into per-photo links to open next."""
    title = _page_title(page_html)
    sign_in_required = _looks_like_sign_in(page_html)
    arrays = _extract_data_arrays(page_html)
    items: list[dict] = []
    for blob in arrays:
        _collect(blob, items)
    partial = any(_batch_is_partial(blob) for blob in arrays)
    if items:
        return ParsedPage(title, _dedupe(items), [], sign_in_required, partial)

    photo_pages = _photo_page_urls(page_html, album_url)
    if photo_pages:
        return ParsedPage(title, [], photo_pages, sign_in_required, False)

    loose = _dedupe([_item_from_loose(match) for match in _LOOSE_URL.findall(page_html)])
    return ParsedPage(title, loose, [], sign_in_required, False)


def parse_photo_html(page_html: str, page_url: str) -> dict | None:
    """Read one photo page. Returns the first media item, if the page has one."""
    parsed = parse_album_html(page_html, page_url)
    if parsed.items:
        return parsed.items[0]
    return None


def looks_like_google_album(page_html: str) -> bool:
    return "AF_initDataCallback" in page_html or "googleusercontent.com" in page_html


def _batch_is_partial(node) -> bool:
    """True when a batch of photos is followed by a continuation token.

    Google leaves that token empty when the page already has the whole album.
    """
    if isinstance(node, dict):
        return any(_batch_is_partial(value) for value in node.values())
    if not isinstance(node, list):
        return False
    saw_media = False
    for child in node:
        if _media_from_node(child) is not None:
            saw_media = True
        elif isinstance(child, list) and any(_media_from_node(item) is not None for item in child):
            saw_media = True
        elif saw_media and isinstance(child, str) and len(child) > 20 and not child.startswith("http"):
            return True
    return any(_batch_is_partial(child) for child in node if isinstance(child, (list, dict)))


def _collect(node, items: list[dict]) -> None:
    if isinstance(node, dict):
        for value in node.values():
            _collect(value, items)
        return
    if not isinstance(node, list):
        return
    media = _media_from_node(node)
    if media is not None:
        items.append(media)
        return
    for child in node:
        _collect(child, items)


def _media_from_node(node) -> dict | None:
    if not isinstance(node, list) or len(node) < 2:
        return None
    item_id = node[0]
    detail = node[1]
    if not isinstance(item_id, str) or item_id.startswith("http"):
        return None
    if not isinstance(detail, list) or not detail:
        return None
    raw_url = detail[0]
    if not isinstance(raw_url, str) or "googleusercontent.com" not in raw_url:
        return None
    width = _as_int(detail[1]) if len(detail) > 1 else None
    height = _as_int(detail[2]) if len(detail) > 2 else None
    date = _timestamp_to_iso(node[2]) if len(node) > 2 else None
    kind = _detect_kind(node, raw_url)
    return _item(item_id, raw_url, kind, width, height, date)


def _item_from_loose(raw_url: str) -> dict:
    base = _strip_size(raw_url)
    token = base.rstrip("/").rsplit("/", 1)[-1] or "photo"
    kind = "video" if token.lower().endswith(_VIDEO_EXTENSIONS) else "image"
    return _item(token, raw_url, kind, None, None, None)


def _item(item_id: str, raw_url: str, kind: str, width: int | None, height: int | None, date: str | None) -> dict:
    base = _strip_size(raw_url)
    return {
        "id": item_id,
        "filename": _filename_for(item_id, kind),
        "kind": kind,
        "url": base + "=s2048",
        "original_url": base + "=d",
        "width": width,
        "height": height,
        "date": date,
        "size_bytes": None,
    }


def _photo_page_urls(page_html: str, album_url: str) -> list[str]:
    album_query = urlparse(album_url).query
    found: list[str] = []
    seen: set[str] = set()
    for match in _PHOTO_LINK.finditer(page_html):
        album_id, photo_id, query = match.group(1), match.group(2), match.group(3) or ""
        if query.startswith("?"):
            query = query[1:]
        if not query:
            query = album_query
        if photo_id in seen:
            continue
        seen.add(photo_id)
        found.append(
            urlunparse(
                ("https", "photos.google.com", f"/share/{album_id}/photo/{photo_id}", "", query, "")
            )
        )
    return found


def _extract_data_arrays(page_html: str) -> list:
    arrays = []
    marker = "data:"
    index = 0
    while True:
        found = page_html.find(marker, index)
        if found == -1:
            break
        start = found + len(marker)
        while start < len(page_html) and page_html[start] in " \t\r\n":
            start += 1
        if start >= len(page_html) or page_html[start] != "[":
            index = found + len(marker)
            continue
        end = _match_bracket(page_html, start)
        if end == -1:
            index = found + len(marker)
            continue
        try:
            arrays.append(json.loads(page_html[start : end + 1]))
        except json.JSONDecodeError:
            pass
        index = end + 1
    return arrays


def _match_bracket(text: str, open_index: int) -> int:
    depth = 0
    in_string = False
    quote = ""
    index = open_index
    while index < len(text):
        char = text[index]
        if in_string:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                in_string = False
            index += 1
            continue
        if char in {'"', "'"}:
            in_string = True
            quote = char
            index += 1
            continue
        if char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _page_title(page_html: str) -> str | None:
    for pattern in _TITLE_PATTERNS:
        match = pattern.search(page_html)
        if match:
            title = html.unescape(match.group(1)).strip()
            return title or None
    return None


def _looks_like_sign_in(page_html: str) -> bool:
    lowered = page_html.lower()
    return (
        "accounts.google.com/servicelogin" in lowered
        or "accounts.google.com/v3/signin" in lowered
        or "sign in - google accounts" in lowered
    )


def _detect_kind(node, raw_url: str) -> str:
    for text in _iter_strings(node):
        lowered = text.lower()
        if lowered.startswith("video/") or "videoplayback" in lowered:
            return "video"
        if lowered.endswith(_VIDEO_EXTENSIONS):
            return "video"
    if raw_url.lower().endswith(_VIDEO_EXTENSIONS):
        return "video"
    return "image"


def _iter_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for child in node:
            yield from _iter_strings(child)
    elif isinstance(node, dict):
        for child in node.values():
            yield from _iter_strings(child)


def _timestamp_to_iso(value) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number > 10**14:
        seconds = number / 1_000_000
    elif number > 10**11:
        seconds = number / 1_000
    else:
        return None
    try:
        moment = datetime.fromtimestamp(seconds, timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_int(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _strip_size(raw_url: str) -> str:
    base, separator, _rest = raw_url.partition("=")
    return base if separator else raw_url


def _filename_for(item_id: str, kind: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", item_id).strip("._") or "item"
    if "." in safe:
        return safe
    extension = {"image": ".jpg", "video": ".mp4"}.get(kind, "")
    return safe + extension


def _dedupe(items: list[dict]) -> list[dict]:
    kept: list[dict] = []
    seen: set[str] = set()
    for item in items:
        base = _strip_size(item["url"])
        if base in seen:
            continue
        seen.add(base)
        kept.append(item)
    return kept
