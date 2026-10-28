"""A tiny MCP server bots can talk to over stdin and stdout."""

import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from photo_feed.mcp_server import handle, serve

FIXTURE = Path(__file__).parent / "fixtures" / "google_share_page.html"
ALBUM = "https://photos.app.goo.gl/example"


def _fetch(_url, **_kwargs):
    return FIXTURE.read_text(encoding="utf-8")


class McpServerTests(unittest.TestCase):
    def test_initialize_list_and_call_round_trip(self):
        root = Path(tempfile.mkdtemp())
        env = {"PHOTO_FEED_URL": ALBUM}
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_albums", "arguments": {}},
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "list_album_photos", "arguments": {}},
            },
        ]
        stdin = StringIO("".join(json.dumps(message) + "\n" for message in messages))
        stdout = StringIO()
        serve(stdin, stdout, root=root, env=env, fetch_html=_fetch, fetch_file=None)

        lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
        self.assertEqual(len(lines), 4)
        init, tools, albums, photos = (json.loads(line) for line in lines)

        self.assertEqual(init["id"], 1)
        self.assertEqual(init["result"]["serverInfo"]["name"], "photo-feed")
        self.assertEqual(init["result"]["protocolVersion"], "2024-11-05")
        names = [tool["name"] for tool in tools["result"]["tools"]]
        self.assertEqual(names, ["list_albums", "list_album_photos"])

        album_payload = json.loads(albums["result"]["content"][0]["text"])
        self.assertFalse(albums["result"]["isError"])
        self.assertEqual(album_payload["albums"][0]["url"], ALBUM)

        photo_payload = json.loads(photos["result"]["content"][0]["text"])
        self.assertFalse(photos["result"]["isError"])
        self.assertEqual(photo_payload["items"][0]["id"], "fixture-photo-1")
        self.assertEqual(photo_payload["items"][1]["kind"], "video")

    def test_unknown_tool_is_an_error_result(self):
        response = handle(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {"name": "delete_everything", "arguments": {}},
            },
            root=Path(tempfile.mkdtemp()),
            env={},
            fetch_html=_fetch,
            fetch_file=None,
        )
        self.assertEqual(response["id"], 9)
        self.assertTrue(response["result"]["isError"])

    def test_terabox_tool_error_does_not_repeat_the_link(self):
        response = handle(
            {
                "jsonrpc": "2.0",
                "id": "call-1",
                "method": "tools/call",
                "params": {
                    "name": "list_album_photos",
                    "arguments": {"url": "https://www.terabox.com/s/1privateExample"},
                },
            },
            root=Path(tempfile.mkdtemp()),
            env={},
            fetch_html=_fetch,
            fetch_file=None,
        )
        text = response["result"]["content"][0]["text"]
        self.assertTrue(response["result"]["isError"])
        self.assertIn("captcha", text.lower())
        self.assertNotIn("1privateExample", text)


if __name__ == "__main__":
    unittest.main()
