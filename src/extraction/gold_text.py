"""Build the 'best text' per gold document.

Best text per page = embedded PDF text when it is substantial, else OCR text
(the same rule the pipeline uses at scale).

Usage:
    python -m src.extraction.gold_text            # writes gold_text.jsonl
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

GOLD = ROOT / "data" / "gold"
OCR_DIR = GOLD / "ocr"
MIN_EMBEDDED_CHARS = 200
CHAR_CAP = 2500
CHAR_CAP_MERGER = 4000


def best_text(ocr_rec: dict) -> tuple[str, str]:
    """Return (text, source) where source is 'embedded', 'ocr' or 'mixed'."""
    parts, sources = [], set()
    for pg in ocr_rec["pages"]:
        if len(pg["embedded_text"]) >= MIN_EMBEDDED_CHARS:
            parts.append(pg["embedded_text"])
            sources.add("embedded")
        else:
            parts.append(pg["ocr_text"])
            sources.add("ocr")
    src = sources.pop() if len(sources) == 1 else "mixed"
    return "\n".join(parts), src


def condense(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def main() -> None:
    sample = pd.read_csv(GOLD / "gold_sample.csv", dtype={"doc_id": str})
    rows = []
    for r in sample.itertuples():
        f = OCR_DIR / f"{r.doc_id}.json"
        if not f.exists():
            continue
        rec = json.loads(f.read_text(encoding="utf-8"))
        text, src = best_text(rec)
        confs = [p["ocr_conf_mean"] for p in rec["pages"] if p["n_lines"]]
        rows.append({
            "doc_id": r.doc_id, "symbol": r.symbol, "date": r.date, "split": r.split,
            "text_source": src, "n_pages_total": rec["n_pages_total"],
            "n_pages_read": rec["n_pages_read"],
            "ocr_conf_mean": round(sum(confs) / len(confs), 4) if confs else 0.0,
            "text": condense(text),
        })
    out = GOLD / "gold_text.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(rows)} docs -> {out}")


if __name__ == "__main__":
    main()
