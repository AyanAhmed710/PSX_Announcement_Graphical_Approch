# PSX Temporal Knowledge Graph — Progress Log

Project plan: see [PLAN.md](PLAN.md). This file records what has actually been
done, the decisions made, and why.

## Phase 0 — Data Collection ✅ (2026-11-16/17)

### Scraping the PSX Data Portal (dps.psx.com.pk)

Reverse-engineered the portal's internal API from its `static/script.js`:

- Every page embeds a token `window.__ps._k`; all XHR calls must send it back
  as the `X-Req-Id` header, plus browser-like headers
  (Referer/Origin/X-Requested-With) or the server returns 404/403.
- `POST /announcements` (form: `type=C, symbol, count, offset, date_from, date_to, page=annc`)
  returns a server-rendered HTML table → parsed with BeautifulSoup.
- `GET /symbols` → JSON of all 1060 listed instruments (equities + TFCs + ETFs).
- `GET /indices/KSE100` → HTML table of current KSE-100 constituents.

Gotchas discovered (cost one re-scrape):
- The server **caps every page at 100 rows** regardless of `count` — pagination
  must use the "Showing X to Y of **N** entries" total, not batch size.
- The server **ignores `date_from`** — raw files hold full history (back to
  ~2005); the 2018+ cut is applied at export time.
- Announcement titles may carry no text cell ("View PDF" artifact rows, ~100)
  and the portal reposts some announcements (exact symbol+date+title dupes).

Code: `src/scraping/psx_client.py` (token handling, 1 req/s rate limit, retry),
`scrape_announcements.py` (crawl + resume + `--full` one-shot mode),
`export_csv.py`, `make_subset.py`.

### Datasets produced

| File | Contents |
|---|---|
| `data/announcements.csv` | 125,115 announcements, 2018→today, 667 active companies |
| `data/companies_1.csv` | 1060 listed instruments with name/sector/flags |
| `data/kse100_symbols.json` | current 100 KSE-100 constituents |
| `data/announcements_kse100.csv` | 30,941 announcements for the KSE-100 |
| `data/raw/announcements/*.jsonl` | full per-company history (source of truth) |

Scope decision: **KSE-100 = core working set** (dense histories, manageable PDF
volume); the full 667-company set is kept for rare event types. All ~27k PDFs
would be ~13 GB — PDFs are downloaded **selectively** instead (see gold sample).

## EDA ✅ (`EDA/` notebooks, executed with charts)

- `EDA/01_announcements_full_eda.ipynb` — full dataset
- `EDA/02_announcements_kse100_eda.ipynb` — KSE-100 subset

Key findings that shaped the design:

1. **Severe class imbalance**: FINANCIAL_RESULT ≈30%, …, MERGER 0.3%, BUYBACK
   0.1%. KSE-100 alone has only 63 mergers / 25 buybacks → rare types must be
   evaluated on the full dataset.
2. **Keyword tagger covers ~88% of titles** after adding CORP_BRIEFING and
   chairman/management patterns → strong, nearly-free baseline extractor.
3. **Dense event streams**: median gap between a company's consecutive events
   is 5–6 days; ~4 events per company-month in KSE-100 → good for forecasting.
4. **Event mix stable 2019–2026**; 2018 titles formatted differently (OTHER
   spikes) → consider 2019+ training window or normalize 2018 titles.
5. Quarterly seasonality (results/board meetings cluster Feb/Apr/Aug/Oct) →
   frequency baseline will be strong; honest comparison required.
6. Data quality: ~1.4k exact duplicates, ~100 junk titles (both cleaned in
   processed files), 11% of announcements are image-only (no PDF).

## Phase 1 — Information Extraction (in progress)

### Event schema (`src/extraction/schema.py`)

Two levels (decision: **group, don't drop**, since the brief names mergers
explicitly and requires per-type reporting):

- **15 fine-grained `EVENT_TYPES`** for extraction and the knowledge graph
  (FINANCIAL_RESULT, BOARD_MEETING, DIVIDEND, AGM_EGM, EXEC_CHANGE,
  CORP_BRIEFING, MERGER_ACQUISITION, RIGHTS_ISSUE, BUYBACK, CREDIT_RATING,
  DISCLOSURE_INTEREST, BOOK_CLOSURE, MATERIAL_INFO, TRANSMISSION_REPORT, OTHER).
- **9 `FORECAST_CLASSES`** for next-event prediction: the 7 types with ≥~3%
  support stay individual; the scarce corporate-action types share one
  `RARE_EVENT` class; plus OTHER. *Revised 2026-11-17 to 11 classes (10 big
  categories + RARE_EVENT of BUYBACK, BOOK_CLOSURE, MERGER, RIGHTS, CREDIT_RATING)
  after tagger v2 showed DISCLOSURE_INTEREST (14%) and TRANSMISSION_REPORT (11%)
  are not rare.*

### Tagged event streams (`src/extraction/tag_events.py`)

- `data/processed/events.csv` — 123,641 rows (cleaned, tagged)
- `data/processed/events_kse100.csv` — 30,325 rows

### Gold annotation sample (`src/extraction/make_gold_sample.py`)

For extraction F1 we need ground truth. Protocol (model-assisted annotation):

1. Stratified sample: up to 30 **KSE-100** docs per fine-grained event type
   (rare types take all they have) → `data/gold/gold_sample.csv`.
   Decision 2026-11-17: KSE-100 only, the full dataset is not used.
2. Download **only those** PDFs (~400 docs, a few hundred MB, not 13 GB)
   → `data/gold/pdfs/`. Gold labels = event type + key arguments for
   EXEC_CHANGE / DIVIDEND / MERGER (see [APPROACH.md](APPROACH.md)).
3. LLM reads each PDF and proposes labels: event type + entities (company,
   person, role, amounts, dates) + relations.
4. Human review/correction of the proposals → gold set.
5. Extractors (rule baseline vs LLM) scored against it: per-type P/R/F1.

### Gold set built (2026-11-17) — see [GOLD_SET_REPORT.md](GOLD_SET_REPORT.md)

- 400/400 PDFs text-extracted (OCR for 336 scanned/mixed docs; median OCR word recall 97.2%).
- 400/400 LLM label proposals (type + template details); review sheet `data/gold/gold_review.xlsx`.
- Title tagger v2 (rules from dev errors only): test macro-F1 0.884 (v1 0.788).
- Decision: LLM extracts all entity details; regex field rules dropped (kept as an appendix baseline).
- Next: human review → `python -m src.extraction.apply_review` → `python -m src.eval.eval_gold`.

## How each project requirement is met

| Requirement | How |
|---|---|
| Extraction F1 | gold set protocol above; rule tagger vs LLM extractor |
| MRR / Hits@k | time-aware link prediction on the KG quadruples |
| Forecasting macro-F1 per event type | 11 forecast classes; rare types reported within RARE_EVENT + discussed |
| Strict temporal split | all events dated; train ≤ T1 < valid ≤ T2 < test; vocab/stats from train only |
| Baselines | per-company frequency+seasonality prior; text-only classifier over recent titles |
| Stretch: volatility | portal `/historical` OHLCV endpoint identified, not yet scraped |

## Next steps

1. **Human review** of `data/gold/gold_review.xlsx` (team) → `apply_review` → `eval_gold`.
2. Scale-up: OCR + LLM on ~3.8k entity-titled docs + ~1.3k "Material Information"
   docs (page 1 → type → read to page 5 if entity); title v2 labels elsewhere.
3. Entity resolution (names ↔ symbols; person dedup).
4. Build KG quadruples `(head, relation, tail, timestamp)` → Phase 2.
