"""Stratified gold-annotation sample + PDF download.

Picks up to 30 KSE-100 announcements per fine-grained event type (rare types
take whatever exists), then downloads just those PDFs for LLM-assisted labeling.
PDFs no longer in the sample are deleted.

Usage:
    python -m src.extraction.make_gold_sample            # sample + download
    python -m src.extraction.make_gold_sample --no-pdf   # sample only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.scraping.psx_client import PsxClient  # noqa: E402

PER_TYPE = 30
SEED = 42
GOLD_DIR = ROOT / "data" / "gold"
PDF_DIR = GOLD_DIR / "pdfs"


def build_sample() -> pd.DataFrame:
    kse = pd.read_csv(ROOT / "data" / "processed" / "events_kse100.csv")
    parts = []
    for ev in sorted(set(kse["event_type"])):
        cand = kse[(kse["event_type"] == ev) & kse["pdf_url"].notna()]
        n = min(PER_TYPE, len(cand))
        if n:
            parts.append(cand.sample(n, random_state=SEED))
    sample = pd.concat(parts, ignore_index=True)
    sample["doc_id"] = sample["pdf_url"].str.extract(r"/(\d+)\.pdf")
    sample = sample.dropna(subset=["doc_id"]).drop_duplicates("doc_id")
    return sample.sort_values(["event_type", "symbol"]).reset_index(drop=True)


def download_pdfs(sample: pd.DataFrame) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    keep = set(sample["doc_id"])
    stale = [f for f in PDF_DIR.glob("*.pdf") if f.stem not in keep]
    for f in stale:
        f.unlink()
    if stale:
        print(f"removed {len(stale)} PDFs no longer in the sample")
    client = PsxClient(delay_s=0.5)
    done = skip = fail = 0
    for _, row in sample.iterrows():
        out = PDF_DIR / f"{row.doc_id}.pdf"
        if out.exists():
            skip += 1
            continue
        try:
            resp = client._request("GET", f"/download/document/{row.doc_id}.pdf")
            out.write_bytes(resp.content)
            done += 1
        except Exception as e:
            fail += 1
            print(f"{row.doc_id} ({row.symbol}): FAILED {e}", file=sys.stderr, flush=True)
        if (done + skip + fail) % 50 == 0:
            print(f"--- {done + skip + fail}/{len(sample)}", flush=True)
    print(f"downloaded {done}, skipped {skip} existing, failed {fail}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--no-pdf", action="store_true")
    p.add_argument("--download-only", action="store_true",
                   help="keep the existing gold_sample.csv, just fetch missing PDFs")
    args = p.parse_args()

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    if args.download_only:
        # the frozen sample must not be re-drawn: the tagger has changed since
        download_pdfs(pd.read_csv(GOLD_DIR / "gold_sample.csv", dtype={"doc_id": str}))
        return
    sample = build_sample()
    out = GOLD_DIR / "gold_sample.csv"
    sample.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"{len(sample)} docs across {sample['event_type'].nunique()} event types -> {out}")
    print(sample["event_type"].value_counts().to_string())
    if not args.no_pdf:
        download_pdfs(sample)


if __name__ == "__main__":
    main()
