"""Turn the vertical slides into a Reel / YouTube Short with ffmpeg.

Each slide holds long enough to read, zooms in slowly, and cross-fades into the
next. The soundtrack is soft background music (see music.py), widened to stereo
with a little reverb, faded in and out and levelled to a calm loudness. Without
music a silent track is used, since some apps treat video with no audio as a GIF.
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


VOICE_LEAD = 0.7  # the voice starts once the cross-fade into a slide has settled
VOICE_TAIL = 1.2  # a moment of quiet before the next language fades in


def narrated_timing(readings: list[float]) -> tuple[list[float], list[float]]:
    """Slide lengths that fit each reading, and when each reading starts.

    Slide i fades in, waits VOICE_LEAD, is read, rests VOICE_TAIL, then fades
    out; the last slide leaves a second for the music to fade out instead.
    """
    seconds, starts, offset = [], [], 0.0
    for i, length in enumerate(readings):
        fade_in = FADE if i else 0.0
        fade_out = FADE if i < len(readings) - 1 else 1.0
        seconds.append(fade_in + VOICE_LEAD + length + VOICE_TAIL + fade_out)
        starts.append(offset + fade_in + VOICE_LEAD)
        offset += seconds[-1] - FADE  # the next slide's cross-fade begins here
    return seconds, starts


MUSIC_LOUDNESS = -18  # LUFS: present but calm, under the platforms' -14 target
VOICE_LOUDNESS = -16  # LUFS for narrated videos; the music sits well below the voice


def build_command(
    slides: list[Path],
    seconds: list[float],
    out: Path,
    size: tuple[int, int],
    music: Path | None = None,
    narration: Path | None = None,
) -> list[str]:
    """The ffmpeg command line; kept separate so it can be tested without encoding."""
    width, height = size
    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error"]
    for slide in slides:
        cmd += ["-i", str(slide)]
    total = sum(seconds) - FADE * (len(slides) - 1)
    if music:
        # Loop library tracks that are shorter than the video.
        cmd += ["-stream_loop", "-1", "-i", str(music)]
    else:
        cmd += ["-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    if narration:
        cmd += ["-i", str(narration)]

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

    audio = f"{len(slides)}:a"
    if music:
        bed = (
            f"[{len(slides)}:a]atrim=0:{total:.2f},aresample=44100,aformat=channel_layouts=stereo,haas,"
            "aecho=0.8:0.55:80|190|370:0.32|0.22|0.12,highpass=f=70,lowpass=f=7500,"
            f"afade=t=in:st=0:d=1.5,afade=t=out:st={max(0.0, total - 2.5):.2f}:d=2.5"
        )
        if narration:
            # Quiet music bed that ducks further while the voice speaks.
            graph += [
                f"{bed},loudnorm=I=-26:TP=-6:LRA=9,aresample=44100[bed]",
                f"[{len(slides) + 1}:a]aresample=44100,aformat=channel_layouts=stereo,"
                "highpass=f=80,acompressor=threshold=0.1:ratio=3:attack=10:release=200,asplit[v1][v2]",
                "[bed][v1]sidechaincompress=threshold=0.02:ratio=6:attack=80:release=900[ducked]",
                f"[ducked][v2]amix=inputs=2:normalize=0,atrim=0:{total:.2f},"
                f"loudnorm=I={VOICE_LOUDNESS}:TP=-1.5:LRA=11,aresample=44100[aout]",
            ]
        else:
            graph.append(f"{bed},loudnorm=I={MUSIC_LOUDNESS}:TP=-2:LRA=9,aresample=44100[aout]")
        audio = "[aout]"
    cmd += [
        "-filter_complex", ";".join(graph),
        "-map", f"[{previous}]", "-map", audio,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
        str(out),
    ]
    return cmd


def make_video(
    slides: list[Path],
    seconds: list[float],
    out: Path,
    size: tuple[int, int] = (1080, 1920),
    music: Path | None = None,
    narration: Path | None = None,
) -> Path:
    """Encode the slides, background music and optional narration into an MP4 at `out`."""
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        build_command(slides, seconds, out, size, music, narration), check=True, capture_output=True, timeout=600
    )
    return out
