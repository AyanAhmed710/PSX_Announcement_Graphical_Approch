"""Extraction templates: what the LLM fills for each document.

Every document gets `event_type` (one of the 15 EVENT_TYPES). Only three types
carry a details template; for all others `details` is null.
"""

from __future__ import annotations

TEMPLATES: dict[str, dict] = {
    "EXEC_CHANGE": {
        "changes": [
            {
                "person": "full name without honorifics (Mr./Ms./Dr./Syed/Mian)",
                "role": "CEO | CFO | CHAIRMAN | DIRECTOR | INDEPENDENT_DIRECTOR | COMPANY_SECRETARY | COO | HEAD_OF_INTERNAL_AUDIT | OTHER",
                "action": "APPOINTED | RESIGNED | RETIRED | REMOVED | DECEASED",
                "effective_date": "YYYY-MM-DD or null",
            }
        ]
    },
    "DIVIDEND": {
        "kind": "CASH | BONUS | SPECIE",
        "amount": "number, e.g. 4.5",
        "unit": "RS_PER_SHARE | PERCENT",
        "period": "INTERIM | FINAL",
        "interim_number": "1, 2, 3 or null",
        "fiscal_year": "e.g. 2026 or null",
        "book_closure_from": "YYYY-MM-DD or null",
        "book_closure_to": "YYYY-MM-DD or null",
    },
    "MERGER_ACQUISITION": {
        "counterparty": "other company's name exactly as written",
        "counterparty_symbol": "PSX ticker if listed, else null",
        "kind": "MERGER | ACQUISITION | DISPOSAL | SCHEME_OF_ARRANGEMENT | AMALGAMATION",
        "direction": "ACQUIRER | TARGET | MERGING_PARTY | null",
        "stake_pct": "number or null",
        "stage": "INTENT | BOARD_APPROVED | SHAREHOLDER_APPROVED | COURT_SANCTIONED | COMPLETED | null",
    },
}

RULES = """\
- The signatory of the letter (usually the Company Secretary) is NOT an entity
  unless their own role changes in this document.
- Ignore lists of attendees, existing directors, auditors, and addressees
  (e.g. "General Manager, PSX"). Extract only people whose role CHANGES.
- "X in place of Y" / "X replaces Y" -> two changes: Y RESIGNED, X APPOINTED.
- One letter with several changes -> one entry per change.
- A board meeting that only *will consider* a dividend is BOARD_MEETING,
  not DIVIDEND. DIVIDEND requires a declared/announced/credited payout.
- Bonus shares are DIVIDEND with kind=BONUS, unit=PERCENT.
- If a value is not stated, use null. Never guess.
"""
