"""TeraBox share links.

A public TeraBox page does not list its files in the HTML. Getting the list
means running TeraBox's anti-bot script to mint a jsToken, then asking another
endpoint for a signed download URL. That signing step often returns a captcha
from a cloud computer such as a Codespace. There is no stable login-free API.

This module explains that instead of pretending a download worked, and it does
not send the link to a third-party downloader.
"""

TERABOX_ERROR = (
    "TeraBox share links are not supported. "
    "The share page does not include the file list in a form this tool can read "
    "without running TeraBox's anti-bot script to mint a jsToken. "
    "Direct file links then need a signed URL, and TeraBox often answers that "
    "request with a captcha, especially from a Codespace. "
    "This tool will not sign in and will not send your link to a third-party downloader. "
    "Use a Google Photos link shared so anyone with the link can view."
)
