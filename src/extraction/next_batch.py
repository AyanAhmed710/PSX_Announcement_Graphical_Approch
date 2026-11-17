"""Print the next batch of OCR'd, not-yet-labeled gold docs for LLM labeling.

No title and no tagger label are shown, so the label is an independent
judgement from the document content. Order is a fixed shuffle.

Usage:
    python -m src.extraction.next_batch [N]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.extraction.gold_text import CHAR_CAP, CHAR_CAP_MERGER, best_text, condense  # noqa: E402

GOLD = ROOT / "data" / "gold"


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    sample = pd.read_csv(GOLD / "gold_sample.csv", dtype={"doc_id": str})
    sample = sample.sample(frac=1, random_state=11)
    labels_f = GOLD / "llm_labels.jsonl"
    done = set()
    if labels_f.exists():
        done = {json.loads(l)["doc_id"] for l in labels_f.read_text(encoding="utf-8").splitlines() if l.strip()}
    shown = 0
    for r in sample.itertuples():
        f = GOLD / "ocr" / f"{r.doc_id}.json"
        if r.doc_id in done or not f.exists():
            continue
        rec = json.loads(f.read_text(encoding="utf-8"))
        text, _ = best_text(rec)
        cap = CHAR_CAP_MERGER if r.event_type == "MERGER_ACQUISITION" else CHAR_CAP
        print(f"=== DOC {r.doc_id} | {r.symbol} | {r.date} | pages {rec['n_pages_read']}/{rec['n_pages_total']} ===")
        print(condense(text)[:cap] or "[NO TEXT EXTRACTED]")
        print()
        shown += 1
        if shown >= n:
            break
    print(f"### shown {shown} | labeled so far {len(done)}")


if __name__ == "__main__":
    main()
