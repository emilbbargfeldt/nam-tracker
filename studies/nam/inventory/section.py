"""Layer 1: page range of the non-clinical section (outcome-neutral).

Located by PDF bookmarks, else by heading-like lines, using the section-title
words of outline.py (no codebook words). A separate non-clinical review is the
non-clinical section as a whole. If the section cannot be located, the whole
document is passed on and logged (PREREG v3 b). Only page numbers and
character counts leave this module; no text is printed or stored.

Rule (one rule for every format, fixed before the rerun; it replaces the
numbered-first choice of the first run, which could pick a labelling line
instead of the section, and a one-page sub-heading in Integrated Reviews):
 - The section is the union of every match of the section-title words. Table
   of contents lines never count.
 - Bookmarks: each matching bookmark (title of at most 90 characters, as for
   headings; a long title that merely lists review types or is a sentence is
   not a section title) runs from its page to the page of the
   next bookmark at the same or a shallower level (that page is included),
   else to the last page.
 - Headings: each heading-like line (<= 90 characters) with a title word runs
   from its page to the page of the first later numbered heading at the same
   or a higher level (higher number, first number at most one higher); a
   sub-heading never ends it. For an unnumbered match the end is the first
   later heading beginning with "Clinical". Else the last page.
 - Formats "separate" and "pharmtox" (a separate non-clinical review) are the
   section as a whole: the document is the non-clinical review.
Overlapping and adjacent ranges are merged.

Usage: NAM_DATA=... python -I -m studies.nam.inventory.section
"""
import json
import re
import subprocess
import sys
from collections import Counter

from . import measure, outline
from .fetch import Fetcher

_TOKEN = re.compile(r'<(/?)outline>|<item[^>]*?page="(\d+)"[^>]*>(.*?)</item>', re.S)
_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+\S")
_CLINICAL = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?clinical\b", re.I)
WHOLE_DOCUMENT = ("separate", "pharmtox")
_TOC_LINE = re.compile(r"\.{4,}|(?:\.\s){3,}|\s\d{1,4}\s*$")


def parse_outline(xml):
    """[(level, page, title)] in document order; level 1 = top."""
    depth, items = 0, []
    for m in _TOKEN.finditer(xml):
        if m.group(3) is None:
            depth += -1 if m.group(1) else 1
        else:
            title = re.sub(r"<[^>]+>", "", m.group(3)).strip()
            items.append((max(depth, 1), int(m.group(2)), title))
    return items


def merge(ranges):
    """Sorted, overlapping or adjacent (start, end) ranges merged."""
    out = []
    for lo, hi in sorted(ranges):
        if out and lo <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def from_bookmarks(items, n_pages):
    """([(start, end)], n_matches) or None."""
    hits = [i for i, (_, _, t) in enumerate(items)
            if len(t) <= outline.MAX_HEADING_LEN and outline.title_matches(t)]
    if not hits:
        return None
    ranges = []
    for first in hits:
        level, start = items[first][0], items[first][1]
        end = n_pages
        for lvl, page, _ in items[first + 1:]:
            if lvl <= level:
                end = page
                break
        if end < start:
            end = n_pages
        ranges.append((start, min(max(end, start), n_pages)))
    return merge(ranges), len(hits)


def _number(line):
    m = _NUMBER.match(line)
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def _ends(num, cand):
    """A numbered heading cand ends a section that starts at num: later, at the
    same or a higher level, first number at most one higher."""
    return (cand is not None and len(cand) <= len(num) and cand > num
            and cand[0] <= num[0] + 1)


def _heading_lines(pages):
    """[(page, line)] of short lines, 1-based pages."""
    out = []
    for pno, text in enumerate(pages, 1):
        for ln in text.splitlines():
            if 0 < len(ln.strip()) <= outline.MAX_HEADING_LEN:
                out.append((pno, ln))
    return out


