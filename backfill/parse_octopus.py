"""
parse_octopus.py — parse Octopus/Kraken HTML email bodies saved as JSON.

Input:  raw_emails/octopus/<msgId>.json  ({"date":"YYYY-MM-DD","body":"<html...>"})
Output: parsed/octopus/<date>.json       ({"date","source","ggr_eur","rows":[...]})
"""
import json, re, os
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "pip", "install", "beautifulsoup4", "--break-system-packages", "-q"])
    from bs4 import BeautifulSoup


EUR_RE = re.compile(r'€\s*([-\d,]+\.?\d*)')

def parse_eur(text):
    """Extract first EUR value from a string like '€1,234.56 (↑ 5%)'"""
    m = EUR_RE.search(text or '')
    if not m:
        return 0.0
    return float(m.group(1).replace(',', ''))


def parse_octopus_body(body: str, date: str) -> dict:
    soup = BeautifulSoup(body, 'html.parser')

    # ── Global daily GGR ──────────────────────────────────────────────────────
    # First <table> has headers: Total Wager | Total Win | GGR | RTP | Game Count
    global_ggr = 0.0
    tables = soup.find_all('table')
    for tbl in tables:
        headers = [th.get_text(strip=True) for th in tbl.find_all('th')]
        if 'GGR' in headers and 'Total Wager' in headers and 'Game Name' not in headers:
            # Find GGR column index
            ggr_idx = headers.index('GGR')
            rows = tbl.find_all('tr')
            for row in rows[1:]:
                cells = row.find_all('td')
                if len(cells) > ggr_idx:
                    global_ggr = parse_eur(cells[ggr_idx].get_text())
                    break  # first data row is the global daily figure
            break

    # ── Per-game rows ─────────────────────────────────────────────────────────
    # Table with headers: Game Name | Total Wager | Total Win | GGR | RTP | Game Count
    game_rows = []
    for tbl in tables:
        headers = [th.get_text(strip=True) for th in tbl.find_all('th')]
        if 'Game Name' in headers and 'GGR' in headers:
            hi = {h: i for i, h in enumerate(headers)}
            for row in tbl.find_all('tr')[1:]:
                cells = row.find_all('td')
                if len(cells) < 4:
                    continue
                game_name = cells[hi.get('Game Name', 0)].get_text(strip=True)
                ggr = parse_eur(cells[hi.get('GGR', 3)].get_text())
                wager = parse_eur(cells[hi.get('Total Wager', 1)].get_text())
                if game_name and game_name.lower() not in ('total', 'totals'):
                    game_rows.append({
                        'game': game_name,
                        'source': 'octopus',
                        'ggr_eur': round(ggr, 2),
                        'rev_share_eur': round(ggr * 0.04, 2),
                        'wager_eur': round(wager, 2),
                    })
            break

    # If no per-game rows but we have a global GGR, create a synthetic row
    if not game_rows and global_ggr:
        game_rows.append({
            'game': 'Octopus (aggregate)',
            'source': 'octopus',
            'ggr_eur': round(global_ggr, 2),
            'rev_share_eur': round(global_ggr * 0.04, 2),
            'wager_eur': 0.0,
        })

    total_ggr = sum(r['ggr_eur'] for r in game_rows) if game_rows else global_ggr

    return {
        'date': date,
        'source': 'octopus',
        'ggr_eur': round(total_ggr, 2),
        'rev_share_eur': round(total_ggr * 0.04, 2),
        'rows': game_rows,
    }


def process_file(raw_path: str, out_dir: str):
    data = json.load(open(raw_path))
    date = data['date']
    body = data['body']
    parsed = parse_octopus_body(body, date)
    out = Path(out_dir) / f'{date}.json'
    json.dump(parsed, open(out, 'w'), indent=2)
    return parsed


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print("Usage: python parse_octopus.py <raw_dir> <out_dir>")
        sys.exit(1)
    raw_dir, out_dir = sys.argv[1], sys.argv[2]
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    for f in sorted(Path(raw_dir).glob('*.json')):
        result = process_file(str(f), out_dir)
        print(f"{result['date']}: GGR €{result['ggr_eur']:,.2f}  ({len(result['rows'])} games)")
