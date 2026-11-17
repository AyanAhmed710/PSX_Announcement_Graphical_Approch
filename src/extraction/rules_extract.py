"""Rule-based (regex) detail extraction from announcement text — the baseline.

Fills the same templates as the LLM (see templates.py) for EXEC_CHANGE,
DIVIDEND and MERGER_ACQUISITION. Tuned on the gold dev split only.
"""

from __future__ import annotations

import re

HONORIFIC = r"(?:Mr|Mrs|Ms|Miss|Dr|Syed|Mian|Engr|Prof|Haji|Lt\.?\s*Gen|Maj\.?\s*Gen|Brig)\.?"
NAME = rf"{HONORIFIC}\s+((?:[A-Z][A-Za-z'\-\.]*\s*){{1,5}})"

ROLE_PATTERNS = [
    ("CHAIRMAN", r"chair(?:man|person|woman)"),
    ("CEO", r"chief executive(?: officer)?|\bceo|managing director|president\s*(?:&|and)\s*ceo"),
    ("CFO", r"chief financial officer|\bcfo\b"),
    ("COO", r"chief operating officer|\bcoo\b"),
    ("COMPANY_SECRETARY", r"company secretary"),
    ("HEAD_OF_INTERNAL_AUDIT", r"head of internal audit|chief internal auditor"),
    ("INDEPENDENT_DIRECTOR", r"independent (?:non[- ]executive )?director"),
    ("DIRECTOR", r"\bdirector"),
]
ACTION_PATTERNS = [
    ("RESIGNED", r"resign"),
    ("RETIRED", r"retire"),
    ("DECEASED", r"demise|passed away|death|deceased"),
    ("REMOVED", r"removed|removal"),
    ("APPOINTED", r"appoint|elected|co-?opted|nominated|filled the casual vacancy"),
]


def _first(patterns: list[tuple[str, str]], text: str) -> str | None:
    t = text.lower()
    best = None
    for name, pat in patterns:
        m = re.search(pat, t)
        if m and (best is None or m.start() < best[1]):
            best = (name, m.start())
    return best[0] if best else None


def _nearest(patterns: list[tuple[str, str]], before: str, after: str) -> str | None:
    """Pattern whose match lies closest to the name (end of `before` / start of `after`)."""
    b, a = before.lower(), after.lower()
    best = None
    for name, pat in patterns:
        hits = [len(b) - m.end() for m in re.finditer(pat, b)] + [m.start() for m in re.finditer(pat, a)]
        if hits and (best is None or min(hits) < best[1]):
            best = (name, min(hits))
    return best[0] if best else None


def _clean_name(raw: str) -> str:
    words = raw.strip().split()
    stop = {"As", "The", "Has", "Have", "With", "In", "On", "From", "Who", "Was", "Is", "And", "To", "Of",
            "Mr", "Mrs", "Ms", "Dr", "Syed", "Mian"}
    out = []
    for w in words:
        if w.strip(".,") in stop:
            break
        out.append(w.strip(".,"))
    return " ".join(out)


SIGN_OFF = re.compile(r"yours|sincerely|faithfully|regards|thanking you", re.I)
WINDOW = 160


def _flatten(text: str) -> str:
    """One line; split OCR-glued CamelCase words ("NaeemMukhtar") and "Mr.Name"."""
    t = re.sub(r"\s+", " ", text)
    t = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", t)
    return re.sub(rf"({HONORIFIC})(?=[A-Z])", r"\1 ", t)


def extract_exec(text: str) -> dict:
    # OCR breaks sentences across lines, so look for the action/role in a
    # character window around each honorific-led name instead of per sentence
    t = _flatten(text)
    sign_off = SIGN_OFF.search(t)
    cutoff = sign_off.start() if sign_off else len(t)
    changes = []
    for m in re.finditer(NAME, t):
        if m.start() >= cutoff:  # signatory block
            break
        name = _clean_name(m.group(1))
        if len(name.split()) < 2:
            continue
        before = t[max(0, m.start() - WINDOW):m.start()]
        after = t[m.end():m.end() + WINDOW]
        action = _nearest(ACTION_PATTERNS + [("REMOVED", r"ceased")], before, after)
        if not action:
            continue
        role = _nearest(ROLE_PATTERNS, before, after) or "OTHER"
        # "X appointed ... in place of Y": the name right after "in place of" left
        if re.search(r"in place of\s*$|replac\w*\s*$", before[-40:], re.I):
            action = "RESIGNED"
        changes.append({"person": name, "role": role, "action": action})
    # de-duplicate by person
    seen, uniq = set(), []
    for c in changes:
        k = c["person"].lower()
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return {"changes": uniq}


