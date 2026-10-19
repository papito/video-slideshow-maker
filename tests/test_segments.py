from datetime import datetime
from pathlib import Path

from fixtures import make_photo, set_mtime
from slideshow.config import Settings
from slideshow.segments import Source, fitted_size, ken_burns_expressions, segment_path


def test_fitted_size_is_even_and_inside_canvas():
    assert fitted_size(4000, 3000, 1920, 1080) == (1440, 1080)
    assert fitted_size(3000, 4000, 1920, 1080) == (810, 1080)
    assert fitted_size(1921, 1080, 1920, 1080) == (1920, 1078)
    w, h = fitted_size(333, 777, 854, 480)
    assert w % 2 == 0 and h % 2 == 0 and w <= 854 and h <= 480


def test_ken_burns_variants_cycle():
    variants = [ken_burns_expressions(i, 1.08, 120) for i in range(5)]
    assert variants[0] == variants[4]
    assert len({v for v in variants[:4]}) == 4
    for z, x, y in variants:
        assert "on/119" in z or "on/119" in x or "on/119" in y


def test_segment_key_depends_on_file_and_settings(tmp_path: Path):
    photo = make_photo(tmp_path / "p.jpg")
    src = Source(photo, "photo", 4.0)
    first = segment_path(src, Settings(), tmp_path)
    assert first == segment_path(src, Settings(), tmp_path)
    assert first == segment_path(src, Settings(nvenc_cq=30), tmp_path)  # join quality is not a segment setting
    assert first != segment_path(src, Settings(photo_duration=5), tmp_path)
    assert first != segment_path(src, Settings(width=854, height=480), tmp_path)
    set_mtime(photo, datetime(2020, 1, 1))
    assert first != segment_path(src, Settings(), tmp_path)


def test_perspective_expressions_cover_four_moves():
    from slideshow.segments import perspective_expressions
    variants = [perspective_expressions(i, 1.08, 120) for i in range(5)]
    assert variants[0] == variants[4]
    assert len(set(variants[:4])) == 4
    for corners in variants:
        assert "interpolation=cubic:sense=source:eval=frame" in corners
        assert "on/119" in corners
        assert all(f"{k}='" in corners for k in ("x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3"))


def test_segment_key_depends_on_engine_for_photos_only(tmp_path: Path):
    from fixtures import make_clip
    photo = Source(make_photo(tmp_path / "p.jpg"), "photo", 4.0)
    assert segment_path(photo, Settings(), tmp_path, "perspective") != segment_path(photo, Settings(), tmp_path, "zoompan")
    clip = Source(make_clip(tmp_path / "c.mp4", seconds=0.3), "clip", 0.3, True)
    assert segment_path(clip, Settings(), tmp_path, "perspective") == segment_path(clip, Settings(), tmp_path, "zoompan")
