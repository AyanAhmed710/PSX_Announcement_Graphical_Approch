# PSX Temporal Knowledge Graph (Group 4)

Extract companies, executives, dividends, mergers and other events from Pakistan
Stock Exchange (PSX) filings into a time-aware knowledge graph, and forecast the
next likely event for a company with a temporal graph model.

**Status:** data collected (KSE-100, 2018 → today), EDA done, 400-document gold
set OCR'd and LLM-labelled. **Next: human verification of the gold set.**

## Read first

| Doc | What |
|---|---|
| [TEAM_BRIEFING.md](TEAM_BRIEFING.md) | Everything decided so far, in one place |
| [APPROACH.md](APPROACH.md) | Design and the reasons behind it |
| [GOLD_SET_REPORT.md](GOLD_SET_REPORT.md) | Gold-set results (provisional until human review) |
| [PROGRESS.md](PROGRESS.md) | Log of what was done |
| [PLAN.md](PLAN.md) | Original phase plan (APPROACH.md is current where they differ) |

## Setup

```
pip install -r requirements.txt
```

Regenerate the ignored folders:

```
python -m src.scraping.scrape_announcements --full    # data/raw + announcements CSVs (slow, ~1 req/s)
python -m src.extraction.tag_events                   # data/processed/events*.csv
python -m src.extraction.make_gold_sample --download-only   # the 400 gold PDFs -> data/gold/pdfs/
```

## Layout

```
src/scraping/      PSX portal client, scraper, CSV export, KSE-100 subset
src/extraction/    event schema + title tagger, OCR, gold-set tools, review sheet
src/eval/          gold-set evaluation (eval_gold.py)
EDA/               two executed EDA notebooks (all companies, KSE-100)
data/              KSE-100 announcements, symbols, index weights
data/gold/         gold sample, OCR output, LLM labels, review sheet, eval results
```

## Gold-set review (team task)

1. Fetch the PDFs: `python -m src.extraction.make_gold_sample --download-only`
2. Open `data/gold/gold_review.xlsx`. Fill the yellow columns only where the LLM
   label is wrong; for exec-change / dividend / merger rows also fix or complete
   `correct_details` (JSON). Guidelines: `data/gold/labeling_guidelines.md`.
3. `python -m src.extraction.apply_review` → `data/gold/gold_labels.jsonl`
4. `python -m src.eval.eval_gold` → `data/gold/eval_results.json`
