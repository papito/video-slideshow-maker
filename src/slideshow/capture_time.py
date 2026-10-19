"""Capture time of a photo or clip, as a timezone-aware datetime in local time.

Photos carry EXIF wall-clock time (local, sometimes with an offset tag). Clips carry a
container creation_time in UTC, and iPhone MOVs additionally carry a QuickTime
creationdate with an explicit offset. Everything is normalised to the local zone so
photos and clips from one event sort together.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

EXIF_IFD = 0x8769
TAG_DATETIME = 0x0132
TAG_OFFSET_TIME = 0x9010
TAG_DATETIME_ORIGINAL = 0x9003
TAG_OFFSET_TIME_ORIGINAL = 0x9011

_EXIF_DATE = re.compile(r"^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})")


@dataclass(frozen=True)
class CaptureTime:
    when: datetime  # timezone-aware, converted to local time
    source: str  # exif | quicktime | container | mtime


def _localize(dt: datetime) -> datetime:
    """Naive datetimes are taken as local wall time; aware ones are converted to local."""
    if dt.tzinfo is None:
        return dt.astimezone()  # interprets naive as local
    return dt.astimezone()


def parse_exif_datetime(value: str, offset: str | None = None) -> datetime | None:
    match = _EXIF_DATE.match(value.strip())
    if not match:
        return None
    parts = [int(g) for g in match.groups()]
    try:
        dt = datetime(*parts)
    except ValueError:
        return None
    if offset:
        offset = offset.strip()
        try:
            dt = datetime.fromisoformat(dt.isoformat() + offset)
        except ValueError:
            pass
    return dt


def photo_capture_time(path: Path) -> datetime | None:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
    except Exception:
        return None
    if not exif:
        return None
    exif_ifd = exif.get_ifd(EXIF_IFD)
    candidates = (
        (exif_ifd.get(TAG_DATETIME_ORIGINAL), exif_ifd.get(TAG_OFFSET_TIME_ORIGINAL)),
        (exif.get(TAG_DATETIME), exif_ifd.get(TAG_OFFSET_TIME)),
    )
    for raw, offset in candidates:
        if isinstance(raw, str):
            dt = parse_exif_datetime(raw, offset if isinstance(offset, str) else None)
            if dt is not None:
                return dt
    return None


def _parse_iso(value: str) -> datetime | None:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.year < 1980:  # zeroed/epoch timestamps written by some tools
        return None
    return dt


def clip_capture_time(info: dict) -> tuple[datetime, str] | None:
    """From an ffprobe result: QuickTime creationdate (with offset) beats container creation_time (UTC)."""
    tag_sets = [info.get("format", {}).get("tags", {})]
    tag_sets += [s.get("tags", {}) for s in info.get("streams", [])]
    for tags in tag_sets:
        raw = tags.get("com.apple.quicktime.creationdate")
        if raw and (dt := _parse_iso(raw)):
            return dt, "quicktime"
    for tags in tag_sets:
        raw = tags.get("creation_time")
        if raw and (dt := _parse_iso(raw)):
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt, "container"
    return None


def capture_time(path: Path, kind: str, info: dict | None = None) -> CaptureTime:
    if kind == "photo":
        dt = photo_capture_time(path)
        if dt is not None:
            return CaptureTime(_localize(dt), "exif")
    elif kind == "clip" and info is not None:
        found = clip_capture_time(info)
        if found is not None:
            dt, source = found
            return CaptureTime(_localize(dt), source)
    mtime = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
    return CaptureTime(mtime, "mtime")
