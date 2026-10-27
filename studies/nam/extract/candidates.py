"""Layer 2 run (PREREG v5): candidate pages per document and code A, B, C, D, S.

For every layer 1 document the keyword patterns of keywords.py run per page on
the layer 1 text (text layer, OCR text from the cache where it is longer).
Page numbers are 1-based, as everywhere in layer 1 (page n is pages[n - 1]).
Output has page numbers and counts only: no quote and no matched text.

Reads the local cache only (no network, no OCR is started). Output goes to
$NAM_DATA/candidates/ (one JSONL file per document, manifest.json, and
missing_text.jsonl for documents without layer 1 text or with missing OCR).
The pilot drugs are skipped. --pilot runs only them, and only if Emil's blind
codings (all 15 coder drugs filled in for A-D in coding_template.csv) are in
git HEAD; the result goes to $NAM_DATA/candidates_pilot/ and nothing about it
is printed (see DECISIONS, blinding).

stdout has aggregates only: documents, layer 1 pages, candidate pages (union of
the codes), estimated input tokens (characters / 4, as in inventory.cost, over
the whitespace-folded characters of the candidate pages; lower bound) and an
upper bound that adds, for every layer 1 page without text and without cached
OCR, the median characters per text page of the same authority (as if all of
them become candidates; the 27.3 M method imputes the same way), and the share of
layer 1 pages that have no text.

Usage: NAM_DATA=... python -m studies.nam.extract.candidates [--pilot | --v6-tokens]
(--v6-tokens: one line, token bounds of the PREREG v6 A windows; writes nothing)
"""
import csv
import hashlib
import io
import json
import re
import statistics as st
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from studies.nam.inventory import cost, measure

from . import keywords

REPO = Path(__file__).resolve().parents[3]
PREREG = REPO / "studies" / "nam" / "PREREG.md"
CODING = "studies/nam/pilot/coding_template.csv"
CODES = keywords.CODES


class BlindingError(RuntimeError):
    """--pilot is not allowed before the blind codings are committed."""


def page_codes(text):
    """Codes with at least one hit on one page of text (normalized inside
    keywords.match_page)."""
    hits = keywords.match_page(text)
    return [c for c in CODES if hits[c]]


def candidate_pages(pages, numbers):
    """({code: sorted page numbers}, union of those pages). pages: texts, page
    n at index n - 1; numbers: the layer 1 pages."""
    out = {c: [] for c in CODES}
    union = set()
    for n in sorted(numbers):
        codes = page_codes(pages[n - 1])
        for c in codes:
            out[c].append(n)
        if codes:
            union.add(n)
    return out, sorted(union)


def apply_cached_ocr(pages, low, cached):
    """(pages with cached OCR text where longer, low pages without cached OCR).
    Same rule as ocr.apply_ocr (non-blank characters)."""
    new = list(pages)
    for p in low:
        if p in cached and _chars(cached[p]) > _chars(new[p - 1]):
            new[p - 1] = cached[p]
    return new, [p for p in low if p not in cached]


def _chars(text):
    return len("".join(text.split()))


def folded_chars(text):
    return len(" ".join(text.split()))


WINDOW_LINES = 10  # PREREG v6 (a)


def a_hit_lines(text):
    """0-based indices of the raw lines of one page that hold the start of an
    A hit. Hits are found on the normalized text; an offset is mapped back to
    a line with the normalized length of the line prefixes. A hit on a word
    split at a line end can land one line off (the prefix keeps the hyphen),
    which a window of +-10 lines absorbs."""
    hits = keywords.match_page(text)["A"]
    if not hits:
        return set()
    lines = text.split("\n")
    prefix = [None] * (len(lines) + 1)

    def norm_len(k):
        if prefix[k] is None:
            prefix[k] = len(keywords._normalize("\n".join(lines[:k])))
        return prefix[k]

    out = set()
    for _, start, _ in hits:
        lo, hi = 1, len(lines)  # smallest k with norm_len(k) > start
        while lo < hi:
            mid = (lo + hi) // 2
            if norm_len(mid) > start:
                hi = mid
            else:
                lo = mid + 1
        out.add(lo - 1)
    return out


def _runs(numbers):
    """Contiguous runs of page numbers."""
    runs = []
    for n in sorted(numbers):
        if runs and runs[-1][-1] == n - 1:
            runs[-1].append(n)
        else:
            runs.append([n])
    return runs


