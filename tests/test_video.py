"""Video assembly: timing maths, plus a tiny real encode."""

from pathlib import Path
import subprocess

import pytest

imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")

from daily_verse import video  # noqa: E402


def test_reading_time_is_clamped() -> None:
    assert video.reading_seconds("short") == 5.0
    assert video.reading_seconds("x" * 1000) == 9.0
    assert 5.0 < video.reading_seconds("x" * 90) < 9.0


def test_cross_fades_start_before_each_slide_ends() -> None:
    cmd = video.build_command([Path("a.png"), Path("b.png"), Path("c.png")], [6.0, 5.0, 7.0], Path("o.mp4"), (1080, 1920))
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "xfade=transition=fade:duration=0.8:offset=5.20" in graph
    assert "xfade=transition=fade:duration=0.8:offset=9.40" in graph
    # Silent audio lasts exactly as long as the video: 18s minus two fades.
    assert cmd[cmd.index("lavfi") + 2] == "16.40"


def test_make_video(tmp_path: Path) -> None:
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    slides = []
    for i, colour in enumerate(("red", "green", "blue")):
        slide = tmp_path / f"{i}.png"
        subprocess.run([exe, "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={colour}:s=108x192",
                        "-frames:v", "1", str(slide)], check=True)
        slides.append(slide)
    out = video.make_video(slides, [2.0, 2.0, 2.0], tmp_path / "out.mp4", size=(108, 192))
    frames, seconds = imageio_ffmpeg.count_frames_and_secs(str(out))
    assert seconds == pytest.approx(6.0 - 2 * video.FADE, abs=0.1)
