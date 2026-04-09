"""
CrownCoins Superset scraper — Playwright.

Env vars required:
  SUPERSET_URL   — Superset login URL (or dashboard URL with login redirect)
  SUPERSET_USER  — username
  SUPERSET_PASS  — password

STATUS: SCAFFOLD. Selectors below are placeholders — pin them via
`playwright codegen` after the first manual login session.

CrownCoins reports ACTUAL revenue (not GGR × rev share), so the output
uses a `net_revenue_eur` field directly.

Output:
  {
    "source": "crowncoins",
    "date": "YYYY-MM-DD",
    "net_revenue_eur": float,     # actual CC revenue for the day
    "notes": "<any flag>",
  }
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout


@dataclass
class CrownCoinsRow:
    source: str
    date: str
    net_revenue_eur: float
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "date": self.date,
            "net_revenue_eur": round(self.net_revenue_eur, 2),
            "notes": self.notes,
        }


def _report_date() -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()


def scrape() -> CrownCoinsRow:
    url = os.environ["SUPERSET_URL"]
    user = os.environ["SUPERSET_USER"]
    pw = os.environ["SUPERSET_PASS"]

    report_date = _report_date()
    net_rev = 0.0
    notes = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = ctx.new_page()
        page.set_default_timeout(45_000)

        try:
            page.goto(url, wait_until="networkidle")

            # -----------------------------------------------------------
            # TODO: pin these selectors via `playwright codegen <url>`
            # -----------------------------------------------------------
            page.fill('input[name="username"]', user)                     # TODO
            page.fill('input[name="password"]', pw)                       # TODO
            page.click('input[type="submit"]')                            # TODO
            page.wait_for_load_state("networkidle")

            # Navigate to the "Atlantic Daily Revenue" dashboard
            # TODO: page.goto(f"{url.rstrip('/')}/superset/dashboard/atlantic-daily/")

            # Set native filter to yesterday
            # TODO: page.click('button[aria-label="Date filter"]')
            # TODO: page.fill('input[placeholder="Start"]', report_date)
            # TODO: page.fill('input[placeholder="End"]',   report_date)
            # TODO: page.click('button:has-text("Apply")')
            # TODO: page.wait_for_selector('[data-test="big-number"]')

            # Read the big-number chart for net revenue
            # TODO: raw = page.locator('[data-test="big-number"]').first.inner_text()
            # TODO: net_rev = float(raw.replace("$","").replace(",",""))

        except PlaywrightTimeout as e:
            notes = f"timeout: {e}"
        finally:
            ctx.close()
            browser.close()

    return CrownCoinsRow(
        source="crowncoins",
        date=report_date,
        net_revenue_eur=net_rev,
        notes=notes,
    )


if __name__ == "__main__":
    row = scrape()
    print(f"CrownCoins {row.date}: ${row.net_revenue_eur:,.2f} (scaffold)")
