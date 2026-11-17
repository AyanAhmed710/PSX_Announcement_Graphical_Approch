"""EDA over scraped PSX announcements (full set + KSE-100 subset).

Usage:
    python -m src.analysis.eda_announcements
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

pd.set_option("display.width", 200)

# quick-and-dirty event buckets from title keywords, to gauge schema coverage
EVENT_PATTERNS = [
    ("FINANCIAL_RESULT", r"financial result|quarterly report|annual report|half yearly|accounts for"),
    ("BOARD_MEETING", r"board meeting"),
    ("DIVIDEND", r"dividend"),
    ("AGM_EGM", r"annual general meeting|extraordinary general meeting|\bagm\b|\begm\b|general meeting"),
    ("EXEC_CHANGE", r"appointment|resignation|casual vacancy|chief executive|director|company secretary|cfo\b"),
    ("MERGER_ACQUISITION", r"merger|amalgamation|acquisition|scheme of arrangement|takeover"),
    ("RIGHTS_ISSUE", r"right issue|rights issue|right shares"),
    ("BUYBACK", r"buy back|buyback|repurchase"),
    ("CREDIT_RATING", r"credit rating|rating report|entity rating"),
    ("DISCLOSURE_INTEREST", r"disclosure of interest|substantial shareholder|free float"),
    ("BOOK_CLOSURE", r"book closure|closed period|register of members"),
    ("MATERIAL_INFO", r"material information|price sensitive"),
    ("TRANSMISSION_REPORT", r"transmission of"),
]


def tag_event(title: str) -> str:
    t = str(title).lower()
    for name, pat in EVENT_PATTERNS:
        if re.search(pat, t):
            return name
    return "OTHER"


def profile(df: pd.DataFrame, label: str) -> None:
    print(f"\n{'='*70}\n{label}: {len(df)} rows, {df['symbol'].nunique()} companies\n{'='*70}")
    df = df.copy()
    df["year"] = df["date"].str[:4]
    df["dt"] = pd.to_datetime(df["date"], errors="coerce")

    print("\n-- rows per year:")
    print(df["year"].value_counts().sort_index().to_string())

    per_co = df.groupby("symbol").size().sort_values()
    print("\n-- announcements per company: "
          f"min={per_co.min()} p25={per_co.quantile(.25):.0f} median={per_co.median():.0f} "
          f"p75={per_co.quantile(.75):.0f} max={per_co.max()}")
    print("top 5:", dict(per_co.tail(5)))
    print("bottom 5:", dict(per_co.head(5)))

    print("\n-- event-type coverage (keyword tagger):")
    df["event"] = df["title"].map(tag_event)
    ev = df["event"].value_counts()
    print((ev.to_frame("n").assign(pct=lambda x: (100 * x.n / len(df)).round(1))).to_string())

    print("\n-- top 15 OTHER titles (schema gaps):")
    other = df[df["event"] == "OTHER"]["title"].str.strip().value_counts().head(15)
    print(other.to_string())

    print("\n-- duplicates: exact (symbol,date,title) dupes:",
          df.duplicated(["symbol", "date", "title"]).sum())
    print("-- missing pdf_url:", df["pdf_url"].isna().sum(),
          f"({100*df['pdf_url'].isna().mean():.1f}%)")
    print("-- missing/blank time:", (df["time"].isna() | (df["time"] == "")).sum())

    # temporal texture for forecasting
    gaps = (df.sort_values("dt").groupby("symbol")["dt"].diff().dt.days.dropna())
    print(f"\n-- inter-event gap days: median={gaps.median():.0f} p75={gaps.quantile(.75):.0f} "
          f"p95={gaps.quantile(.95):.0f}")
    print("-- events per company-month (mean):",
          round(df.groupby(["symbol", df["dt"].dt.to_period("M")]).size().mean(), 2))

    # event mix stability over time (train/test drift check)
    print("\n-- event mix by year (% of year's rows):")
    mix = (df.pivot_table(index="year", columns="event", aggfunc="size", fill_value=0)
             .pipe(lambda x: (100 * x.div(x.sum(axis=1), axis=0)).round(1)))
    keep = ev.head(8).index
    print(mix[[c for c in keep if c in mix.columns]].to_string())


def main() -> None:
    full = pd.read_csv(ROOT / "data" / "announcements.csv")
    kse = pd.read_csv(ROOT / "data" / "announcements_kse100.csv")
    profile(full, "FULL (all companies, 2018+)")
    profile(kse, "KSE-100 subset")


if __name__ == "__main__":
    main()
