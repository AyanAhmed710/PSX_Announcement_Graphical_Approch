"""Tag all announcements with event types and forecast classes.

Usage:
    python -m src.extraction.tag_events

Outputs:
    data/processed/events.csv          all companies
    data/processed/events_kse100.csv   KSE-100 subset
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.extraction.schema import forecast_class, tag_event  # noqa: E402

OUT_DIR = ROOT / "data" / "processed"


def tag_file(src: Path, dst: Path) -> None:
    df = pd.read_csv(src)
    # clean known junk: parser artifact rows and exact repost duplicates
    df = df[df["title"].str.strip() != "View PDF"]
    df = df.drop_duplicates(["symbol", "date", "title"])
    df["event_type"] = df["title"].map(tag_event)
    df["forecast_class"] = df["event_type"].map(forecast_class)
    df = df.sort_values(["symbol", "date", "time"]).reset_index(drop=True)
    df.to_csv(dst, index=False, encoding="utf-8-sig")
    print(f"{len(df)} rows -> {dst}")
    print(df["event_type"].value_counts().to_string(), "\n")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag_file(ROOT / "data" / "announcements.csv", OUT_DIR / "events.csv")
    tag_file(ROOT / "data" / "announcements_kse100.csv", OUT_DIR / "events_kse100.csv")


if __name__ == "__main__":
    main()
