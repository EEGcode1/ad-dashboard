# Atlantic Digital Revenue Dashboard

Source-of-truth daily revenue dashboard for Atlantic Digital (LNW Regulated) and Tidal Interactive (BGaming, CrownCoins, Octopus/Kraken). Parses the **actual upstream source emails and backoffices** — not Gary's parsed reports — and publishes to GitHub Pages.

**Philosophy:** Gary's reports are audited against this dashboard, not the other way around.

---

## Architecture

```
     ┌─────────────────────────────────────────────────────────────┐
     │                   GOSPEL SOURCES                            │
     ├─────────────────────────────────────────────────────────────┤
     │  SGI_Reporting@lnw.com   → "Atlantic Digital Extended       │
     │                             Report" (daily xlsx)            │
     │  kraken@octopusrgs.com   → daily HTML email body            │
     │  BGaming backoffice      → scraped via Playwright login     │
     │  CrownCoins Superset     → scraped via Playwright login     │
     │  JP/LNW billing emails   → monthly cross-check only         │
     │  Kerri @ Bangbang Games  → Godfather the Offer collab       │
     └──────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
     ┌─────────────────────────────────────────────────────────────┐
     │              GitHub Actions — daily-refresh.yml             │
     │                    (runs 06:00 GMT daily)                   │
     │                                                             │
     │  1. parsers/sgi_parser.py        → lnw rows                 │
     │  2. parsers/kraken_parser.py     → octopus rows             │
     │  3. parsers/bgaming_scraper.py   → bgaming rows             │
     │  4. parsers/superset_scraper.py  → crowncoins rows          │
     │  5. build/build_data.py          → merge into data.json     │
     │  6. build/render_html.py         → render site/index.html   │
     │  7. git commit & push                                       │
     │  8. GitHub Pages serves /site                               │
     └──────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
          https://<user>.github.io/ad-dashboard/  (shareable link)
```

**Runs nowhere except GitHub Actions.** No Mac mini dependency (that's Gary/OpenClaw's sandbox). No Cowork dependency for daily refresh (Cowork is used only for design, audit passes, and troubleshooting).

---

## Why this exists

Before this dashboard, daily revenue reporting was done by Gary (an AI agent running on the Mac mini). From his own W14 self-review: 3/7 reports generated last week, 0/7 on time, multiple auto-sent DRAFTs with stale/wrong-dated data, SGI parser inflating Mar 18 and Mar 23 by 1.7–1.96× because it was reading the wrong Excel tabs, and a missed Sunday because the BGaming API 404'd with no fallback.

The fix isn't to make Gary more reliable. The fix is to go straight to the source — the actual SGI xlsx, the actual Kraken email, the actual backoffices — and treat Gary's reports as audit material.

---

## Data sources

### 1. LNW Regulated — `SGI_Reporting@lnw.com`

- **Email:** "Atlantic Digital Extended Report" — arrives daily ~05:30 BST
- **Format:** `.xlsx` attachment (~1.6MB)
- **Tab to parse:** **`Previous Day - By Game` ONLY.** Other tabs cause 1.7–1.96× inflation.
- **Fields per game:** wager (€), GGR (€), RTP
- **Revenue share:** 4% of GGR
- **Parser:** `parsers/sgi_parser.py`

There's also a separate email: **"A Game for Yesterday - Godfather the Offer"** (~30KB xlsx). This is **not the main daily LNW report**. It's a game-specific report for the Godfather the Offer title, which is a collab with **Bangbang Games** (contact: Kerri). Parse it separately and file under a `godfather_collab` line item. Cross-check with Kerri's statements.

### 2. Octopus / Kraken RGS — `kraken@octopusrgs.com`

- **Email:** "Atlantic Digital Revenue Report | Daily Revenue for DD-MM-YYYY"
- **Format:** HTML email body (no attachment needed)
- **Arrives:** 06:00 UTC daily
- **Fields:** Total Wager (€), Total Win (€), GGR (€), RTP, Game Count, per-game breakdown
- **Revenue share:** 4% of GGR
- **Parser:** `parsers/kraken_parser.py`
- Weekly and monthly versions of the same email also arrive — `kraken_parser.py` ignores these and only uses the dailies.

### 3. BGaming — backoffice scrape

- **URL:** `[BGaming backoffice URL — set via secret]`
- **Credentials:** stored in GitHub repo secrets `BGAMING_USER` / `BGAMING_PASS`
- **Scraper:** `parsers/bgaming_scraper.py` (Playwright, headless Chromium)
- **Fields to extract:** daily GGR per game, wager per game
- **Revenue share:** 4% of GGR

### 4. CrownCoins — Superset dashboard

- **URL:** `[Superset URL — set via secret]`
- **Credentials:** stored in GitHub repo secrets `SUPERSET_USER` / `SUPERSET_PASS`
- **Scraper:** `parsers/superset_scraper.py` (Playwright)
- **Fields:** daily net revenue (CC use actual revenue, not GGR × rev share)

### 5. Billing cross-check (monthly audit only)

- **Emails from JP** (our accountant) and **LNW billing statements** — contain actual invoiced/paid revenue
- **Parser:** `parsers/billing_cross_check.py`
- **Runs:** monthly, not daily
- **Purpose:** reconcile daily-scraped GGR × rev-share against the billing statements. Any >1% delta gets flagged in `audit/billing_reconciliation.md`.

---

## Repo layout

