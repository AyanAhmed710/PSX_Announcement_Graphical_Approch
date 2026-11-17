"""OCR announcement PDFs (first pages only) with PyMuPDF + RapidOCR.

Page 1 is always OCR'd, even when the PDF has embedded text, so OCR accuracy
can be measured against the embedded text. Later pages that already carry
substantial embedded text are not OCR'd.

RapidOCR's recognizer is faster single-threaded than multi-threaded on this
machine, so documents are processed by a pool of single-threaded workers.

Usage:
    python -m src.extraction.ocr                 # gold sample
    python -m src.extraction.ocr --ids 277230 274976

Output: data/gold/ocr/<doc_id>.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import pandas as pd
import pymupdf
from rapidocr_onnxruntime import RapidOCR

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data" / "gold"
PDF_DIR = GOLD / "pdfs"
OUT_DIR = GOLD / "ocr"

PAGE_CAP = 3
PAGE_CAP_MERGER = 5
DPI = 200
MIN_EMBEDDED_CHARS = 200
SHORT_COVER_CHARS = 800
ENTITY_CANDIDATES = {"EXEC_CHANGE", "DIVIDEND", "MERGER_ACQUISITION"}
WORKERS = 10

_engine: RapidOCR | None = None


def _init_worker() -> None:
    global _engine
    _engine = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)


def page_cap(event_type: str) -> int:
    return PAGE_CAP_MERGER if event_type == "MERGER_ACQUISITION" else PAGE_CAP


def needs_more_pages(first_page: dict, event_type: str) -> bool:
    """Read past page 1 only for entity-type candidates or a short cover page.

    Pages 2-3 of financial reports are dense statements (150+ OCR lines each)
    that never decide the event type; the cover letter on page 1 does.
    """
    if event_type in ENTITY_CANDIDATES:
        return True
    text = first_page["embedded_text"] if len(first_page["embedded_text"]) >= MIN_EMBEDDED_CHARS \
        else first_page["ocr_text"]
    return len(text) < SHORT_COVER_CHARS


def ocr_page(engine: RapidOCR, page: pymupdf.Page) -> dict:
    png = page.get_pixmap(dpi=DPI).tobytes("png")
    result, _ = engine(png)
    lines = result or []
    # sort top-to-bottom, then left-to-right, using each box's top-left corner
    lines = sorted(lines, key=lambda r: (round(r[0][0][1] / 12), r[0][0][0]))
    confs = [float(r[2]) for r in lines]
    return {
        "ocr_text": "\n".join(r[1] for r in lines),
        "ocr_conf_mean": round(sum(confs) / len(confs), 4) if confs else 0.0,
        "ocr_conf_min": round(min(confs), 4) if confs else 0.0,
        "n_lines": len(lines),
    }


def process(engine: RapidOCR, doc_id: str, event_type: str) -> dict:
    doc = pymupdf.open(PDF_DIR / f"{doc_id}.pdf")
    n_total = doc.page_count
    pages = []
    for i in range(min(n_total, page_cap(event_type))):
        if i > 0 and not needs_more_pages(pages[0], event_type):
            break
        page = doc[i]
        rec = {"page": i + 1, "embedded_text": page.get_text().strip()}
        if i > 0 and len(rec["embedded_text"]) >= MIN_EMBEDDED_CHARS:
            rec.update({"ocr_text": "", "ocr_conf_mean": 0.0, "ocr_conf_min": 0.0,
                        "n_lines": 0, "ocr_skipped": True})
        else:
            rec.update(ocr_page(engine, page))
        pages.append(rec)
    return {"doc_id": doc_id, "n_pages_total": n_total, "n_pages_read": len(pages), "pages": pages}


def _work(args: tuple[str, str]) -> tuple[str, str | None]:
    doc_id, event_type = args
    try:
        out = process(_engine, doc_id, event_type)
        (OUT_DIR / f"{doc_id}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        return doc_id, None
    except Exception as e:
        return doc_id, str(e)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ids", nargs="*")
    p.add_argument("--workers", type=int, default=WORKERS)
    args = p.parse_args()

    sample = pd.read_csv(GOLD / "gold_sample.csv", dtype={"doc_id": str})
    if args.ids:
        sample = sample[sample["doc_id"].isin(args.ids)]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    todo = [(r.doc_id, r.event_type) for r in sample.itertuples()
            if not (OUT_DIR / f"{r.doc_id}.json").exists()]
    print(f"{len(sample) - len(todo)} already done, {len(todo)} to OCR "
          f"with {args.workers} workers", flush=True)
    t0 = time.time()
    with Pool(args.workers, initializer=_init_worker) as pool:
        for i, (doc_id, err) in enumerate(pool.imap_unordered(_work, todo), 1):
            if err:
                print(f"{doc_id}: FAILED {err}", file=sys.stderr, flush=True)
            if i % 20 == 0:
                rate = (time.time() - t0) / i
                print(f"--- {i}/{len(todo)} docs, ~{rate * (len(todo) - i) / 60:.0f} min left", flush=True)
    print(f"done in {(time.time() - t0) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