def from_headings(pages):
    """([(start, end)], n_matches) or None."""
    lines = _heading_lines(pages)
    hits = [i for i, (_, ln) in enumerate(lines)
            if outline._HEADING.match(ln) and not _TOC_LINE.search(ln)]
    if not hits:
        return None
    ranges = []
    for first in hits:
        start, line = lines[first]
        num = _number(line)
        end = len(pages)
        for pno, ln in lines[first + 1:]:
            if _TOC_LINE.search(ln):
                continue
            ok = bool(_CLINICAL.match(ln)) if num is None else _ends(num, _number(ln))
            if ok:
                end = pno
                break
        ranges.append((start, min(max(end, start), len(pages))))
    return merge(ranges), len(hits)


def locate(fmt, xml, pages):
    """Return dict(found, basis, ranges, start, end, n_matches); start and end
    are the first and last page of the ranges."""
    n = len(pages)
    if fmt in WHOLE_DOCUMENT:
        return _loc(True, "document type", [(1, n)], 0)
    tries = [("bookmarks", lambda: from_bookmarks(parse_outline(xml), n)),
             ("headings", lambda: from_headings(pages))]
    for basis, fn in tries:
        res = fn()
        if res:
            return _loc(True, basis, res[0], res[1])
    return _loc(False, "not found", [(1, n)], 0)


def _loc(found, basis, ranges, n_matches):
    return {"found": found, "basis": basis, "ranges": [list(r) for r in ranges],
            "start": ranges[0][0], "end": ranges[-1][1], "n_matches": n_matches}


def page_counts(pages):
    """Per page: (characters with whitespace folded, non-blank characters)."""
    return [(len(" ".join(p.split())), len("".join(p.split()))) for p in pages]


def low_pages(loc, pages, threshold=measure.TEXT_LAYER_MIN_CHARS):
    """Page numbers inside the ranges of loc with fewer non-blank characters
    than the threshold."""
    counts = page_counts(pages)
    return [p for lo, hi in loc["ranges"] for p in range(lo, hi + 1)
            if counts[p - 1][1] < threshold]


def summarize(loc, pages, threshold=measure.TEXT_LAYER_MIN_CHARS):
    counts = page_counts(pages)
    sec = [counts[p - 1] for lo, hi in loc["ranges"] for p in range(lo, hi + 1)]
    return {"pages": len(pages), "section_pages": len(sec),
            "found": loc["found"], "basis": loc["basis"],
            "ranges": loc["ranges"], "start": loc["start"], "end": loc["end"],
            "n_matches": loc["n_matches"],
            "chars": sum(c for c, _ in sec),
            "chars_nonblank": sum(b for _, b in sec),
            "low_text_pages": sum(1 for _, b in sec if b < threshold),
            "chars_low": sum(c for c, b in sec if b < threshold)}


def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError("%s failed" % cmd[0])
    return proc.stdout.decode("utf8", "replace")


def load_pages(path):
    """Text per page (1-based page n is element n-1)."""
    pages = _run(["pdftotext", "-enc", "UTF-8", str(path), "-"]).split("\f")
    if pages and pages[-1] == "":
        pages = pages[:-1]
    return pages


def locate_pdf(path, fmt):
    """(location dict, page texts) of a PDF."""
    pages = load_pages(path)
    xml = ""
    if fmt not in WHOLE_DOCUMENT:
        xml = _run(["pdftohtml", "-xml", "-stdout", "-i", "-q", str(path)])
    return locate(fmt, xml, pages), pages


def analyse_pdf(path, fmt):
    loc, pages = locate_pdf(path, fmt)
    return summarize(loc, pages)


def found_share(records, key):
    """{group: (found, total)} grouped by record[key]."""
    tot, hit = Counter(), Counter()
    for r in records:
        tot[r[key]] += 1
        hit[r[key]] += bool(r["found"])
    return {k: (hit[k], tot[k]) for k in tot}


def main():
    f = Fetcher()
    sample = json.loads((f.root / "derived" / "sample.json").read_text())
    out = []
    for st in sample:
        for r in st["picked"]:
            rec = {"authority": r["authority"], "year": r["year"],
                   "name": r["name"], "format": r["format"]}
            rec.update(analyse_pdf(f.path_for(r["url"]), r["format"]))
            out.append(rec)
    (f.root / "derived" / "layer1.json").write_text(json.dumps(out, indent=1))
    print("documents", len(out))


if __name__ == "__main__":
    sys.exit(main())
