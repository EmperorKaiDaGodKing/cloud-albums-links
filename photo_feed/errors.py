"""Errors a person can read. Messages stay short and leave album contents out."""


class PhotoFeedError(Exception):
    """The album could not be read. The message is safe to show to a person or a bot."""
