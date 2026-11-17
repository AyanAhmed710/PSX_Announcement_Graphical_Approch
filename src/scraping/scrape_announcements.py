"""Scrape PSX company announcements into JSONL files.

Usage:
    python -m src.scraping.scrape_announcements --symbols            # dump symbol list
    python -m src.scraping.scrape_announcements --symbol HBL         # one company
    python -m src.scraping.scrape_announcements --all --from 2020-01-01
    python -m src.scraping.scrape_announcements --probe              # raw HTML sample

Output: data/raw/announcements/<SYMBOL>.jsonl (one JSON object per line).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.scraping.psx_client import PsxClient  # noqa: E402

RAW_DIR = ROOT / "data" / "raw" / "announcements"
PAGE_SIZE = 100  # the portal serves at most 100 rows per request


def dump_symbols(client: PsxClient) -> Path:
    out = ROOT / "data" / "raw" / "symbols.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    syms = client.symbols()
    out.write_text(json.dumps(syms, indent=1), encoding="utf-8")
    print(f"{len(syms)} symbols -> {out}")
    return out


def scrape_symbol(client: PsxClient, symbol: str, date_from: date | None) -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{symbol}.jsonl"
    seen: set[tuple] = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            seen.add((r["date"], r["title"], r.get("pdf_url", "")))
    n_new = 0
    offset = 0
    with out_path.open("a", encoding="utf-8") as fh:
        while True:
            batch, total = client.announcements_page(
                symbol=symbol, date_from=date_from, count=PAGE_SIZE, offset=offset
            )
            if not batch:
                break
            for ann in batch:
                key = (ann.date, ann.title, ann.pdf_url)
                if key in seen:
                    continue
                seen.add(key)
                rec = ann.to_dict()
                rec["scraped_at"] = datetime.now(timezone.utc).isoformat()
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n_new += 1
            offset += len(batch)
            if offset >= total:
                break
    print(f"{symbol}: +{n_new} new (total {len(seen)}) -> {out_path}", flush=True)
    return n_new


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", action="store_true", help="dump symbol list and exit")
    p.add_argument("--symbol", help="scrape one symbol")
    p.add_argument("--all", action="store_true", help="scrape every listed symbol")
    p.add_argument("--from", dest="date_from", help="YYYY-MM-DD lower bound")
    p.add_argument("--probe", action="store_true", help="print raw HTML sample and exit")
    p.add_argument("--full", action="store_true", help="symbols + scrape all + export CSV")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    args = p.parse_args()

    client = PsxClient(delay_s=args.delay)
    date_from = date.fromisoformat(args.date_from) if args.date_from else None

    if args.probe:
        html = client.announcements_html(symbol=args.symbol or "HBL", count=5)
        print(html[:5000])
        return
    if args.symbols:
        dump_symbols(client)
        return
    if args.symbol:
        scrape_symbol(client, args.symbol.upper(), date_from)
        return
    if args.all or args.full:
        syms_file = ROOT / "data" / "raw" / "symbols.json"
        if not syms_file.exists():
            dump_symbols(client)
        symbols = [s["symbol"] for s in json.loads(syms_file.read_text(encoding="utf-8"))]
        print(f"scraping {len(symbols)} symbols...", flush=True)
        for i, sym in enumerate(symbols, 1):
            try:
                scrape_symbol(client, sym, date_from)
            except Exception as e:  # keep going; log failures
                print(f"{sym}: FAILED {e}", file=sys.stderr, flush=True)
            if i % 25 == 0:
                print(f"--- progress: {i}/{len(symbols)} symbols done", flush=True)
        if args.full:
            from src.scraping.export_csv import export_announcements, export_companies

            export_companies()
            export_announcements()
        return
    p.print_help()


if __name__ == "__main__":
    main()
