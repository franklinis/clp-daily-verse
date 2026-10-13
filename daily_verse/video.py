"""Turn the vertical slides into a Reel / YouTube Short with ffmpeg.

Each slide holds long enough to read, zooms in slowly, and cross-fades into the
next. A silent audio track is included because some apps treat video without
audio as a GIF.
"""

from __future__ import annotations

from pathlib import Path
import subprocess

import imageio_ffmpeg

FPS = 30
FADE = 0.8  # seconds of cross-fade between slides
ZOOM = 0.05  # how far each slide zooms in over its time on screen


def reading_seconds(text: str) -> float:
    """Time to read a verse comfortably: 5 to 9 seconds depending on length."""
    return min(9.0, max(5.0, 3.5 + len(text) / 30))


def build_command(slides: list[Path], seconds: list[float], out: Path, size: tuple[int, int]) -> list[str]:
    """The ffmpeg command line; kept separate so it can be tested without encoding."""
    width, height = size
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error"]
    for slide in slides:
        cmd += ["-i", str(slide)]
    total = sum(seconds) - FADE * (len(slides) - 1)
    cmd += ["-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]

    graph = []
    for i, length in enumerate(seconds):
        frames = round(length * FPS)
        # Upscale first so the slow zoom moves in sub-pixel steps instead of jittering.
        graph.append(
            f"[{i}:v]scale={width * 2}:{height * 2},"
            f"zoompan=z='1+{ZOOM}*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={width}x{height}:fps={FPS},setsar=1,format=yuv420p[v{i}]"
        )
    previous, offset = "v0", 0.0
    for i in range(1, len(slides)):
        offset += seconds[i - 1] - FADE
        label = f"x{i}"
        graph.append(f"[{previous}][v{i}]xfade=transition=fade:duration={FADE}:offset={offset:.2f}[{label}]")
        previous = label

    cmd += [
        "-filter_complex", ";".join(graph),
        "-map", f"[{previous}]", "-map", f"{len(slides)}:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
        str(out),
    ]
    return cmd


def make_video(slides: list[Path], seconds: list[float], out: Path, size: tuple[int, int] = (1080, 1920)) -> Path:
    """Encode the slides into an MP4 at `out`."""
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(build_command(slides, seconds, out, size), check=True, capture_output=True, timeout=600)
    return out
