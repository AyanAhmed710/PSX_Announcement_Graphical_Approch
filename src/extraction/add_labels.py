"""Append LLM label records (JSON lines on stdin) to data/gold/llm_labels.jsonl.

Each line: {"doc_id", "event_type", "details", "confidence", "note"}.
Validates event types and skips doc_ids already labeled.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.extraction.schema import EVENT_TYPES  # noqa: E402

OUT = ROOT / "data" / "gold" / "llm_labels.jsonl"


def main() -> None:
    done = set()
    if OUT.exists():
        done = {json.loads(l)["doc_id"] for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()}
    added = 0
    with OUT.open("a", encoding="utf-8") as fh:
        for line in sys.stdin.read().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            rec["doc_id"] = str(rec["doc_id"])
            assert rec["event_type"] in EVENT_TYPES, rec
            if rec["doc_id"] in done:
                continue
            rec.setdefault("details", None)
            rec.setdefault("confidence", "high")
            rec.setdefault("note", "")
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            done.add(rec["doc_id"])
            added += 1
    print(f"added {added}, total {len(done)}")


if __name__ == "__main__":
    main()
