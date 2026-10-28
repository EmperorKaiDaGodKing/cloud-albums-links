"""Where the project folder is, so config and storage are found next to the code."""

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
