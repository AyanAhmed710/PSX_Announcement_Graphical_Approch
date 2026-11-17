# PSX Temporal Knowledge Graph — Team Briefing

Group 4. Status as of 2026-11-17. Covers everything decided so far, up to the
gold set (OCR → LLM labels → human check). Detail lives in `APPROACH.md`
(design) and `PROGRESS.md` (log).

**One-line summary:** we scraped every PSX announcement since 2018, narrowed the
work to the 100 KSE-100 companies, used EDA to fix a 15-type event schema (9
classes for forecasting), and built a 400-document gold set (OCR'd, LLM-labelled).
**The remaining step is human verification of those 400 labels.**

---

## 1. What the project must deliver (from the brief)

| Requirement | Our answer |
|---|---|
| Extract companies, executives, dividends, mergers, other events from PSX filings | Event type for every announcement; person / dividend / merger details for 3 entity types |
| Time-aware knowledge graph | Quadruples `(head, relation, tail, date)` |
| Temporal graph model predicting the next event | RE-GCN / TGN-style model over the quadruples |
| Compare with frequency baseline and text-only model | Per-company frequency + seasonality; classifier over recent titles |
| Strict time split | train ≤ T1 < valid ≤ T2 < test, by announcement date |
| Metrics | Extraction F1, MRR, Hits@k, forecasting macro-F1 — each per event type |
| Stretch | Do graph features improve a volatility model? |

---

## 2. Data collection (done)

Source: PSX Data Portal (dps.psx.com.pk). We reverse-engineered its internal API:

- Every page embeds a token (`window.__ps._k`) that must be sent back as an
  `X-Req-Id` header, with browser-like headers, or the server refuses.
- The server returns at most **100 rows per request** whatever you ask for, so we
  paginate using the "of N entries" total. (Our first scrape missed this and only
  got the newest ~100 per company; fixed and re-scraped — e.g. HBL went 86 → 1,009.)
- The server ignores the date filter; we cut to 2018+ ourselves.

| Dataset | Size |
|---|---|
| All listed instruments | 1,060 |
| All announcements 2018 → today | 125,115 (667 companies) → 123,641 after cleaning |
| **KSE-100 announcements** (working set) | 30,941 → **30,325 after cleaning** |
| KSE-100 announcements with a PDF | 26,729 |

Cleaning removed ~1.4k exact duplicates (portal reposts) and ~100 junk "View PDF" rows.

---

## 3. EDA — what we found (EDA/01 full, EDA/02 KSE-100 notebooks)

1. **Severe class imbalance.** FINANCIAL_RESULT ≈ 30% of announcements; mergers
   0.3%, buybacks 0.1%. In KSE-100 there are only 63 mergers, 25 buybacks,
   18 credit ratings.
2. **Titles are very informative.** A keyword tagger on the title alone assigns a
   type to ~88% of announcements → a strong, almost free baseline.
3. **Dense event streams.** Median gap between a company's consecutive
   announcements is 5–6 days; ~4 events per company per month → enough history
   for sequence/graph forecasting.
4. **Event mix is stable 2019–2026.** 2018 titles are formatted differently
   (OTHER spikes) → train from 2019 or normalise 2018 titles.
5. **Strong quarterly seasonality.** Results and board meetings cluster in
   Feb / Apr / Aug / Oct → the frequency baseline will be hard to beat; we report
   the comparison honestly either way.
6. **Data quality.** Duplicates and junk rows (cleaned); 11% of announcements
   have no PDF.
7. **PDFs (gold sample).** 73% are image scans (need OCR); 67% are 1–2 pages,
   but some run to 200+ pages (annual reports) → we cap pages read.

---

## 4. Decisions we finalised (and why)

| Decision | Why |
|---|---|
| **Scope = KSE-100 only** (100 companies, 2018+) | Dense histories, manageable PDF volume (all ~27k PDFs ≈ 13 GB). Full dataset stays on disk, unused. |
| **15 fine-grained event types** for extraction + graph | Brief asks for per-type reporting and names mergers explicitly — we group, never drop. |
| **11 forecast classes**: the 10 big categories (each ≥ 4% of announcements) individual; the low-frequency tail — BUYBACK, BOOK_CLOSURE, MERGER_ACQUISITION, RIGHTS_ISSUE, CREDIT_RATING (2.8% together) → `RARE_EVENT` | Test window holds only a handful of each rare type; macro-F1 weighs every class equally, so tiny classes would be noise. |
| Rare types stay **distinct in the graph**, grouped **only in the forecast target** | A merger edge is one of the few company↔company links; graph is never modified, the target is mapped at the end. |
| **Use entities, not titles only** | Without person names there are no Person nodes, without counterparties no company–company links → the "graph" model would collapse into a per-company sequence model. |
| Entities extracted for **3 types only**: EXEC_CHANGE, DIVIDEND, MERGER_ACQUISITION | These carry the brief's "executives, dividends, mergers". Other types need only company + date (from portal metadata). |
| **Page reading**: page 1 always; pages 2–3 (5 for mergers) only for entity candidates or a near-empty page 1 | The key facts are on the cover letter; avoids reading 200-page annual reports. |
| Non-entity types use the **title only** | Title tagger v2 gets test macro-F1 0.884 and agrees with the LLM on 90% of docs; avoids OCR of ~27k PDFs. |
| **LLM extracts all entity details**; no regex field rules | Rules measured once: fine for dividends but executive names F1 ≈ 0.6 and merger counterparties F1 0.36. The LLM reads context. |
| **"Material Information" titles go to OCR** (page 1 → LLM type → if entity, read to page 5) | 1,324 KSE-100 titles say only "Material Information" and hide mergers and exec changes; title merger recall is only 0.60. |

**The 15 types** (share of KSE-100 announcements, tagger v2):

| Big categories, individual forecast classes | Low-frequency tail, grouped as RARE_EVENT for forecasting |
|---|---|
| BOARD_MEETING 16.2% | BUYBACK 1.1% |
| DISCLOSURE_INTEREST 14.2% | BOOK_CLOSURE 0.9% |
| FINANCIAL_RESULT 12.3% | MERGER_ACQUISITION 0.4% |
| TRANSMISSION_REPORT 10.7% | RIGHTS_ISSUE 0.3% |
| OTHER 10.6% | CREDIT_RATING 0.1% |
| AGM_EGM 9.6% | |
| EXEC_CHANGE 7.8% | |
| DIVIDEND 6.2% | |
| MATERIAL_INFO 5.3% | |
| CORP_BRIEFING 4.3% | |

All 15 stay distinct in the graph. The grouping applies only to the
forecasting target.

### Extraction templates (what we pull from an entity document)

| Type | Fields |
|---|---|
| EXEC_CHANGE | list of `{person, role, action, effective_date}`; role = CEO / CFO / CHAIRMAN / DIRECTOR / INDEPENDENT_DIRECTOR / COMPANY_SECRETARY / COO / HEAD_OF_INTERNAL_AUDIT / OTHER; action = APPOINTED / RESIGNED / RETIRED / REMOVED / DECEASED |
| DIVIDEND | kind (CASH / BONUS / SPECIE), amount, unit (Rs per share / %), period (INTERIM / FINAL), interim number, fiscal year, book-closure dates |
| MERGER_ACQUISITION | counterparty (+ symbol if listed), kind (MERGER / ACQUISITION / DISPOSAL / SCHEME_OF_ARRANGEMENT / AMALGAMATION), direction, stake %, stage (INTENT → BOARD_APPROVED → SHAREHOLDER_APPROVED → COURT_SANCTIONED → COMPLETED) |

Rules for PSX letter traps: the signatory (usually Company Secretary) is never an
entity; attendee/director lists ignored; "X in place of Y" = two facts (Y left,
X appointed); a board meeting that will only *consider* a dividend is
BOARD_MEETING; bonus shares = DIVIDEND (kind BONUS); anything not stated = null,
never guessed.

---

## 5. The gold set — how we measure extraction F1

**Sample:** 400 KSE-100 documents, stratified — up to 30 per event type, rare
types take all they have (seed fixed, reproducible).
**Split:** dev 150 / test 250 (stratified). Dev is used to inspect errors and fix
rules; **test is never looked at while tuning — all reported scores come from test.**

**Two levels of labels:**
- Level 1 — event type, for all 400 documents.
- Level 2 — template details, for the EXEC_CHANGE / DIVIDEND / MERGER documents.

**Pipeline:**

1. **Download** the 400 PDFs only.
2. **Text:** embedded PDF text when present (≥ 200 chars), otherwise **OCR**
   (PyMuPDF renders at 200 dpi, RapidOCR reads — local, free, CPU). Page 1 always;
   pages 2–3 (5 for mergers) only for entity-type candidates or when page 1 is
   nearly empty. *(This adaptive rule is a speed-up over the flat 3/5 cap and will
   be disclosed in the report.)*
3. **LLM proposes labels** from the document text: event type (+ template details
   for entity types). It is **not shown the title or the title-tagger's guess**, so
   its label is an independent reading of the content. Written labeling guidelines
   (G1–G8, `data/gold/labeling_guidelines.md`) settle ambiguous cases, e.g. an AGM
   notice that also approves a dividend is AGM_EGM; a director's share dealing is
   DISCLOSURE_INTEREST, not EXEC_CHANGE.
4. **Human verification (us).** Every row checked against the actual PDF in
   `data/gold/gold_review.xlsx`: event type for all 400, type + details for entity
   docs. Corrections go into yellow columns. The corrected sheet = the gold set.
   We also report how often the LLM was right (LLM-vs-human agreement).
5. **Score** against the human-verified gold (`apply_review` → `eval_gold`).

**What we report from it:**

| Metric | How |
|---|---|
| **Event-type extraction F1** | Title tagger and LLM each vs human: precision / recall / F1 per type + macro-F1 (test split) |
| **Entity extraction F1** | LLM vs human per field (person, role, action, amount, counterparty, …). TP / FP / FN are summed across all docs of a type (micro). Names count as equal after normalisation ("Mr. Ghias Khan" = "Ghias Khan"). |
| **Three-way agreement** | Title vs LLM vs human per document. All three agreeing means a very reliable label. Now: title = LLM on 90.7%. |
| Title **recall** on the 3 entity types | Decides which PDFs get routed to OCR |
| OCR word recall | Share of words recovered vs embedded PDF text (median 97.2%) |

**Quality control:**
- OCR word recall on PDFs that also have embedded text.
- Automatic per-doc flags: low OCR confidence (< 0.85), appointment title with no name in the text, dividend with no amount, LLM disagreeing with the title. Flagged rows get a closer look.
- Errors are attributed to OCR vs extraction.
- Finding: where the score is low, the PDF's own embedded text layer is usually *worse* than our OCR ("Altied Bank" vs our "Allied Bank").
- Known limitation: OCR reads English only; Urdu is ignored.

### 5b. Gold-set results so far (provisional — reference = LLM labels until review)

| Result (test split, 250 docs) | Value |
|---|---|
| Title tagger v2 (rules from dev errors only): accuracy / macro-F1 | **0.896 / 0.884** (v1: 0.796 / 0.788) |
| Forecast classes (11) macro-F1 | 0.875 |
| Title recall: exec change / dividend / merger | 0.89 / 0.89 / **0.60** |
| OCR word recall (median) | 0.972 |

Full detail: `GOLD_SET_REPORT.md`.

### 5c. Scale-up routing (agreed)

```
30,325 KSE-100 announcements
 ├─ title clearly non-entity (results, AGM, board meeting, …)  → event type from title only
 ├─ title = EXEC_CHANGE / DIVIDEND / MERGER (~3.8k docs)       → OCR + LLM extracts entities
 └─ title = bare "Material Information" (~1.3k docs)           → OCR page 1 → LLM decides type
                                                                  → if entity type: read to page 5 + extract
```

---

## 6. Knowledge graph (next phase, design fixed)

- Quadruples, e.g. `(HBL, declares, CASH_DIVIDEND, 2024-02-10)`,
  `(Person:X, appointed_as_CEO, ENGRO, 2021-03-01)`, `(CompanyA, merges_with, CompanyB, 2023-05-12)`.
- Nodes: Company, Person, Sector, EventType.
- **Entity resolution** links documents: names normalised (strip Mr./Dr./Syed,
  fuzzy match). Same person at two companies → the companies become connected
  (interlocking directorates are common in Pakistani business groups). Common
  names are merged only with supporting context (same company/group/role history).
- Two dates kept: **announcement date** (used for the time split — prevents
  leakage) and **effective date** (attribute).

---

## 7. Where we are now

| Step | Status |
|---|---|
| Scraping, cleaning, KSE-100 subset | Done |
| EDA (2 notebooks) | Done |
| Schema, templates, guidelines | Done |
| Gold sample (400 PDFs) downloaded, dev/test split | Done |
| OCR of the 400 | Done |
| LLM label proposals (type + entity details) | Done, 400/400 |
| Title tagger v2 + provisional evaluation + report | Done (`GOLD_SET_REPORT.md`) |
| Review sheet → **human verification by the team** | **Next — our task** |
| Final evaluation (LLM type + entity F1, 3-way agreement) | After review (one command) |
| Scale-up: OCR + LLM on ~5.1k docs | After that |
| Graph build, models, baselines, metrics | After that |

**What the team needs to do next:**
1. Split the 400 rows of `data/gold/gold_review.xlsx`. Start with the 83 flagged rows (LLM ≠ title) and the 64 medium-confidence labels.
2. Open each PDF (the `local_pdf` link). If the LLM is right, leave the yellow columns empty.
3. If the type is wrong, write the correct one in `correct_event_type`.
4. For exec-change / dividend / merger rows, check the details. If they're wrong, put corrected JSON in `correct_details`. **Add anything the LLM missed** (needed for recall). Remove wrong values.
5. When done: `python -m src.extraction.apply_review`, then `python -m src.eval.eval_gold`.

Open question for the team: is buying an oil/gas **working interest** in a block a MERGER_ACQUISITION or MATERIAL_INFO? (Currently labelled MATERIAL_INFO.)

---

## 8. Likely evaluator questions — short answers

- **Why only KSE-100?** Densest histories, most market-relevant companies, and a
  PDF volume we can actually process; the full 667-company data is kept.
- **Why group rare events?** Too few test examples for a meaningful per-class
  F1; they stay distinct in the graph and are reported in an appendix table.
- **Isn't LLM labeling circular?** The LLM only *proposes*; humans verify every
  row against the PDF, and we report LLM-vs-human agreement. The LLM never sees
  the title tagger's output.
- **Why not OCR every PDF?** ~27k PDFs ≈ 13 GB; titles already identify most
  event types. The gold set measures whether that shortcut is safe before we take it.
- **How do you avoid tuning on the test set?** Fixed dev/test split; rules are
  improved on dev only; reported numbers come from test.
- **How is time leakage prevented?** Split by announcement date; vocabularies,
  statistics and baselines fitted on the training period only.
- **How do you know OCR is accurate?** Word recall against embedded PDF text
  (median 97.2%), confidence flags, and per-error attribution to OCR vs extraction.
  Raw character error rate is misleading because OCR reads lines in a different
  order and glues words.
- **Why not use the title as ground truth?** The title tagger is one of the
  systems being tested, so it can't also be the judge. Many titles ("Material
  Information", "Corporate Announcement") don't reveal the event at all.
- **Why an LLM instead of regex for entities?** Measured: regex reaches F1 ≈ 0.9
  on dividends but only ≈ 0.6 on executive names and 0.36 on merger
  counterparties.