```
ad-dashboard/
├── README.md                         ← you are here
├── requirements.txt
├── .gitignore
├── .github/
│   └── workflows/
│       └── daily-refresh.yml         ← GitHub Actions cron
├── parsers/
│   ├── gmail_client.py               ← Gmail API wrapper (shared)
│   ├── sgi_parser.py                 ← LNW xlsx parser
│   ├── kraken_parser.py              ← Octopus email body parser
│   ├── bgaming_scraper.py            ← Playwright scraper
│   ├── superset_scraper.py           ← Playwright scraper
│   └── billing_cross_check.py        ← monthly audit
├── build/
│   ├── build_data.py                 ← orchestrator
│   └── render_html.py                ← data.json → site/index.html
├── data/
│   ├── data.json                     ← current state, read by site/
│   ├── data.schema.json              ← JSON schema
│   └── history/                      ← daily snapshots (audit trail)
├── site/
│   ├── index.html                    ← the dashboard
│   └── assets/
└── audit/
    ├── gary_vs_source.md             ← running log of Gary discrepancies
    └── billing_reconciliation.md     ← monthly billing audit output
```

---

## Setup (one-time, ~30 min)

### 1. Create the GitHub repo

```bash
cd /path/where/you/cloned/ad-dashboard
git init
git add .
git commit -m "Initial: ad-dashboard scaffolding (architecture + parsers + workflow)"

# Create a private repo under your account (requires gh CLI)
gh repo create ad-dashboard --private --source=. --remote=origin --push

# Or manually:
#   - create empty repo at https://github.com/<you>/ad-dashboard
#   - git remote add origin git@github.com:<you>/ad-dashboard.git
#   - git push -u origin main
```

### 2. Enable GitHub Pages

```bash
# Set pages source to the 'gh-pages' branch (workflow will publish to it)
gh api -X POST repos/:owner/:repo/pages -f source.branch=gh-pages -f source.path=/
```

Or manually: repo → Settings → Pages → Source: GitHub Actions.

### 3. Add secrets

Repo → Settings → Secrets and variables → Actions → New repository secret. Add:

| Name | Value |
|---|---|
| `GMAIL_CLIENT_ID` | OAuth client ID from Google Cloud Console |
| `GMAIL_CLIENT_SECRET` | OAuth client secret |
| `GMAIL_REFRESH_TOKEN` | Refresh token for `ali@atlanticd.co` |
| `BGAMING_URL` | BGaming backoffice login URL |
| `BGAMING_USER` | BGaming username |
| `BGAMING_PASS` | BGaming password |
| `SUPERSET_URL` | CrownCoins Superset login URL |
| `SUPERSET_USER` | Superset username |
| `SUPERSET_PASS` | Superset password |

### 4. Gmail API one-time auth

The Gmail API needs a refresh token to read mail non-interactively from Actions.

```bash
python parsers/gmail_client.py --first-time-auth
# Follow the prompts; paste the refresh token into the GMAIL_REFRESH_TOKEN secret
```

### 5. First manual run

```bash
# Trigger the workflow once manually to verify
gh workflow run daily-refresh.yml
gh run watch
```

After it succeeds, the dashboard is live at:
```
https://<your-username>.github.io/ad-dashboard/
```

---

## Daily cadence

- **06:00 GMT** — GitHub Actions cron fires
- **06:00–06:08** — SGI + Kraken parsers run
- **06:08–06:15** — BGaming + Superset Playwright scrapers run
- **06:15** — `build_data.py` merges everything into `data/data.json`
- **06:16** — `render_html.py` writes `site/index.html`
- **06:17** — commit + push; GitHub Pages auto-deploys
- **06:18** — dashboard live

If any source fails, the workflow still commits what it has, updates `data.json` freshness flags so the dashboard UI shows the gap clearly, and posts a failure summary to the workflow run. No silent normalization of missing data.

---

## Model / cost notes

- **GitHub Actions does the daily work** — pure Python, no LLM tokens consumed.
- **Cowork is used sparingly**, only for:
  - Weekly audit pass comparing Gary's emails vs this dashboard (Sonnet, scheduled task)
  - Troubleshooting failed workflow runs (on-demand)
  - Monthly billing reconciliation (Sonnet)
  - Architecture changes (Opus — rarely)
- This keeps Cowork token burn low. Don't run Opus against ingestion or audit tasks — Sonnet is plenty for parsing and diffing.

---

## Gary's role going forward

- Gary stops building dashboards. He's removed from the dashboard path entirely.
- Gary keeps: the single daily digest email (one per day, ~05:45 GMT), Telegram interactive commands, weekly self-review, SGI arrival monitoring, and month-close narrative.
- Gary's daily digest email now **links to this dashboard** instead of duplicating the numbers in the email body.
- If Gary's reported number for a day disagrees with this dashboard's number by more than 2%, the audit file `audit/gary_vs_source.md` logs it automatically.

---

## Known open items (flagged for future work)

- [ ] Jan 1 – Feb 24 2026 historical backfill — no clean Gary summary exists; need to backfill by parsing ~55 SGI Extended Report attachments from Gmail
- [ ] BGaming API (not backoffice) — investigate whether the official API can replace Playwright scraping once the 404 issue is resolved
- [ ] Mar 31 2026 — Gary auto-sent a DRAFT with stale data; real numbers need to be reconstructed from SGI xlsx
- [ ] Apr 4 2026 — full day missing; Gary never generated it; need to parse SGI + Kraken for that date
- [ ] Godfather the Offer — separate line item; cross-check with Kerri @ Bangbang Games monthly
