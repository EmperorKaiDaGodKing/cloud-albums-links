"""TeraBox share links are recognized and then refused.

Listing a TeraBox share without a signed-in session is not reliable: the
site asks for a cookie and often a captcha, and file links are signed.
This tool must not call the network and must not pass the link to someone else.
"""

import unittest
from unittest import mock

from photo_feed.errors import PhotoFeedError
from photo_feed.terabox import list_share


class TeraBoxStubTests(unittest.TestCase):
    def test_refuses_without_opening_a_connection(self):
        def boom(*args, **kwargs):
            raise AssertionError("TeraBox listing must not use the network")

        with mock.patch("urllib.request.urlopen", boom):
            with self.assertRaises(PhotoFeedError) as caught:
                list_share("https://www.terabox.com/s/1privateExample")

        message = str(caught.exception).lower()
        self.assertNotIn("1privateexample", message)
        self.assertIn("sign", message)
        self.assertIn("captcha", message)
        self.assertIn("third-party", message)


if __name__ == "__main__":
    unittest.main()
