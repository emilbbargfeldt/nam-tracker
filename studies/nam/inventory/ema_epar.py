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
_PUBLIC = "epar-public-assessment-report"


_DOC = re.compile(r'href="(/en/documents/([a-z-]+)/([^"/]+))"')
_SUFFIX = r"(?:-\d+)?"
_PUBLIC_NAME = re.compile(r"-public-assessment-report_en\.pdf" + _SUFFIX + "$")
_EPAR_PUBLIC_NAME = re.compile(r"-epar-public-assessment-report_en\.pdf" + _SUFFIX + "$")
_PLAIN_NAME = re.compile(r"-assessment-report_en\.pdf" + _SUFFIX + "$")
# Names of variation, post-authorisation and similar reports. Applied to the
# fallback tiers only; tier 1 is the original rule and stays as it was.
_NOT_INITIAL = re.compile(r"variation|-vr-|-pam-|-h-c-\d|-ii-\d")


def report_link(page):
    """English public assessment report (EPAR) link on a medicine page.

    Tiers, first hit wins (the first tier is the original rule and keeps every
    earlier result unchanged);
     1. folder assessment-report, name has epar-public-assessment-report, ends _en.pdf
     2. folder assessment-report, name ends public-assessment-report_en.pdf,
        with or without epar- and with an optional -N suffix
     3. folder assessment-report, name ends assessment-report_en.pdf
     4. any other folder (including variation-report, where EMA files some
        initial reports, e.g. Tuzulby), name ends epar-public-assessment-report_en.pdf
    Tiers 2-4 skip names that look like variation or post-authorisation
    reports (variation, -vr-, -pam-, -h-c-<digit>, -ii-<digit>).
    Returns None when there is none.
    """
    found = _DOC.findall(page)
    tiers = [
        lambda f, n: f == "assessment-report" and _PUBLIC in n and n.endswith("_en.pdf"),
        lambda f, n: f == "assessment-report" and _PUBLIC_NAME.search(n) and not _NOT_INITIAL.search(n),
        lambda f, n: f == "assessment-report" and _PLAIN_NAME.search(n) and not _NOT_INITIAL.search(n),
        lambda f, n: _EPAR_PUBLIC_NAME.search(n) and not _NOT_INITIAL.search(n),
    ]
    for ok in tiers:
        for path, folder, name in found:
            if ok(folder, name):
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
