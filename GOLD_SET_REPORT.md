# Gold Set Report — PSX Temporal Knowledge Graph (Group 4)

Status as of 2026-11-17. Numbers below come from `data/gold/eval_results.json`
(produced by `python -m src.eval.eval_gold`).

> **Important:** the reference labels used here are **LLM proposals that a human has
> not yet verified**. Every score in this report is provisional. Once the team fills
> in `data/gold/gold_review.xlsx` and the corrections are saved as
> `data/gold/gold_labels.jsonl`, rerunning `eval_gold` replaces all the numbers.
> The pipeline does not change.

---

## 1. Summary

| Question | Answer (provisional, test split, n = 250) |
|---|---|
| How well does the **title alone** give the event type? | Tagger v2: accuracy **0.896**, macro-F1 **0.884** over 15 types (v1 baseline: 0.796 / 0.788) |
| Forecast-class macro-F1 of the title tagger (11 classes) | **0.875** |
| Title recall on the 3 entity types (decides which PDFs to OCR) | EXEC_CHANGE **0.89**, DIVIDEND **0.89**, MERGER_ACQUISITION **0.60**, all below the 0.95 target |
| Title vs LLM agreement on event type | 90.7% of all 400 docs (test 89.6%) |
| Who extracts entity details? | **The LLM**, for all three entity types (team decision; field regex rules dropped) |
| Is OCR accurate enough? | Yes. Median 97.2% of words recovered on pages with a text reference |

**Scale-up decision (§7):**
- Use the title for the event type of non-entity announcements.
- Widen the OCR pool beyond title-tagged entity docs, because merger deals hide under "Material Information" titles.
- The LLM extracts the details of every entity doc.

---

## 2. Sample composition

- **400 KSE-100 announcements**, 2018–2026, stratified by title-tagger type: up to 30 per type, and all available for rare types. Seed 42.
- **Split:** dev 150 / test 250, stratified, seed 7. Rules were tuned **on dev only**, and all reported scores are on test.
- **PDFs:** 400/400 downloaded. 3,456 pages in total; **588 pages actually read** (see §3).

Label distribution after the LLM read the content. It differs from the title-based stratification because titles mislead:

| Event type | LLM labels | dev | test |
|---|---|---|---|
| DISCLOSURE_INTEREST | 47 | 17 | 30 |
| TRANSMISSION_REPORT | 46 | 17 | 29 |
| BOOK_CLOSURE | 31 | 12 | 19 |
| CORP_BRIEFING | 30 | 11 | 19 |
| DIVIDEND | 30 | 11 | 19 |
| BOARD_MEETING | 30 | 11 | 19 |
| AGM_EGM | 30 | 13 | 17 |
| MERGER_ACQUISITION | 28 | 13 | 15 |
| BUYBACK | 27 | 10 | 17 |
| MATERIAL_INFO | 26 | 11 | 15 |
| RIGHTS_ISSUE | 22 | 8 | 14 |
| CREDIT_RATING | 18 | 7 | 11 |
| **EXEC_CHANGE** | **13** | 4 | 9 |
| OTHER | 11 | 2 | 9 |
| FINANCIAL_RESULT | 11 | 3 | 8 |

**Finding:** 30 documents were sampled as "EXEC_CHANGE" by title, but only 13 actually are. Most of the rest are *"Disclosure of Interest by a Director…"* share-dealing filings. EXEC_CHANGE scores therefore rest on very few examples (9 in test). **Recommendation:** top up the gold set with about 30 more true executive-change documents before the final report.

---

## 3. Text extraction & OCR

| Item | Value |
|---|---|
| Text source per doc | OCR 280 · embedded text 64 · mixed 56 |
| Image-only (scanned) PDFs | ~73% of the sample |
| Pages read per doc | 1 page: 300 · 2: 22 · 3: 71 · 4: 4 · 5: 3 |
| Engine | PyMuPDF render at 200 dpi + RapidOCR (ONNX, CPU, local) |
| Mean OCR line confidence (median doc) | 0.975 |
| Run time | about 46 min in total for 400 docs (4–10 worker processes) |

**Deviation from the agreed plan (disclosed):** the plan was a flat cap of 3 pages (5 for mergers). For speed we read **page 1 always**, and pages 2–3 (5 for mergers) only when:
- the title suggests an entity type (EXEC_CHANGE, DIVIDEND or MERGER_ACQUISITION), or
- page 1 has fewer than 800 characters (a cover letter whose content is on the next page).

This read 588 pages instead of 754. Non-entity announcements state their purpose on page 1, so their labels are unaffected.

**OCR accuracy** was measured on 66 page-1s that have both an embedded text layer and OCR:

