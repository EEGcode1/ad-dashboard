"""
Renderer — copies data.json next to each HTML page in site/.

The three HTML files (index.html, lnw.html, tidal.html) are
written directly by this repo; they fetch data.json at page-load
time via a relative path, so we just need to ensure data.json is
present in site/. A build stamp is written to a separate meta file
so we don't have to template the HTML files themselves.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_JSON = REPO_ROOT / "data" / "data.json"
SITE_DIR  = REPO_ROOT / "site"
OUT_DATA  = SITE_DIR / "data.json"
STAMP_FILE = SITE_DIR / "build_stamp.txt"


def main() -> int:
    if not DATA_JSON.exists():
        raise SystemExit(f"Missing {DATA_JSON}. Run build_data.py first.")

    SITE_DIR.mkdir(parents=True, exist_ok=True)

    # Copy data.json into site/ for GitHub Pages to serve
    shutil.copyfile(DATA_JSON, OUT_DATA)

    # Validate JSON (catch corrupt writes early)
    json.loads(OUT_DATA.read_text())

    # Stamp file — read by CI to confirm render ran
    build_stamp = datetime.now(timezone.utc).isoformat()
    STAMP_FILE.write_text(build_stamp + "\n")

    print(f"Rendered site/ (stamp {build_stamp})")
    print(f"  data.json    → {OUT_DATA}")
    print(f"  index.html   → {SITE_DIR / 'index.html'}")
    print(f"  lnw.html     → {SITE_DIR / 'lnw.html'}")
    print(f"  tidal.html   → {SITE_DIR / 'tidal.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
