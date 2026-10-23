"""OCR the layer 1 pages below the threshold of the pilot drugs, ahead of extraction.

Prints only page numbers counts per drug: pages below the threshold before OCR,
pages replaced by OCR text, pages still below the threshold after OCR. The text
is cached in $NAM_DATA/ocr/ by the OCR module.

Usage: NAM_DATA=... python -I -m studies.nam.pilot.ocr_fill
"""
import json
import sys

from studies.nam.extract import ocr, run
from studies.nam.inventory import measure, section
from studies.nam.inventory.fetch import Fetcher
from studies.nam.inventory.fetch_tocs import get_with_retry
from studies.nam.pilot import draw


def still_low(pages, numbers, threshold=measure.TEXT_LAYER_MIN_CHARS):
    counts = section.page_counts(pages)
    return [p for p in numbers if counts[p - 1][1] < threshold]


def main():
    f = Fetcher()
    print("drug | agency | year | below before | replaced by OCR | still below after")
    total = [0, 0, 0]
    for item in json.loads(draw.OUT.read_text())["items"]:
        path = get_with_retry(f, item["url"])
        loc, raw = section.locate_pdf(path, item["format"])
        before = section.low_pages(loc, raw)
        if not before:
            continue
        pages, numbers, info = run.prepare_document(path, item["format"], f.root / "ocr")
        after = still_low(pages, numbers)
        row = (len(before), len(info["replaced"]), len(after))
        total = [a + b for a, b in zip(total, row)]
        print("%s | %s | %s | %d | %d | %d" % ((item["name"], item["authority"],
                                                 item["year"]) + row))
    print("total: below before %d, replaced %d, still below %d" % tuple(total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
