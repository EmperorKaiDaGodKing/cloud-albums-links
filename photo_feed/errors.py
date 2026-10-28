"""Plain-language errors a person can act on."""


class AlbumError(Exception):
    """A problem with the album link or the local setup.

    The message is safe to show. It should not include page HTML or photo URLs.
    """
