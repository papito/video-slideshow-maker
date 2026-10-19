"""The playlist: an ordered, hand-editable text list of items."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

COMMENT_SEPARATOR = " #"


@dataclass(frozen=True)
class Item:
    path: Path
    kind: str  # photo | clip
    captured: datetime
    length: float  # seconds on screen
    time_source: str  # exif | quicktime | container | mtime


def format_length(seconds: float) -> str:
    seconds = round(seconds)
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s"


def estimated_length(lengths: list[float], crossfade: float) -> float:
    if not lengths:
        return 0.0
    return sum(lengths) - crossfade * (len(lengths) - 1)


def write_playlist(items: list[Item], source: Path, crossfade: float, out: Path) -> None:
    photos = sum(1 for i in items if i.kind == "photo")
    clips = len(items) - photos
    total = estimated_length([i.length for i in items], crossfade)
    width = max((len(str(i.path)) for i in items), default=0)
    lines = [
        f"# playlist written {datetime.now().replace(microsecond=0).isoformat()} from {source}",
        f"# {len(items)} items: {photos} photos, {clips} clips, "
        f"estimated length {format_length(total)} (with {crossfade:g} s crossfades)",
        "# delete or reorder lines freely; everything after ' #' on a line is ignored",
        f"# {'path'.ljust(width)}   kind  capture-time               length",
    ]
    for item in items:
        note = "  (mtime fallback)" if item.time_source == "mtime" else ""
        stamp = item.captured.replace(microsecond=0).isoformat()
        lines.append(
            f"{str(item.path).ljust(width)}{COMMENT_SEPARATOR} {item.kind:<5} {stamp}  {item.length:.1f}s{note}"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_playlist(path: Path) -> list[Path]:
    """Paths in file order. Relative paths are resolved against the playlist's folder."""
    paths: list[Path] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(COMMENT_SEPARATOR, 1)[0] if COMMENT_SEPARATOR in raw else raw
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        item = Path(line)
        if not item.is_absolute():
            item = (path.parent / item).resolve()
        paths.append(item)
    return paths