| Metric | Median |
|---|---|
| Word recall (share of embedded words ≥ 4 letters found in OCR text) | **0.972** (10th percentile 0.880; 68% of pages ≥ 0.95) |
| Character error rate (raw) | 0.258 |
| Character error rate (whitespace removed) | 0.231 |

The raw character error rate overstates the errors, for two reasons:
- OCR reads lines top to bottom, while the embedded text follows the PDF's internal object order.
- OCR often glues words together ("PakistanStockExchange").

Word recall ignores word order and is the fairer measure of whether the information survived. Known limitation: the OCR model reads English only, so Urdu sections are ignored. The English part is normally present.

---

## 4. Labeling protocol

1. **LLM proposals.** The LLM read the OCR or embedded text of every document (first 2,500 characters; 4,000 for mergers). It was **not shown the title or the tagger's guess**, and it assigned one of the 15 types.
2. **Template details** were filled for the three entity types:
   - **EXEC_CHANGE:** `{person, role, action, effective_date}` for each change.
   - **DIVIDEND:** `kind, amount, unit, period, interim_number, fiscal_year, book_closure_from/to`.
   - **MERGER_ACQUISITION:** `counterparty, counterparty_symbol, kind, direction, stake_pct, stage`.
3. Ambiguous cases follow the written guidelines G1–G8 in `data/gold/labeling_guidelines.md`. Examples:
   - A results announcement that also declares a dividend is FINANCIAL_RESULT.
   - A director's share dealing is DISCLOSURE_INTEREST.
   - A merger announced as "material information" is MERGER_ACQUISITION.
   - Values not stated in the document are null and are never guessed.
4. **Confidence:** 336 labels high, 64 medium. Every medium label has a note naming the alternative type.
5. **Human verification (pending):** `data/gold/gold_review.xlsx`, one row per document.
   - Each row has a clickable local PDF, the tagger label, the LLM label, details and note, and QC flags.
   - Yellow columns `correct_event_type`, `correct_details` and `reviewer_notes` are left empty when the LLM is right.
   - Reviewers **add** anything the LLM missed and **remove** wrong values. This is needed so that recall (false negatives) can be measured, not just accuracy.

### Three-way agreement: title, LLM and human

Every document gets up to three independent event-type labels:
- the **title tagger**, from the title only;
- the **LLM**, from the content only, never shown the title;
- the **human reviewer**, from the PDF.

When all three agree, the label is very reliable. Disagreements show where each source fails.

| Agreement | dev | test | all |
|---|---|---|---|
| Title = LLM | 0.927 | 0.896 | **0.907** |
| LLM = human | after review | after review | after review |
| Title = human | after review | after review | after review |
| All three agree | after review | after review | after review |

`eval_gold` also counts the cases where the title and the LLM agree but the human differs. Those are the errors that agreement alone would not catch.

Title rules are improved on **dev** errors and checked on **test** (§5).

### QC flags on the review sheet

| Flag | Rows | Meaning |
|---|---|---|
| LLM_DISAGREES_WITH_TITLE | 83 | LLM type ≠ v1 title tagger; review these first |
| DIVIDEND_WITHOUT_AMOUNT | 3 | dividend title but no Rs/% amount found in text |
| LOW_OCR_CONFIDENCE | 1 | mean OCR confidence < 0.85 |
| APPOINTMENT_WITHOUT_NAME | 1 | appointment/resignation title but no honorific-led name in text |

---

## 5. Event-type extraction (title tagger), test split

Tagger v1 is the original keyword list. **Tagger v2** adds 7 priority rules derived **only from dev-split errors** (`PRIORITY_PATTERNS_V2` in `src/extraction/schema.py`):
- "transmission of" → TRANSMISSION_REPORT
- "board meeting other than financial results" → BOARD_MEETING
- buy-back wording → BUYBACK
- "disclosure of interest" / section 110 → DISCLOSURE_INTEREST
- takeover book closure → BOOK_CLOSURE
- "public announcement of offer/intention" → MERGER_ACQUISITION
- election-of-directors notices → AGM_EGM

| | dev acc | dev macro-F1 | **test acc** | **test macro-F1** |
|---|---|---|---|---|
| Tagger v1 | 0.787 | 0.762 | 0.796 | 0.788 |
| Tagger v2 | 0.927 | 0.896 | **0.896** | **0.884** |

The improvement holds on the untouched test split (+0.10 accuracy, +0.10 macro-F1), so the rules generalise rather than memorise.

Per-type F1 on test (v1 → v2):

