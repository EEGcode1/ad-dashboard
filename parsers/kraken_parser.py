"""
Kraken / Octopus parser.

Source: kraken@octopusrgs.com
Subject: "Atlantic Digital Revenue Report | Daily Revenue for DD-MM-YYYY"
Format: HTML email BODY (no attachment).

Weekly + monthly variants of the same email also arrive — we ignore anything
whose subject doesn't contain "Daily Revenue for".

Output rows:
  {
    "source": "octopus",
    "date": "YYYY-MM-DD",
    "game": "<game name>" or "__total__",
    "wager_eur": float,
    "win_eur": float,
    "ggr_eur": float,
    "rtp": float or None,
    "rev_share_eur": ggr * 0.04,
  }
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup

from . import gmail_client

OCTOPUS_REV_SHARE = 0.04
OCTOPUS_SENDER = "kraken@octopusrgs.com"
DAILY_SUBJECT_MARKER = "Daily Revenue for"


@dataclass
class KrakenRow:
    source: str
    date: str
    game: str
    wager_eur: float
    win_eur: float
    ggr_eur: float
    rtp: Optional[float]
    rev_share_eur: float

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "date": self.date,
            "game": self.game,
            "wager_eur": round(self.wager_eur, 2),
            "win_eur": round(self.win_eur, 2),
            "ggr_eur": round(self.ggr_eur, 2),
            "rtp": self.rtp,
            "rev_share_eur": round(self.rev_share_eur, 2),
        }


def _money(s: str) -> float:
    if s is None:
        return 0.0
    s = str(s).strip().replace("€", "").replace("$", "").replace(",", "").replace("\xa0", " ").strip()
    if not s or s == "-":
        return 0.0
    try:
        return float(s)
    except ValueError:
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        return float(m.group(0)) if m else 0.0


def _parse_date_from_subject(subject: str) -> Optional[str]:
    m = re.search(r"Daily Revenue for\s+(\d{1,2})[-/](\d{1,2})[-/](\d{4})", subject)
    if not m:
        return None
    d, mo, y = m.groups()
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def parse_html_body(html: str, subject: str) -> list[KrakenRow]:
    report_date = _parse_date_from_subject(subject)
    if not report_date:
        raise ValueError(f"Could not extract date from subject: {subject!r}")

    soup = BeautifulSoup(html, "html.parser")
    rows: list[KrakenRow] = []

    # The Kraken emails use an HTML table per-game with columns:
    # Game | Wager | Win | GGR | RTP | (sometimes: count)
    for table in soup.find_all("table"):
        header_cells = [
            _norm_text(c.get_text()) for c in (table.find("tr").find_all(["th", "td"]) if table.find("tr") else [])
        ]
        if not header_cells:
            continue
        col = {}
        for i, h in enumerate(header_cells):
            if "game" in h and "count" not in h and "game" not in col:
                col["game"] = i
            elif "wager" in h or "stake" in h or "turnover" in h:
                col["wager"] = i
            elif h == "win" or "total win" in h:
                col["win"] = i
            elif "ggr" in h or "gross" in h:
                col["ggr"] = i
            elif "rtp" in h or "payout" in h:
                col["rtp"] = i

        if not {"game", "wager", "ggr"}.issubset(col):
            continue

        for tr in table.find_all("tr")[1:]:
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < max(col.values()) + 1:
                continue
            game_name = cells[col["game"]].strip()
            if not game_name or game_name.lower() in ("total", "totals", "grand total"):
                continue
            wager = _money(cells[col["wager"]])
            win = _money(cells[col["win"]]) if "win" in col else 0.0
            ggr = _money(cells[col["ggr"]])
            rtp = None
            if "rtp" in col:
                try:
                    rtp_raw = cells[col["rtp"]].replace("%", "").strip()
                    rtp = float(rtp_raw) if rtp_raw else None
                except (ValueError, IndexError):
                    rtp = None
            rows.append(KrakenRow(
                source="octopus",
                date=report_date,
                game=game_name,
                wager_eur=wager,
                win_eur=win,
                ggr_eur=ggr,
                rtp=rtp,
                rev_share_eur=ggr * OCTOPUS_REV_SHARE,
            ))

    if not rows:
        raise ValueError(
            f"Kraken email for {report_date} produced zero rows. "
            "HTML structure may have changed — investigate."
        )
    return rows


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def fetch_latest(service=None, lookback_days: int = 3) -> list[KrakenRow]:
    if service is None:
        service = gmail_client.get_service()
    query = (
        f'from:{OCTOPUS_SENDER} subject:"{DAILY_SUBJECT_MARKER}" '
        f'newer_than:{lookback_days}d'
    )
    ids = gmail_client.search_messages(service, query, max_results=5)
    if not ids:
        raise RuntimeError(f"No Kraken daily email in last {lookback_days} days.")

    # Walk results until we find one with "Daily Revenue for" (skip weekly/monthly).
    for mid in ids:
        msg = gmail_client.get_message(service, mid)
        if DAILY_SUBJECT_MARKER not in msg.subject:
            continue
        html = msg.body_html or msg.body_text or ""
        if not html:
            continue
        return parse_html_body(html, msg.subject)

    raise RuntimeError("No daily Kraken variant found in recent messages.")


if __name__ == "__main__":
    rows = fetch_latest()
    total_ggr = sum(r.ggr_eur for r in rows)
    total_share = sum(r.rev_share_eur for r in rows)
    print(f"Parsed {len(rows)} Octopus rows for {rows[0].date}")
    print(f"  GGR total:       €{total_ggr:,.2f}")
    print(f"  Rev share (4%):  €{total_share:,.2f}")
