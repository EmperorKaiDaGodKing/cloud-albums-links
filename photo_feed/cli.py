"""Commands: list-albums, list-photos, and mcp."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from photo_feed.errors import PhotoFeedError
from photo_feed.google_photos import fetch_html as default_fetch_html
from photo_feed.mcp_server import serve
from photo_feed.service import albums_document, photos_document
from photo_feed.sources import repo_root


def main(
    argv: list[str] | None = None,
    *,
    root: Path | None = None,
    env: dict[str, str] | None = None,
    stdout=None,
    stderr=None,
    stdin=None,
    fetch_html=None,
    fetch_file=None,
) -> int:
    """Run one command. Returns a process exit code."""

    argv = list(sys.argv[1:] if argv is None else argv)
    env = dict(os.environ if env is None else env)
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    stdin = stdin or sys.stdin
    root = root or repo_root()
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 1

    try:
        if args.command == "list-albums":
            document = albums_document(root, env)
        elif args.command == "list-photos":
            download_dir = Path(args.download) if args.download else None
            document = photos_document(
                root,
                env,
                url=args.url,
                name=args.name,
                download_dir=download_dir,
                fetch_html=fetch_html or default_fetch_html,
                fetch_file=fetch_file,
            )
            if document.get("warning"):
                print(document["warning"], file=stderr)
        elif args.command == "mcp":
            serve(
                stdin,
                stdout,
                root=root,
                env=env,
                fetch_html=fetch_html or default_fetch_html,
                fetch_file=fetch_file,
            )
            return 0
        else:
            return _fail(f"Unknown command {args.command}.", stdout, stderr)
    except (PhotoFeedError, ValueError) as exc:
        return _fail(str(exc), stdout, stderr)
    _write_json(document, stdout)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m photo_feed",
        description="List photos and videos from a public Google Photos shared album.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-albums", help="Show the album links this tool will use")
    photos = commands.add_parser("list-photos", help="List photos and videos in one album")
    photos.add_argument("--url", help="Shared album link. If you skip this, the saved link is used.")
    photos.add_argument("--name", help="Album name from list-albums")
    photos.add_argument(
        "--download",
        metavar="FOLDER",
        help="Save copies into this folder. Keep the folder git-ignored.",
    )
    commands.add_parser("mcp", help="Speak MCP on stdin/stdout so a bot can call this tool")
    return parser


def _write_json(document: dict, stdout) -> None:
    json.dump(document, stdout, indent=2, ensure_ascii=False)
    stdout.write("\n")


def _fail(message: str, stdout, stderr) -> int:
    print(message, file=stderr)
    _write_json({"error": message}, stdout)
    return 1


if __name__ == "__main__":
    sys.exit(main())
