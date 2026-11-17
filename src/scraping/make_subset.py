"""Create the KSE-100 working subset.

Fetches current KSE-100 constituents from the portal (GET /indices/KSE100),
saves them, and filters announcements.csv down to those companies.

Usage:
    python -m src.scraping.make_subset
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.scraping.export_csv import _safe_write  # noqa: E402
from src.scraping.psx_client import PsxClient  # noqa: E402


def fetch_kse100_symbols(client: PsxClient) -> list[str]:
    html = client._request("GET", "/indices/KSE100").text
    soup = BeautifulSoup(html, "lxml")
    symbols = []
    for row in soup.select("table tbody tr"):
        cells = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        if not cells:
            continue
        # first cell is "SYMBOL" possibly followed by status tags like "XD"/"SPOT"
        token = cells[0].split()[0] if cells[0] else ""
        if re.fullmatch(r"[A-Z0-9.]{2,12}", token):
            symbols.append(token)
    return sorted(set(symbols))


def main() -> None:
    client = PsxClient()
    symbols = fetch_kse100_symbols(client)
    if len(symbols) < 80:
        print(f"WARNING: only {len(symbols)} constituents parsed — check /indices/KSE100 markup")
    out_json = ROOT / "data" / "kse100_symbols.json"
    out_json.write_text(json.dumps(symbols, indent=1), encoding="utf-8")
    print(f"{len(symbols)} KSE-100 symbols -> {out_json}")

    ann = pd.read_csv(ROOT / "data" / "announcements.csv")
    sub = ann[ann["symbol"].isin(symbols)].reset_index(drop=True)
    out = _safe_write(sub, ROOT / "data" / "announcements_kse100.csv")
    print(f"{len(sub)} announcements for {sub['symbol'].nunique()} companies -> {out}")

    n_pdf = sub["pdf_url"].notna().sum()
    print(f"PDF links in subset: {n_pdf} (~{n_pdf * 0.5 / 1024:.1f} GB at ~500KB avg)")


if __name__ == "__main__":
    main()
