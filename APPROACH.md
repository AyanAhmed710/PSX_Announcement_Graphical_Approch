# Approach — PSX Temporal Knowledge Graph

How we meet each requirement of the brief, and the decisions behind it.
Progress log: [PROGRESS.md](PROGRESS.md). Original plan: [PLAN.md](PLAN.md).

## Scope

- **Working dataset: KSE-100 only** — the 100 current KSE-100 constituents,
  announcements 2018 → today: `data/processed/events_kse100.csv` (30,325 rows).
- The full 667-company dataset stays on disk but is not used for modeling or
  evaluation.
- PDFs are downloaded **selectively** (gold sample + documents whose details the
  graph needs), never all ~27k.

## Event schema (two levels — group, don't drop)

Defined in `src/extraction/schema.py`.

| Level | Used for | Classes |
|---|---|---|
| 15 fine-grained event types | extraction, knowledge graph | FINANCIAL_RESULT, BOARD_MEETING, DIVIDEND, AGM_EGM, EXEC_CHANGE, CORP_BRIEFING, MATERIAL_INFO, MERGER_ACQUISITION, RIGHTS_ISSUE, BUYBACK, CREDIT_RATING, DISCLOSURE_INTEREST, BOOK_CLOSURE, TRANSMISSION_REPORT, OTHER |
| 11 forecast classes | next-event prediction | the 10 big categories stay individual (BOARD_MEETING, DISCLOSURE_INTEREST, FINANCIAL_RESULT, TRANSMISSION_REPORT, OTHER, AGM_EGM, EXEC_CHANGE, DIVIDEND, MATERIAL_INFO, CORP_BRIEFING — each ≥ 4%); the low-frequency tail (BUYBACK, BOOK_CLOSURE, MERGER_ACQUISITION, RIGHTS_ISSUE, CREDIT_RATING — each ≤ ~1%, 2.8% together) → **RARE_EVENT** |

Rare types are grouped for forecasting only — they remain individual nodes in
the graph and are still reported per type for extraction. Dropping them is not
an option: the brief names mergers explicitly.

## Gold set — what we annotate and why

The brief asks for a pipeline that "extracts companies, **executives,
dividends, mergers** and other events" and to "report **extraction F1**".
Labeling only *which event type a document is* would measure document
classification, which is part of extraction but not all of it. The graph also
needs the details: without executive names there are no person nodes, and
without merger counterparties no company-to-company links — the "graph"
model would collapse into a plain per-company sequence model.

So the gold set has **two levels**, kept deliberately small:

**Level 1 — event type (every document).** One label from the 15 types.

**Level 2 — key arguments (only 3 event types):**

| Event type | Arguments annotated |
|---|---|
| EXEC_CHANGE | person name, role (CEO/CFO/Director/Chairman/Secretary…), action (appointed / resigned / replaced) |
| DIVIDEND | kind (cash / bonus / specie), amount (Rs per share or %), period (interim/final + year) |
| MERGER_ACQUISITION | counterparty company, kind (merger / acquisition / scheme of arrangement), stake % if stated |

All other types carry only the company and the date, which come from the
portal metadata and need no annotation.

**Annotation protocol (model-assisted):**

1. Stratified sample: up to 30 KSE-100 documents per event type, rare types
   take all they have → ~400 docs (`data/gold/gold_sample.csv`).
2. Download only those PDFs (`data/gold/pdfs/`); extract text (PyMuPDF
   embedded text, RapidOCR for scanned pages).
3. An LLM reads each document's content (never the title) and proposes
   Level 1 + Level 2 labels into a review sheet.
4. A human checks and corrects every row → this is the gold set
   (`apply_review` → `gold_labels.jsonl`). The title is only context for the
   reviewer, never the ground truth: the title tagger is a system under test.

**Metrics (agreed):**

- Level 1 (event type): per-type precision / recall / F1 + macro-F1 for the
  title tagger and for the LLM, each against human gold.
- Level 2 (entities): LLM vs human per field; TP / FP / FN summed over all
  documents of a type (micro P / R / F1). Names match after normalisation
  (titles stripped, fuzzy similarity ≥ 0.85).
- Three-way agreement title / LLM / human per document; all three agreeing
  means a highly reliable label, and disagreements show where each source fails.

## Extraction templates — what to pull from a document

The event type decides what is extracted. Each type has a fixed template (a
short list of slots); the LLM receives the document plus only that type's
template, and everything outside it is ignored. A document can mention ten
people — only those filling a slot are kept.

| Event type | Template |
|---|---|
| EXEC_CHANGE | list of `{person, role, action: appointed/resigned/replaced, effective_date}` |
| DIVIDEND | `{kind: cash/bonus/specie, amount, unit: Rs/%, period: interim/final + year}` |
| MERGER_ACQUISITION | `{counterparty, kind: merger/acquisition/scheme, stake_pct}` |
| all others | none (company + date come from portal metadata) |