def a_windows(pages, numbers, radius=WINDOW_LINES):
    """The A windows (PREREG v6 a): +-radius lines around every A hit,
    overlapping windows merged; a window near a page edge continues onto the
    adjacent layer 1 page (lines of a run of contiguous pages are one
    sequence). Each window is a list of segments [page, first line index on
    that page (0-based), [lines]]."""
    out = []
    for run in _runs(numbers):
        lines, owner, hits = [], [], []
        for n in run:
            page_lines = pages[n - 1].split("\n")
            hits += [len(lines) + i for i in a_hit_lines(pages[n - 1])]
            owner += [(n, i) for i in range(len(page_lines))]
            lines += page_lines
        merged = []
        for h in sorted(hits):
            lo, hi = max(0, h - radius), min(len(lines) - 1, h + radius)
            if merged and lo <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        for lo, hi in merged:
            window = []
            for k in range(lo, hi + 1):
                n, i = owner[k]
                if window and window[-1][0] == n:
                    window[-1][2].append(lines[k])
                else:
                    window.append([n, i, [lines[k]]])
            out.append(window)
    return out


def a_window_chars(pages, numbers, radius=WINDOW_LINES):
    """Whitespace-folded characters of the A windows."""
    return sum(folded_chars("\n".join(ln for _, _, lines in w for ln in lines))
               for w in a_windows(pages, numbers, radius))


def estimate_tokens(pages, union):
    return sum(cost.tokens(folded_chars(pages[p - 1])) for p in union)


def check_blind_codings(show=None):
    """Raise BlindingError unless git HEAD holds coding_template.csv with A
    exactly "0" or "1" (after strip) for all 15 coder drugs (PREREG v6: B-D
    are ignored). The error names row and column, never the value."""
    if show is None:
        def show():
            proc = subprocess.run(["git", "show", "HEAD:" + CODING], cwd=REPO,
                                  capture_output=True, text=True, timeout=60)
            return proc.stdout if proc.returncode == 0 else None
    text = show()
    if not text:
        raise BlindingError("blind codings are not in git HEAD")
    coders = pilot_coder_names()
    rows = {}
    for n, r in enumerate(csv.DictReader(io.StringIO(text)), 2):
        name = (r.get("drug") or "").strip()
        if name in rows:
            raise BlindingError("row %d repeats an earlier drug" % n)
        rows[name] = (n, r)
    for i, name in enumerate(coders, 1):
        if name not in rows:
            raise BlindingError("no row for coder drug %d of %d" % (i, len(coders)))
        n, row = rows[name]
        if (row.get("A") or "").strip() not in ("0", "1"):
            raise BlindingError("row %d column A must be 0 or 1" % n)


def pilot_coder_names():
    from studies.nam.pilot import draw
    return [i["name"] for i in json.loads(draw.OUT.read_text())["items"]
            if i["coder"]]


def pilot_keys():
    from studies.nam.pilot import draw
    return {draw.key_of(i)
            for i in json.loads(draw.OUT.read_text())["items"]}


def doc_id_of(item):
    slug = re.sub(r"[^A-Za-z0-9]+", "_", item["name"]).strip("_")[:60]
    tag = hashlib.sha256(str(item["id"]).encode()).hexdigest()[:8]
    return "%s_%s_%s_%s" % (item["authority"], item["year"], slug, tag)


def prereg_version(path=PREREG):
    found = re.findall(r"(?m)^- \d{4}-\d{2}-\d{2} version (\d+)\b",
                       Path(path).read_text())
    return max(map(int, found)) if found else None


def git_head():
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                          capture_output=True, text=True, timeout=60)
    return proc.stdout.strip()


