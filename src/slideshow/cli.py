"""Command line: `slideshow plan SOURCE` and `slideshow render PLAYLIST`."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import ffmpeg, join as joiner, segments
from .capture_time import capture_time
from .config import ConfigError, Settings, load_settings
from .playlist import Item, format_length, read_playlist, write_playlist
from .scan import kind_of, scan

app = typer.Typer(help="Stitch a folder of phone photos and clips into one video.", no_args_is_help=True)

ConfigOpt = Annotated[Optional[Path], typer.Option("--config", "-c", help="TOML settings file (default: ./slideshow.toml if present).")]
PhotoDurationOpt = Annotated[Optional[float], typer.Option("--photo-duration", help="Seconds each photo stays on screen.")]
CrossfadeOpt = Annotated[Optional[float], typer.Option("--crossfade", help="Crossfade length in seconds.")]


def fail(message: str) -> None:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


def resolve_settings(config: Path | None, draft: bool = False, **overrides: object) -> Settings:
    try:
        settings, used = load_settings(config, overrides=overrides, draft=draft)
    except (ConfigError, OSError) as exc:
        fail(str(exc))
    if used is not None:
        typer.echo(f"settings from {used}", err=True)
    return settings


@app.command()
def plan(
    source: Annotated[Path, typer.Argument(help="Folder of photos and clips.", exists=True, file_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o", help="Playlist to write.")] = Path("playlist.txt"),
    config: ConfigOpt = None,
    photo_duration: PhotoDurationOpt = None,
    crossfade: CrossfadeOpt = None,
) -> None:
    """Scan SOURCE, order everything by capture time, and write an editable playlist."""
    settings = resolve_settings(config, photo_duration=photo_duration, crossfade=crossfade)
    try:
        files = scan(source.resolve())
        items: list[Item] = []
        for path in files:
            kind = kind_of(path) or "photo"
            if kind == "clip":
                info = ffmpeg.probe(path)
                length = ffmpeg.duration(info)
            else:
                info, length = None, settings.photo_duration
            when = capture_time(path, kind, info)
            items.append(Item(path, kind, when.when, length, when.source))
    except (ffmpeg.FfmpegError, ffmpeg.ToolMissing) as exc:
        fail(str(exc))
    items.sort(key=lambda i: (i.captured, i.path.name))
    write_playlist(items, source.resolve(), settings.crossfade, output)
    fallbacks = sum(1 for i in items if i.time_source == "mtime")
    photos = sum(1 for i in items if i.kind == "photo")
    total = sum(i.length for i in items) - settings.crossfade * max(0, len(items) - 1)
    typer.echo(f"{len(items)} items ({photos} photos, {len(items) - photos} clips), "
               f"estimated length {format_length(total)}")
    if fallbacks:
        typer.echo(f"{fallbacks} items had no capture time in metadata and use file modification time", err=True)
    typer.echo(f"playlist written to {output}")


@app.command()
def render(
    playlist: Annotated[Path, typer.Argument(help="Playlist written by `plan`, possibly edited.", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o", help="Slideshow to write.")] = Path("slideshow.mp4"),
    draft: Annotated[bool, typer.Option("--draft", help="Quick low-resolution render to check order and transitions.")] = False,
    config: ConfigOpt = None,
    photo_duration: PhotoDurationOpt = None,
    crossfade: CrossfadeOpt = None,
    jobs: Annotated[Optional[int], typer.Option("--jobs", "-j", help="Parallel segment renders.")] = None,
    encoder: Annotated[Optional[str], typer.Option("--encoder", help="auto, nvenc or x264.")] = None,
) -> None:
    """Render the slideshow from PLAYLIST."""
    settings = resolve_settings(
        config, draft, photo_duration=photo_duration, crossfade=crossfade, jobs=jobs, encoder=encoder
    )
    paths = read_playlist(playlist)
    if not paths:
        fail(f"{playlist} lists no items")
    missing = [p for p in paths if not p.is_file()]
    if missing:
        fail("missing files:\n  " + "\n  ".join(str(p) for p in missing))

    try:
        enc = ffmpeg.choose_encoder(settings.encoder)
        engine = ffmpeg.choose_motion_engine(settings.ken_burns_engine)
        typer.echo(f"encoder: {'h264_nvenc' if enc.name == 'nvenc' else 'libx264'}, "
                   f"ken burns: {engine}{' (draft)' if settings.draft else ''}", err=True)
        sources: list[segments.Source] = []
        for path in paths:
            kind = kind_of(path)
            if kind is None:
                fail(f"unsupported file type: {path}")
            if kind == "clip":
                info = ffmpeg.probe(path)
                sources.append(segments.Source(path, kind, ffmpeg.duration(info), ffmpeg.has_audio(info)))
            else:
                sources.append(segments.Source(path, kind, settings.photo_duration))

        cache_dir = playlist.resolve().parent / settings.cache_dir
        if settings.draft:
            cache_dir = cache_dir / "draft"
        rendered = segments.render_segments(sources, settings, enc, cache_dir, settings.jobs, engine)
        with tempfile.TemporaryDirectory(dir=cache_dir, prefix="join-") as work:
            total = joiner.join(rendered, settings, enc, output, Path(work))
    except (ffmpeg.FfmpegError, ffmpeg.ToolMissing, ValueError) as exc:
        fail(str(exc))
    typer.echo(f"wrote {output}: {len(sources)} items, {format_length(total)}")


def main() -> None:
    app()


if __name__ == "__main__":
    sys.exit(main())
