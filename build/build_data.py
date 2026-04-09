"""
Orchestrator — runs every parser, merges the rows into data/data.json,
writes a daily history snapshot, and computes day / 7-day / MTD
aggregations from the history folder so dashboards don't have to.

Design rule: NO SILENT NORMALIZATION. If a source fails, the corresponding
freshness flag goes stale, the error is recorded, and the dashboard shows
a visible gap. We never paper over missing data.
"""

from __future__ import annotations

import json
import shutil
import sys
import traceback
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DATA_JSON = DATA_DIR / "data.json"
HISTORY_DIR = DATA_DIR / "history"

LNW_REV_SHARE = 0.04
TIDAL_REV_SHARE = 0.04  # BGaming + Octopus; CrownCoins uses net revenue directly


# ---------------------------------------------------------------------------
# Source status dataclass
# ---------------------------------------------------------------------------
@dataclass
class SourceStatus:
    name: str
    ok: bool = False
    error: str | None = None
    row_count: int = 0
    last_run_utc: str = ""
    covered_date: str | None = None


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _load_history_range(from_date: str, to_date: str) -> list[dict]:
    """Return all rows from history snapshots in [from_date, to_date] inclusive."""
    all_rows: list[dict] = []
    for snap in sorted(HISTORY_DIR.glob("*.json")):
        d = snap.stem
        if from_date <= d <= to_date:
            try:
                payload = json.loads(snap.read_text())
                all_rows.extend(payload.get("day", {}).get("rows", []))
            except Exception:
                pass
    return all_rows


def _aggregate_rows(rows: list[dict], source_filter: str | None = None) -> dict:
    """
    Aggregate a flat list of rows into:
      - by_game: [{game, source, wager_eur, ggr_eur, rev_share_eur, net_revenue_eur}]
      - totals: {lnw_rev_share_eur, octopus_rev_share_eur, bgaming_rev_share_eur,
                  crowncoins_net_revenue_eur, regulated_total_eur, tidal_total_eur,
                  combined_total_eur}
    """
    if source_filter:
        rows = [r for r in rows if r.get("source") == source_filter]

    game_map: dict[tuple, dict] = defaultdict(lambda: {
        "wager_eur": 0.0, "ggr_eur": 0.0, "rev_share_eur": 0.0,
        "net_revenue_eur": 0.0, "win_eur": 0.0,
    })
    for r in rows:
        key = (r.get("source", ""), r.get("game", ""))
        agg = game_map[key]
        agg["wager_eur"] += r.get("wager_eur") or 0.0
        agg["ggr_eur"] += r.get("ggr_eur") or 0.0
        agg["rev_share_eur"] += r.get("rev_share_eur") or 0.0
        agg["net_revenue_eur"] += r.get("net_revenue_eur") or 0.0
        agg["win_eur"] += r.get("win_eur") or 0.0

    by_game = []
    for (src, game), agg in sorted(game_map.items(), key=lambda x: -x[1]["ggr_eur"]):
        by_game.append({
            "source": src,
            "game": game,
            "wager_eur": round(agg["wager_eur"], 2),
            "win_eur": round(agg["win_eur"], 2),
            "ggr_eur": round(agg["ggr_eur"], 2),
            "rev_share_eur": round(agg["rev_share_eur"], 2),
            "net_revenue_eur": round(agg["net_revenue_eur"], 2),
        })

    totals = _compute_totals(rows)
    return {"by_game": by_game, "totals": totals}


def _compute_totals(rows: list[dict]) -> dict:
    lnw = sum(r.get("rev_share_eur") or 0.0 for r in rows if r.get("source") == "lnw")
    oct_ = sum(r.get("rev_share_eur") or 0.0 for r in rows if r.get("source") == "octopus")
    bg = sum(r.get("rev_share_eur") or 0.0 for r in rows if r.get("source") == "bgaming")
    cc = sum(r.get("net_revenue_eur") or 0.0 for r in rows if r.get("source") == "crowncoins")
    regulated = lnw
    tidal = oct_ + bg + cc
    return {
        "lnw_rev_share_eur": round(lnw, 2),
        "octopus_rev_share_eur": round(oct_, 2),
        "bgaming_rev_share_eur": round(bg, 2),
        "crowncoins_net_revenue_eur": round(cc, 2),
        "regulated_total_eur": round(regulated, 2),
        "tidal_total_eur": round(tidal, 2),
        "combined_total_eur": round(regulated + tidal, 2),
    }


def _daily_series(rows: list[dict]) -> list[dict]:
    """
    Group rows by date and return [{date, lnw, octopus, bgaming, crowncoins, combined}]
    sorted ascending — used for trend charts.
    """
    by_date: dict[str, dict] = defaultdict(lambda: {
        "lnw": 0.0, "octopus": 0.0, "bgaming": 0.0, "crowncoins": 0.0
    })
    for r in rows:
        d = r.get("date", "")
        src = r.get("source", "")
        if src in ("lnw", "octopus", "bgaming"):
            by_date[d][src] += r.get("rev_share_eur") or 0.0
        elif src == "crowncoins":
            by_date[d]["crowncoins"] += r.get("net_revenue_eur") or 0.0

    series = []
    for d in sorted(by_date):
        v = by_date[d]
        combined = sum(v.values())
        series.append({
            "date": d,
            "lnw": round(v["lnw"], 2),
            "octopus": round(v["octopus"], 2),
            "bgaming": round(v["bgaming"], 2),
            "crowncoins": round(v["crowncoins"], 2),
            "tidal": round(v["octopus"] + v["bgaming"] + v["crowncoins"], 2),
            "combined": round(combined, 2),
        })
    return series


