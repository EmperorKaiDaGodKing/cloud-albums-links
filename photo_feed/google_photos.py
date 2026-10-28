"""Read a public Google Photos shared album without signing in.

Google serves the album page to anyone who has the share link. The photo
list is embedded in that page as ``AF_initDataCallback`` data. This is the
same page a browser opens. It is not an official API, and Google can change
the page. The first response includes one batch of items (about 300). The
rest of a very large album is loaded only as someone scrolls.
"""

from __future__ import annotations

import gzip
import json
import re
import urllib.request
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone

from photo_feed.errors import PhotoFeedError

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
_FALLBACK_URL_RE = re.compile(r"https://lh3\.googleusercontent\.com/pw/[A-Za-z0-9_\-]+")
_FILENAME_RE = re.compile(
    r"^[^/\\]+\.(?:jpe?g|png|gif|webp|heic|heif|bmp|tiff?|mp4|mov|m4v|avi|mkv|webm)$",
    re.IGNORECASE,
)
_MAX_HTML_BYTES = 20_000_000
# 1990-01-01 through 2100-01-01, in seconds and in milliseconds.
_MIN_SECONDS = 631152000
_MAX_SECONDS = 4102444800
_MIN_MILLIS = _MIN_SECONDS * 1000
_MAX_MILLIS = _MAX_SECONDS * 1000

_EMPTY_PAGE_MESSAGE = (
    "No photos were found. In Google Photos, open the album, tap Share, then "
    "Create link, and paste that link. Link sharing has to be turned on. "
    "A very new or empty album can also look like this."
)


@dataclass(frozen=True)
class MediaItem:
    """One photo or video from a shared album."""

    id: str
    filename: str | None
    kind: str
    url: str
    width: int | None
    height: int | None
    created_at: str | None
    added_at: str | None
    size_bytes: int | None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "kind": self.kind,
            "url": self.url,
            "width": self.width,
            "height": self.height,
            "created_at": self.created_at,
            "added_at": self.added_at,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class AlbumListing:
    """Photos and videos parsed from one share page."""

    album_id: str | None
    title: str | None
    items: list[MediaItem]
    truncated: bool


