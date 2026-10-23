"""Material for Emil's blind coding of 15 pilot drugs.

Writes the coding template (one row per drug) and, per drug, a PDF with the
layer 1 pages, into $NAM_DATA/pilot/emil/. Only drug, agency, year and page
numbers are printed. The PDFs are public documents downloaded read-only.

Usage: NAM_DATA=... python -I -m studies.nam.pilot.coder
"""
import csv
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from studies.nam.inventory import section
from studies.nam.inventory.fetch import Fetcher
from studies.nam.inventory.fetch_tocs import get_with_retry
from studies.nam.pilot import draw

COLUMNS = ["drug", "agency", "year", "A", "B", "C", "D", "A_pages", "B_pages",
           "C_pages", "D_pages", "species", "species_pages", "notes"]
TEMPLATE = Path(__file__).with_name("coding_template.csv")
LONG = 150


def coder_items(pilot):
    items = [i for i in pilot if i.get("coder")]
    return sorted(items, key=lambda i: (i["authority"], i["year"], i["name"]))


def write_template(path, items):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(COLUMNS)
        for i in items:
            w.writerow([i["name"], i["authority"], i["year"]] + [""] * (len(COLUMNS) - 3))


def pdf_name(item):
    name = re.sub(r"[^A-Za-z0-9]+", "_", item["name"]).strip("_")
    return "%s_%s_%s.pdf" % (item["authority"], item["year"], name)


def page_list(ranges):
    return [p for lo, hi in ranges for p in range(lo, hi + 1)]


def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError("%s failed" % cmd[0])


def extract_pages(src, dst, pages):
    """Write the given 1-based pages of src, in order, to dst."""
    with tempfile.TemporaryDirectory() as tmp:
        _run(["pdfseparate", "-f", str(min(pages)), "-l", str(max(pages)),
              str(src), "%s/p-%%d.pdf" % tmp])
        parts = ["%s/p-%d.pdf" % (tmp, p) for p in pages]
        if len(parts) == 1:
            Path(parts[0]).replace(dst)
        else:
            _run(["pdfunite"] + parts + [str(dst)])


def main():
    f = Fetcher()
    pilot = json.loads(draw.OUT.read_text())["items"]
    items = coder_items(pilot)
    write_template(TEMPLATE, items)
    out_dir = f.root / "pilot" / "emil"
    out_dir.mkdir(parents=True, exist_ok=True)
    total = long_docs = 0
    print("drug | agency | year | pages (ranges) | n pages")
    for i in items:
        src = get_with_retry(f, i["url"])
        loc, _ = section.locate_pdf(src, i["format"])
        pages = page_list(loc["ranges"])
        extract_pages(src, out_dir / pdf_name(i), pages)
        total += len(pages)
        long_docs += len(pages) > LONG
        print("%s | %s | %s | %s | %d%s" % (
            i["name"], i["authority"], i["year"],
            ",".join("%d-%d" % tuple(r) for r in loc["ranges"]), len(pages),
            "  > %d" % LONG if len(pages) > LONG else ""))
    print("total pages %d | documents over %d pages: %d" % (total, LONG, long_docs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