def _mtd_cumulative(daily_series: list[dict]) -> list[dict]:
    """Convert daily series to cumulative MTD totals."""
    cum = {"lnw": 0.0, "tidal": 0.0, "combined": 0.0}
    out = []
    for day in daily_series:
        cum["lnw"] += day["lnw"]
        cum["tidal"] += day["tidal"]
        cum["combined"] += day["combined"]
        out.append({
            "date": day["date"],
            "lnw_cum": round(cum["lnw"], 2),
            "tidal_cum": round(cum["tidal"], 2),
            "combined_cum": round(cum["combined"], 2),
        })
    return out


# ---------------------------------------------------------------------------
# Runner helper
# ---------------------------------------------------------------------------

def _run(name: str, fn) -> tuple[SourceStatus, Any]:
    status = SourceStatus(name=name, last_run_utc=datetime.now(timezone.utc).isoformat())
    try:
        out = fn()
        status.ok = True
        if isinstance(out, list):
            status.row_count = len(out)
            if out and hasattr(out[0], "date"):
                status.covered_date = out[0].date
        elif out is not None and hasattr(out, "date"):
            status.covered_date = out.date
            status.row_count = 1
        return status, out
    except Exception as e:
        status.ok = False
        status.error = f"{type(e).__name__}: {e}"
        traceback.print_exc(file=sys.stderr)
        return status, None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    from parsers import (
        sgi_parser,
        kraken_parser,
        bgaming_scraper,
        superset_scraper,
        godfather_parser,
    )

    # 1. Pull today's data from all sources
    lnw_status, lnw_rows = _run("lnw", sgi_parser.fetch_latest)
    octopus_status, octopus_rows = _run("octopus", kraken_parser.fetch_latest)
    bgaming_status, bgaming_rows = _run("bgaming", bgaming_scraper.scrape)
    cc_status, cc_row = _run("crowncoins", superset_scraper.scrape)
    godfather_status, godfather_row = _run("godfather", godfather_parser.fetch_latest)

    sources = {
        "lnw": lnw_status,
        "octopus": octopus_status,
        "bgaming": bgaming_status,
        "crowncoins": cc_status,
        "godfather": godfather_status,
    }

    # 2. Today's rows (the "Previous Day" report date)
    today_rows: list[dict] = []
    for rows in (lnw_rows, octopus_rows, bgaming_rows):
        if rows:
            today_rows.extend(r.to_dict() for r in rows)
    if cc_row:
        today_rows.append(cc_row.to_dict())

    covered_date = (
        lnw_status.covered_date
        or octopus_status.covered_date
        or (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    )

    # 3. Write history snapshot BEFORE computing aggregations
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    if today_rows:
        snap = {"day": {"date": covered_date, "rows": today_rows}}
        (HISTORY_DIR / f"{covered_date}.json").write_text(json.dumps(snap, indent=2))

    # 4. Compute week (last 7 days) aggregation from history
    today_dt = datetime.now(timezone.utc).date()
    week_from = (today_dt - timedelta(days=6)).isoformat()
    week_to = today_dt.isoformat()
    week_rows = _load_history_range(week_from, week_to)
    week_series = _daily_series(week_rows)
    week_agg = _aggregate_rows(week_rows)

    # 5. Compute MTD aggregation from history
    mtd_from = today_dt.replace(day=1).isoformat()
    mtd_to = today_dt.isoformat()
    mtd_rows = _load_history_range(mtd_from, mtd_to)
    mtd_series = _daily_series(mtd_rows)
    mtd_cum = _mtd_cumulative(mtd_series)
    mtd_agg = _aggregate_rows(mtd_rows)

    # 6. Assemble final payload
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": {k: asdict(v) for k, v in sources.items()},
        "day": {
            "date": covered_date,
            "rows": today_rows,
            "totals": _compute_totals(today_rows),
        },
        "week": {
            "from": week_from,
            "to": week_to,
            "by_game": week_agg["by_game"],
            "by_day": week_series,
            "totals": week_agg["totals"],
        },
        "mtd": {
            "month": today_dt.strftime("%Y-%m"),
            "by_game": mtd_agg["by_game"],
            "by_day": mtd_series,
            "cumulative": mtd_cum,
            "totals": mtd_agg["totals"],
        },
        "godfather": godfather_row.to_dict() if godfather_row else None,
    }
    DATA_JSON.write_text(json.dumps(payload, indent=2) + "\n")

    # 7. Alerting exit rules
    if not lnw_status.ok:
        print(f"::error::LNW source failed: {lnw_status.error}", file=sys.stderr)
        return 1

    tidal_ok = sum(
        1 for s in ("octopus", "bgaming", "crowncoins")
        if sources[s].ok
    )
    if tidal_ok <= 1:
        print("::warning::2+ Tidal sources failed — dashboard will show gaps.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
