"""Turn the human-reviewed sheet into the gold set.

Reads data/gold/gold_review.xlsx. For each row the gold label is the reviewer's
correction when given, otherwise the LLM proposal (reviewer agreed).

Usage:
    python -m src.extraction.apply_review
Output: data/gold/gold_labels.jsonl (picked up automatically by eval_gold)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.extraction.schema import EVENT_TYPES  # noqa: E402

GOLD = ROOT / "data" / "gold"


def _blank(x) -> bool:
    return x is None or (isinstance(x, float) and pd.isna(x)) or str(x).strip() == ""


def main() -> None:
    df = pd.read_excel(GOLD / "gold_review.xlsx", sheet_name="review", dtype={"doc_id": str})
    out, corrected_type, corrected_details = [], 0, 0
    for r in df.itertuples():
        etype = r.llm_event_type
        if not _blank(r.correct_event_type):
            etype = str(r.correct_event_type).strip().upper()
            corrected_type += etype != r.llm_event_type
        assert etype in EVENT_TYPES, f"{r.doc_id}: unknown type {etype}"
        details = None if _blank(r.llm_details) else json.loads(r.llm_details)
        if not _blank(r.correct_details):
            details = json.loads(r.correct_details)
            corrected_details += 1
        out.append({"doc_id": r.doc_id, "event_type": etype, "details": details,
                    "reviewer_notes": "" if _blank(r.reviewer_notes) else str(r.reviewer_notes)})
    dest = GOLD / "gold_labels.jsonl"
    dest.write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in out) + "\n", encoding="utf-8")
    print(f"{len(out)} gold labels -> {dest} | types corrected: {corrected_type} | details corrected: {corrected_details}")


if __name__ == "__main__":
    main()
