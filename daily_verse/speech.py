"""Read the verse aloud with Azure AI Speech neural voices.

Each language slide is read in a calm voice: the reference first, then the
verse. Female and male voices alternate between languages, and the order flips
every day, so each video and each week mixes both.

Needs AZURE_SPEECH_KEY (secret) and AZURE_SPEECH_REGION (e.g. westeurope).
Voices and speaking rate are set in church.json.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path
import re
import urllib.error
import urllib.request
import wave
from xml.sax.saxutils import escape

from .captions import CHURCH

ORDER = ("ta", "en", "de")
LOCALES = {"ta": "ta-IN", "en": "en-GB", "de": "de-DE"}
OUTPUT_FORMAT = "riff-24khz-16bit-mono-pcm"
GERMAN_ORDINALS = {"1": "Erster", "2": "Zweiter", "3": "Dritter"}
MOSE = {"1": "Erstes", "2": "Zweites", "3": "Drittes", "4": "Viertes", "5": "Fünftes"}
_REFERENCE = re.compile(r"^(?P<book>.+?)\s+(?P<chapter>\d+)[:,](?P<first>\d+)(?:-(?P<last>\d+))?$")


class SpeechError(Exception):
    """Azure rejected the request or was unreachable."""


@dataclass(frozen=True)
class Narration:
    lang: str
    voice: str
    path: Path
    seconds: float


def enabled() -> bool:
    return bool(os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION"))


def spoken_reference(lang: str, reference: str) -> str:
    """How a reader would say the reference, e.g. "Leviticus, chapter 20, verse 26"."""
    match = _REFERENCE.match(reference.strip())
    if not match:
        return reference
    book, chapter, first, last = match["book"], match["chapter"], match["first"], match["last"]
    if lang == "en":
        verses = f"verses {first} to {last}" if last else f"verse {first}"
        return f"{book}, chapter {chapter}, {verses}."
    if lang == "de":
        numbered = re.match(r"^(\d)\.\s*(.+)$", book)
        if numbered and numbered[2] == "Mose":
            book = f"{MOSE[numbered[1]]} Buch Mose"
        elif numbered and numbered[1] in GERMAN_ORDINALS:
            book = f"{GERMAN_ORDINALS[numbered[1]]} {numbered[2]}"
        verses = f"Verse {first} bis {last}" if last else f"Vers {first}"
        return f"{book}, Kapitel {chapter}, {verses}."
    verses = f"{first} முதல் {last} வரையிலான வசனங்கள்" if last else f"{first} ஆம் வசனம்"
    return f"{book}, {chapter} ஆம் அதிகாரம், {verses}."


def voices_for(day: date) -> dict[str, str]:
    """Alternate female/male across languages; flip the order every day."""
    genders = ("female", "male") if day.toordinal() % 2 == 0 else ("male", "female")
    return {lang: CHURCH["voices"][lang][genders[i % 2]] for i, lang in enumerate(ORDER)}


def ssml(lang: str, voice: str, reference: str, text: str) -> str:
    rate = CHURCH.get("speaking_rate", "-8%")
    locale = voice.rsplit("-", 1)[0] if voice.count("-") >= 2 else LOCALES[lang]
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{locale}">'
        f'<voice name="{escape(voice)}"><prosody rate="{rate}">'
        f'{escape(spoken_reference(lang, reference))}<break time="700ms"/>{escape(text)}'
        "</prosody></voice></speak>"
    )


def synthesize(document: str, out: Path) -> Path:
    """Send SSML to Azure and write the returned WAV."""
    region = os.environ["AZURE_SPEECH_REGION"].strip()
    request = urllib.request.Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=document.encode("utf-8"),
        headers={
            "Ocp-Apim-Subscription-Key": os.environ["AZURE_SPEECH_KEY"].strip(),
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
            "User-Agent": "clp-daily-verse",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            audio = response.read()
    except urllib.error.HTTPError as err:
        raise SpeechError(f"Azure Speech returned HTTP {err.code}: {err.read().decode(errors='replace')[:200]}") from err
    except OSError as err:
        raise SpeechError(f"Azure Speech unreachable: {err}") from err
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)
    return out


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as wav:
        return wav.getnframes() / wav.getframerate()


def narrate(verses: dict[str, dict[str, str]], day: date, workdir: Path) -> list[Narration]:
    """One WAV per language, in slide order."""
    voices = voices_for(day)
    readings = []
    for lang in ORDER:
        path = synthesize(
            ssml(lang, voices[lang], verses[lang]["reference"], verses[lang]["text"]), workdir / f"voice-{lang}.wav"
        )
        readings.append(Narration(lang, voices[lang], path, wav_seconds(path)))
    return readings


def combine(readings: list[Narration], starts: list[float], total: float, out: Path) -> Path:
    """Place each reading at its start time on one track, silent in between."""
    with wave.open(str(readings[0].path)) as first:
        rate, width = first.getframerate(), first.getsampwidth()
    track = bytearray(int(total * rate) * width)
    for reading, start in zip(readings, starts, strict=True):
        with wave.open(str(reading.path)) as wav:
            frames = wav.readframes(wav.getnframes())
        offset = int(start * rate) * width
        end = min(len(track), offset + len(frames))
        track[offset:end] = frames[: end - offset]
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(bytes(track))
    return out
