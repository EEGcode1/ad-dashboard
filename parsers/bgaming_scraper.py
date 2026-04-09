"""
BGaming backoffice scraper — Playwright.

Env vars required:
  BGAMING_URL   — login URL
  BGAMING_USER  — username
  BGAMING_PASS  — password

STATUS: SCAFFOLD. Selectors below are placeholders — they need to be
pinned after the first manual login session using `playwright codegen`.
Record a session, then paste the real selectors into the marked TODO blocks.

Output rows:
  {
    "source": "bgaming",
    "date": "YYYY-MM-DD",
    "game": "<name>",
    "wager_eur": float,
    "ggr_eur": float,
    "rev_share_eur": ggr * 0.04,
  }
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BGAMING_REV_SHARE = 0.04


@dataclass
class BgamingRow:
    source: str
    date: str
    game: str
    wager_eur: float
    ggr_eur: float
    rev_share_eur: float

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "date": self.date,
            "game": self.game,
            "wager_eur": round(self.wager_eur, 2),
            "ggr_eur": round(self.ggr_eur, 2),
            "rev_share_eur": round(self.rev_share_eur, 2),
        }


def _report_date() -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()


def scrape() -> list[BgamingRow]:
    url = os.environ["BGAMING_URL"]
    user = os.environ["BGAMING_USER"]
    pw = os.environ["BGAMING_PASS"]

    rows: list[BgamingRow] = []
    report_date = _report_date()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(30_000)

        try:
            page.goto(url, wait_until="networkidle")

            # -----------------------------------------------------------
            # TODO: pin these selectors via `playwright codegen <url>`
            # -----------------------------------------------------------
            page.fill('input[name="email"]', user)                        # TODO
            page.fill('input[name="password"]', pw)                       # TODO
            page.click('button[type="submit"]')                           # TODO
            page.wait_for_load_state("networkidle")

            # Navigate to daily reports view
            # TODO: page.goto(f"{url}/reports/daily?date={report_date}")

            # Set date filter to yesterday
            # TODO: page.fill('input[name="from_date"]', report_date)
            # TODO: page.fill('input[name="to_date"]', report_date)
            # TODO: page.click('button:has-text("Apply")')
            # TODO: page.wait_for_selector("table.report-table tbody tr")

            # Harvest rows from the report table
            # TODO: rows_locator = page.locator("table.report-table tbody tr")
            # TODO: for i in range(rows_locator.count()):
            # TODO:     cells = rows_locator.nth(i).locator("td").all_inner_texts()
            # TODO:     game = cells[0].strip()
            # TODO:     wager = float(cells[1].replace("€","").replace(",",""))
            # TODO:     ggr   = float(cells[2].replace("€","").replace(",",""))
            # TODO:     rows.append(BgamingRow(
            # TODO:         source="bgaming", date=report_date, game=game,
            # TODO:         wager_eur=wager, ggr_eur=ggr,
            # TODO:         rev_share_eur=ggr * BGAMING_REV_SHARE,
            # TODO:     ))

        except PlaywrightTimeout as e:
            raise RuntimeError(f"BGaming scrape timed out: {e}") from e
        finally:
            ctx.close()
            browser.close()

    return rows


if __name__ == "__main__":
    out = scrape()
    print(f"BGaming: {len(out)} rows (scaffold — selectors not yet pinned).")