def md5_of(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def write_document(out_dir, doc_id, authority_id, per_code):
    """One JSONL line per code: page numbers and count, nothing else."""
    lines = [{"doc": doc_id, "id": authority_id, "code": c,
              "pages": per_code[c], "n": len(per_code[c])} for c in CODES]
    path = Path(out_dir) / (doc_id + ".jsonl")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("".join(json.dumps(x) + "\n" for x in lines))
    tmp.replace(path)


def process_document(item, path, ocr_dir, out_dir, windows_only=False):
    """Run one document. Returns a stats dict, or {"reason": ...} when there is
    no layer 1 text (no PDF in the cache or no pages)."""
    from studies.nam.inventory import section
    from . import ocr
    if not Path(path).exists():
        return {"reason": "no pdf in cache"}
    loc, pages = section.locate_pdf(path, item["format"])
    numbers = [p for lo, hi in loc["ranges"] for p in range(lo, hi + 1)]
    if not pages or not numbers:
        return {"reason": "no layer 1 pages"}
    low = section.low_pages(loc, pages)
    cached = ocr.cached_pages(path, low, ocr_dir)
    pages, missing = apply_cached_ocr(pages, low, cached)
    lowset = set(low)
    text = [folded_chars(pages[p - 1]) for p in numbers if p not in lowset]
    mean = sum(text) / len(text) if text else None
    if windows_only:
        return {"pages": len(numbers), "missing": missing, "mean_text_chars": mean,
                "tokens": cost.tokens(a_window_chars(pages, numbers))}
    per_code, union = candidate_pages(pages, numbers)
    write_document(out_dir, doc_id_of(item), item["id"], per_code)
    return {"pages": len(numbers), "candidates": len(union),
            "tokens": estimate_tokens(pages, union), "missing": missing,
            "mean_text_chars": mean}


def run_all(items, fetcher, out_dir, windows_only=False):
    """Process items; returns aggregates. Writes only under out_dir. With
    windows_only (PREREG v6 token count) nothing is written and tokens are
    those of the A windows."""
    if not windows_only:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
    agg = {"documents": 0, "pages": 0, "candidate_pages": 0, "tokens": 0.0,
           "pages_without_text": 0, "documents_without_text": 0}
    means, missing_by = {}, {}
    log = []
    for item in items:
        res = process_document(item, fetcher.path_for(item["url"]),
                               fetcher.root / "ocr", out_dir, windows_only)
        doc_id = doc_id_of(item)
        if "reason" in res:
            agg["documents_without_text"] += 1
            log.append({"doc": doc_id, "reason": res["reason"]})
            continue
        agg["documents"] += 1
        agg["pages"] += res["pages"]
        agg["candidate_pages"] += res.get("candidates", 0)
        agg["tokens"] += res["tokens"]
        au = item["authority"]
        if res["mean_text_chars"] is not None:
            means.setdefault(au, []).append(res["mean_text_chars"])
        if res["missing"]:
            missing_by[au] = missing_by.get(au, 0) + len(res["missing"])
            agg["pages_without_text"] += len(res["missing"])
            log.append({"doc": doc_id, "reason": "ocr missing",
                        "pages": res["missing"]})
    agg["tokens_lower"] = agg.pop("tokens")
    pooled = [m for v in means.values() for m in v]
    agg["tokens_upper"] = agg["tokens_lower"] + sum(
        cost.tokens(n * st.median(means.get(au) or pooled))
        for au, n in missing_by.items() if pooled)
    if not windows_only:
        with open(out_dir / "missing_text.jsonl", "w") as fh:
            for r in log:
                fh.write(json.dumps(r) + "\n")
    return agg


def write_manifest(out_dir, agg, keywords_path=None):
    keywords_path = keywords_path or keywords.__file__
    manifest = {"keywords_md5": md5_of(keywords_path),
                "prereg_version": prereg_version(), "git_head": git_head(),
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "aggregates": agg}
    (Path(out_dir) / "manifest.json").write_text(json.dumps(manifest, indent=1))


def format_aggregates(agg):
    """The only text that goes to stdout for a normal run."""
    share = agg["pages_without_text"] / agg["pages"] if agg["pages"] else 0.0
    return "\n".join([
        "documents: %d" % agg["documents"],
        "layer 1 pages: %d" % agg["pages"],
        "candidate pages (union of codes): %d" % agg["candidate_pages"],
        "input tokens lower (candidate pages, chars/4): %.0f" % agg["tokens_lower"],
        "input tokens upper (+ imputed pages without OCR): %.0f"
        % agg["tokens_upper"],
        "pages without text (OCR missing): %d (%.1f %%)"
        % (agg["pages_without_text"], 100 * share),
        "documents without layer 1 text: %d" % agg["documents_without_text"],
    ])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    unknown = [a for a in argv if a not in ("--pilot", "--v6-tokens")]
    if unknown:
        print("unknown option (nothing run)")
        return 2
    pilot = "--pilot" in argv
    v6 = "--v6-tokens" in argv
    if pilot and v6:
        print("--v6-tokens is not allowed with --pilot (blinding)")
        return 2
    if pilot:
        try:
            check_blind_codings()
        except BlindingError as e:
            print("--pilot refused: %s (see DECISIONS, blinding)" % e)
            return 2
    from studies.nam.inventory.fetch import Fetcher
    from studies.nam.pilot import draw
    f = Fetcher()
    units, _ = draw.universe(f)
    keys = pilot_keys()
    items = [u for k, u in sorted(units.items()) if (k in keys) == pilot]
    skipped = sum(1 for k in units if k in keys)
    if not pilot and skipped != len(keys):
        print("stopped: pilot skipped: %d of %d (nothing written)"
              % (skipped, len(keys)))
        return 2
    if v6:
        agg = run_all(items, f, None, windows_only=True)
        print("pilot skipped: %d of %d" % (skipped, len(keys)))
        print("v6 window tokens lower / upper (chars/4): %.0f / %.0f"
              % (agg["tokens_lower"], agg["tokens_upper"]))
        return 0
    out_dir = f.root / ("candidates_pilot" if pilot else "candidates")
    agg = run_all(items, f, out_dir)
    write_manifest(out_dir, agg)
    if pilot:
        print("pilot candidates written (not shown)")
    else:
        print("pilot skipped: %d of %d" % (skipped, len(keys)))
        print(format_aggregates(agg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