| Type | n | v1 F1 | v2 P | v2 R | **v2 F1** |
|---|---|---|---|---|---|
| BUYBACK | 17 | 0.90 | 1.00 | 1.00 | **1.00** |
| CORP_BRIEFING | 19 | 1.00 | 1.00 | 1.00 | **1.00** |
| CREDIT_RATING | 11 | 1.00 | 1.00 | 1.00 | **1.00** |
| FINANCIAL_RESULT | 8 | 0.62 | 1.00 | 1.00 | **1.00** |
| RIGHTS_ISSUE | 14 | 1.00 | 1.00 | 1.00 | **1.00** |
| BOARD_MEETING | 19 | 0.94 | 1.00 | 0.95 | **0.97** |
| BOOK_CLOSURE | 19 | 0.92 | 0.95 | 0.95 | **0.95** |
| TRANSMISSION_REPORT | 29 | 0.77 | 0.96 | 0.93 | **0.95** |
| EXEC_CHANGE | 9 | 0.59 | 1.00 | 0.89 | **0.94** |
| AGM_EGM | 17 | 0.89 | 0.89 | 0.94 | **0.91** |
| DISCLOSURE_INTEREST | 30 | 0.64 | 0.93 | 0.87 | **0.90** |
| DIVIDEND | 19 | 0.90 | 0.90 | 0.90 | **0.90** |
| MATERIAL_INFO | 15 | 0.75 | 0.71 | 0.80 | **0.75** |
| MERGER_ACQUISITION | 15 | 0.58 | 0.64 | 0.60 | **0.62** |
| OTHER | 9 | 0.33 | 0.33 | 0.44 | **0.38** |

Forecast classes (11: 10 big categories + RARE_EVENT), test: accuracy 0.900, **macro-F1 0.875**.

**Remaining confusions (test):**
- MERGER_ACQUISITION ↔ MATERIAL_INFO (3 each way): deals are filed under generic "Material Information" titles.
- Generic titles that only the content can resolve, such as "Corporate Announcement" or "Miscellaneous Information": DIVIDEND ↔ OTHER, TRANSMISSION_REPORT → OTHER.

These are limits of title-only classification, not missing keywords.

---

## 6. Entity extraction (LLM)

**Metric.** For each entity document, the LLM's template details are compared field by field with the human-verified details:
- **TP:** the value is present and correct.
- **FP:** the LLM gave a value that is wrong or extra.
- **FN:** a value is in the document but the LLM missed it or got it wrong.

TP, FP and FN are summed **over all documents of a type** (micro-averaging), and precision, recall and F1 are reported per field. Examples:
- EXEC_CHANGE: person, and person + role + action; changes are matched one-to-one within a document.
- DIVIDEND: kind, amount, unit, period, fiscal year.
- MERGER_ACQUISITION: counterparty, kind, stake %.

Names count as the same after normalisation (Mr./Syed etc. stripped, fuzzy similarity ≥ 0.85), so "Mr. Ghias Khan" = "Ghias Khan". The reviewer also judges equivalent spellings directly.

These numbers become available when `gold_labels.jsonl` exists, as `llm_details_{dev,test,all}` in `eval_results.json`. Until then the LLM labels are the reference, so their score would trivially be 100%.

### Appendix: regex field-rule baseline (measured, then dropped)

The team decided the LLM handles all entity details, so field rules are not part of the pipeline. They were measured once, for comparison only. The rule extractor (`src/extraction/rules_extract.py`) runs on the document text. It was improved on dev only:
- an OCR-robust context window replaces sentence splitting;
- CamelCase de-gluing for OCR-merged words;
- the signatory block is excluded;
- fiscal-year patterns are tolerant of missing spaces;
- the counterparty is the company name nearest a deal word, excluding the issuer and regulators.

Scoring:
- **Precision / recall / F1 per field.** A wrong value counts as a false positive and also a false negative.
- **Names** match after normalisation (titles stripped, Levenshtein similarity ≥ 0.85).
- **Executive changes** are matched one-to-one between gold and predicted lists.

| Type (test docs) | Field | P | R | **F1** |
|---|---|---|---|---|
| DIVIDEND (19) | kind (cash/bonus/specie) | 1.00 | 1.00 | **1.00** |
| | amount | 0.94 | 0.89 | **0.91** |
| | unit (Rs/share, %) | 1.00 | 0.94 | **0.97** |
| | period (interim/final) | 1.00 | 0.94 | **0.97** |
| | fiscal year | 0.80 | 0.86 | **0.83** |
| EXEC_CHANGE (9; 21 changes) | person | 0.85 | 0.52 | **0.65** |
| | person + role + action | 0.69 | 0.43 | **0.53** |
| MERGER_ACQUISITION (15) | kind | 1.00 | 0.93 | **0.97** |
| | stake % | 0.67 | 0.44 | **0.53** |
| | counterparty | 0.38 | 0.33 | **0.36** |

