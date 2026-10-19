from pathlib import Path

import pytest

from slideshow.config import ConfigError, Settings, load_settings


def test_defaults_when_no_file(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings, used = load_settings()
    assert settings == Settings()
    assert used is None


def test_toml_sections_map_to_fields(tmp_path: Path):
    cfg = tmp_path / "s.toml"
    cfg.write_text('[photo]\nduration = 6\n[crossfade]\nduration = 1.0\n[encode]\nencoder = "x264"\n')
    settings, used = load_settings(cfg)
    assert used == cfg
    assert (settings.photo_duration, settings.crossfade, settings.encoder) == (6, 1.0, "x264")


def test_default_file_in_cwd_is_picked_up(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("slideshow.toml").write_text("[canvas]\nfps = 24\n")
    settings, used = load_settings()
    assert settings.fps == 24 and used == Path("slideshow.toml")


def test_flags_override_file_and_draft(tmp_path: Path):
    cfg = tmp_path / "s.toml"
    cfg.write_text("[photo]\nduration = 6\n")
    settings, _ = load_settings(cfg, overrides={"photo_duration": 2.5, "jobs": None}, draft=True)
    assert settings.photo_duration == 2.5
    assert settings.draft and settings.width == 854


def test_draft_section_customises_profile(tmp_path: Path):
    cfg = tmp_path / "s.toml"
    cfg.write_text("[draft]\nwidth = 640\nheight = 360\n")
    settings, _ = load_settings(cfg, draft=True)
    assert (settings.width, settings.height, settings.photo_duration) == (640, 360, 6.0)
    normal, _ = load_settings(cfg)
    assert normal.width == 1920


def test_unknown_keys_are_errors(tmp_path: Path):
    cfg = tmp_path / "s.toml"
    cfg.write_text("[photo]\nlength = 6\n")
    with pytest.raises(ConfigError):
        load_settings(cfg)
    cfg.write_text("[nope]\nx = 1\n")
    with pytest.raises(ConfigError):
        load_settings(cfg)


def test_fingerprint_tracks_visual_settings_only():
    base = Settings()
    assert Settings(photo_duration=5).segment_fingerprint() != base.segment_fingerprint()
    assert Settings(nvenc_cq=30, batch_threshold=3).segment_fingerprint() == base.segment_fingerprint()


def test_motion_engine_choice():
    from slideshow.ffmpeg import choose_motion_engine
    assert choose_motion_engine("auto") == "perspective"
    assert choose_motion_engine("zoompan") == "zoompan"
    with pytest.raises(ValueError):
        choose_motion_engine("libplacebo")


def test_draft_keeps_photo_duration_from_file(tmp_path: Path):
    cfg = tmp_path / "s.toml"
    cfg.write_text("[photo]\nduration = 9\n")
    settings, _ = load_settings(cfg, draft=True)
    assert settings.draft and settings.photo_duration == 9


def test_draft_section_may_set_any_setting(tmp_path: Path):
    cfg = tmp_path / "s.toml"
    cfg.write_text("[draft]\nphoto_duration = 2\ncrossfade = 0.1\n")
    settings, _ = load_settings(cfg, draft=True)
    assert (settings.photo_duration, settings.crossfade, settings.width) == (2, 0.1, 854)
    cfg.write_text("[draft]\nnope = 1\n")
    with pytest.raises(ConfigError):
        load_settings(cfg, draft=True)
