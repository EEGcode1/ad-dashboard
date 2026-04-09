"""
Billing cross-check — monthly audit only.

Inputs:
  - Emails from JP (accountant) with our billing statements
  - LNW billing statements

Purpose: reconcile the daily-scraped GGR × rev-share totals (in data.json)
against the actual invoiced / paid amounts. Any delta > 1% is flagged in
audit/billing_reconciliation.md.

STATUS: SCAFFOLD. Runs monthly, not daily. Separate workflow step or
manual invocation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from . import gmail_client

JP_SENDER_HINT = "jp"           # TODO: pin exact sender address
LNW_BILLING_HINT = "billing"    # TODO: pin exact subject/sender

DELTA_THRESHOLD = 0.01          # 1%


@dataclass
class ReconciliationLine:
    month: str                  # "YYYY-MM"
    source: str                 # lnw | octopus | bgaming | crowncoins
    scraped_total_eur: float
    billed_total_eur: float

    @property
    def delta_abs(self) -> float:
        return self.billed_total_eur - self.scraped_total_eur

    @property
    def delta_pct(self) -> float:
        if self.scraped_total_eur == 0:
            return 0.0
        return self.delta_abs / self.scraped_total_eur

    @property
    def flagged(self) -> bool:
        return abs(self.delta_pct) > DELTA_THRESHOLD


def load_scraped_totals(data_json_path: Path, month: str) -> dict[str, float]:
    """
    Walk data/history/*.json and sum rev_share_eur / net_revenue_eur by source
    for the given month (YYYY-MM).
    """
    totals: dict[str, float] = {"lnw": 0.0, "octopus": 0.0, "bgaming": 0.0, "crowncoins": 0.0}
    history_dir = data_json_path.parent / "history"
    if not history_dir.exists():
        return totals

    for snap in sorted(history_dir.glob("*.json")):
        if not snap.stem.startswith(month):
            continue
        with snap.open() as f:
            payload = json.load(f)
        for row in payload.get("rows", []):
            src = row.get("source")
            if src in ("lnw", "octopus", "bgaming"):
                totals[src] += row.get("rev_share_eur", 0.0)
            elif src == "crowncoins":
                totals["crowncoins"] += row.get("net_revenue_eur", 0.0)
    return totals


def fetch_billing_totals(month: str) -> dict[str, float]:
    """
    TODO: parse JP's email attachments + LNW billing statements and return
    {source: invoiced_total_eur}.
    """
    # Scaffold — returns empty until pinned to the real statement format.
    return {"lnw": 0.0, "octopus": 0.0, "bgaming": 0.0, "crowncoins": 0.0}


def reconcile(month: str, data_json_path: Path) -> list[ReconciliationLine]:
    scraped = load_scraped_totals(data_json_path, month)
    billed = fetch_billing_totals(month)
    lines = []
    for src in ("lnw", "octopus", "bgaming", "crowncoins"):
        lines.append(ReconciliationLine(
            month=month,
            source=src,
            scraped_total_eur=scraped.get(src, 0.0),
            billed_total_eur=billed.get(src, 0.0),
        ))
    return lines


def write_report(lines: list[ReconciliationLine], out_path: Path) -> None:
    lines_md = ["# Billing reconciliation", ""]
    month = lines[0].month if lines else "unknown"
    lines_md += [f"**Month:** {month}", "", "| Source | Scraped (€) | Billed (€) | Δ (€) | Δ % | Flag |",
                 "|---|---:|---:|---:|---:|:---:|"]
    for ln in lines:
        flag = "⚠️" if ln.flagged else "✓"
        lines_md.append(
            f"| {ln.source} | {ln.scraped_total_eur:,.2f} | {ln.billed_total_eur:,.2f} "
            f"| {ln.delta_abs:,.2f} | {ln.delta_pct:+.2%} | {flag} |"
        )
    out_path.write_text("\n".join(lines_md) + "\n")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=date.today().strftime("%Y-%m"))
    ap.add_argument("--data", default="data/data.json")
    ap.add_argument("--out", default="audit/billing_reconciliation.md")
    args = ap.parse_args()

    lines = reconcile(args.month, Path(args.data))
    write_report(lines, Path(args.out))
    print(f"Wrote {args.out} for {args.month}")
