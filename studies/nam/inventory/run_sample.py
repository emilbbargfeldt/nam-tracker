"""Draw, download and measure the stratified sample (2 per year per authority).

Measures only: pages, text-layer share, file size; plus, for FDA Integrated
Reviews, a yes/no/unknown for a non-clinical section from bookmarks or
headings. Usage: NAM_DATA=... python -I -m studies.nam.inventory.run_sample

Known limitation: sample.json is written once per authority-year stratum, but
a crash in the middle of a stratum loses that stratum (rerun is cheap, every
download is cached).
"""
import json
import subprocess
import sys
import urllib.error
import zipfile
from collections import defaultdict

from . import fda, fda_sample, measure, outline, sample
from .fetch import Fetcher
from .fetch_tocs import get_with_retry

PER_STRATUM = 2
CAUGHT = (urllib.error.URLError, ValueError, OSError, RuntimeError,
          measure.MeasureError, subprocess.TimeoutExpired)


def fda_candidates(f):
    """{year: {appl_no: (status, payload)}} for drugs found in Drugs@FDA."""
    data = fda.load_datafiles(f.path_for(fda.DATAFILES_URL))
    products = fda.read_tsv(zipfile.ZipFile(f.path_for(fda.DATAFILES_URL)),
                            "Products.txt")
    apps = {a["ApplNo"] for a in data["applications"]}
    docs = defaultdict(list)
    for d in data["docs"]:
        docs[d["ApplNo"]].append(d)
    out, excluded = {}, {}
    for year in range(fda.FIRST_YEAR, fda.LAST_YEAR + 1):
        rows = fda.resolve_rows(
            fda.parse_novel_page(fda.decode_body(f.path_for(fda.year_url(year)).read_bytes())),
            year, products, data["applications"], data["submissions"])
        cands = {}
        excluded[year] = 0
        for r in rows:
            a = r["appl_no"]
            if not a or a not in apps:
                excluded[year] += 1  # not in Drugs@FDA or no application number
                continue
            urls = sorted({d["ApplicationDocsURL"] for d in docs.get(a, [])
                           if d["SubmissionType"].strip() == "ORIG"
                           and d["ApplicationDocsTypeID"].strip() == "3"
                           and d["ApplicationDocsURL"].lower().endswith("toc.html")})
            tocs = []
            for u in urls:
                p = f.path_for(u)
                tocs.append((u, fda.decode_body(p.read_bytes()) if p.exists() else None))
            cands[a] = fda_sample.resolve_candidate(r["name"], tocs)
        out[year] = cands
    return out, excluded


def ema_candidates(path):
    out = defaultdict(dict)
    for r in json.loads(path.read_text()):
        out[r["year"]][r["url"]] = (
            ("ok", (r["name"], r["report"], "epar")) if r["report"] else ("none", None))
    return out


def run_stratum(authority, year, cands, fetch, measure_fn, outline_fn,
                k=PER_STRATUM, excluded=0):
    """Walk the seeded order; status none -> skipped, error -> logged and
    skipped, ok -> download and measure (failures logged, next one drawn)."""
    picked, none, errors = [], [], []
    for key in sample.order(list(cands), authority, year):
        if len(picked) == k:
            break
        status, payload = cands[key]
        if status == "none":
            none.append(key)
            continue
        if status == "error":
            errors.append({"id": key, "error": payload})
            continue
        name, url, fmt = payload
        try:
            path = fetch(url)
            m = measure_fn(path)
        except CAUGHT as exc:
            errors.append({"id": key, "error": type(exc).__name__})
            continue
        nc = None
        if fmt == "integrated":
            try:
                nc = outline_fn(path)
            except CAUGHT as exc:  # the document is kept; verdict unknown
                nc = {"verdict": "unknown", "basis": type(exc).__name__,
                      "n_items": 0, "n_matches": 0}
        rec = {"authority": authority, "year": year, "id": key, "name": name,
               "format": fmt, "url": url, "pages": m["pages"],
               "text_pages": m["text_pages"], "text_share": m["text_share"],
               "size_bytes": m["size_bytes"],
               "chars_per_page": m["chars_per_page"]}
        if nc is not None:
            rec["nonclinical_section"] = nc
        picked.append(rec)
    return {"authority": authority, "year": year, "picked": picked,
            "none": none, "errors": errors, "not_in_drugsatfda": excluded}


def main():
    f = Fetcher()
    fetch = lambda url: get_with_retry(f, url)
    out_path = f.root / "derived" / "sample.json"
    results = []

    def save():
        out_path.write_text(json.dumps(results, indent=1))

    fda_c, fda_excl = fda_candidates(f)
    for year, cands in fda_c.items():
        results.append(run_stratum("FDA", year, cands, fetch, measure.measure,
                                   outline.check, excluded=fda_excl[year]))
        save()
    ema = ema_candidates(f.root / "derived" / "ema_epar.json")
    for year in range(2015, 2027):
        results.append(run_stratum("EMA", year, ema.get(year, {}), fetch,
                                   measure.measure, outline.check))
        save()
    print("requests", f.requests)


if __name__ == "__main__":
    sys.exit(main())
