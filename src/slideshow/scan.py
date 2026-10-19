"""Discover photos and clips in a source folder."""

from __future__ import annotations

from pathlib import Path

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
CLIP_EXTENSIONS = {".mp4", ".mov"}


def kind_of(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in PHOTO_EXTENSIONS:
        return "photo"
    if suffix in CLIP_EXTENSIONS:
        return "clip"
    return None


def scan(source: Path) -> list[Path]:
    """All photos and clips under source, recursively, in a stable path order."""
    if not source.is_dir():
        raise NotADirectoryError(source)
    found = [p for p in source.rglob("*") if p.is_file() and kind_of(p) and not p.name.startswith(".")]
    return sorted(found)
