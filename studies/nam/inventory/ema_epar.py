"""Find the public assessment report (EPAR) link on each medicine page.

Only the medicine page is fetched (cached); the report itself is not opened
here. Usage: NAM_DATA=... python -I -m studies.nam.inventory.ema_epar
"""
import json
import re
import sys
import urllib.error

from . import ema, fda
from .fetch import Fetcher
from .fetch_tocs import get_with_retry
from .xlsx import read_xlsx

BASE = "https://www.ema.europa.eu"
_REPORT = re.compile(r'href="(/en/documents/assessment-report/[^"]+_en\.pdf)"')
_PUBLIC = "epar-public-assessment-report"


def report_link(page):
    """English public assessment report (EPAR) link on a medicine page.

    Only a link named *-epar-public-assessment-report_en.pdf counts; any other
    assessment-report link is ignored. Returns None when there is none.
    """
    for path in _REPORT.findall(page):
        if _PUBLIC in path:
            return BASE + path
    return None


def main():
    f = Fetcher()
    table = ema.load_table(read_xlsx(get_with_retry(f, ema.TABLE_URL).read_bytes()))
    nas, _ = ema.new_active_substances(table)
    nas = [r for r in nas if 2015 <= r["date"].year <= 2026]
    out, failed = [], []
    for r in nas:
        link, err = None, None
        try:
            page = fda.decode_body(get_with_retry(f, r["url"]).read_bytes())
            link = report_link(page)
        except (urllib.error.URLError, ValueError, OSError) as exc:
            err = type(exc).__name__
            failed.append(r["url"])
        out.append({"name": r["name"], "date": str(r["date"]),
                    "year": r["date"].year, "status": r["status"],
                    "url": r["url"], "report": link, "error": err})
    path = f.root / "derived" / "ema_epar.json"
    path.write_text(json.dumps(out, indent=1))
    print("requests", f.requests, "failed", len(failed))


if __name__ == "__main__":
    sys.exit(main())
