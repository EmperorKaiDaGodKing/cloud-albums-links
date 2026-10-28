"""Open a public web page or download one file. No login cookies are stored."""

from __future__ import annotations

import socket
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from photo_feed.errors import AlbumError

# A browser user agent makes photos.app.goo.gl return a JavaScript shell with no
# photos in it. A plain client gets an HTTP redirect to the album page, which
# is the page this tool can read.
USER_AGENT = "photo-feed/1.0"
MAX_HTML_BYTES = 25 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024
_CONSENT_COOKIE = "CONSENT=YES+cb.20210720-07-p0.en+FX+410"


def fetch_text(url: str) -> str:
    """Download an HTML page. Retries once if Google shows a consent wall."""
    page = _read_text(url, cookie=None)
    if _looks_like_consent(page):
        page = _read_text(url, cookie=_CONSENT_COOKIE)
    return page


def download_to_file(url: str, path: Path, max_bytes: int = MAX_DOWNLOAD_BYTES) -> str:
    """Save one file. Returns the content type, such as image/jpeg."""
    _check_http(url)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers=_headers(None))
    try:
        with urlopen(request, timeout=60) as response:
            content_type = response.headers.get_content_type()
            total = 0
            with path.open("wb") as handle:
                while True:
                    chunk = response.read(65_536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise AlbumError("That file is larger than this tool will download.")
                    handle.write(chunk)
            return content_type
    except AlbumError:
        path.unlink(missing_ok=True)
        raise
    except HTTPError as exc:
        path.unlink(missing_ok=True)
        raise AlbumError(f"The file returned HTTP {exc.code}.") from None
    except (URLError, TimeoutError, socket.timeout):
        path.unlink(missing_ok=True)
        raise AlbumError("Could not download that file. Check your internet connection and try again.") from None


def _read_text(url: str, cookie: str | None) -> str:
    _check_http(url)
    request = Request(url, headers=_headers(cookie))
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read(MAX_HTML_BYTES + 1)
            if len(raw) > MAX_HTML_BYTES:
                raise AlbumError("The album page was too large to read.")
            charset = response.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
    except AlbumError:
        raise
    except HTTPError as exc:
        raise AlbumError(
            f"The album link returned HTTP {exc.code}. "
            "If the album is private, share it so anyone with the link can view."
        ) from None
    except (URLError, TimeoutError, socket.timeout):
        raise AlbumError("Could not open the album link. Check your internet connection and try again.") from None


def _headers(cookie: str | None) -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _looks_like_consent(page_html: str) -> bool:
    lowered = page_html.lower()
    return "consent.google.com" in lowered and "googleusercontent.com" not in lowered


def _check_http(url: str) -> None:
    scheme = urlparse(url).scheme.lower()
    if scheme not in {"http", "https"}:
        raise AlbumError("Only http and https links can be opened.")
