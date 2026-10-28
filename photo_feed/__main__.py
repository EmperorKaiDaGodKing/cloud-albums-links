"""Let ``python3 -m photo_feed`` run the command line."""

import sys

from photo_feed.cli import main

if __name__ == "__main__":
    sys.exit(main())
