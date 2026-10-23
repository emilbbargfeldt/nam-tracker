"""Per-year FDA counts from the novel list, Drugs@FDA files and TOC flags."""
import json
import sys
import zipfile
from collections import defaultdict

from . import fda
from .fda_titles import (TocParseError, categories, has_strict_nonclinical,
                         parse_flags)
from .fetch import Fetcher

REVIEW_TYPE_IDS = ("3", "21")  # Review, Summary Review


def count_year(rows, docs_by_appl, apps, toc_pages):
    """rows: resolved novel rows of one year; toc_pages: url -> html or None."""
    c = defaultdict(int)
    detail = []
    seen = set()
    for r in rows:
        c["listed"] += 1
        a = r["appl_no"]
        if a is not None and a in seen:
            c["duplicate_appl_no"] += 1
        seen.add(a)
        rec = {"name": r["name"], "appl_no": a, "cats": [], "toc": None}
        if a is None:
            c["no_appl_no"] += 1
        elif a not in apps:
            c["not_in_drugsatfda"] += 1
        else:
            c["in_drugsatfda"] += 1
            orig = [d for d in docs_by_appl.get(a, [])
                    if d["SubmissionType"].strip() == "ORIG"
                    and d["ApplicationDocsTypeID"].strip() in REVIEW_TYPE_IDS]
            if orig:
                c["with_review_docs"] += 1
            tocs = sorted({d["ApplicationDocsURL"] for d in orig
                           if d["ApplicationDocsURL"].lower().endswith("toc.html")})
            if not tocs:
                c["no_toc"] += 1
            cats_all, ok, unparsed, missing = set(), 0, 0, 0
            for url in tocs:
                page = toc_pages.get(url)
                if page is None:
                    missing += 1
                    continue
                try:
                    cats_all |= categories(parse_flags(page))
                    ok += 1
                except TocParseError:
                    unparsed += 1
            if len(tocs) > 1:
                c["multiple_tocs"] += 1
            if ok:
                cats = cats_all
                rec["cats"] = sorted(cats)
                rec["toc"] = tocs
                c["toc_ok"] += 1
                for cat in cats:
                    c[cat] += 1
                if has_strict_nonclinical(cats):
                    c["strict_nonclinical"] += 1
                if has_strict_nonclinical(cats) or "integrated" in cats:
                    c["strict_or_integrated"] += 1
            elif unparsed:
                c["toc_unparsed"] += 1
            elif missing:
                c["toc_not_fetched"] += 1
        detail.append(rec)
    return dict(c), detail


def main():
    f = Fetcher()
    data = fda.load_datafiles(f.path_for(fda.DATAFILES_URL))
    zf = zipfile.ZipFile(f.path_for(fda.DATAFILES_URL))
    products = fda.read_tsv(zf, "Products.txt")
    apps = {a["ApplNo"] for a in data["applications"]}
    docs_by_appl = defaultdict(list)
    for d in data["docs"]:
        docs_by_appl[d["ApplNo"]].append(d)

    def page_of(url):
        p = f.path_for(url)
        return fda.decode_body(p.read_bytes()) if p.exists() else None

    result, problems = {}, []
    for year in range(fda.FIRST_YEAR, fda.LAST_YEAR + 1):
        page = fda.decode_body(f.path_for(fda.year_url(year)).read_bytes())
        rows = fda.parse_novel_page(page)
        problems += fda.validate_page(rows, year)
        rows = fda.resolve_rows(rows, year, products, data["applications"],
                                data["submissions"])
        toc_pages = {d["ApplicationDocsURL"]: page_of(d["ApplicationDocsURL"])
                     for r in rows if r["appl_no"]
                     for d in docs_by_appl.get(r["appl_no"], [])
                     if d["ApplicationDocsURL"].lower().endswith("toc.html")}
        counts, detail = count_year(rows, docs_by_appl, apps, toc_pages)
        counts["notes"] = sum(1 for r in rows if r["notes"])
        result[year] = {"counts": counts, "detail": detail}
    out = f.root / "derived" / "fda_counts.json"
    out.write_text(json.dumps({"years": result, "problems": problems}, indent=1))
    print(json.dumps({y: v["counts"] for y, v in result.items()}, indent=1))
    print("problems", problems)


if __name__ == "__main__":
    sys.exit(main())
