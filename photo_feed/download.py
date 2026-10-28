"""Save photos and videos into a folder on this computer.

Nothing here uploads a file. Callers pass the folder, and that folder should
stay in .gitignore.
"""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path
from urllib.parse import unquote

from photo_feed.errors import PhotoFeedError
from photo_feed.google_photos import MediaItem

_MAX_BYTES = 512 * 1024 * 1024
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def fetch_bytes(url: str, *, open_url=None, timeout: int = 60) -> tuple[bytes, dict[str, str]]:
    """Download one web URL. Returns the body and response headers."""

    if not url.startswith(("http://", "https://")):
        raise PhotoFeedError("Refusing to download a non-web link.")
    if open_url is None:
        open_url = urllib.request.urlopen
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with open_url(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            if status != 200:
                raise PhotoFeedError(f"Download failed with HTTP {status}.")
            raw = response.read()
            headers = {key: value for key, value in response.headers.items()}
    except PhotoFeedError:
        raise
    except Exception as exc:
        raise PhotoFeedError("Could not download that file.") from exc
    if len(raw) > _MAX_BYTES:
        raise PhotoFeedError("That file is larger than 512 MB, so it was not saved.")
    return raw, headers


def download_items(items: list[MediaItem], dest: Path, *, fetch_bytes=fetch_bytes) -> list[dict]:
    """Write each item into ``dest``. Filenames cannot escape that folder."""

    for item in items:
        if not item.url.startswith(("http://", "https://")):
            raise PhotoFeedError(f"Refusing to download a non-web link for {item.id}.")

    dest.mkdir(parents=True, exist_ok=True)
    dest_resolved = dest.resolve()
    used = {path.name for path in dest_resolved.iterdir()}
    saved: list[dict] = []
    for item in items:
        body, headers = fetch_bytes(item.url)
        preferred = _filename_from_headers(headers) or item.filename or f"{item.id}.bin"
        name = _unique_name(_safe_name(preferred, f"{item.id}.bin"), used)
        target = dest / name
        if dest_resolved not in target.resolve().parents:
            raise PhotoFeedError("Refusing to write outside the download folder.")
        target.write_bytes(body)
        saved.append({"id": item.id, "path": str(target), "bytes": len(body)})
    return saved


def _filename_from_headers(headers: dict[str, str]) -> str | None:
    disposition = ""
    for key, value in headers.items():
        if key.lower() == "content-disposition":
            disposition = value
            break
    if not disposition:
        return None
    encoded = re.search(r"filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)", disposition)
    if encoded:
        return unquote(encoded.group(1).strip())
    quoted = re.search(r'filename\s*=\s*"([^"]+)"', disposition)
    if quoted:
        return quoted.group(1)
    plain = re.search(r"filename\s*=\s*([^;]+)", disposition)
    if plain:
        return plain.group(1).strip().strip('"')
    return None


def _safe_name(name: str, fallback: str) -> str:
    cleaned = unquote(name).replace("\\", "/").split("/")[-1]
    cleaned = re.sub(r"[^A-Za-z0-9._ -]", "_", cleaned).strip("._ ")
    if not cleaned or cleaned in {".", ".."}:
        return fallback
    return cleaned[:180]


def _unique_name(name: str, used: set[str]) -> str:
    if name not in used:
        used.add(name)
        return name
    stem = Path(name).stem
    suffix = Path(name).suffix
    number = 2
    while True:
        candidate = f"{stem}-{number}{suffix}"
        if candidate not in used:
            used.add(candidate)
            return candidate
        number += 1
