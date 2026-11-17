# PSX Temporal Knowledge Graph — Project Plan

Build a pipeline that extracts companies, executives, dividends, mergers and other
events from Pakistan Stock Exchange (PSX) filings and news, stores them in a
time-aware knowledge graph, and trains a temporal graph model to predict the next
likely event for a company.

> **Status 2026-11-17:** Phase 0 done; Phase 1 gold set built and awaiting
> human verification. Agreed design details live in [APPROACH.md](APPROACH.md),
> results in [GOLD_SET_REPORT.md](GOLD_SET_REPORT.md), and the team summary in
> [TEAM_BRIEFING.md](TEAM_BRIEFING.md). Where this plan and APPROACH.md differ,
> APPROACH.md is current.

## Phase 0 — Data Collection (web scraping)  ✅ done

Result: 125,115 announcements 2018+ (667 companies). **Working set = KSE-100
only**: 30,325 announcements after cleaning. Financial-news scraping (below)
has not been started and is not needed for the brief.

**Sources**
| Source | What | How |
|---|---|---|
| dps.psx.com.pk | Company announcements (title, date, symbol, category, PDF link) | POST `/announcements` API (HTML fragment, needs `X-Req-Id` token scraped from page) |
| dps.psx.com.pk | Symbol list / company metadata | GET `/symbols` (same token) |
| dps.psx.com.pk | Daily OHLCV (for stretch volatility goal) | POST `/historical` / `/timeseries` |
| Announcement PDFs | Full filing text | Download link per announcement, then PDF text extraction |
| Financial news | Business Recorder, Dawn Business, Profit (Pakistan Today) | RSS / archive scraping (phase 0.5) |

**API details discovered (from dps.psx.com.pk/static/script.js):**
- Every page embeds `window.__ps = {..., "_k": "<token>"}`; all XHR calls send it
  as header `X-Req-Id`. Token obtained by fetching any portal page first.
- `POST /announcements` form fields:
  `type` (C = companies), `symbol`, `query`, `count`, `offset`,
  `date_from` (YYYY-MM-DD, "" = all), `date_to`, `page` ("annc").
  Response = server-rendered HTML table → parse with BeautifulSoup.

**Deliverables**
- `src/scraping/psx_client.py` — session with token handling, retry, rate limit
- `src/scraping/scrape_announcements.py` — crawl all symbols × months → JSONL
- `data/raw/announcements/*.jsonl` — one record per announcement with
  `scraped_at`, `symbol`, `date`, `time`, `title`, `category`, `pdf_url`
- PDF downloader + text extractor (PyMuPDF embedded text; RapidOCR for scans)

## Phase 1 — Information Extraction  ← current phase (gold set awaiting human review)

Agreed (supersedes the original draft):
- **Schema:** 15 fine-grained event types for extraction and the graph; 9
  forecast classes: 10 big categories individual, the 5 low-frequency types grouped as RARE_EVENT for prediction only.
- **Entities** for 3 types only, each with a fixed template:
  - EXEC_CHANGE: person / role / action / date;
  - DIVIDEND: kind / amount / period / year;
  - MERGER_ACQUISITION: counterparty / kind / stake / stage.
- **Extractors:**
  - **title tagger** (regex on titles; v2 rules from dev errors) for the event type;
  - **LLM** reading OCR'd content for the event type and all entity details.
  - Regex *field* rules were measured and dropped.
- **Gold set:** 400 KSE-100 docs, stratified, split dev 150 / test 250. The LLM
  proposes and humans verify. Metrics:
  - per-type P / R / F1 + macro-F1;
  - entity P / R / F1 per field, summed over docs;
  - title / LLM / human agreement.
- **Scale-up routing:**
  - clearly non-entity titles: title label only;
  - entity titles (~3.8k): OCR + LLM;
  - bare "Material Information" titles (~1.3k): OCR page 1 → LLM type → if an
    entity type, read to page 5 and extract.

Remaining: human review of `data/gold/gold_review.xlsx`, then the final
evaluation, then the scale-up run.

## Phase 2 — Temporal Knowledge Graph
- Quadruple store: (head, relation, tail, timestamp) + event attributes.
- Storage: plain parquet/JSONL + NetworkX for analysis; optionally Neo4j.
- Entity resolution: company names ↔ symbols (aliases from symbols endpoint),
  person name dedup (fuzzy match within company context).

## Phase 3 — Temporal Graph Model (advanced component)
- Task: given company's history up to time t, predict next event type.
- Models: temporal KG embedding (RE-GCN / TGN-style) vs
  (a) frequency baseline (per-company event-type prior + seasonality),
  (b) text-only model (classifier over recent announcement titles).
- **Strict temporal split**: train ≤ T1 < valid ≤ T2 < test. No future leakage —
  entity vocab, normalization stats, labels all built from train window only.

## Phase 4 — Evaluation
- Extraction: precision/recall/F1 per event type (title tagger and LLM vs
  human gold) and per entity field (LLM vs human gold, summed over docs).
- KG link prediction: MRR, Hits@1/3/10 (time-aware filtered setting).
- Event forecasting: macro-F1, reported **separately per event type**.
- Ablations: graph vs text-only vs frequency.

## Stretch — Volatility experiment
- Features from graph (event counts, embedding deltas) added to GARCH/HAR-style
  volatility model on OHLCV. Research experiment only, not investment advice.

## Repo layout
```
PLAN.md
requirements.txt
src/
  scraping/        # phase 0
  extraction/      # phase 1
  kg/              # phase 2
  models/          # phase 3
  eval/            # phase 4
data/
  raw/             # scraped (gitignored)
  processed/
```
