"""Fetch (cache) the Drugs@FDA approval-package TOC pages of the novel list.

Only the TOC pages are fetched; documents are not opened. Usage:
    NAM_DATA=... python -I -m studies.nam.inventory.fetch_tocs
"""
import sys
import time
import urllib.error

from . import fda
from .fetch import Fetcher

RETRY_CODES = {403, 429, 500, 502, 503, 504}


def get_with_retry(fetcher, url, tries=3, pause=30):
    for attempt in range(tries):
        try:
            return fetcher.get(url)
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRY_CODES or attempt == tries - 1:
                raise
            time.sleep(pause * (attempt + 1))


def toc_urls(novel_appl_nos, docs):
    urls = []
    for d in docs:
        if (d["ApplNo"] in novel_appl_nos
                and d["SubmissionType"].strip() == "ORIG"
                and d["ApplicationDocsTypeID"] == "3"
                and d["ApplicationDocsURL"].lower().endswith("toc.html")):
            urls.append(d["ApplicationDocsURL"])
    return sorted(set(urls))


def main():
    f = Fetcher()
    data = fda.load_datafiles(get_with_retry(f, fda.DATAFILES_URL))
    types = {t["ApplicationDocsType_Lookup_ID"]: t["ApplicationDocsType_Lookup_Description"]
             for t in data["doctypes"]}
    assert types["3"] == "Review", "doc type 3 is not Review"
    novel = set()
    for year in range(fda.FIRST_YEAR, fda.LAST_YEAR + 1):
        page = get_with_retry(f, fda.year_url(year)).read_bytes()
        page = fda.decode_body(page)
        novel |= {r["appl_no"] for r in fda.parse_novel_page(page) if r["appl_no"]}
    failed = []
    for url in toc_urls(novel, data["docs"]):
        try:
            get_with_retry(f, url)
        except urllib.error.HTTPError as exc:
            failed.append((url, exc.code))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            failed.append((url, type(exc).__name__))
    print("requests", f.requests, "failed", len(failed))
    for url, code in failed:
        print(code, url)


if __name__ == "__main__":
    sys.exit(main())