def fetch_html(url: str, *, open_url=None, timeout: int = 30) -> str:
    """Download the share page HTML. Redirects are followed by urllib."""

    if open_url is None:
        open_url = urllib.request.urlopen
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip",
        },
    )
    try:
        with open_url(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            if status != 200:
                raise PhotoFeedError(
                    f"The album link returned HTTP {status}. "
                    "Check that it is a Google Photos share link and that link sharing is on."
                )
            raw = _decode_body(response.read(), getattr(response, "headers", None))
    except PhotoFeedError:
        raise
    except Exception as exc:
        raise PhotoFeedError(
            "Could not open the album link. Check the link and your internet connection."
        ) from exc
    if isinstance(raw, str):
        text = raw
        size = len(raw.encode("utf-8"))
    else:
        size = len(raw)
        text = raw.decode("utf-8", errors="replace")
    if size > _MAX_HTML_BYTES:
        raise PhotoFeedError("The album page was larger than this tool will read.")
    return text


def _decode_body(raw, headers):
    """Turn a response body into HTML bytes. Does not include the body in errors."""

    if isinstance(raw, str):
        return raw
    encoding = ""
    if headers is not None and hasattr(headers, "get"):
        encoding = (headers.get("Content-Encoding") or "").lower()
    if "br" in {part.strip() for part in encoding.split(",") if part.strip()}:
        raise PhotoFeedError(
            "The album page was compressed in a way this tool cannot read. Try the link again."
        )
    if "gzip" in encoding or raw[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(raw)
        except (OSError, EOFError, gzip.BadGzipFile) as exc:
            raise PhotoFeedError("The album page could not be read.") from exc
    if "deflate" in encoding:
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


def parse_shared_album_html(html: str) -> AlbumListing:
    """Turn share-page HTML into photos and videos.

    Raises PhotoFeedError when the page has no media. The error does not
    include the page body, which can contain album contents.
    """

    items: list[MediaItem] = []
    seen: set[str] = set()
    title = None
    album_id = None
    truncated = False
    for data in _extract_data_arrays(html):
        found_id, found_title, found_truncated = _album_meta(data)
        if found_title and title is None:
            album_id = found_id
            title = found_title
        truncated = truncated or found_truncated
        _collect_media(data, items, seen)
    if not items:
        _collect_fallback_urls(html, items, seen)
    if not items:
        raise PhotoFeedError(_EMPTY_PAGE_MESSAGE)
    return AlbumListing(album_id=album_id, title=title, items=items, truncated=truncated)


def _extract_data_arrays(html: str) -> list[list]:
    arrays: list[list] = []
    cursor = 0
    while True:
        cursor = html.find("data:", cursor)
        if cursor < 0:
            return arrays
        start = _array_start(html, cursor + len("data:"))
        if start < 0:
            cursor += len("data:")
            continue
        end = _match_bracket(html, start)
        if end < 0:
            cursor += len("data:")
            continue
        try:
            parsed = json.loads(html[start : end + 1])
        except json.JSONDecodeError:
            cursor = end + 1
            continue
        if isinstance(parsed, list):
            arrays.append(parsed)
        cursor = end + 1


def _array_start(html: str, pos: int) -> int:
    rest = html[pos:]
    stripped = rest.lstrip()
    offset = pos + (len(rest) - len(stripped))
    if stripped.startswith("["):
        return offset
    if not stripped.startswith("function"):
        return -1
    returned = stripped.find("return")
    if returned < 0:
        return -1
    bracket = stripped.find("[", returned)
    if bracket < 0:
        return -1
    if stripped[returned + len("return") : bracket].strip() != "":
        return -1
    return offset + bracket


def _match_bracket(text: str, open_index: int) -> int:
    """Index of the closing bracket, ignoring brackets inside strings."""

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
        if char in ('"', "'"):
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


def _album_meta(data: list) -> tuple[str | None, str | None, bool]:
    truncated = len(data) > 2 and isinstance(data[2], str) and bool(data[2].strip())
    album_id = None
    title = None
    if len(data) > 3 and isinstance(data[3], list) and len(data[3]) >= 2:
        maybe_id, maybe_title = data[3][0], data[3][1]
        if (
            isinstance(maybe_id, str)
            and isinstance(maybe_title, str)
            and not maybe_title.startswith("http")
        ):
            album_id = maybe_id
            title = maybe_title
    return album_id, title, truncated


def _collect_media(node, items: list[MediaItem], seen: set[str]) -> None:
    if not isinstance(node, list):
        return
    item = _media_from_node(node)
    if item is not None:
        if item.id not in seen:
            seen.add(item.id)
            items.append(item)
        return
    for child in node:
        if isinstance(child, list):
            _collect_media(child, items, seen)


def _media_from_node(node: list) -> MediaItem | None:
    if len(node) < 2 or not isinstance(node[0], str) or not node[0].strip():
        return None
    detail = node[1]
    if not isinstance(detail, list) or not detail or not isinstance(detail[0], str):
        return None
    raw_url = detail[0]
    if not raw_url.startswith("https://") or _is_avatar(raw_url):
        return None
    width = _positive_int(detail[1]) if len(detail) > 1 else None
    height = _positive_int(detail[2]) if len(detail) > 2 else None
    video = _has_video_marker(node)
    if video:
        kind = "video"
    elif width and height:
        kind = "photo"
    elif _iso_timestamp(node[2] if len(node) > 2 else None):
        kind = "video"
    else:
        return None
    created_at = _iso_timestamp(node[2]) if len(node) > 2 else None
    added_at = _iso_timestamp(node[5]) if len(node) > 5 else None
    return MediaItem(
        id=node[0].strip(),
        filename=_find_filename(node),
        kind=kind,
        url=_direct_url(raw_url),
        width=width,
        height=height,
        created_at=created_at,
        added_at=added_at,
        size_bytes=_size_bytes(detail),
    )


def _collect_fallback_urls(html: str, items: list[MediaItem], seen: set[str]) -> None:
    number = 0
    for match in _FALLBACK_URL_RE.finditer(html):
        number += 1
        media_id = f"url-{number}"
        if media_id in seen:
            continue
        seen.add(media_id)
        items.append(
            MediaItem(
                id=media_id,
                filename=None,
                kind="photo",
                url=_direct_url(match.group(0)),
                width=None,
                height=None,
                created_at=None,
                added_at=None,
                size_bytes=None,
            )
        )


def _direct_url(url: str) -> str:
    if "googleusercontent.com" not in url:
        return url
    return url.split("=", 1)[0] + "=d"


def _is_avatar(url: str) -> bool:
    return "googleusercontent.com" in url and "/a/" in url and "/pw/" not in url


def _positive_int(value) -> int | None:
    if type(value) is int and value > 0:
        return value
    return None


def _iso_timestamp(value) -> str | None:
    if type(value) is not int:
        return None
    if _MIN_MILLIS <= value <= _MAX_MILLIS:
        seconds = value / 1000
    elif _MIN_SECONDS <= value <= _MAX_SECONDS:
        seconds = value
    else:
        return None
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _size_bytes(detail: list) -> int | None:
    for part in detail[3:]:
        if isinstance(part, list) and len(part) == 1 and type(part[0]) is int and part[0] > 0:
            return part[0]
    return None


def _find_filename(node) -> str | None:
    found: list[str] = []

    def walk(value) -> None:
        if isinstance(value, str):
            candidate = value.strip()
            if _FILENAME_RE.match(candidate):
                found.append(candidate)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(node)
    return found[0] if found else None


def _has_video_marker(node) -> bool:
    def walk(value) -> bool:
        if isinstance(value, str):
            lowered = value.lower()
            return (
                "video/" in lowered
                or "video-downloads.googleusercontent.com" in lowered
                or "type=video" in lowered
            )
        if isinstance(value, list):
            return any(walk(child) for child in value)
        return False

    return walk(node)
