"""Background music: composed per date, or a church-chosen library track."""

from datetime import date
from pathlib import Path
import wave

import pytest

from daily_verse import music


def test_compose_is_the_right_length_and_stable_per_day(tmp_path: Path) -> None:
    a = music.compose(date(2026, 10, 14), 10.0, tmp_path / "a.wav")
    b = music.compose(date(2026, 10, 14), 10.0, tmp_path / "b.wav")
    c = music.compose(date(2026, 10, 15), 10.0, tmp_path / "c.wav")
    with wave.open(str(a)) as wav:
        assert wav.getnframes() == 10 * music.RATE
    assert a.read_bytes() == b.read_bytes()
    assert a.read_bytes() != c.read_bytes()


def test_library_tracks_take_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    library = tmp_path / "music"
    library.mkdir()
    for name in ("hymn-a.mp3", "hymn-b.mp3", "notes.txt"):
        (library / name).write_bytes(b"x")
    monkeypatch.setattr(music, "MUSIC_DIR", library)
    picks = {music.track_for(date(2026, 10, 14) + __import__("datetime").timedelta(days=i), 20, tmp_path)[0].name
             for i in range(4)}
    assert picks == {"hymn-a.mp3", "hymn-b.mp3"}


def test_composed_when_no_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(music, "MUSIC_DIR", tmp_path / "missing")
    track, from_library = music.track_for(date(2026, 10, 14), 2.0, tmp_path)
    assert not from_library and track.suffix == ".wav"
