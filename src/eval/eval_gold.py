"""Evaluate the title tagger and the rule-based detail extractor on the gold set.

Reference labels: data/gold/llm_labels.jsonl (LLM proposals; replaced by the
human-verified file data/gold/gold_labels.jsonl when it exists).

Usage:
    python -m src.eval.eval_gold
Writes data/gold/eval_results.json (consumed by the report).
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
from rapidfuzz.distance import Levenshtein
from sklearn.metrics import precision_recall_fscore_support

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.extraction import schema  # noqa: E402
from src.extraction.rules_extract import extract_details  # noqa: E402

GOLD = ROOT / "data" / "gold"
ENTITY_TYPES = ["EXEC_CHANGE", "DIVIDEND", "MERGER_ACQUISITION"]


def _load_jsonl(path: Path) -> pd.DataFrame:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    df = pd.DataFrame(rows)
    df["doc_id"] = df["doc_id"].astype(str)
    return df


def load_reference() -> tuple[pd.DataFrame, str]:
    human = GOLD / "gold_labels.jsonl"
    src = human if human.exists() else GOLD / "llm_labels.jsonl"
    return _load_jsonl(src), ("human-verified" if src == human else "LLM proposals (not yet human-verified)")


# ---------------------------------------------------------------- type metrics

def type_metrics(y_true: pd.Series, y_pred: pd.Series) -> dict:
    labels = sorted(set(y_true) | set(y_pred))
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    per = {lab: {"precision": round(pi, 3), "recall": round(ri, 3), "f1": round(fi, 3), "support": int(si)}
           for lab, pi, ri, fi, si in zip(labels, p, r, f, s)}
    present = [lab for lab in labels if per[lab]["support"] > 0]
    return {
        "accuracy": round(float((y_true.values == y_pred.values).mean()), 3),
        "macro_f1": round(sum(per[l]["f1"] for l in present) / len(present), 3),
        "per_class": per,
    }


# ------------------------------------------------------------- detail metrics

def norm_name(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(mr|mrs|ms|miss|dr|syed|sayed|mian|haji|engr|prof)\b\.?", " ", s)
    return " ".join(re.sub(r"[^a-z ]", " ", s).split())


def names_match(a: str | None, b: str | None) -> bool:
    na, nb = norm_name(a), norm_name(b)
    if not na or not nb:
        return False
    return na == nb or Levenshtein.normalized_similarity(na, nb) >= 0.85


def _num(x) -> float | None:
    try:
        return round(float(str(x).replace(",", "")), 4)
    except (TypeError, ValueError):
        return None


def score_fields(gold: dict, pred: dict, fields: list[str], numeric: set[str], namey: set[str]) -> dict:
    out = {}
    for f in fields:
        g, p = (gold or {}).get(f), (pred or {}).get(f)
        g_has, p_has = g not in (None, "", []), p not in (None, "", [])
        if f in numeric:
            ok = g_has and p_has and _num(g) == _num(p)
        elif f in namey:
            ok = g_has and p_has and names_match(g, p)
        else:
            ok = g_has and p_has and str(g).upper() == str(p).upper()
        out[f] = {"tp": int(ok), "fp": int(p_has and not ok), "fn": int(g_has and not ok)}
    return out


def score_exec(gold: dict, pred: dict) -> dict:
    """Match change tuples (person, role, action) one-to-one."""
    g = list((gold or {}).get("changes") or [])
    p = list((pred or {}).get("changes") or [])
    res = {k: {"tp": 0, "fp": 0, "fn": 0} for k in ["person", "person+role+action"]}
    used = set()
    for gi in g:
        hit = None
        for j, pj in enumerate(p):
            if j not in used and names_match(gi.get("person"), pj.get("person")):
                hit = j
                break
        if hit is None:
            res["person"]["fn"] += 1
            res["person+role+action"]["fn"] += 1
            continue
        used.add(hit)
        res["person"]["tp"] += 1
        pj = p[hit]
        full = (str(gi.get("role")).upper() == str(pj.get("role")).upper()
                and str(gi.get("action")).upper() == str(pj.get("action")).upper())
        res["person+role+action"]["tp" if full else "fn"] += 1
        if not full:
            res["person+role+action"]["fp"] += 1
    extra = len(p) - len(used)
    res["person"]["fp"] += extra
    res["person+role+action"]["fp"] += extra
    return res


DETAIL_SPECS = {
    "DIVIDEND": dict(fields=["kind", "amount", "unit", "period", "fiscal_year"],
                     numeric={"amount", "fiscal_year"}, namey=set()),
    "MERGER_ACQUISITION": dict(fields=["counterparty", "kind", "stake_pct"],
                               numeric={"stake_pct"}, namey={"counterparty"}),
}


def prf(c: dict) -> dict:
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3), "tp": tp, "fp": fp, "fn": fn}


def detail_metrics(ref: pd.DataFrame, texts: dict[str, str], issuers: dict[str, str]) -> dict:
    out = {}
    for et in ENTITY_TYPES:
        sub = ref[ref["event_type"] == et]
        agg: dict[str, dict] = {}
        for r in sub.itertuples():
            pred = extract_details(et, texts.get(r.doc_id, ""), issuers.get(r.doc_id))
            if et == "EXEC_CHANGE":
                scores = score_exec(r.details, pred)
            else:
                spec = DETAIL_SPECS[et]
                scores = score_fields(r.details, pred, spec["fields"], spec["numeric"], spec["namey"])
            for k, c in scores.items():
                a = agg.setdefault(k, {"tp": 0, "fp": 0, "fn": 0})
                for m in a:
                    a[m] += c[m]
        out[et] = {"n_docs": len(sub), "fields": {k: prf(c) for k, c in agg.items()}}
    return out


def llm_detail_metrics(gold: pd.DataFrame, llm: pd.DataFrame) -> dict:
    """LLM template details vs human gold, TP/FP/FN summed over all documents."""
    pred = dict(zip(llm["doc_id"], llm["details"]))
    out = {}
    for et in ENTITY_TYPES:
        sub = gold[gold["event_type"] == et]
        agg: dict[str, dict] = {}
        for r in sub.itertuples():
            p = pred.get(r.doc_id)
            if et == "EXEC_CHANGE":
                scores = score_exec(r.details, p)
            else:
                spec = DETAIL_SPECS[et]
                scores = score_fields(r.details, p, spec["fields"], spec["numeric"], spec["namey"])
            for k, c in scores.items():
                a = agg.setdefault(k, {"tp": 0, "fp": 0, "fn": 0})
                for m in a:
                    a[m] += c[m]
        out[et] = {"n_docs": len(sub), "fields": {k: prf(c) for k, c in agg.items()}}
    return out


def agreement(df: pd.DataFrame, has_human: bool) -> dict:
    """How often title tagger, LLM and (when available) human gold agree per document."""
    t, l = df["tagger_v2"], df["llm_type"]
    res = {"title_eq_llm": round(float((t == l).mean()), 3)}
    if has_human:
        g = df["gold_type"]
        res.update({
            "llm_eq_human": round(float((l == g).mean()), 3),
            "title_eq_human": round(float((t == g).mean()), 3),
            "all_three_agree": round(float(((t == l) & (l == g)).mean()), 3),
            "title_and_llm_agree_but_human_differs": int(((t == l) & (l != g)).sum()),
        })
    return res


# ------------------------------------------------------------------ OCR & QC

def ocr_quality() -> dict:
    """OCR vs embedded text on page 1 of PDFs that have both.

    Raw CER is inflated by layout: OCR reads lines top-to-bottom while embedded
    text follows the PDF's internal order, and OCR glues words. So we also
    report CER with whitespace removed and an order-free word recall: the share
    of embedded words (>=4 letters) that appear in the OCR text.
    """
    rows = []
    for f in (GOLD / "ocr").glob("*.json"):
        rec = json.loads(f.read_text(encoding="utf-8"))
        p1 = rec["pages"][0] if rec["pages"] else None
        if not p1 or len(p1["embedded_text"]) < 200 or not p1["ocr_text"]:
            continue
        a = re.sub(r"\s+", " ", p1["embedded_text"]).strip().lower()
        b = re.sub(r"\s+", " ", p1["ocr_text"]).strip().lower()
        a0, b0 = a.replace(" ", ""), b.replace(" ", "")
        words = re.findall(r"[a-z]{4,}", a)
        rows.append({
            "doc_id": rec["doc_id"],
            "cer": Levenshtein.distance(a, b) / max(len(a), 1),
            "cer_nospace": Levenshtein.distance(a0, b0) / max(len(a0), 1),
            "word_recall": sum(w in b0 for w in words) / max(len(words), 1),
        })
    d = pd.DataFrame(rows)
    if d.empty:
        return {"n_pages": 0}
    q = lambda c, x: round(float(d[c].quantile(x)), 4)  # noqa: E731
    return {
        "n_pages": len(d),
        "cer_median": q("cer", 0.5),
        "cer_nospace_median": q("cer_nospace", 0.5),
        "word_recall_median": q("word_recall", 0.5),
        "word_recall_p10": q("word_recall", 0.1),
        "share_word_recall_above_95pct": round(float((d["word_recall"] >= 0.95).mean()), 3),
        "worst": d.sort_values("word_recall").head(5).round(4).to_dict("records"),
    }


def main() -> None:
    sample = pd.read_csv(GOLD / "gold_sample.csv", dtype={"doc_id": str})
    texts_df = pd.read_json(GOLD / "gold_text.jsonl", lines=True, dtype={"doc_id": str})
    texts = dict(zip(texts_df["doc_id"], texts_df["text"]))
    ref, ref_kind = load_reference()

    df = sample.merge(ref[["doc_id", "event_type", "details"]].rename(columns={"event_type": "gold_type"}),
                      on="doc_id", how="inner")
    df["tagger_v1"] = df["title"].map(schema.tag_event_v1)
    df["tagger_v2"] = df["title"].map(schema.tag_event)

    results = {"reference": ref_kind, "n_docs": len(df), "splits": df["split"].value_counts().to_dict()}
    for split in ["dev", "test"]:
        d = df[df["split"] == split]
        results[f"type_{split}_v1"] = type_metrics(d["gold_type"], d["tagger_v1"])
        results[f"type_{split}_v2"] = type_metrics(d["gold_type"], d["tagger_v2"])
        results[f"forecast_{split}_v2"] = type_metrics(d["gold_type"].map(schema.forecast_class),
                                                       d["tagger_v2"].map(schema.forecast_class))
    test_ref = ref[ref["doc_id"].isin(df.loc[df["split"] == "test", "doc_id"])]
    dev_ref = ref[ref["doc_id"].isin(df.loc[df["split"] == "dev", "doc_id"])]
    llm = _load_jsonl(GOLD / "llm_labels.jsonl")
    has_human = ref_kind == "human-verified"
    df = df.merge(llm[["doc_id", "event_type"]].rename(columns={"event_type": "llm_type"}), on="doc_id")
    for split in ["dev", "test", "all"]:
        d = df if split == "all" else df[df["split"] == split]
        results[f"agreement_{split}"] = agreement(d, has_human)
        if has_human:  # LLM extraction F1 is only meaningful against human gold
            results[f"llm_type_{split}"] = type_metrics(d["gold_type"], d["llm_type"])
            results[f"llm_details_{split}"] = llm_detail_metrics(ref[ref["doc_id"].isin(d["doc_id"])], llm)

    issuers = dict(zip(sample["doc_id"], sample["company_name"]))
    results["details_dev"] = detail_metrics(dev_ref, texts, issuers)
    results["details_test"] = detail_metrics(test_ref, texts, issuers)
    results["ocr"] = ocr_quality()
    results["confusions_test_v2"] = (
        df[(df["split"] == "test") & (df["gold_type"] != df["tagger_v2"])]
        .groupby(["gold_type", "tagger_v2"]).size().sort_values(ascending=False).head(15)
        .reset_index().rename(columns={0: "n"}).to_dict("records")
    )
    out = GOLD / "eval_results.json"
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"reference: {ref_kind} | docs: {len(df)} -> {out}")
    for split in ["dev", "test"]:
        for v in ["v1", "v2"]:
            m = results[f"type_{split}_{v}"]
            print(f"{split} tagger {v}: accuracy {m['accuracy']} macro-F1 {m['macro_f1']}")


if __name__ == "__main__":
    main()