Dev scores for comparison (the rules were tuned here, so these are optimistic):
- dividend fiscal year F1 0.93;
- executive person F1 0.91;
- merger counterparty F1 0.18.

The merger counterparty failed on dev too, so it is a genuine weakness of regex, not over-fitting.

The comparison shows why the LLM is used. Regex handles fixed-format dividend notices well, but executive names (F1 0.53–0.65) and merger counterparties (F1 0.36) need reading comprehension.

---

## 7. Scale-up decision (full KSE-100: 30,325 announcements)

| Measured on test | Threshold | Result | Decision |
|---|---|---|---|
| Title tagger F1, non-entity types | high | 0.75–1.00 (most ≥ 0.90) | **Event type from the title** for non-entity announcements; no PDFs |
| Title recall, EXEC_CHANGE / DIVIDEND | ≥ 0.95 | 0.89 / 0.89 | Slightly below the target, so widen the OCR pool (below) |
| Title recall, MERGER_ACQUISITION | ≥ 0.95 | 0.60 | Clearly below, so deals also hide under "Material Information" |
| LLM entity F1 (after human review) | high | pending | **LLM** extracts details for all entity docs (team decision) |

**OCR pool at scale (tagger v2, KSE-100 announcements with a PDF):**

| Pool | Docs | Pages | Why |
|---|---|---|---|
| Title-tagged entity docs (EXEC 2,074 · DIVIDEND 1,626 · MERGER 130) | 3,830 | ~5.5k | details needed for the graph |
| + bare "Material Information" titles: page 1 → LLM type; if entity type, read to page 5 | 1,312 | ~1.3k + extra | recovers mergers and executive changes hidden under generic titles (decision recorded in APPROACH.md) |
| Optional: + "OTHER" titles (page 1 only) | 3,108 | ~3.1k | generic titles ("Corporate Announcement"); recovers the remaining misses |

The recommended pool is **~5.4k docs and ~7k pages**: about 3–4 hours of OCR on this laptop with 4 workers. A content classifier (or the LLM on page 1) then re-labels the Material-Information docs.

---

## 8. Error attribution: OCR vs extraction

From the dev-set inspection:
- **Extraction errors dominate.** The OCR text contained the correct answer, but the rule did not find it. Causes: names separated from their role by line breaks, words glued together, company names not adjacent to the deal verb.
- **OCR-caused errors are rare but real:**
  - 1 dividend amount was unreadable in a low-quality 2019 newspaper scan (doc 128821, Bank Alfalah);
  - 1 executive letter had its line order scrambled (doc 147591, FFC);
  - 1 quarterly report was almost entirely garbage glyphs (doc 137831, ISL).
- Measured on test after human verification, this becomes a formal split: "extraction F1 = X, of which Y% of errors originate in OCR". It is computed by tagging each error in the review sheet's `reviewer_notes`.

---

## 9. What happens next

1. **Team review** of `gold_review.xlsx` (400 rows; start with the 83 flagged rows and the 64 medium-confidence labels). Leave the yellow columns empty when the LLM is right.
2. Optional: top up ~30 more true EXEC_CHANGE documents (only 13 in the sample).
3. Run `python -m src.extraction.apply_review`, which writes `gold_labels.jsonl`, then `python -m src.eval.eval_gold`. This adds LLM extraction F1 (type and entity fields) and three-way agreement, and re-scores the title tagger against human gold.
4. Run the scale-up (§7):
   - OCR ~5.4k docs;
   - LLM for entity details;
   - title tagger v2 for event types elsewhere.
5. Entity resolution (person-name normalisation and fuzzy matching), then the temporal knowledge graph, models and metrics (MRR, Hits@k, forecasting macro-F1 per class).

---

## 10. Files

| File | Contents |
|---|---|
| `data/gold/gold_sample.csv` | the 400 sampled announcements + dev/test split |
| `data/gold/pdfs/` | the 400 PDFs |
| `data/gold/ocr/*.json` | per-page embedded text, OCR text, confidences |
| `data/gold/gold_text.jsonl` | best text per document (embedded if ≥ 200 chars, else OCR) |
| `data/gold/llm_labels.jsonl` | LLM proposals: type, details, confidence, note |
| `data/gold/labeling_guidelines.md` | rules G1–G8 for ambiguous cases |
| `data/gold/gold_review.xlsx` | **human review sheet** |
| `data/gold/eval_results.json` | all metrics in this report |
| `src/extraction/schema.py` | 15 types, tagger v1 (frozen) and v2 |
| `src/extraction/rules_extract.py` | regex detail extractor (appendix baseline only) |
| `src/extraction/apply_review.py` | reviewed sheet → `gold_labels.jsonl` |
| `src/eval/eval_gold.py` | evaluation script |
