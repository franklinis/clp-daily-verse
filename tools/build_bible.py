"""Build the bundled Bible texts used for custom verses (run once; the output is committed).

    python tools/build_bible.py

Downloads two public-domain texts and writes compact copies to daily_verse/bible/:
- kjv.json.gz: King James Version (1769) from eBible.org's USFM files; psalm titles,
  footnotes and Strong's numbers removed, italics kept as plain words.
- lu12.json.gz: Lutherbibel 1912 from eBible.org, arranged in English verse
  numbering, plus "refs" giving the German verse number wherever it differs
  (most Psalms, Joel, Malachi, ...). Psalm titles are removed from verse 1; where
  they end comes from bolls.life's copy of the same text, which separates the
  original verses of a psalm's first English verse with double spaces.
"""

from __future__ import annotations

import gzip
import io
import json
from pathlib import Path
import re
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "daily_verse" / "bible"
KJV_USFM = "https://ebible.org/Scriptures/eng-kjv_usfm.zip"
LU12_VPL = "https://ebible.org/Scriptures/deu1912_vpl.zip"
LU12_BOLLS = "https://bolls.life/static/translations/LUT.zip"

# The 66 books in eBible's USFM file numbering (02-40 Old Testament, 70-96 New Testament).
USFM_NUMBERS = [f"{n:02d}" for n in range(2, 41)] + [str(n) for n in range(70, 97)]
SKIP_LINE = re.compile(r"^\\(id|ide|h|toc\d*|mt\d*|ms\d*|mr|s\d*|sr|r|d|ip|is\d*|qa|rem|sp|cl|cp)\b")
PSALMS = 19


def download(url: str) -> zipfile.ZipFile:
    request = urllib.request.Request(url, headers={"User-Agent": "clp-daily-verse/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return zipfile.ZipFile(io.BytesIO(response.read()))


def clean(text: str) -> str:
    text = re.sub(r"\\f .*?\\f\*", "", text, flags=re.S)  # footnotes
    text = re.sub(r"\\x .*?\\x\*", "", text, flags=re.S)  # cross references
    text = re.sub(r"\\\+?w ([^|\\]*)(\|[^\\]*)?\\\+?w\*", r"\1", text)  # \w word|strong="H1234"\w*
    text = re.sub(r"\\\+?[a-z]+\d*\*?", " ", text)  # \add, \nd, \wj, \q1, \p ... keep their words
    text = text.replace("¶", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r" ([,;:.!?)])", r"\1", text)


def parse_usfm(source: str) -> tuple[list[list[str]], set[int]]:
    """Chapters of verse texts, and the chapters that open with a title (\\d)."""
    chapters: list[list[str]] = []
    titled: set[int] = set()
    verse: list[str] | None = None
    for line in source.splitlines():
        line = line.strip()
        if match := re.match(r"^\\c (\d+)", line):
            chapters.append([])
            verse = None
            continue
        if line.startswith("\\d") and chapters:
            titled.add(len(chapters))
        if SKIP_LINE.match(line) or not chapters:
            continue
        for part in re.split(r"(\\v \d+\s)", line):
            if match := re.match(r"\\v (\d+)\s", part):
                if int(match[1]) != len(chapters[-1]) + 1:
                    raise ValueError(f"verse {match[1]} out of order in chapter {len(chapters)}")
                verse = []
                chapters[-1].append("")
            elif verse is not None and chapters[-1]:
                chapters[-1][-1] += " " + part
    return [[clean(v) for v in chapter] for chapter in chapters], titled


def build_kjv() -> tuple[dict, dict[int, set[int]]]:
    archive = download(KJV_USFM)
    names = {name[:2]: name for name in archive.namelist() if name.endswith(".usfm")}
    books, titles = [], {}
    for index, number in enumerate(USFM_NUMBERS, start=1):
        chapters, titled = parse_usfm(archive.read(names[number]).decode("utf-8-sig"))
        books.append(chapters)
        titles[index] = titled
    return {"name": "King James Version", "source": "eBible.org eng-kjv, public domain", "books": books}, titles


def psalm_offsets() -> dict[int, list[str]]:
    """For each psalm, its first English verse split into the original (German) verses."""
    archive = download(LU12_BOLLS)
    verses = json.loads(archive.read("LUT.json"))
    return {
        v["chapter"]: re.split(r"\s{2,}", v["text"].strip())
        for v in verses if v["book"] == PSALMS and v["verse"] == 1
    }


def build_lu12(psalm_titles: set[int]) -> dict:
    archive = download(LU12_VPL)
    lines = archive.read("deu1912_vpl.txt").decode("utf-8-sig").splitlines()
    codes: list[str] = []
    books: list[list[list[str]]] = []
    refs: dict[str, str] = {}
    for line in lines:
        code, _, rest = line.partition(" ")
        number, _, text = rest.partition(" ")
        if code not in codes:
            codes.append(code)
            books.append([])
        chapter, verse = (int(n) for n in number.split(":"))
        while len(books[-1]) < chapter:
            books[-1].append([])
        if match := re.match(r"^\[(\d+:\d+)\]\s*", text):
            refs[f"{len(codes)}:{chapter}:{verse}"] = match[1]
            text = text[match.end():]
        text = re.sub(r"\[\d+(:\d+)?[ab]?\]\s*", "", text)  # a German verse starting mid-verse
        books[-1][chapter - 1].append(re.sub(r"\s+", " ", text).strip())
    if len(books) != 66:
        raise ValueError(f"expected 66 books, found {len(books)}")

    # Psalms: German numbering counts the title as verse 1 (or 1-2) in many psalms.
    split = psalm_offsets()
    psalms = books[PSALMS - 1]
    for chapter, verses in enumerate(psalms, start=1):
        parts = split[chapter]
        offset = len(parts) - 1
        if offset:
            start = verses[0].lower().find(parts[-1][:15].lower())
            if start <= 0:
                raise ValueError(f"Psalm {chapter}: title end not found")
            verses[0] = verses[0][start:]
            for verse in range(1, len(verses) + 1):
                refs[f"{PSALMS}:{chapter}:{verse}"] = f"{chapter}:{verse + offset}"
            if chapter == 13:  # English 13:5-6 is German 13,6
                refs[f"{PSALMS}:13:6"] = "13:6"
        elif chapter in psalm_titles and ". " in verses[0]:
            # Short titles share verse 1 with the text, e.g. "Ein Psalm Davids. Der HERR ist mein Hirte".
            verses[0] = verses[0].split(". ", 1)[1]
    return {"name": "Lutherbibel 1912", "source": "eBible.org deu1912, public domain", "books": books, "refs": refs}


def write(name: str, data: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    (OUT / name).write_bytes(gzip.compress(raw, mtime=0))
    print(f"{name}: {sum(len(c) for b in data['books'] for c in b)} verses, {len(raw) // 1024} KB")


def main() -> int:
    kjv, titles = build_kjv()
    lu12 = build_lu12(titles[PSALMS])
    for index, (english, german) in enumerate(zip(kjv["books"], lu12["books"], strict=True), start=1):
        if [len(c) for c in english] != [len(c) for c in german]:
            raise ValueError(f"book {index}: verse counts differ between KJV and Luther 1912")
    write("kjv.json.gz", kjv)
    write("lu12.json.gz", lu12)
    return 0


if __name__ == "__main__":
    sys.exit(main())
