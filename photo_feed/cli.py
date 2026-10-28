"""Command line for the photo feed.

Examples:
    python3 -m photo_feed list-albums
    python3 -m photo_feed list-photos
    python3 -m photo_feed list-photos --download
    python3 -m photo_feed mcp
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from photo_feed import __version__
from photo_feed.errors import AlbumError
from photo_feed.mcp_server import serve
from photo_feed.paths import repo_root
from photo_feed.service import list_album_photos, list_albums


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "mcp":
        serve()
        return 0
    if args.command is None:
        parser.print_help()
        return 0

    root = repo_root()
    try:
        if args.command == "list-albums":
            payload = list_albums(root)
        elif args.command == "list-photos":
            download_dir = Path(args.download_dir) if args.download_dir else None
            if download_dir is not None and not download_dir.is_absolute():
                download_dir = root / download_dir
            payload = list_album_photos(
                root,
                album_id=args.album,
                url=args.url,
                limit=args.limit,
                download=args.download or download_dir is not None,
                download_dir=download_dir,
            )
        else:
            parser.print_help()
            return 2
    except AlbumError as exc:
        payload = {"error": str(exc)}

    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 1 if payload.get("error") else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="photo-feed",
        description=(
            "Read photos and videos from a public shared album link. "
            "Links are read from the PHOTO_FEED_URL environment variable, "
            "then a config file (PHOTO_FEED_CONFIG or photo-feed.local.json), "
            "then files in shared-album-link-storage/."
        ),
    )
    parser.add_argument("--version", action="version", version=f"photo-feed {__version__}")
    commands = parser.add_subparsers(dest="command")

    commands.add_parser("list-albums", help="Show the album links this tool will read.")

    photos = commands.add_parser("list-photos", help="List photos and videos as JSON.")
    photos.add_argument(
        "url",
        nargs="?",
        help="One shared album link. If you leave this out, the configured link is used.",
    )
    photos.add_argument("--album", help="Album id printed by list-albums.")
    photos.add_argument("--limit", type=int, help="Maximum number of items to return.")
    photos.add_argument(
        "--download",
        action="store_true",
        help="Save files into the downloads folder (that folder is not committed).",
    )
    photos.add_argument(
        "--download-dir",
        help="Folder for saved files. Inside this project, use downloads or output.",
    )

    commands.add_parser("mcp", help="Speak MCP on stdin/stdout so a bot can call this tool.")
    return parser
