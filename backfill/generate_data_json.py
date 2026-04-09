"""
Generate data/data.json from history snapshots (Octopus only for now).
Mirrors the logic of build/build_data.py but standalone,
working directly from history files.
"""
from __future__ import annotations
import json, sys
from collections import defaultdict
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

HISTORY_DIR = Path('/tmp/ad-dashboard/data/history')
DATA_JSON = Path('/tmp/ad-dashboard/data/data.json')

TODAY = date.today()

# Effective LNW GP rate derived from actual monthly supplier statements
# Oct 25: 3.94%, Nov 25: 5.02%, Dec 25: 4.79%, Jan 26: 3.77% → average 4.38%
LNW_EFFECTIVE_RATE = 0.0438

def lnw_rev_share(row: dict) -> float:
    """Return LNW rev share: use actual rate applied to GGR."""
    return (row.get('ggr_eur') or 0) * LNW_EFFECTIVE_RATE

def load_history(from_d: str, to_d: str) -> list[dict]:
    rows = []
    for snap in sorted(HISTORY_DIR.glob('*.json')):
        d = snap.stem
        if from_d <= d <= to_d:
            payload = json.loads(snap.read_text())
            rows.extend(payload.get('day', {}).get('rows', []))
    return rows

def aggregate(rows, source_filter=None):
    if source_filter:
        rows = [r for r in rows if r.get('source') == source_filter]
    game_map = defaultdict(lambda: {'wager_eur':0.0,'ggr_eur':0.0,'rev_share_eur':0.0,'net_revenue_eur':0.0,'win_eur':0.0})
    for r in rows:
        k = (r.get('source',''), r.get('game',''))
        g = game_map[k]
        for field in ('wager_eur','ggr_eur','rev_share_eur','net_revenue_eur','win_eur'):
            g[field] += r.get(field) or 0.0
    by_game = []
    for (src, game), g in sorted(game_map.items(), key=lambda x: -x[1]['ggr_eur']):
        by_game.append({'source':src,'game':game,**{k:round(v,2) for k,v in g.items()}})
    return {'by_game': by_game, 'totals': compute_totals(rows)}

def compute_totals(rows):
    lnw = sum(lnw_rev_share(r) for r in rows if r.get('source')=='lnw')
    oct_ = sum(r.get('rev_share_eur') or 0 for r in rows if r.get('source')=='octopus')
    bg = sum(r.get('rev_share_eur') or 0 for r in rows if r.get('source')=='bgaming')
    cc = sum(r.get('net_revenue_eur') or 0 for r in rows if r.get('source')=='crowncoins')
    return {
        'lnw_rev_share_eur': round(lnw,2),
        'octopus_rev_share_eur': round(oct_,2),
        'bgaming_rev_share_eur': round(bg,2),
        'crowncoins_net_revenue_eur': round(cc,2),
        'regulated_total_eur': round(lnw,2),
        'tidal_total_eur': round(oct_+bg+cc,2),
        'combined_total_eur': round(lnw+oct_+bg+cc,2),
    }

def daily_series(rows):
    by_date = defaultdict(lambda: {'lnw':0.0,'octopus':0.0,'bgaming':0.0,'crowncoins':0.0})
    for r in rows:
        d = r.get('date','')
        src = r.get('source','')
        if src == 'lnw':
            by_date[d]['lnw'] += lnw_rev_share(r)
        elif src in ('octopus','bgaming'):
            by_date[d][src] += r.get('rev_share_eur') or 0
        elif src == 'crowncoins':
            by_date[d]['crowncoins'] += r.get('net_revenue_eur') or 0
    series = []
    for d in sorted(by_date):
        v = by_date[d]
        series.append({
            'date': d,
            'lnw': round(v['lnw'],2),
            'octopus': round(v['octopus'],2),
            'bgaming': round(v['bgaming'],2),
            'crowncoins': round(v['crowncoins'],2),
            'tidal': round(v['octopus']+v['bgaming']+v['crowncoins'],2),
            'combined': round(sum(v.values()),2),
        })
    return series

