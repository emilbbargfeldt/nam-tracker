"""List the layer 1 pages below the text-layer threshold for a1 and a2, ahead of OCR.

Read-only: nothing is fetched, no OCR is run, no text is printed. Prints counts
per part (and per document). The page numbers are written to a new file
$NAM_DATA/pilot/ocr_manifest_<tag>.json (an existing file is never overwritten).

a1 = the documents of the coded a1 draws ($NAM_DATA/a1/batch*.json).
a2 = the documents that receive the spike-ins (same choice as spikein prepare,
from the seed and the local cache; it depends on the OCR cache, so run again
after OCR until the list no longer changes, at most 2 rounds). Unlike spikein
prepare it does not refuse a dirty git tree (only the codes CSV is checked
against git HEAD, by spikein.a1_pmids).
"todo" = low pages that are not in the OCR cache yet.

Usage: NAM_DATA=... python -m studies.nam.pilot.ocr_list <tag>   (from the repo root, PYTHONPATH=.)
"""
import glob
import json
import os
import sys
from pathlib import Path

from studies.nam.extract import ocr, spikein
from studies.nam.inventory import measure, section
from studies.nam.inventory.fetch import Fetcher

PARTS = ("a1", "a2")


def a1_doc_ids(a1_dir):
    """Sorted doc ids of the a1 draws (all batches)."""
    ids = set()
    for path in sorted(glob.glob(str(Path(a1_dir) / "batch[0-9]*.json"))):
        ids |= {d["doc"] for d in json.loads(Path(path).read_text())["draws"]}
    return sorted(ids)


def collect(doc_ids, load_raw, cached):
    """[{doc, pdf, layer1, low, todo}] per document. load_raw(doc) gives
    (pdf name, layer 1 page count, low pages of the raw text layer) or None;
    cached(doc, pages) gives the subset of pages already in the OCR cache."""
    rows = []
    for doc in doc_ids:
        raw = load_raw(doc)
        if raw is None:
            rows.append({"doc": doc, "pdf": None, "layer1": 0, "low": [],
                         "todo": [], "missing": True})
            continue
        name, n_layer1, low = raw
        have = set(cached(doc, low))
        rows.append({"doc": doc, "pdf": name, "layer1": n_layer1,
                     "low": list(low), "todo": [p for p in low if p not in have]})
    return rows


def totals(rows):
    return {"documents": len(rows),
            "missing": sum(1 for r in rows if r.get("missing")),
            "layer1": sum(r["layer1"] for r in rows),
            "low": sum(len(r["low"]) for r in rows),
            "todo": sum(len(r["todo"]) for r in rows)}


def write_new(path, data):
    """Write JSON to a file that must not exist yet."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=1))
        os.link(tmp, path)  # fails if path exists: never overwrites
    except FileExistsError:
        raise FileExistsError("exists, not overwritten: %s" % path.name) from None
    finally:
        if tmp.exists():
            tmp.unlink()


def make_raw_loader(f, items):
    """load_raw(doc) and cached(doc, pages) on the local cache only."""
    def load_raw(doc):
        path = f.path_for(items[doc]["url"])
        if not path.exists():
            return None
        loc, pages = section.locate_pdf(path, items[doc]["format"])
        n = sum(hi - lo + 1 for lo, hi in loc["ranges"])
        if not pages or n == 0:
            return None  # same as spikein.make_loader: unreadable or no layer 1
        return path.name, n, section.low_pages(loc, pages)

    def cached(doc, pages):
        path = f.path_for(items[doc]["url"])
        return ocr.cached_pages(path, pages, f.root / "ocr")

    return load_raw, cached


def a2_doc_ids(f, items, load):
    """Documents of the spike-in placement (spikein.choose, nothing written)."""
    abstracts = spikein.load_abstracts(f.root / "spikeins", spikein.a1_pmids())
    chosen = spikein.choose(sorted(items), abstracts, spikein.SEED, load)
    return sorted({c["doc"] for c in chosen})


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or not (argv[0].isascii() and argv[0].isalnum()):
        print("usage: ocr_list <tag>  (letters and digits only)")
        return 2
    f = spikein.read_only_fetcher(Fetcher)()
    manifest = f.root / "pilot" / ("ocr_manifest_%s.json" % argv[0])
    if manifest.exists():
        print("manifest for this tag exists (nothing written)")
        return 2
    items, load = spikein.real_loader(f)
    load_raw, cached = make_raw_loader(f, items)
    ids = {"a1": a1_doc_ids(f.root / "a1")}
    unknown = [d for d in ids["a1"] if d not in items]
    if unknown:
        print("a1 doc ids not in the universe: %d (nothing written)" % len(unknown))
        return 2
    try:
        ids["a2"] = a2_doc_ids(f, items, load)
    except spikein.SpikeError as exc:
        print("spike-in choice failed: %s (nothing written)" % exc)
        return 2
    out = {}
    for part in PARTS:
        rows = collect(ids[part], load_raw, cached)
        out[part] = rows
        t = totals(rows)
        print("%s: documents %d (missing pdf %d), layer 1 pages %d, below %d chars %d, "
              "not in OCR cache %d" % (part, t["documents"], t["missing"], t["layer1"],
                                       measure.TEXT_LAYER_MIN_CHARS,
                                       t["low"], t["todo"]))
        for r in rows:
            if r["low"]:
                print("  %s | %d layer 1 | %d low | %d todo"
                      % (r["doc"], r["layer1"], len(r["low"]), len(r["todo"])))
    try:
        write_new(manifest, {"parts": out, "min_chars": measure.TEXT_LAYER_MIN_CHARS})
    except FileExistsError:
        print("manifest for this tag exists (nothing written)")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
