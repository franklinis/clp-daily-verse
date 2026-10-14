"""The church's own verse picks, kept in custom-verses.csv at the repository root.

One row per date: the reference in English numbering (e.g. "Psalm 51:10") and
optional theme words that steer the AI background. Days without a row use
DailyVerses.net. Rows are added from Teams (see teams.py) or by editing the file.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .render import ROOT

PATH = ROOT / "custom-verses.csv"
FIELDS = ("date", "reference", "theme")


@dataclass(frozen=True)
class Entry:
    reference: str
    theme: str = ""

    @property
    def topics(self) -> list[str]:
        return [word.strip() for word in self.theme.split(",") if word.strip()]


def load(path: Path = PATH) -> dict[date, Entry]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as file:
        return {
            date.fromisoformat(row["date"].strip()): Entry(row["reference"].strip(), (row.get("theme") or "").strip())
            for row in csv.DictReader(file)
            if row.get("date", "").strip() and row.get("reference", "").strip()
        }


def save(entries: dict[date, Entry], path: Path = PATH) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(FIELDS)
        for day in sorted(entries):
            writer.writerow([day.isoformat(), entries[day].reference, entries[day].theme])
