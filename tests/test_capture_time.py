from datetime import datetime, timedelta, timezone
from pathlib import Path

from fixtures import make_clip, make_photo, set_mtime
from slideshow import ffmpeg
from slideshow.capture_time import capture_time, clip_capture_time, parse_exif_datetime


def test_exif_datetime_with_offset_is_aware():
    dt = parse_exif_datetime("2026:09:13 14:02:11", "+02:00")
    assert dt == datetime(2026, 9, 13, 14, 2, 11, tzinfo=timezone(timedelta(hours=2)))


def test_exif_datetime_without_offset_is_naive():
    assert parse_exif_datetime("2026:09:13 14:02:11") == datetime(2026, 9, 13, 14, 2, 11)


def test_exif_garbage_is_ignored():
    assert parse_exif_datetime("0000:00:00 00:00:00") is None
    assert parse_exif_datetime("not a date") is None


def test_photo_uses_exif_as_local_wall_time(tmp_path: Path):
    photo = make_photo(tmp_path / "p.jpg", taken=datetime(2026, 9, 13, 14, 2, 11))
    found = capture_time(photo, "photo")
    assert found.source == "exif"
    assert found.when.replace(tzinfo=None) == datetime(2026, 9, 13, 14, 2, 11)
    assert found.when.tzinfo is not None


def test_photo_exif_offset_is_converted_to_local(tmp_path: Path):
    photo = make_photo(tmp_path / "p.jpg", taken=datetime(2026, 9, 13, 12, 0, 0), offset="+00:00")
    found = capture_time(photo, "photo")
    assert found.when == datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)


def test_photo_without_exif_falls_back_to_mtime(tmp_path: Path):
    photo = make_photo(tmp_path / "p.png")
    set_mtime(photo, datetime(2026, 1, 2, 3, 4, 5))
    found = capture_time(photo, "photo")
    assert found.source == "mtime"
    assert found.when.replace(tzinfo=None) == datetime(2026, 1, 2, 3, 4, 5)


def test_clip_container_time_is_utc(tmp_path: Path):
    clip = make_clip(tmp_path / "c.mp4", seconds=0.5, created=datetime(2026, 9, 13, 18, 5, 40))
    found = capture_time(clip, "clip", ffmpeg.probe(clip))
    assert found.source == "container"
    assert found.when == datetime(2026, 9, 13, 18, 5, 40, tzinfo=timezone.utc)


def test_quicktime_creationdate_beats_container_time():
    info = {"format": {"tags": {
        "creation_time": "2026-09-13T18:05:40.000000Z",
        "com.apple.quicktime.creationdate": "2026-09-13T14:05:40-0400",
    }}, "streams": []}
    dt, source = clip_capture_time(info)
    assert source == "quicktime"
    assert dt.utcoffset() == timedelta(hours=-4)
    assert dt == datetime(2026, 9, 13, 18, 5, 40, tzinfo=timezone.utc)


def test_epoch_creation_time_is_rejected():
    info = {"format": {"tags": {"creation_time": "1970-01-01T00:00:00.000000Z"}}, "streams": []}
    assert clip_capture_time(info) is None