Template rules for the traps found in PSX letters:

- The **signatory** (usually the Company Secretary, who signs every notice) is
  not an entity unless their own role changed.
- **Attendee / director lists** are ignored; only people whose role *changed*.
- "X **in place of** Y" → two facts: Y resigned, X appointed.
- Several changes in one letter → a list of separate facts.
- An **unlisted counterparty** in a merger becomes a Company node without a symbol.
- Two dates kept: **announcement date** (when the market learned it — used for
  the temporal split, prevents leakage) and **effective date** (stored as an
  attribute).

## Gold-set pipeline and the scale-up decision

1. **OCR** the 400 gold PDFs, local and pip-only (PyMuPDF + RapidOCR, CPU).
   Adaptive reading (a disclosed deviation from the flat 3/5 cap):
   - page 1 always;
   - pages 2–3 (5 for mergers) only for entity candidates or when page 1 has
     < 800 characters.

   This read 588 pages instead of 754. Embedded text is used when a page has
   ≥ 200 characters; otherwise OCR.
2. **LLM proposes** for each doc: the event type (one of 15) and, for
   EXEC_CHANGE / DIVIDEND / MERGER_ACQUISITION, the template details.
   It is not shown the title-tagger label.
3. **Human verifies** against the actual PDF: event type for all 400; type +
   details for entity docs. Corrected sheet = gold.
4. **Split the gold set:** dev ≈150 (used to inspect errors and fix tagger /
   extraction rules) and test ≈250 (never looked at while tuning; all reported
   scores come from here).

Scale-up rule — each decision backed by a test-set number:

| Measured on gold test | Then at scale (100 companies) |
|---|---|
| title-tagger per-class F1 high for non-entity types | event type from title only, no PDFs ✔ (v2 test macro-F1 0.884) |
| title-tagger **recall** high (≥ ~95%) for the 3 entity types | measured 0.89 / 0.89 / 0.60 (exec / dividend / merger) → route "Material Information" titles through OCR too (below) |
| entity details | **LLM** extracts all entity details (decision). Regex field rules were measured once and dropped: dividends F1 ≈ 0.9, executive names ≈ 0.6, merger counterparty 0.36. |

Title tagger v2 = v1 plus 7 priority rules learned from **dev** errors only
(e.g. "transmission of", "disclosure of interest" before "director", buy-back).
Test went from 0.788 to 0.884 macro-F1, so the rules generalise. Any new rule
found during review is validated on dev or on the full title list, never tuned
on test.

Tagger recall matters most: an executive change mislabelled as OTHER is never
OCR'd, so its person is lost from the graph.

### "Material Information" documents — content decides (decision 2026-11-17)

The gold set showed that title recall for mergers is only 0.60, because deals
are filed under generic titles. Of the 30,325 KSE-100 announcements, **1,324
(4.4%) are titled only "Material Information" / "Disclosure of Material
Information"** (1,312 with a PDF, from 96 of the 100 companies). These titles
hide mergers, executive changes, plant shutdowns, lawsuits and expansions; no
title rule can separate them.

Two-step handling for these documents:

1. **OCR page 1 only** and let the LLM classify the event type from content.
2. Then, depending on the result:
   - **not** EXEC_CHANGE / DIVIDEND / MERGER_ACQUISITION → keep the event type
     only (page 1 is enough); no further reading.
   - **one of the 3 entity types** → read on up to **page 5** and extract the
     entity template (people/roles, dividend amounts, merger counterparty).

Cost: ~1,312 page-1 reads (~1 h OCR on a laptop) plus extra pages for the
minority that turn out to be entity events.

Scale-up routing becomes:

```
30,325 announcements
 ├─ title clearly non-entity (results, AGM, board meeting, …)  → title label only
 ├─ title = EXEC_CHANGE / DIVIDEND / MERGER (~3.8k)            → OCR + LLM entities
 └─ title = bare "Material Information" (~1.3k)                → OCR p.1 → LLM type
                                                                  → entity type? read to p.5 + extract
```

## Quality control — knowing what OCR missed

1. **Direct OCR accuracy.** On pages with an embedded text layer, OCR is run
   anyway and compared using **word recall**: the share of embedded words
   found in the OCR, independent of word order. Median 97.2% on 66 pages.
   Raw character error rate is misleading, because OCR reads lines top-to-bottom
   and glues words. On the lowest-scoring pages the embedded layer itself was
   the bad copy (an old scanner OCR).
2. **Automatic flags on every page:** low mean OCR confidence; near-empty page;
   content contradicting the title (appointment with no person name, dividend
   with no Rs/% amount, unparseable date). Flagged docs go to a review list.
3. **End-to-end attribution on gold:** each pipeline error is tagged as an OCR
   error (text misread) or an extraction error (text fine, rule missed) →
   report "extraction F1 = X, of which Y% of errors originate in OCR".

