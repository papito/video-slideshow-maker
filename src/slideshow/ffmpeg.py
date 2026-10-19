"""Thin wrappers around the ffmpeg and ffprobe executables."""

from __future__ import annotations

import functools
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ToolMissing(RuntimeError):
    pass


class FfmpegError(RuntimeError):
    pass


@functools.cache
def tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise ToolMissing(f"{name} not found on PATH; install ffmpeg (which provides {name})")
    return path


def run(args: list[str]) -> None:
    """Run ffmpeg with the given arguments, raising FfmpegError with the log tail on failure."""
    cmd = [tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tail = result.stderr.strip().splitlines()[-15:]
        raise FfmpegError("ffmpeg failed:\n  " + " ".join(cmd) + "\n" + "\n".join(tail))


def probe(path: Path) -> dict:
    cmd = [
        tool("ffprobe"), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FfmpegError(f"ffprobe failed on {path}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def video_stream(info: dict) -> dict | None:
    return next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)


def has_audio(info: dict) -> bool:
    return any(s.get("codec_type") == "audio" for s in info.get("streams", []))


def duration(info: dict) -> float:
    """Best-effort duration in seconds: the video stream's, else the container's."""
    stream = video_stream(info)
    for source in (stream or {}, info.get("format", {})):
        raw = source.get("duration")
        if raw not in (None, "N/A"):
            return float(raw)
    raise FfmpegError("no duration in probe result")


@dataclass(frozen=True)
class Encoder:
    """H.264 encoder selection and its argument shapes."""

    name: str  # "nvenc" or "x264"

    def video_args(self, *, preset: str, quality: int) -> list[str]:
        if self.name == "nvenc":
            return [
                "-c:v", "h264_nvenc", "-preset", preset, "-tune", "hq",
                "-rc", "vbr", "-cq", str(quality), "-b:v", "0", "-profile:v", "high",
            ]
        return ["-c:v", "libx264", "-preset", preset, "-crf", str(quality), "-profile:v", "high"]


@functools.cache
def nvenc_available() -> bool:
    """True when h264_nvenc is compiled in and the driver accepts a test encode."""
    listing = subprocess.run(
        [tool("ffmpeg"), "-hide_banner", "-encoders"], capture_output=True, text=True
    ).stdout
    if "h264_nvenc" not in listing:
        return False
    test = subprocess.run(
        [
            tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin",
            "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2:r=25",
            "-c:v", "h264_nvenc", "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    return test.returncode == 0


MOTION_ENGINES = ("perspective", "zoompan")


def choose_motion_engine(preference: str) -> str:
    """Which filter performs the Ken Burns move.

    'perspective' resamples with sub-pixel precision (cubic) so the move is smooth;
    'zoompan' crops on whole pixels and visibly jitters, kept only as a fallback.
    """
    if preference == "auto":
        return "perspective"
    if preference in MOTION_ENGINES:
        return preference
    raise ValueError(f"unknown motion engine {preference!r}; use auto, perspective or zoompan")


def choose_encoder(preference: str) -> Encoder:
    if preference == "x264":
        return Encoder("x264")
    if preference == "nvenc":
        if not nvenc_available():
            raise FfmpegError("NVENC requested but h264_nvenc is not usable on this machine")
        return Encoder("nvenc")
    if preference != "auto":
        raise ValueError(f"unknown encoder preference {preference!r}; use auto, nvenc or x264")
    return Encoder("nvenc" if nvenc_available() else "x264")
