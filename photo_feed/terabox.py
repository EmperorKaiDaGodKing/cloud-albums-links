"""TeraBox share links.

A public Google Photos link can be read without an account. A TeraBox share
link cannot: the site asks for a signed-in cookie and often a captcha, then
signs each file URL. Sending the link to a third-party "downloader" site
would also hand a private album to someone else, so this tool does not do that.
"""

from __future__ import annotations

from photo_feed.errors import PhotoFeedError

REASON = (
    "TeraBox share links are recognized, but this tool cannot list them without signing in. "
    "TeraBox asks for a session cookie and often a captcha before it will show the file list, "
    "and the file links themselves are signed. "
    "This tool does not log in, and it does not send your link to a third-party downloader. "
    "Use a Google Photos shared album link instead."
)


def list_share(url: str) -> None:
    """Refuse to list a TeraBox share. ``url`` is accepted and not repeated."""

    del url
    raise PhotoFeedError(REASON)