Known limitation: bilingual notices — the OCR model reads English only; the
English part is normally present, Urdu is ignored.

## Knowledge graph

Time-stamped quadruples `(head, relation, tail, date)`, e.g.
`(HBL, declares, CASH_DIVIDEND, 2026-11-10)`,
`(Person:X, appointed_as_CEO, ENGRO, 2024-03-01)`,
`(CompanyA, merges_with, CompanyB, 2023-05-12)`.
Node types: Company, Person, Sector, EventType. All 15 fine-grained event types
stay distinct in the graph.

**Entity resolution — how documents link up.** Each extracted name is
normalised (strip Mr./Dr./Syed/Mian, unify spelling, fuzzy match) and matched to
existing nodes. A match reuses the node, which is what connects documents:

```
2021 ENGRO : "Mr. Ghias Khan appointed as Chief Executive"
2023 ENGRO : "Resignation of Mr. Ghias Khan"
2023 ENGROH: "Appointment of Ghias Khan as Director"

(Ghias Khan) --appointed_CEO-->      ENGRO   [2021]
(Ghias Khan) --resigned-->           ENGRO   [2023]
(Ghias Khan) --appointed_Director--> ENGROH  [2023]   → ENGRO and ENGROH now linked
```

Interlocking directorates are common within Pakistani business groups, so
these person bridges carry real signal. Guard against false merges: two people
with the same common name (e.g. "Muhammad Ali") are merged only with supporting
context — same company, same business group, or a consistent role history.

Scale: the gold set (~30 docs per type) only measures extraction accuracy. The
graph itself is built by running OCR + LLM over:
- all KSE-100 docs that title tagger v2 marks EXEC_CHANGE / DIVIDEND / MERGER:
  3,830 docs (2,074 / 1,626 / 130);
- plus the ~1,312 bare "Material Information" docs (page 1 first, see above).

That is ~5.1k docs in total. Company ranking by index weight is in `data/kse100_weights.csv`
(top 30 = 79% of the index) should scope ever need cutting.

## Why rare events stay distinct in the graph but grouped in forecasting

| Part | Rare types | Reason |
|---|---|---|
| Graph storage | distinct | no cost; a merger edge is one of the few direct company↔company links |
| Link prediction (MRR/Hits@k) | distinct | low support only lowers those relations' own scores; reported per relation |
| Forecast target | grouped → RARE_EVENT | the test window holds only ~3–8 examples of each rare type; macro-F1 weighs every class equally, so near-zero scores on tiny classes would be noise |

The graph is **never modified for training**. The model sees the fine-grained
history (a past merger is useful input); only the prediction target is mapped
through `forecast_class()` at the end:

```
history : BOARD_MEETING → FINANCIAL_RESULT → MERGER_ACQUISITION → EXEC_CHANGE → ?
target  : actual next = BUYBACK → forecast_class("BUYBACK") = RARE_EVENT
```

An appendix table reports the 15-class fine-grained forecast with test-set
counts, to show per-type results and justify the grouping.

## Models and evaluation

| Requirement | How it is met |
|---|---|
| Strict temporal split | train ≤ T1 < validation ≤ T2 < test, by announcement date; vocabularies, normalisation stats and baselines fitted on train only |
| Next-event forecasting | temporal graph model (RE-GCN / TGN style) over the quadruples |
| Frequency baseline | per-company event-type frequency + quarterly seasonality |
| Text-only baseline | classifier over the titles of a company's recent announcements |
| Forecasting macro-F1 | over the 11 forecast classes, reported **per class** |
| MRR / Hits@k | time-aware filtered link prediction on held-out test quadruples |
| Stretch (volatility) | graph features added to a volatility model on daily OHLCV from the portal; research only, not investment advice |

## Status (2026-11-17)

Gold set built: 400/400 OCR'd and LLM-labelled; provisional results in
`GOLD_SET_REPORT.md`. **Remaining before scale-up: human verification of the
400 labels** (`data/gold/gold_review.xlsx` → `apply_review` → `eval_gold`).

Open question for the team: is an oil/gas working-interest farm-in a
MERGER_ACQUISITION or MATERIAL_INFO? Decide during review and add it to the
labeling guidelines.

## Known risks

- 2018 titles are formatted differently (OTHER spikes) → start training in 2019
  or normalise 2018 titles.
- Few true executive changes in the gold set (13; most "Director" titles are
  share-dealing disclosures) → exec-change scores have wide uncertainty;
  consider topping up ~30 docs.
- Rare types are thin in KSE-100 (e.g. 18 credit ratings, 25 buybacks) → their
  per-type scores will have wide uncertainty; reported with counts.
- Quarterly seasonality makes the frequency baseline strong; the comparison is
  reported honestly whichever way it goes.
