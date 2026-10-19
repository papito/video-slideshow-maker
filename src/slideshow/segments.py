"""Render every item to a uniform, cached segment: canvas size, constant fps, stereo AAC."""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

from . import ffmpeg
from .config import Settings

MAX_PHOTO_SIDE = 3840
NVENC_MAX_JOBS = 4  # consumer GeForce cards cap concurrent NVENC sessions


@dataclass(frozen=True)
class Source:
    path: Path
    kind: str  # photo | clip
    length: float  # seconds the segment lasts
    has_audio: bool = False


def even(value: float) -> int:
    return max(2, int(value) // 2 * 2)


def fitted_size(iw: int, ih: int, width: int, height: int) -> tuple[int, int]:
    scale = min(width / iw, height / ih)
    return even(iw * scale), even(ih * scale)


def segment_path(source: Source, settings: Settings, cache_dir: Path, engine: str = "perspective") -> Path:
    stat = source.path.stat()
    key = "\n".join([
        str(source.path.resolve()), str(stat.st_size), str(stat.st_mtime_ns),
        source.kind, settings.segment_fingerprint(),
        engine if source.kind == "photo" else "",
    ])
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    return cache_dir / f"{digest}.mp4"


def _segment_encode_args(settings: Settings, encoder: ffmpeg.Encoder) -> list[str]:
    if encoder.name == "nvenc":
        video = encoder.video_args(preset=settings.segment_nvenc_preset, quality=settings.segment_nvenc_cq)
    else:
        video = encoder.video_args(preset=settings.segment_x264_preset, quality=settings.segment_x264_crf)
    return [
        *video, "-pix_fmt", "yuv420p", "-r", str(settings.fps),
        "-c:a", "aac", "-b:a", settings.audio_bitrate, "-ar", "48000", "-ac", "2",
    ]


def backdrop_filter(settings: Settings) -> str:
    """Blur at quarter size, then stretch to the canvas: cheap and very soft."""
    w, h = settings.width, settings.height
    bw, bh = even(w / 4), even(h / 4)
    return (
        f"scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
        f"boxblur={settings.backdrop_blur}:2,"
        f"eq=brightness={settings.backdrop_brightness}:saturation={settings.backdrop_saturation},"
        f"scale={w}:{h},setsar=1"
    )


def ken_burns_expressions(variant: int, zoom: float, frames: int) -> tuple[str, str, str]:
    """(z, x, y) zoompan expressions; variant alternates so consecutive photos differ."""
    steps = max(frames - 1, 1)
    zoom_in = f"1+({zoom}-1)*on/{steps}"
    zoom_out = f"{zoom}-({zoom}-1)*on/{steps}"
    centre_x = "iw/2-(iw/zoom/2)"
    centre_y = "ih/2-(ih/zoom/2)"
    pan_x = f"(iw-iw/zoom)*on/{steps}"
    pan_y = f"(ih-ih/zoom)*on/{steps}"
    return [
        (zoom_in, centre_x, centre_y),
        (zoom_out, centre_x, centre_y),
        (zoom_in, pan_x, centre_y),
        (zoom_out, centre_x, pan_y),
    ][variant % 4]


def perspective_expressions(variant: int, zoom: float, frames: int) -> str:
    """Corner options for the perspective filter: the same four moves with sub-pixel precision.

    Evaluated per frame; `on` is the output frame number, W/H the input size. The source
    rectangle (W/z by H/z) is mapped onto the whole output, so shrinking it zooms in.
    """
    steps = max(frames - 1, 1)
    p = f"(on/{steps})"
    zoom_in = f"(1+({zoom}-1)*{p})"
    zoom_out = f"({zoom}-({zoom}-1)*{p})"
    z = zoom_in if variant % 4 in (0, 2) else zoom_out
    w, h = f"(W/{z})", f"(H/{z})"
    centre_x, centre_y = f"((W-{w})/2)", f"((H-{h})/2)"
    x, y = [
        (centre_x, centre_y),
        (centre_x, centre_y),
        (f"((W-{w})*{p})", centre_y),
        (centre_x, f"((H-{h})*{p})"),
    ][variant % 4]
    return (
        f"x0='{x}':y0='{y}':x1='{x}+{w}':y1='{y}':"
        f"x2='{x}':y2='{y}+{h}':x3='{x}+{w}':y3='{y}+{h}':"
        f"interpolation=cubic:sense=source:eval=frame"
    )


def prepare_photo(src: Path, dst: Path) -> tuple[int, int]:
    """Apply EXIF orientation, cap the size, save as PNG. Returns the saved (width, height)."""
    with Image.open(src) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((MAX_PHOTO_SIDE, MAX_PHOTO_SIDE), Image.Resampling.LANCZOS)
        img.save(dst, format="PNG", compress_level=1)
        return img.size


def render_photo_segment(
    source: Source, dst: Path, settings: Settings, encoder: ffmpeg.Encoder, variant: int, workdir: Path,
    engine: str = "perspective",
) -> None:
    png = workdir / (dst.stem + ".png")
    iw, ih = prepare_photo(source.path, png)
    try:
        fw, fh = fitted_size(iw, ih, settings.width, settings.height)
        frames = max(1, round(source.length * settings.fps))
        looped = ["-loop", "1", "-framerate", str(settings.fps), "-t", f"{source.length:.3f}", "-i", str(png)]
        if engine == "perspective":
            # Sub-pixel move: the still is oversampled 2x, the moving source rectangle is
            # resampled (cubic) onto the full 2x frame every frame, then downscaled to fit.
            corners = perspective_expressions(variant, settings.ken_burns_zoom, frames)
            inputs = looped
            audio_index = 1
            graph = (
                f"[0:v]split=2[bgi][fgi];"
                f"[bgi]{backdrop_filter(settings)}[bg];"
                f"[fgi]scale={fw * 2}:{fh * 2},format=rgb24,perspective={corners},"
                f"scale={fw}:{fh}:flags=lanczos,setsar=1[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p[v]"
            )
        else:
            # zoompan emits `frames` frames from a single still; oversample 2x to soften its integer steps.
            z, x, y = ken_burns_expressions(variant, settings.ken_burns_zoom, frames)
            inputs = [*looped, "-i", str(png)]
            audio_index = 2
            graph = (
                f"[0:v]{backdrop_filter(settings)}[bg];"
                f"[1:v]scale={fw * 2}:{fh * 2},"
                f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={fw}x{fh}:fps={settings.fps},setsar=1[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p[v]"
            )
        tmp = dst.with_name(dst.stem + ".part.mp4")
        ffmpeg.run([
            *inputs,
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-filter_complex", graph, "-map", "[v]", "-map", f"{audio_index}:a",
            "-t", f"{source.length:.3f}", "-frames:v", str(frames),
            *_segment_encode_args(settings, encoder), str(tmp),
        ])
        os.replace(tmp, dst)
    finally:
        png.unlink(missing_ok=True)


def render_clip_segment(source: Source, dst: Path, settings: Settings, encoder: ffmpeg.Encoder) -> None:
    w, h = settings.width, settings.height
    graph = (
        f"[0:v]fps={settings.fps},split=2[bgi][fgi];"
        f"[bgi]{backdrop_filter(settings)}[bg];"
        f"[fgi]scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]"
    )
    inputs = ["-i", str(source.path)]
    if source.has_audio:
        audio_map = ["-map", "0:a:0"]
    else:
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        audio_map = ["-map", "1:a"]
    tmp = dst.with_name(dst.stem + ".part.mp4")
    ffmpeg.run([
        *inputs, "-filter_complex", graph, "-map", "[v]", *audio_map,
        "-t", f"{source.length:.3f}", "-fps_mode", "cfr",
        *_segment_encode_args(settings, encoder), str(tmp),
    ])
    os.replace(tmp, dst)


def default_jobs(encoder: ffmpeg.Encoder) -> int:
    cpus = os.cpu_count() or 4
    return min(NVENC_MAX_JOBS, cpus) if encoder.name == "nvenc" else cpus


def render_segments(
    sources: list[Source], settings: Settings, encoder: ffmpeg.Encoder, cache_dir: Path,
    jobs: int | None = None, engine: str = "perspective",
) -> list[Path]:
    """Render missing segments in parallel; return one segment path per source, in order."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    targets = [segment_path(s, settings, cache_dir, engine) for s in sources]
    todo = [(i, s, t) for i, (s, t) in enumerate(zip(sources, targets)) if not t.exists()]
    cached = len(sources) - len(todo)
    if cached:
        print(f"{cached} of {len(sources)} segments already cached", file=sys.stderr)
    if not todo:
        return targets

    workers = jobs or default_jobs(encoder)
    done = 0
    with tempfile.TemporaryDirectory(dir=cache_dir, prefix="work-") as work:
        workdir = Path(work)

        def render(index: int, source: Source, target: Path) -> None:
            if source.kind == "photo":
                render_photo_segment(source, target, settings, encoder, index, workdir, engine)
            else:
                render_clip_segment(source, target, settings, encoder)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(render, i, s, t): s for i, s, t in todo}
            for future in as_completed(futures):
                source = futures[future]
                future.result()  # re-raise the first failure
                done += 1
                print(f"[{done}/{len(todo)}] {source.kind} {source.path.name}", file=sys.stderr)
    return targets
