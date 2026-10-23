"""Layer 1: page range of the non-clinical section (outcome-neutral).

Located by PDF bookmarks, else by heading-like lines, using the section-title
words of outline.py (no codebook words). A separate non-clinical review is the
non-clinical section as a whole. If the section cannot be located, the whole
document is passed on and logged (PREREG v3 b). Only page numbers and
character counts leave this module; no text is printed or stored.

Rules (fixed before the run):
 - Bookmarks: start = first bookmark with a title word at the shallowest
   level that has one; end = page of the next bookmark at the same or a
   shallower level (that page is included), else the last page.
 - Headings: start = first heading-like line (<= 90 characters, not a table
   of contents line) with a title word; end = page of the first later
   numbered heading that is a sibling or ancestor successor of a numbered
   start (higher number, no deeper, first number at most one higher), or for
   an unnumbered start the first later heading beginning with "Clinical";
   else the last page.

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


def from_bookmarks(items, n_pages):
    """(start, end, n_matches) or None."""
    hits = [i for i, (_, _, t) in enumerate(items) if outline.title_matches(t)]
    if not hits:
        return None
    top = min(items[i][0] for i in hits)
    first = next(i for i in hits if items[i][0] == top)
    level, start = items[first][0], items[first][1]
    end = n_pages
    for lvl, page, _ in items[first + 1:]:
        if lvl <= level:
            end = page
            break
    if end < start:
        end = n_pages
    return start, min(max(end, start), n_pages), len(hits)


def _number(line):
    m = _NUMBER.match(line)
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def _heading_lines(pages):
    """[(page, line)] of short lines, 1-based pages."""
    out = []
    for pno, text in enumerate(pages, 1):
        for ln in text.splitlines():
            if 0 < len(ln.strip()) <= outline.MAX_HEADING_LEN:
                out.append((pno, ln))
    return out


def from_headings(pages):
    """(start, end, n_matches) or None."""
    lines = _heading_lines(pages)
    hits = [i for i, (_, ln) in enumerate(lines)
            if outline._HEADING.match(ln) and not _TOC_LINE.search(ln)]
    if not hits:
        return None
    first = hits[0]
    start, line = lines[first]
    num = _number(line)
    end = len(pages)
    for pno, ln in lines[first + 1:]:
        if _TOC_LINE.search(ln):
            continue
        if num is None:
            ok = bool(_CLINICAL.match(ln))
        else:
            cand = _number(ln)
            ok = (cand is not None and len(cand) <= len(num) and cand > num
                  and cand[0] <= num[0] + 1)
        if ok:
            end = pno
            break
    return start, min(max(end, start), len(pages)), len(hits)


def locate(fmt, xml, pages):
    """Return dict(found, basis, start, end, n_matches)."""
    n = len(pages)
    if fmt == "separate":
        return {"found": True, "basis": "document type", "start": 1, "end": n,
                "n_matches": 0}
    tries = [("bookmarks", lambda: from_bookmarks(parse_outline(xml), n)),
             ("headings", lambda: from_headings(pages))]
    for basis, fn in tries:
        res = fn()
        if res:
            return {"found": True, "basis": basis, "start": res[0],
                    "end": res[1], "n_matches": res[2]}
    return {"found": False, "basis": "not found", "start": 1, "end": n,
            "n_matches": 0}


def page_counts(pages):
    """Per page: (characters with whitespace folded, non-blank characters)."""
    return [(len(" ".join(p.split())), len("".join(p.split()))) for p in pages]


def summarize(loc, pages, threshold=measure.TEXT_LAYER_MIN_CHARS):
    counts = page_counts(pages)
    sec = counts[loc["start"] - 1:loc["end"]]
    return {"pages": len(pages), "section_pages": len(sec),
            "found": loc["found"], "basis": loc["basis"],
            "start": loc["start"], "end": loc["end"],
            "n_matches": loc["n_matches"],
            "chars": sum(c for c, _ in sec),
            "chars_nonblank": sum(b for _, b in sec),
            "low_text_pages": sum(1 for _, b in sec if b < threshold)}


def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError("%s failed" % cmd[0])
    return proc.stdout.decode("utf8", "replace")


def analyse_pdf(path, fmt):
    pages = _run(["pdftotext", "-enc", "UTF-8", str(path), "-"]).split("\f")
    if pages and pages[-1] == "":
        pages = pages[:-1]
    xml = ""
    if fmt != "separate":
        xml = _run(["pdftohtml", "-xml", "-stdout", "-i", "-q", str(path)])
    return summarize(locate(fmt, xml, pages), pages)


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
