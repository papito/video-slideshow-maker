# Video Slideshow Maker

Turn a folder of phone photos and video clips into one video. Photos get a slow, sub-pixel smooth Ken Burns move,
clips play in full with their own sound, everything is ordered by capture time and joined with
short crossfades over a blurred backdrop.

## Problem

Imagine you are trying to do a photo/video slideshow for your kid's birthday party. Even if you get past the hassle 
of figuring out how to set up a media server (assuming your TV has an app that can play media as slideshows),
the experience is usually awful:

* Blank images or videos because of unsupported formats
* Images shrink below TV's max height or width
* Play controls keep popping up when a video starts playing

This tool removes all these issues by creating one, solid video with 100% predictable experience. All you need is
any out-of-the box media server that you may already have or software like [Jellyfin](https://jellyfin.org/).

## Workflow

Requires `ffmpeg`/`ffprobe` on PATH (NVENC is used automatically when available) and
[uv](https://docs.astral.sh/uv/).


```
uv sync
uv run slideshow plan ~/Pictures/party            # writes playlist.txt
$EDITOR playlist.txt                              # delete or reorder lines
uv run slideshow render playlist.txt --draft      # quick 480p check -> slideshow.mp4
uv run slideshow render playlist.txt -o party.mp4 # full quality
```

`plan` reads EXIF dates from photos and creation tags from clips (converting UTC container
times to local time so the two sort together) and falls back to file modification time,
marking such lines with `(mtime fallback)`.

`render` turns each item into a cached segment under `.slideshow-cache/` next to the
playlist, in parallel, then joins the segments with xfade/acrossfade in one pass. Re-rendering
after editing the playlist only encodes what changed.

Supported inputs: JPEG, PNG, MP4, MOV. HEIC and HDR clips are not handled.

## Settings

Defaults live in `slideshow.toml` (used automatically when present in the current directory,
or passed with `--config`). Common flags: `--photo-duration`, `--crossfade`, `--jobs`,
`--encoder auto|nvenc|x264`, `--draft`.

The Ken Burns move uses ffmpeg's `perspective` filter, which resamples with sub-pixel precision so
the motion is smooth. `[photo] engine = "zoompan"` switches to the cheaper `zoompan` filter, which
steps on whole pixels and visibly jitters.

## Development

```
uv run pytest
```

The tests generate their own photos and clips with Pillow and ffmpeg; the end-to-end test
renders a six-item slideshow with libx264.
