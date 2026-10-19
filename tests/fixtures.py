"""Tiny synthetic photos and clips for tests and smoke runs."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from slideshow.capture_time import (
    EXIF_IFD, TAG_DATETIME, TAG_DATETIME_ORIGINAL, TAG_OFFSET_TIME_ORIGINAL,
)


def make_photo(
    path: Path,
    size: tuple[int, int] = (640, 480),
    *,
    taken: datetime | None = None,
    offset: str | None = None,
    orientation: int | None = None,
    colour: str = "steelblue",
    label: str | None = None,
) -> Path:
    img = Image.new("RGB", size, colour)
    draw = ImageDraw.Draw(img)
    draw.rectangle((10, 10, size[0] // 2, size[1] // 2), fill="white")  # asymmetric: orientation is visible
    draw.text((20, 20), label or path.stem, fill="black")
    exif = Image.Exif()
    if taken is not None:
        stamp = taken.strftime("%Y:%m:%d %H:%M:%S")
        exif[TAG_DATETIME] = stamp
        exif.get_ifd(EXIF_IFD)[TAG_DATETIME_ORIGINAL] = stamp
        if offset is not None:
            exif.get_ifd(EXIF_IFD)[TAG_OFFSET_TIME_ORIGINAL] = offset
    if orientation is not None:
        exif[0x0112] = orientation
    save_kwargs = {"exif": exif.tobytes()} if len(exif) else {}
    img.save(path, **save_kwargs)
    return path


def make_clip(
    path: Path,
    size: tuple[int, int] = (320, 240),
    *,
    seconds: float = 2.0,
    audio: bool = True,
    created: datetime | None = None,
    quicktime_date: str | None = None,
    fps: int = 25,
) -> Path:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size={size[0]}x{size[1]}:rate={fps}:duration={seconds}",
    ]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds}"]
    if created is not None:
        cmd += ["-metadata", f"creation_time={created.strftime('%Y-%m-%dT%H:%M:%S.000000Z')}"]
    if quicktime_date is not None:
        cmd += ["-metadata", f"com.apple.quicktime.creationdate={quicktime_date}", "-movflags", "use_metadata_tags"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac"]
    cmd += ["-shortest", str(path)]
    subprocess.run(cmd, check=True)
    return path


def set_mtime(path: Path, when: datetime) -> None:
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))


def make_event_folder(folder: Path) -> list[Path]:
    """A small mixed folder whose correct capture order is the returned list."""
    folder.mkdir(parents=True, exist_ok=True)
    base = datetime(2026, 9, 13, 14, 0, 0)
    ordered = [
        make_photo(folder / "b_landscape.jpg", (640, 480), taken=base.replace(minute=2), colour="tomato"),
        make_clip(folder / "a_clip.mp4", (240, 320), seconds=2.0, created=base.replace(minute=5).astimezone().astimezone(__import__("datetime").timezone.utc).replace(tzinfo=None)),
        make_photo(folder / "c_portrait.jpg", (480, 640), taken=base.replace(minute=6), colour="seagreen"),
        make_photo(folder / "d_rotated.jpg", (640, 480), taken=base.replace(minute=7), orientation=6, colour="goldenrod"),
        make_clip(folder / "e_silent.mov", (320, 240), seconds=1.5, audio=False, created=base.replace(minute=9).astimezone().astimezone(__import__("datetime").timezone.utc).replace(tzinfo=None)),
        make_photo(folder / "f_nodate.png", (300, 300), colour="orchid"),
    ]
    set_mtime(ordered[-1], base.replace(minute=11))
    return ordered
