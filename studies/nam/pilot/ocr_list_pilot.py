"""Count the layer 1 pages of the 30 pilot drugs below the text-layer threshold.

Read-only: nothing is fetched, no OCR is run, nothing is written (no manifest)
and no text or per-document line is printed. Prints the document and page totals, then: pages below
the threshold (100 non-blank characters in the raw text layer), of these in the
OCR cache, and of these not in the OCR cache yet (todo). These are input
metadata, not extraction output.

Usage: NAM_DATA=... PYTHONPATH=. python -m studies.nam.pilot.ocr_list_pilot
"""
import json
import sys

from studies.nam.extract import candidates, spikein
from studies.nam.inventory import measure
from studies.nam.inventory.fetch import Fetcher
from studies.nam.pilot import draw, ocr_list


def pilot_counts(items, load_raw, cached):
    """{documents, missing, layer1, low, in_cache, todo} for {doc id: unit}."""
    t = ocr_list.totals(ocr_list.collect(sorted(items), load_raw, cached))
    t["in_cache"] = t["low"] - t["todo"]
    return t


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        print("usage: ocr_list_pilot (no arguments; nothing written)")
        return 2
    f = spikein.read_only_fetcher(Fetcher)()
    items = {candidates.doc_id_of(i): i
             for i in json.loads(draw.OUT.read_text())["items"]}
    load_raw, cached = ocr_list.make_raw_loader(f, items)
    t = pilot_counts(items, load_raw, cached)
    print("pilot: documents %d (missing pdf %d), layer 1 pages %d" %
          (t["documents"], t["missing"], t["layer1"]))
    print("below %d chars before OCR %d, in OCR cache %d, todo %d" %
          (measure.TEXT_LAYER_MIN_CHARS, t["low"], t["in_cache"], t["todo"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
