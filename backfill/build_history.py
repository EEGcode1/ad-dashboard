"""
Convert parsed/octopus/*.json into data/history/YYYY-MM-DD.json
Each history file follows the format expected by build_data.py:
  { "day": { "date": "...", "rows": [...] } }

Rows include a 'date' field so _daily_series can group them.
"""
import json
from pathlib import Path

OCTOPUS_DIR = Path('/tmp/ad-dashboard/backfill/parsed/octopus')
HISTORY_DIR = Path('/tmp/ad-dashboard/data/history')
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

created = 0
for f in sorted(OCTOPUS_DIR.glob('*.json')):
    date = f.stem
    parsed = json.loads(f.read_text())

    # Add 'date' to each row so _daily_series works
    rows = []
    for r in parsed.get('rows', []):
        row = dict(r)
        row['date'] = date
        row['net_revenue_eur'] = 0.0
        row['win_eur'] = 0.0
        rows.append(row)

    # If no per-game rows, make one aggregate row
    if not rows and parsed.get('ggr_eur', 0):
        rows = [{
            'date': date,
            'source': 'octopus',
            'game': 'Octopus (aggregate)',
            'ggr_eur': parsed['ggr_eur'],
            'rev_share_eur': parsed['rev_share_eur'],
            'wager_eur': 0.0,
            'net_revenue_eur': 0.0,
            'win_eur': 0.0,
        }]

    hist = {'day': {'date': date, 'rows': rows}}

    out_path = HISTORY_DIR / f'{date}.json'
    if not out_path.exists():
        out_path.write_text(json.dumps(hist, indent=2))
        created += 1
        print(f'  {date}: {len(rows)} rows, GGR €{parsed["ggr_eur"]:,.2f}')

print(f'\nCreated {created} history files. Total: {len(list(HISTORY_DIR.glob("*.json")))}')
