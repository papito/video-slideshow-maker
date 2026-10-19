from datetime import datetime
from pathlib import Path

from slideshow.playlist import Item, estimated_length, format_length, read_playlist, write_playlist


def test_round_trip_keeps_order_and_paths(tmp_path: Path):
    items = [
        Item(tmp_path / "a photo.jpg", "photo", datetime(2026, 9, 13, 14, 0), 4.0, "exif"),
        Item(tmp_path / "b.mp4", "clip", datetime(2026, 9, 13, 14, 1), 12.25, "container"),
        Item(tmp_path / "c.png", "photo", datetime(2026, 9, 13, 14, 2), 4.0, "mtime"),
    ]
    out = tmp_path / "playlist.txt"
    write_playlist(items, tmp_path, 0.5, out)
    assert read_playlist(out) == [i.path for i in items]
    text = out.read_text()
    assert "3 items: 2 photos, 1 clips" in text
    assert "(mtime fallback)" in text.splitlines()[-1]


def test_comments_blank_lines_and_relative_paths(tmp_path: Path):
    out = tmp_path / "playlist.txt"
    out.write_text("# header\n\nsub/x.jpg # photo 2026 4.0s\n   \n/abs/y.mp4\n# trailing\n")
    assert read_playlist(out) == [(tmp_path / "sub/x.jpg").resolve(), Path("/abs/y.mp4")]


def test_estimated_length_subtracts_crossfades():
    assert estimated_length([4.0, 4.0, 10.0], 0.5) == 17.0
    assert estimated_length([4.0], 0.5) == 4.0
    assert estimated_length([], 0.5) == 0.0


def test_format_length():
    assert format_length(17.4) == "0m 17s"
    assert format_length(3725) == "1h 02m 05s"
