"""MCP server over stdin and stdout.

The protocol is newline-delimited JSON-RPC. Album contents go in the tool
result only. This process does not print them anywhere else.
"""

from __future__ import annotations

import json
from pathlib import Path

from photo_feed import __version__
from photo_feed.errors import PhotoFeedError
from photo_feed.service import albums_document, photos_document

_PROTOCOL = "2024-11-05"
_SUPPORTED = {"2024-11-05", "2025-03-26", "2025-06-18"}

_TOOLS = [
    {
        "name": "list_albums",
        "description": (
            "List the shared album links this tool knows about. "
            "Does not open the albums or download photos."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "list_album_photos",
        "description": (
            "List photos and videos in one public Google Photos shared album. "
            "Pass url, or a name from list_albums. With no arguments, uses the one saved link. "
            "Optional download_dir saves copies on this computer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Shared album link, such as https://photos.app.goo.gl/...",
                },
                "name": {
                    "type": "string",
                    "description": "Album name returned by list_albums.",
                },
                "download_dir": {
                    "type": "string",
                    "description": "Folder to save copies into. Leave this out to only list links.",
                },
            },
            "additionalProperties": False,
        },
    },
]


def handle(message: dict, *, root: Path, env: dict[str, str], fetch_html, fetch_file) -> dict | None:
    """Answer one JSON-RPC message. Notifications return None."""

    if not isinstance(message, dict):
        return _error(None, -32600, "Invalid request")
    method = message.get("method")
    has_id = "id" in message
    msg_id = message.get("id")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    if isinstance(method, str) and method.startswith("notifications/"):
        return None
    if method == "initialize":
        version = params.get("protocolVersion") or _PROTOCOL
        if version not in _SUPPORTED:
            version = _PROTOCOL
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "photo-feed", "version": __version__},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": _TOOLS}}
    if method == "tools/call":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": _call_tool(
                params.get("name"),
                params.get("arguments") or {},
                root=root,
                env=env,
                fetch_html=fetch_html,
                fetch_file=fetch_file,
            ),
        }
    if not has_id:
        return None
    return _error(msg_id, -32601, "Unknown method")


def serve(stdin, stdout, *, root: Path, env: dict[str, str], fetch_html, fetch_file) -> None:
    """Read JSON-RPC messages until stdin closes."""

    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = _error(None, -32700, "Parse error")
        else:
            response = handle(
                message,
                root=root,
                env=env,
                fetch_html=fetch_html,
                fetch_file=fetch_file,
            )
        if response is None:
            continue
        stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        stdout.flush()


def _call_tool(name, arguments, *, root, env, fetch_html, fetch_file) -> dict:
    if not isinstance(arguments, dict):
        arguments = {}
    try:
        if name == "list_albums":
            payload = albums_document(root, env)
        elif name == "list_album_photos":
            download_dir = arguments.get("download_dir")
            payload = photos_document(
                root,
                env,
                url=arguments.get("url") if isinstance(arguments.get("url"), str) else None,
                name=arguments.get("name") if isinstance(arguments.get("name"), str) else None,
                download_dir=Path(download_dir) if isinstance(download_dir, str) and download_dir.strip() else None,
                fetch_html=fetch_html,
                fetch_file=fetch_file,
            )
        else:
            return _tool_error(f"Unknown tool {name}.")
    except (PhotoFeedError, ValueError) as exc:
        return _tool_error(str(exc))
    except Exception:
        return _tool_error("Something went wrong while reading the album.")
    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2, ensure_ascii=False)}],
        "isError": False,
    }


def _tool_error(message: str) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
