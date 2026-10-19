"""Settings: built-in defaults, overridden by a TOML file, overridden by CLI flags."""

from __future__ import annotations

import dataclasses
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_NAME = "slideshow.toml"


@dataclass(frozen=True)
class Settings:
    # canvas
    width: int = 1920
    height: int = 1080
    fps: int = 30
    # photo
    photo_duration: float = 6.0
    ken_burns_zoom: float = 1.08
    ken_burns_engine: str = "auto"  # auto | perspective | zoompan
    # backdrop
    backdrop_blur: int = 10
    backdrop_brightness: float = -0.12
    backdrop_saturation: float = 0.85
    # crossfade
    crossfade: float = 0.5
    # encode
    encoder: str = "auto"  # auto | nvenc | x264
    nvenc_preset: str = "p5"
    nvenc_cq: int = 19
    segment_nvenc_preset: str = "p4"
    segment_nvenc_cq: int = 16
    x264_preset: str = "slow"
    x264_crf: int = 18
    segment_x264_preset: str = "veryfast"
    segment_x264_crf: int = 14
    audio_bitrate: str = "192k"
    # render
    jobs: int | None = None
    cache_dir: str = ".slideshow-cache"
    batch_threshold: int = 60
    draft: bool = False

    def segment_fingerprint(self) -> str:
        """Every setting that changes what a rendered segment looks like."""
        fields = (
            "width", "height", "fps", "photo_duration", "ken_burns_zoom",
            "backdrop_blur", "backdrop_brightness", "backdrop_saturation",
            "segment_nvenc_preset", "segment_nvenc_cq", "segment_x264_preset",
            "segment_x264_crf", "audio_bitrate",
        )
        return "|".join(f"{f}={getattr(self, f)}" for f in fields)


# TOML section -> settings field. Keys inside each section map 1:1 to fields
# unless renamed here.
SECTIONS: dict[str, dict[str, str]] = {
    "canvas": {"width": "width", "height": "height", "fps": "fps"},
    "photo": {
        "duration": "photo_duration",
        "ken_burns_zoom": "ken_burns_zoom",
        "engine": "ken_burns_engine",
    },
    "backdrop": {
        "blur": "backdrop_blur",
        "brightness": "backdrop_brightness",
        "saturation": "backdrop_saturation",
    },
    "crossfade": {"duration": "crossfade"},
    "encode": {
        "encoder": "encoder",
        "nvenc_preset": "nvenc_preset",
        "nvenc_cq": "nvenc_cq",
        "segment_nvenc_preset": "segment_nvenc_preset",
        "segment_nvenc_cq": "segment_nvenc_cq",
        "x264_preset": "x264_preset",
        "x264_crf": "x264_crf",
        "segment_x264_preset": "segment_x264_preset",
        "segment_x264_crf": "segment_x264_crf",
        "audio_bitrate": "audio_bitrate",
    },
    "render": {"jobs": "jobs", "cache_dir": "cache_dir", "batch_threshold": "batch_threshold"},
}

DRAFT_PROFILE: dict[str, Any] = {
    "width": 854,
    "height": 480,
    "nvenc_preset": "p1",
    "nvenc_cq": 28,
    "segment_nvenc_preset": "p1",
    "segment_nvenc_cq": 24,
    "x264_preset": "ultrafast",
    "x264_crf": 26,
    "segment_x264_preset": "ultrafast",
    "segment_x264_crf": 22,
    "draft": True,
}


class ConfigError(ValueError):
    pass


def settings_from_toml(data: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for section, entries in data.items():
        mapping = SECTIONS.get(section)
        if mapping is None:
            raise ConfigError(f"unknown section [{section}]")
        if not isinstance(entries, dict):
            raise ConfigError(f"[{section}] must be a table")
        for key, value in entries.items():
            field = mapping.get(key)
            if field is None:
                raise ConfigError(f"unknown key {key!r} in [{section}]")
            values[field] = value
    return values


def draft_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """A [draft] table may replace any entry of the built-in draft profile or set any other setting."""
    section = data.get("draft", {})
    if not isinstance(section, dict):
        raise ConfigError("[draft] must be a table")
    known = {f.name for f in dataclasses.fields(Settings)} - {"draft"}
    unknown = set(section) - known
    if unknown:
        raise ConfigError(f"unknown keys in [draft]: {sorted(unknown)}")
    return {**DRAFT_PROFILE, **section}


def load_settings(
    config_path: Path | None = None,
    *,
    overrides: dict[str, Any] | None = None,
    draft: bool = False,
) -> tuple[Settings, Path | None]:
    """Resolve settings. Returns the settings and the config file actually used, if any."""
    if config_path is None and Path(DEFAULT_CONFIG_NAME).is_file():
        config_path = Path(DEFAULT_CONFIG_NAME)
    data: dict[str, Any] = {}
    if config_path is not None:
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
    draft_section = data.pop("draft", None)
    values = settings_from_toml(data)
    if draft:
        values.update(draft_overrides({"draft": draft_section} if draft_section else {}))
    values.update({k: v for k, v in (overrides or {}).items() if v is not None})
    known = {f.name for f in dataclasses.fields(Settings)}
    unknown = set(values) - known
    if unknown:
        raise ConfigError(f"unknown settings: {sorted(unknown)}")
    return Settings(**values), config_path
