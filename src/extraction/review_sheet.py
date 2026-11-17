"""Build the human review sheet for the gold set (Excel) with QC flags.

Usage:
    python -m src.extraction.review_sheet
Output: data/gold/gold_review.xlsx
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.extraction import schema  # noqa: E402

GOLD = ROOT / "data" / "gold"
LOW_CONF = 0.85
NEAR_EMPTY_CHARS = 100


def qc_flags(row: pd.Series) -> list[str]:
    flags = []
    if row["text_source"] != "embedded" and row["ocr_conf_mean"] < LOW_CONF:
        flags.append("LOW_OCR_CONFIDENCE")
    if len(row["text"]) < NEAR_EMPTY_CHARS:
        flags.append("NEAR_EMPTY_TEXT")
    title, text = str(row["title"]).lower(), row["text"]
    if re.search(r"appoint|resign", title) and not re.search(r"\b(?:Mr|Mrs|Ms|Dr|Syed|Mian)\b\.?", text):
        flags.append("APPOINTMENT_WITHOUT_NAME")
    if "dividend" in title and not re.search(r"(?:Rs\.?|PKR)\s*\d|\d\s*%", text):
        flags.append("DIVIDEND_WITHOUT_AMOUNT")
    if row.get("llm_event_type") and row["llm_event_type"] != row["tagger_v1"]:
        flags.append("LLM_DISAGREES_WITH_TITLE")
    return flags


def main() -> None:
    sample = pd.read_csv(GOLD / "gold_sample.csv", dtype={"doc_id": str})
    text = pd.read_json(GOLD / "gold_text.jsonl", lines=True, dtype={"doc_id": str})
    labels = pd.read_json(GOLD / "llm_labels.jsonl", lines=True, dtype={"doc_id": str})
    df = sample.merge(text[["doc_id", "text_source", "n_pages_total", "n_pages_read", "ocr_conf_mean", "text"]],
                      on="doc_id", how="left")
    df = df.merge(labels.rename(columns={"event_type": "llm_event_type", "details": "llm_details",
                                         "confidence": "llm_confidence", "note": "llm_note"}),
                  on="doc_id", how="left")
    df["text"] = df["text"].fillna("")
    df["tagger_v1"] = df["title"].map(schema.tag_event_v1)
    df["qc_flags"] = df.apply(lambda r: ", ".join(qc_flags(r)), axis=1)
    df["local_pdf"] = df["doc_id"].map(lambda d: str((GOLD / "pdfs" / f"{d}.pdf").resolve()))
    df["llm_details"] = df["llm_details"].map(
        lambda d: json.dumps(d, ensure_ascii=False) if isinstance(d, dict) else "")
    for c in ["correct_event_type", "correct_details", "reviewer_notes"]:
        df[c] = ""

    cols = ["doc_id", "split", "symbol", "date", "title", "local_pdf", "pdf_url", "n_pages_total",
            "n_pages_read", "text_source", "ocr_conf_mean", "qc_flags", "tagger_v1",
            "llm_event_type", "llm_details", "llm_confidence", "llm_note",
            "correct_event_type", "correct_details", "reviewer_notes"]
    df = df[cols].sort_values(["split", "llm_event_type", "symbol"])
    out = GOLD / "gold_review.xlsx"
    with pd.ExcelWriter(out, engine="openpyxl") as xl:
        df.to_excel(xl, sheet_name="review", index=False)
        guide = pd.DataFrame({"How to review": [
            "1. Open the PDF (local_pdf path, or pdf_url on the PSX portal).",
            "2. Check llm_event_type. If wrong, write the right type in correct_event_type (one of the 15 types).",
            "3. For EXEC_CHANGE / DIVIDEND / MERGER_ACQUISITION also check llm_details; if wrong, write corrected JSON in correct_details.",
            "4. Leave correct_* empty when the LLM is right.",
            "5. Rows with qc_flags deserve a closer look (low OCR confidence, missing name/amount, disagreement with title).",
            "6. Rules: signatory is not an entity; 'X in place of Y' = two changes; a board meeting that will *consider* a dividend is BOARD_MEETING.",
            "Event types: " + ", ".join(schema.EVENT_TYPES),
        ]})
        guide.to_excel(xl, sheet_name="guide", index=False)
        ws = xl.sheets["review"]
        widths = {"title": 50, "llm_details": 60, "llm_note": 40, "local_pdf": 30, "pdf_url": 30,
                  "qc_flags": 30, "correct_details": 40, "reviewer_notes": 30}
        for i, c in enumerate(cols, 1):
            ws.column_dimensions[get_column_letter(i)].width = widths.get(c, 14)
            ws.cell(1, i).font = Font(bold=True)
        edit_fill = PatternFill("solid", fgColor="FFF4CC")
        for c in ["correct_event_type", "correct_details", "reviewer_notes"]:
            col = cols.index(c) + 1
            for r in range(1, len(df) + 2):
                ws.cell(r, col).fill = edit_fill
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=False, vertical="top")
        for r in range(2, len(df) + 2):
            cell = ws.cell(r, cols.index("local_pdf") + 1)
            cell.hyperlink = cell.value
            cell.font = Font(color="2A78D6", underline="single")
        ws.freeze_panes = "B2"
        xl.sheets["guide"].column_dimensions["A"].width = 140
    print(f"{len(df)} rows -> {out}")
    print("flag counts:", df["qc_flags"].str.split(", ").explode().value_counts().drop("", errors="ignore").to_dict())


if __name__ == "__main__":
    main()
