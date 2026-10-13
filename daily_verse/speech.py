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
class Word:
    """A spoken word: when it is said, and where it sits in the SSML document."""

    start: float
    end: float
    offset: int
    text: str


@dataclass(frozen=True)
class Narration:
    lang: str
    voice: str
    path: Path
    seconds: float
    words: tuple[Word, ...] = ()
    document: str = ""


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


def synthesize(document: str, out: Path) -> tuple[Path, list[Word]]:
    """Speak the SSML into a WAV at `out`, returning each word's timing.

    Uses the Azure Speech SDK, which reports when every word is spoken; without
    the SDK it falls back to the REST API, which gives audio only.
    """
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError:
        return _synthesize_rest(document, out), []
    config = speechsdk.SpeechConfig(
        subscription=os.environ["AZURE_SPEECH_KEY"].strip(), region=os.environ["AZURE_SPEECH_REGION"].strip()
    )
    config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=None)
    words: list[Word] = []

    def on_word(event) -> None:
        if event.boundary_type == speechsdk.SpeechSynthesisBoundaryType.Word:
            start = event.audio_offset / 10_000_000
            words.append(Word(start, start + event.duration.total_seconds(), event.text_offset, event.text))

    synthesizer.synthesis_word_boundary.connect(on_word)
    result = synthesizer.speak_ssml_async(document).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        details = result.cancellation_details
        raise SpeechError(f"Azure Speech failed: {details.reason} {details.error_details}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(result.audio_data)
    return out, words


def _synthesize_rest(document: str, out: Path) -> Path:
    """Send SSML to Azure's REST endpoint and write the returned WAV."""
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


def narrate_one(lang: str, verse: dict[str, str], day: date, workdir: Path) -> Narration:
    """The reference and verse read aloud in one language, as a WAV."""
    voice = voices_for(day)[lang]
    document = ssml(lang, voice, verse["reference"], verse["text"])
    path, words = synthesize(document, workdir / f"voice-{lang}.wav")
    return Narration(lang, voice, path, wav_seconds(path), tuple(words), document)


def word_times(reading: Narration, text: str) -> list[tuple[float, float]]:
    """When each displayed word (text.split()) is spoken, in seconds into the reading.

    Azure's word offsets point into the SSML, so each spoken word is matched to
    the displayed word at that position. Words Azure didn't report are filled
    in from their neighbours; with no usable timings at all, the words are
    spread over the verse part of the reading in proportion to their length.
    """
    display = text.split()
    escaped = escape(text)
    verse_at = reading.document.rfind(escaped) if reading.document else -1
    spans, cursor = [], 0
    for word in display:
        start = escaped.index(escape(word), cursor)
        spans.append((verse_at + start, verse_at + start + len(escape(word))))
        cursor = start + len(escape(word))

    times: list[tuple[float, float] | None] = [None] * len(display)
    if verse_at >= 0:
        for word in reading.words:
            for k, (first, last) in enumerate(spans):
                if first <= word.offset < last:
                    current = times[k]
                    times[k] = (word.start, word.end) if current is None else (current[0], max(current[1], word.end))
                    break

    if sum(t is not None for t in times) * 2 < len(display):
        # Too few matches: estimate where the verse starts from the reference's share of the text.
        spoken = re.search(r"<prosody[^>]*>(.*?)<break", reading.document)
        reference = len(spoken[1]) if spoken else 20
        body = max(reading.seconds - 0.7, 0.1)
        begin = 0.7 + body * reference / (reference + len(text))
        span = max(reading.seconds - 0.2 - begin, 0.1)
        total = sum(len(w) for w in display) or 1
        result, t = [], begin
        for word in display:
            length = span * len(word) / total
            result.append((t, t + length))
            t += length
        return result

    for k, value in enumerate(times):
        if value is None:
            before = next((times[j][1] for j in range(k - 1, -1, -1) if times[j]), None)
            after = next((times[j][0] for j in range(k + 1, len(times)) if times[j]), None)
            start = before if before is not None else max(0.0, (after or 0.0) - 0.3)
            times[k] = (start, after if after is not None else start + 0.3)
    return times  # type: ignore[return-value]


def narrate(verses: dict[str, dict[str, str]], day: date, workdir: Path) -> list[Narration]:
    """One WAV per language, in slide order."""
    return [narrate_one(lang, verses[lang], day, workdir) for lang in ORDER]


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
