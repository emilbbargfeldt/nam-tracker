"""Count pages below the text-layer threshold inside layer 1, per pilot drug.

Prints only the number per drug. The page numbers are saved to
$NAM_DATA/pilot/lowtext.json for the OCR step. No text is read or printed.

Usage: NAM_DATA=... python -I -m studies.nam.pilot.lowtext
"""
import json
import sys

from studies.nam.inventory import measure, section
from studies.nam.inventory.fetch import Fetcher
from studies.nam.inventory.fetch_tocs import get_with_retry
from studies.nam.pilot import draw
from studies.nam.extract.run import doc_id_of


def main():
    f = Fetcher()
    out = {}
    print("drug | agency | year | layer 1 pages | pages below %d characters"
          % measure.TEXT_LAYER_MIN_CHARS)
    for item in json.loads(draw.OUT.read_text())["items"]:
        path = get_with_retry(f, item["url"])
        loc, pages = section.locate_pdf(path, item["format"])
        low = section.low_pages(loc, pages)
        n = sum(hi - lo + 1 for lo, hi in loc["ranges"])
        out[doc_id_of(item)] = {"ranges": loc["ranges"], "low": low}
        print("%s | %s | %s | %d | %d" % (item["name"], item["authority"],
                                          item["year"], n, len(low)))
    (f.root / "pilot" / "lowtext.json").write_text(json.dumps(out, indent=1))
    print("drugs with low-text pages: %d of %d; pages: %d" % (
        sum(1 for v in out.values() if v["low"]), len(out),
        sum(len(v["low"]) for v in out.values())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
