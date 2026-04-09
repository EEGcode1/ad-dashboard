"""
Parse all Octopus gmail_read_message tool-result files into dated JSONs.
Uses date from EMAIL BODY (the 'for DD-MM-YYYY' in the report) -- NOT receipt date.
Skips dates already parsed.
"""
import glob, json, re, os, sys
from pathlib import Path

sys.path.insert(0, '/tmp/ad-dashboard/backfill')
from parse_octopus import parse_octopus_body

RESULTS_DIR = '/sessions/admiring-friendly-bardeen/mnt/.claude/projects/-sessions-admiring-friendly-bardeen/c67834bf-0083-4993-ac11-68e50cb94ad2/tool-results/'
OUT_DIR = '/tmp/ad-dashboard/backfill/parsed/octopus/'

Path(OUT_DIR).mkdir(parents=True, exist_ok=True)

pattern = RESULTS_DIR + 'mcp-abbe7b42-ec87-4016-95f8-5818fc9d163d-gmail_read_message-*.txt'
files = sorted(glob.glob(pattern))
print(f"Found {len(files)} result files")

processed = 0
skipped = 0
errors = 0

for fpath in files:
    try:
        raw = open(fpath).read()
        data = json.loads(raw)
        text = data[0]['text'] if data and isinstance(data[0], dict) else ''
        msg = json.loads(text)

        msg_id = msg.get('messageId', '')
        snippet = msg.get('snippet', '') or ''

        # ALWAYS extract date from email body ("for DD-MM-YYYY")
        date = None
        m = re.search(r'Daily Revenue for (\d{2}-\d{2}-\d{4})', snippet)
        if m:
            raw_date = m.group(1)
            d, mo, y = raw_date.split('-')
            date = f'{y}-{mo}-{d}'

        if not date:
            body = msg.get('body', '') or ''
            m = re.search(r'Daily Revenue for (\d{2}-\d{2}-\d{4})', body[:2000])
            if m:
                raw_date = m.group(1)
                d, mo, y = raw_date.split('-')
                date = f'{y}-{mo}-{d}'

        if not date:
            # Skip monthly/other emails
            continue

        out_path = Path(OUT_DIR) / f'{date}.json'
        if out_path.exists():
            skipped += 1
            continue

        body = msg.get('body', '') or ''
        if not body:
            print(f"  SKIP (no body): {date}")
            continue

        parsed = parse_octopus_body(body, date)
        json.dump(parsed, open(out_path, 'w'), indent=2)
        print(f"  {date}: GGR EUR{parsed['ggr_eur']:,.2f}  ({len(parsed['rows'])} games)")
        processed += 1

    except Exception as e:
        import traceback
        print(f"  ERROR {os.path.basename(fpath)}: {e}")
        errors += 1

print(f"\nDone: {processed} new, {skipped} skipped, {errors} errors")
print(f"Total in output: {len(list(Path(OUT_DIR).glob('*.json')))}")
print(f"\nDate range: {sorted(Path(OUT_DIR).glob('*.json'))[0].stem} -> {sorted(Path(OUT_DIR).glob('*.json'))[-1].stem}")
