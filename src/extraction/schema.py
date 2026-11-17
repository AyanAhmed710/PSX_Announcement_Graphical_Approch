"""Event schema for the PSX temporal knowledge graph.

Two levels:
- EVENT_TYPES: fine-grained labels used for extraction and stored in the KG.
- FORECAST_CLASS: grouping used by the next-event forecasting task. Classes with
  enough support (>=~3% of announcements) stay individual; scarce corporate
  actions share one RARE_EVENT class. Nothing is dropped from the graph.
"""

from __future__ import annotations

import re

# fine-grained extraction labels -> regex over announcement titles (lowercased)
EVENT_PATTERNS: list[tuple[str, str]] = [
    ("FINANCIAL_RESULT", r"financial result|quarterly report|annual report|half yearly|accounts for"),
    ("BOARD_MEETING", r"board meeting"),
    ("DIVIDEND", r"dividend"),
    ("AGM_EGM", r"annual general meeting|extraordinary general meeting|\bagm\b|\begm\b|general meeting"),
    ("EXEC_CHANGE", r"appointment|resignation|casual vacancy|chief executive|director|company secretary|\bcfo\b|change of management|change of chairman"),
    ("CORP_BRIEFING", r"corporate briefing|analyst briefing"),
    ("MERGER_ACQUISITION", r"merger|amalgamation|acquisition|scheme of arrangement|takeover"),
    ("RIGHTS_ISSUE", r"right issue|rights issue|right shares"),
    ("BUYBACK", r"buy back|buyback|repurchase"),
    ("CREDIT_RATING", r"credit rating|rating report|entity rating"),
    ("DISCLOSURE_INTEREST", r"disclosure of interest|substantial shareholder|free float"),
    ("BOOK_CLOSURE", r"book closure|closed period|register of members"),
    ("MATERIAL_INFO", r"material information|price sensitive"),
    ("TRANSMISSION_REPORT", r"transmission of"),
]

EVENT_TYPES = [name for name, _ in EVENT_PATTERNS] + ["OTHER"]

# frozen copy of the first tagger, kept so its gold-set score stays reproducible
EVENT_PATTERNS_V1 = list(EVENT_PATTERNS)

# tagger v2: checked before EVENT_PATTERNS. Derived from errors on the gold dev
# split only (never the test split) - see data/gold/eval_results.json.
PRIORITY_PATTERNS_V2: list[tuple[str, str]] = [
    ("TRANSMISSION_REPORT", r"transmission of"),
    ("BOARD_MEETING", r"other than financial result"),
    ("BUYBACK", r"buy-back|purchase of (?:its )?own shares"),
    ("DISCLOSURE_INTEREST", r"disclosure of interest|section 110|intimation for (?:purchase|sale) of shares"),
    ("BOOK_CLOSURE", r"book closure under regulation 9"),
    ("MERGER_ACQUISITION", r"public announcement of (?:offer|intention)"),
    ("AGM_EGM", r"notice of election of directors|section 159"),
]

_COMPILED = [(name, re.compile(pat)) for name, pat in PRIORITY_PATTERNS_V2 + EVENT_PATTERNS]
_COMPILED_V1 = [(name, re.compile(pat)) for name, pat in EVENT_PATTERNS_V1]

# forecasting task: the big categories stay individual, the low-frequency tail
# (each <= ~1% of KSE-100 announcements under tagger v2) is grouped
RARE_TYPES = {
    "MERGER_ACQUISITION",
    "RIGHTS_ISSUE",
    "BUYBACK",
    "CREDIT_RATING",
    "BOOK_CLOSURE",
}

FORECAST_CLASSES = [
    "BOARD_MEETING",
    "DISCLOSURE_INTEREST",
    "FINANCIAL_RESULT",
    "TRANSMISSION_REPORT",
    "AGM_EGM",
    "EXEC_CHANGE",
    "DIVIDEND",
    "MATERIAL_INFO",
    "CORP_BRIEFING",
    "RARE_EVENT",
    "OTHER",
]


def tag_event(title: str) -> str:
    """Rule-based event type from an announcement title (the baseline extractor)."""
    t = str(title).lower()
    for name, rx in _COMPILED:
        if rx.search(t):
            return name
    return "OTHER"


def tag_event_v1(title: str) -> str:
    t = str(title).lower()
    for name, rx in _COMPILED_V1:
        if rx.search(t):
            return name
    return "OTHER"


def forecast_class(event_type: str) -> str:
    return "RARE_EVENT" if event_type in RARE_TYPES else event_type
