"""Join uniform segments into one video with crossfades, then encode the slideshow."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from . import ffmpeg
from .config import Settings


@dataclass(frozen=True)
class Boundary:
    offset: float  # where, in the accumulated stream, the fade starts
    fade: float  # fade length at this boundary


def crossfade_plan(durations: list[float], fade: float) -> tuple[list[Boundary], float]:
    """Offsets for a chained xfade. The fade is clamped to half the shorter neighbour."""
    if not durations:
        return [], 0.0
    boundaries: list[Boundary] = []
    total = durations[0]
    for previous, following in zip(durations, durations[1:]):
        d = max(0.0, min(fade, previous / 2, following / 2))
        boundaries.append(Boundary(offset=total - d, fade=d))
        total += following - d
    return boundaries, total


def frame_aligned_duration(path: Path, fps: int) -> float:
    info = ffmpeg.probe(path)
    return round(ffmpeg.duration(info) * fps) / fps


def filter_graph(durations: list[float], boundaries: list[Boundary]) -> str:
    """Trim/pad every audio track to its video length, then chain xfade and acrossfade."""
    parts: list[str] = []
    for i, d in enumerate(durations):
        parts.append(f"[{i}:a]aresample=48000,apad=whole_dur={d:.4f},atrim=end={d:.4f},asetpts=PTS-STARTPTS[a{i}]")
    video, audio = "[0:v]", "[a0]"
    for i, b in enumerate(boundaries, start=1):
        if b.fade > 0:
            parts.append(
                f"{video}[{i}:v]xfade=transition=fade:duration={b.fade:.4f}:offset={b.offset:.4f}[v{i}]"
            )
            parts.append(f"{audio}[a{i}]acrossfade=d={b.fade:.4f}:c1=tri:c2=tri[ax{i}]")
        else:
            parts.append(f"{video}[{i}:v]concat=n=2:v=1:a=0[v{i}]")
            parts.append(f"{audio}[a{i}]concat=n=2:v=0:a=1[ax{i}]")
        video, audio = f"[v{i}]", f"[ax{i}]"
    parts.append(f"{video}null[vout]")
    parts.append(f"{audio}anull[aout]")
    return ";".join(parts)


def _encode_args(settings: Settings, encoder: ffmpeg.Encoder, *, final: bool) -> list[str]:
    if encoder.name == "nvenc":
        preset = settings.nvenc_preset if final else settings.segment_nvenc_preset
        quality = settings.nvenc_cq if final else settings.segment_nvenc_cq
    else:
        preset = settings.x264_preset if final else settings.segment_x264_preset
        quality = settings.x264_crf if final else settings.segment_x264_crf
    args = [
        *encoder.video_args(preset=preset, quality=quality), "-pix_fmt", "yuv420p", "-r", str(settings.fps),
        "-c:a", "aac", "-b:a", settings.audio_bitrate, "-ar", "48000", "-ac", "2",
    ]
    if final:
        args += ["-movflags", "+faststart"]
    return args


def join_once(
    segments: list[Path], settings: Settings, encoder: ffmpeg.Encoder, output: Path, *, final: bool
) -> float:
    durations = [frame_aligned_duration(s, settings.fps) for s in segments]
    boundaries, total = crossfade_plan(durations, settings.crossfade)
    inputs = [arg for s in segments for arg in ("-i", str(s))]
    ffmpeg.run([
        *inputs, "-filter_complex", filter_graph(durations, boundaries),
        "-map", "[vout]", "-map", "[aout]",
        *_encode_args(settings, encoder, final=final), str(output),
    ])
    return total


def join(segments: list[Path], settings: Settings, encoder: ffmpeg.Encoder, output: Path, workdir: Path) -> float:
    """Join all segments into output. Large playlists are joined in batches first."""
    if not segments:
        raise ValueError("nothing to join: the playlist is empty")
    threshold = max(2, settings.batch_threshold)
    level = 0
    while len(segments) > threshold:
        batches = [segments[i:i + threshold] for i in range(0, len(segments), threshold)]
        if len(batches[-1]) == 1:  # a lone tail would be re-encoded for nothing; fold it in
            batches[-2].extend(batches.pop())
        print(f"joining {len(segments)} segments in {len(batches)} batches", file=sys.stderr)
        joined: list[Path] = []
        for n, batch in enumerate(batches):
            target = workdir / f"batch-{level}-{n:04d}.mp4"
            join_once(batch, settings, encoder, target, final=False)
            joined.append(target)
        segments, level = joined, level + 1
    print(f"joining {len(segments)} segments into {output}", file=sys.stderr)
    return join_once(segments, settings, encoder, output, final=True)
