"""Combine scraped JSONL announcements + symbol metadata into CSV files.

Usage:
    python -m src.scraping.export_csv

Outputs:
    data/companies.csv           symbol, name, sector, isETF, isDebt, ...
    data/announcements.csv       symbol, date, time, title, pdf_url, company_name
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


def _safe_write(df: pd.DataFrame, out: Path) -> Path:
    """Write CSV; if the target is locked (open in Excel), use a numbered name."""
    for i in range(10):
        target = out if i == 0 else out.with_name(f"{out.stem}_{i}{out.suffix}")
        try:
            df.to_csv(target, index=False, encoding="utf-8-sig")
            return target
        except PermissionError:
            continue
    raise PermissionError(f"could not write {out} (file locked)")

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw" / "announcements"
SYMBOLS_JSON = ROOT / "data" / "raw" / "symbols.json"


def export_companies() -> pd.DataFrame | None:
    if not SYMBOLS_JSON.exists():
        print("symbols.json missing — run scrape_announcements --symbols first", file=sys.stderr)
        return None
    df = pd.DataFrame(json.loads(SYMBOLS_JSON.read_text(encoding="utf-8")))
    out = _safe_write(df, ROOT / "data" / "companies.csv")
    print(f"{len(df)} companies -> {out}")
    return df


def export_announcements() -> None:
    files = sorted(RAW_DIR.glob("*.jsonl"))
    if not files:
        print(f"no JSONL files in {RAW_DIR} — run the scraper first", file=sys.stderr)
        return
    frames = []
    for f in files:
        rows = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
        if rows:
            frames.append(pd.DataFrame(rows))
    df = pd.concat(frames, ignore_index=True)
    # the portal ignores date_from, so the raw files hold full history; keep 2018+
    df = df[df["date"] >= "2018-01-01"]
    df = df.sort_values(["symbol", "date", "time"]).reset_index(drop=True)
    cols = ["symbol", "date", "time", "title", "category", "pdf_url", "company_name", "scraped_at"]
    df = df[[c for c in cols if c in df.columns]]
    out = _safe_write(df, ROOT / "data" / "announcements.csv")
    print(f"{len(df)} announcements from {len(files)} companies -> {out}")


if __name__ == "__main__":
    export_companies()
    export_announcements()