def mtd_cumulative(series):
    cum = {'lnw':0.0,'tidal':0.0,'combined':0.0}
    out = []
    for day in series:
        cum['lnw'] += day['lnw']
        cum['tidal'] += day['tidal']
        cum['combined'] += day['combined']
        out.append({'date':day['date'],'lnw_cum':round(cum['lnw'],2),'tidal_cum':round(cum['tidal'],2),'combined_cum':round(cum['combined'],2)})
    return out

# Covered date = latest history file date
covered = sorted(HISTORY_DIR.glob('*.json'))[-1].stem if list(HISTORY_DIR.glob('*.json')) else TODAY.isoformat()

# Yesterday's day data
day_snap_path = HISTORY_DIR / f'{covered}.json'
day_rows = json.loads(day_snap_path.read_text()).get('day',{}).get('rows',[]) if day_snap_path.exists() else []

# Week (last 7 days ending at covered)
covered_dt = date.fromisoformat(covered)
week_from = (covered_dt - timedelta(days=6)).isoformat()
week_rows = load_history(week_from, covered)
week_series = daily_series(week_rows)
week_agg = aggregate(week_rows)

# MTD
mtd_from = covered_dt.replace(day=1).isoformat()
mtd_rows = load_history(mtd_from, covered)
mtd_series = daily_series(mtd_rows)
mtd_cum = mtd_cumulative(mtd_series)
mtd_agg = aggregate(mtd_rows)

# All-time series (for charts)
all_rows = load_history('2000-01-01', '2099-12-31')
all_series = daily_series(all_rows)

payload = {
    'generated_at_utc': datetime.now(timezone.utc).isoformat(),
    'sources': {
        'lnw':       {'name':'lnw','ok':True,'error':None,'row_count':len([r for r in all_rows if r.get('source')=='lnw']),'last_run_utc':datetime.now(timezone.utc).isoformat(),'covered_date':max((r.get('date','') for r in all_rows if r.get('source')=='lnw'), default=None)},
        'octopus':   {'name':'octopus','ok':True,'error':None,'row_count':len(day_rows),'last_run_utc':datetime.now(timezone.utc).isoformat(),'covered_date':covered},
        'bgaming':   {'name':'bgaming','ok':False,'error':'not yet configured','row_count':0,'last_run_utc':'','covered_date':None},
        'crowncoins':{'name':'crowncoins','ok':False,'error':'not yet configured','row_count':0,'last_run_utc':'','covered_date':None},
        'godfather': {'name':'godfather','ok':False,'error':'xlsx downloads unavailable','row_count':0,'last_run_utc':'','covered_date':None},
    },
    'day': {
        'date': covered,
        'rows': day_rows,
        'totals': compute_totals(day_rows),
    },
    'week': {
        'from': week_from,
        'to': covered,
        'by_game': week_agg['by_game'],
        'by_day': week_series,
        'totals': week_agg['totals'],
    },
    'mtd': {
        'month': covered_dt.strftime('%Y-%m'),
        'by_game': mtd_agg['by_game'],
        'by_day': mtd_series,
        'cumulative': mtd_cum,
        'totals': mtd_agg['totals'],
    },
    'all': {
        'by_day': all_series,
    },
    'godfather': None,
}

DATA_JSON.write_text(json.dumps(payload, indent=2) + '\n')
print(f'Written {DATA_JSON}')
print(f'Covered date: {covered}')
print(f'Day rows: {len(day_rows)}')
print(f'MTD octopus rev share: €{payload["mtd"]["totals"]["octopus_rev_share_eur"]:,.2f}')
print(f'All-time octopus GGR (from series total):')
total_oct = sum(d["octopus"] for d in all_series)
print(f'  Rev share: €{total_oct:,.2f}')
