"""Client for the PSX Data Portal (dps.psx.com.pk).

The portal is a JS app; every XHR call must carry the per-page token that the
server embeds in each HTML page as ``window.__ps = {..., "_k": "<token>"}``.
The frontend sends it back as the ``X-Req-Id`` header (see static/script.js:
``$.ajaxSetup({headers:{"X-Req-Id":ps._k}})``), so we do the same.

Endpoints used:
    GET  /symbols        -> JSON list of listed symbols
    POST /announcements  -> server-rendered HTML table of announcements
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date

import requests
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

BASE_URL = "https://dps.psx.com.pk"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
_TOKEN_RE = re.compile(r'"_k"\s*:\s*"([^"]+)"')

# Be polite: one request per second by default.
DEFAULT_DELAY_S = 1.0


@dataclass
class Announcement:
    symbol: str
    date: str          # YYYY-MM-DD
    time: str          # HH:MM:SS or ""
    title: str
    category: str      # portal tab/category if present
    pdf_url: str       # absolute URL or ""
    company_name: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class PsxClient:
    delay_s: float = DEFAULT_DELAY_S
    session: requests.Session = field(default_factory=requests.Session)
    _token: str | None = None
    _last_request: float = 0.0

    def __post_init__(self) -> None:
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/announcements/companies",
                "Accept": "text/html, */*; q=0.01",
            }
        )

    # -- token handling -----------------------------------------------------

    def _refresh_token(self) -> None:
        resp = self.session.get(f"{BASE_URL}/announcements/companies", timeout=30)
        resp.raise_for_status()
        m = _TOKEN_RE.search(resp.text)
        if not m:
            raise RuntimeError("could not find _k token in portal page")
        self._token = m.group(1)
        self.session.headers["X-Req-Id"] = self._token

    def _throttle(self) -> None:
        wait = self._last_request + self.delay_s - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(min=2, max=30))
    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        if self._token is None:
            self._refresh_token()
        self._throttle()
        resp = self.session.request(method, f"{BASE_URL}{path}", timeout=30, **kwargs)
        if resp.status_code in (401, 403, 419):
            # token expired / rotated -> refresh once and retry via tenacity
            self._token = None
            resp.raise_for_status()
        resp.raise_for_status()
        return resp

    # -- public API ---------------------------------------------------------

    def symbols(self) -> list[dict]:
        """All listed symbols with name/sector metadata."""
        return self._request("GET", "/symbols").json()

    def announcements_html(
        self,
        symbol: str = "",
        date_from: date | None = None,
        date_to: date | None = None,
        count: int = 50,
        offset: int = 0,
    ) -> str:
        data = {
            "type": "C",                # companies
            "symbol": symbol,
            "query": "",
            "count": str(count),
            "offset": str(offset),
            "date_from": date_from.isoformat() if date_from else "",
            "date_to": date_to.isoformat() if date_to else "",
            "page": "annc",
        }
        return self._request("POST", "/announcements", data=data).text

    def announcements(
        self,
        symbol: str = "",
        date_from: date | None = None,
        date_to: date | None = None,
        count: int = 50,
        offset: int = 0,
    ) -> list[Announcement]:
        html = self.announcements_html(symbol, date_from, date_to, count, offset)
        return parse_announcements(html, fallback_symbol=symbol)

    def announcements_page(
        self,
        symbol: str = "",
        date_from: date | None = None,
        date_to: date | None = None,
        count: int = 100,
        offset: int = 0,
    ) -> tuple[list[Announcement], int]:
        """One page plus the server-reported total ('Showing X to Y of N entries')."""
        html = self.announcements_html(symbol, date_from, date_to, count, offset)
        m = re.search(r"of\s+([\d,]+)\s+entries", html)
        total = int(m.group(1).replace(",", "")) if m else 0
        return parse_announcements(html, fallback_symbol=symbol), total


def parse_announcements(html: str, fallback_symbol: str = "") -> list[Announcement]:
    """Parse the HTML table fragment returned by POST /announcements."""
    soup = BeautifulSoup(html, "lxml")
    out: list[Announcement] = []
    for row in soup.select("table tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        texts = [c.get_text(" ", strip=True) for c in cells]
        pdf_url = ""
        for a in row.find_all("a", href=True):
            href = a["href"]
            if "download" in href or href.lower().endswith(".pdf"):
                pdf_url = href if href.startswith("http") else BASE_URL + href
                break
        # Column order on the portal: DATE | TIME | SYMBOL | NAME | TITLE | ...
        # Fall back gracefully if the layout differs.
        rec = _map_columns(texts, fallback_symbol)
        rec.pdf_url = pdf_url
        out.append(rec)
    return out


_DATE_RE = re.compile(r"^[A-Z][a-z]{2} \d{1,2}, \d{4}$|^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?( ?[AP]M)?$", re.I)


def _map_columns(texts: list[str], fallback_symbol: str) -> Announcement:
    date_s = time_s = symbol = name = title = ""
    rest: list[str] = []
    for t in texts:
        if not date_s and _DATE_RE.match(t):
            date_s = t
        elif not time_s and _TIME_RE.match(t):
            time_s = t
        else:
            rest.append(t)
    if rest:
        # symbol cells are short uppercase tickers
        if re.fullmatch(r"[A-Z0-9.]{2,12}", rest[0]):
            symbol = rest[0]
            rest = rest[1:]
    if len(rest) >= 2:
        name, title = rest[0], max(rest[1:], key=len)
    elif rest:
        title = rest[0]
    return Announcement(
        symbol=symbol or fallback_symbol,
        date=_norm_date(date_s),
        time=time_s,
        title=title,
        category="",
        pdf_url="",
        company_name=name,
    )


def _norm_date(s: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    try:
        from datetime import datetime

        return datetime.strptime(s, "%b %d, %Y").date().isoformat()
    except ValueError:
        return s