AMOUNT_RS = r"(?:Rs\.?|PKR|Rupees?)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:/-)?\s*(?:per share|/share)?"
PCT = r"([0-9]+(?:\.[0-9]+)?)\s*%"


def extract_dividend(text: str) -> dict:
    t = text
    low = t.lower()
    kind = "BONUS" if re.search(r"bonus", low) and not re.search(r"cash dividend", low) else \
        ("SPECIE" if "specie" in low else "CASH")
    period = "FINAL" if re.search(r"final (?:cash )?dividend", low) else \
        ("INTERIM" if "interim" in low else None)
    out = {"kind": kind, "amount": None, "unit": None, "period": period,
           "interim_number": None, "fiscal_year": None}
    if kind == "BONUS":
        m = re.search(r"bonus[^.%]{0,60}?" + PCT, t, re.I) or re.search(PCT + r"[^.]{0,40}bonus", t, re.I)
        if m:
            out.update(amount=float(m.group(1)), unit="PERCENT")
    else:
        m = re.search(AMOUNT_RS, t, re.I)
        if m:
            out.update(amount=float(m.group(1)), unit="RS_PER_SHARE")
        else:
            m = re.search(r"dividend[^.]{0,80}?" + PCT, t, re.I)
            if m:
                out.update(amount=float(m.group(1)), unit="PERCENT")
    m = re.search(r"\b(1st|2nd|3rd|first|second|third)\s+interim", low)
    if m:
        out["interim_number"] = {"1st": 1, "first": 1, "2nd": 2, "second": 2, "3rd": 3, "third": 3}[m.group(1)]
    # OCR often drops spaces ("yearendingDecember31,2026"), so allow none
    flat = re.sub(r"\s+", " ", t)
    m = (re.search(r"(?:year|period)\s*end(?:ed|ing)\D{0,30}?(?:\d{1,2}\D{0,12}?)?(20\d\d)", flat, re.I)
         or re.search(r"\b(20\d\d)\s*[-/]\s*(\d\d)\b", flat)
         or re.search(r"dividend[,\s]*(?:for\s*)?(20\d\d)", flat, re.I))
    if m:
        y = int(m.group(1))
        if m.lastindex == 2:  # "2022-23" -> fiscal year ends in 2023
            y += 1
        out["fiscal_year"] = y
    return out


COMPANY = r"((?:[A-Z][A-Za-z&\.\-']*\s+){1,7}(?:Limited|Ltd\.?|\(Private\) Limited|\(Pvt\.?\) Ltd\.?|Corporation|Company))"
NOT_COUNTERPARTY = re.compile(r"stock exchange|securities|depository|share registrar|registrar services|"
                              r"commission|bank limited|habib limited|topline|associates", re.I)
DEAL_WORDS = r"acqui|merg|amalgamat|shares of|stake in|offer|target|takeover|with and into"


def _company_key(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())[:8]


def extract_merger(text: str, issuer: str | None = None) -> dict:
    low = text.lower()
    if re.search(r"\bmerg|amalgamation", low):  # G2b: merger even via a scheme
        kind = "MERGER"
    elif "scheme of arrangement" in low:
        kind = "SCHEME_OF_ARRANGEMENT"
    elif re.search(r"divest|disposal|sale of (?:its|the) (?:entire )?(?:shareholding|stake)", low):
        kind = "DISPOSAL"
    elif "acqui" in low:
        kind = "ACQUISITION"
    else:
        kind = None
    # counterparty = the company name closest to a deal word, other than the
    # issuer itself and the regulators/intermediaries every letter mentions
    flat = _flatten(text)
    deals = [m.start() for m in re.finditer(DEAL_WORDS, flat, re.I)]
    own = _company_key(issuer) if issuer else None
    counterparty, best = None, None
    for m in re.finditer(COMPANY, flat):
        name = m.group(1).strip()
        if NOT_COUNTERPARTY.search(name) or (own and _company_key(name) == own):
            continue
        if not deals:
            break
        dist = min(abs(m.start() - d) for d in deals)
        if dist <= 300 and (best is None or dist < best):
            counterparty, best = name, dist
    stake = None
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:of the\s+)?(?:issued|paid|share|stake|shareholding|equity)", text, re.I)
    if m:
        stake = float(m.group(1))
    return {"counterparty": counterparty, "kind": kind, "stake_pct": stake}


def extract_details(event_type: str, text: str, issuer: str | None = None) -> dict | None:
    if event_type == "EXEC_CHANGE":
        return extract_exec(text)
    if event_type == "DIVIDEND":
        return extract_dividend(text)
    if event_type == "MERGER_ACQUISITION":
        return extract_merger(text, issuer)
    return None
