import json
import os
import select
import subprocess
import sys
import unittest
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from photo_feed.mcp_server import handle_message, read_message, write_message

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def stored_album_urls():
    storage = ROOT / "shared-album-link-storage"
    urls = []
    for path in storage.rglob("*"):
        if not path.is_file():
            continue
        for token in path.read_text(encoding="utf-8", errors="ignore").split():
            if token.startswith("http://") or token.startswith("https://"):
                urls.append(token.strip())
    return urls


def assert_no_stored_links(test, text):
    for url in stored_album_urls():
        if url and url in text:
            test.fail("output contained a link stored in shared-album-link-storage")


def frame(message):
    body = json.dumps(message).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


class McpProtocolTest(unittest.TestCase):
    def test_content_length_and_newline_readers(self):
        payload = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
        buffered = BytesIO()
        write_message(buffered, payload)
        buffered.seek(0)
        self.assertEqual(read_message(buffered), payload)

        line = BytesIO((json.dumps(payload) + "\n").encode("utf-8"))
        self.assertEqual(read_message(line), payload)

    def test_initialize_and_tools(self):
        init = handle_message({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
        })
        self.assertEqual(init["result"]["serverInfo"]["name"], "photo-feed")
        self.assertEqual(init["result"]["protocolVersion"], "2024-11-05")
        self.assertIsNone(handle_message({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }))

        listed = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [tool["name"] for tool in listed["result"]["tools"]]
        self.assertEqual(names, ["list_albums", "list_album_photos"])

    def test_list_albums_tool_uses_the_env_link(self):
        previous = os.environ.get("PHOTO_FEED_URL")
        os.environ["PHOTO_FEED_URL"] = "https://photos.example.test/album"
        try:
            response = handle_message({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_albums", "arguments": {}},
            })
        finally:
            if previous is None:
                os.environ.pop("PHOTO_FEED_URL", None)
            else:
                os.environ["PHOTO_FEED_URL"] = previous

        text = response["result"]["content"][0]["text"]
        self.assertFalse(response["result"]["isError"])
        self.assertIn("photos.example.test", text)
        assert_no_stored_links(self, text)

    def test_list_album_photos_tool_can_use_a_fake_fetcher(self):
        html = (FIXTURES / "google_album.html").read_text(encoding="utf-8")
        previous = os.environ.get("PHOTO_FEED_URL")
        os.environ["PHOTO_FEED_URL"] = "https://photos.google.com/share/FixtureAlbum?key=fixture-key"
        try:
            response = handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "list_album_photos", "arguments": {}},
                },
                fetch_text=lambda url: html,
            )
        finally:
            if previous is None:
                os.environ.pop("PHOTO_FEED_URL", None)
            else:
                os.environ["PHOTO_FEED_URL"] = previous

        self.assertFalse(response["result"]["isError"])
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["count"], 2)
        assert_no_stored_links(self, response["result"]["content"][0]["text"])


class McpSubprocessTest(unittest.TestCase):
    def test_server_speaks_mcp_and_reads_the_fixture_page(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import threading

        album = (FIXTURES / "google_album.html").read_bytes()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(album)))
                self.end_headers()
                self.wfile.write(album)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        env = os.environ.copy()
        env["PHOTO_FEED_URL"] = f"http://127.0.0.1:{port}/album"
        env["PYTHONUNBUFFERED"] = "1"
        proc = subprocess.Popen(
            [sys.executable, "-m", "photo_feed", "mcp"],
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            assert proc.stdin is not None
            assert proc.stdout is not None
            proc.stdin.write(frame({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
            }))
            proc.stdin.write(frame({"jsonrpc": "2.0", "method": "notifications/initialized"}))
            proc.stdin.write(frame({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_album_photos", "arguments": {}},
            }))
            proc.stdin.close()

            ready, _, _ = select.select([proc.stdout], [], [], 10)
            self.assertTrue(ready, "MCP server did not answer")
            first = read_message(proc.stdout)
            second = read_message(proc.stdout)
            self.assertEqual(first["id"], 1)
            self.assertEqual(second["id"], 2)
            payload = json.loads(second["result"]["content"][0]["text"])
            self.assertEqual(payload["items"][0]["id"], "fixture-photo-1")
            stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            assert_no_stored_links(self, json.dumps(first) + json.dumps(second) + stderr)
        finally:
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
            proc.kill()
            proc.wait(timeout=5)
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
