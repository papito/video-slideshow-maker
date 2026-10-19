"""End-to-end: plan a synthetic folder, render it with libx264 at draft size, check the length."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from fixtures import make_event_folder
from slideshow import ffmpeg
from slideshow.cli import app
from slideshow.playlist import read_playlist

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    """Keep a slideshow.toml in the developer's working directory out of the tests."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture(scope="module")
def event(tmp_path_factory) -> tuple[Path, list[Path]]:
    folder = tmp_path_factory.mktemp("event")
    return folder, make_event_folder(folder / "src")


def test_plan_orders_by_capture_time(event):
    folder, expected = event
    playlist = folder / "playlist.txt"
    result = runner.invoke(app, ["plan", str(folder / "src"), "-o", str(playlist)])
    assert result.exit_code == 0, result.output
    assert read_playlist(playlist) == [p.resolve() for p in expected]
    assert "6 items (4 photos, 2 clips)" in result.output


def test_render_matches_estimated_length(event):
    folder, _ = event
    playlist = folder / "playlist.txt"
    output = folder / "out.mp4"
    result = runner.invoke(app, [
        "render", str(playlist), "-o", str(output), "--draft", "--encoder", "x264",
        "--photo-duration", "1.0", "--crossfade", "0.25",
    ])
    assert result.exit_code == 0, result.output
    info = ffmpeg.probe(output)
    # 4 photos x 1.0 + clips 2.0 + 1.5, minus 5 crossfades of 0.25
    assert ffmpeg.duration(info) == pytest.approx(4.0 + 3.5 - 1.25, abs=0.1)
    video = ffmpeg.video_stream(info)
    assert (video["width"], video["height"], video["codec_name"]) == (854, 480, "h264")
    assert ffmpeg.has_audio(info)


def test_batched_join_gives_same_length(event):
    folder, _ = event
    playlist = folder / "playlist.txt"
    cfg = folder / "batched.toml"
    cfg.write_text("[render]\nbatch_threshold = 2\n")
    output = folder / "batched.mp4"
    result = runner.invoke(app, [
        "render", str(playlist), "-o", str(output), "--draft", "--encoder", "x264", "-c", str(cfg),
        "--photo-duration", "1.0", "--crossfade", "0.25",
    ])
    assert result.exit_code == 0, result.output
    assert "batches" in result.output
    assert ffmpeg.duration(ffmpeg.probe(output)) == pytest.approx(6.25, abs=0.15)


def test_zoompan_engine_still_renders(event):
    folder, _ = event
    playlist = folder / "playlist.txt"
    cfg = folder / "zoompan.toml"
    cfg.write_text('[photo]\nengine = "zoompan"\n')
    output = folder / "zoompan.mp4"
    result = runner.invoke(app, [
        "render", str(playlist), "-o", str(output), "--draft", "--encoder", "x264", "-c", str(cfg),
        "--photo-duration", "1.0", "--crossfade", "0.25",
    ])
    assert result.exit_code == 0, result.output
    assert "ken burns: zoompan" in result.output
    assert ffmpeg.duration(ffmpeg.probe(output)) == pytest.approx(6.25, abs=0.1)
