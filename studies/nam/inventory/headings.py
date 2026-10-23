"""Diagnosis of short layer 1 sections: heading-like lines around the section.

Prints only lines of at most 90 characters that look like headings (a number
and a capital letter, or a section-title match), with page numbers. No body
text. Headings are not outcomes; no codebook word is searched.

Usage: NAM_DATA=... python -I -m studies.nam.inventory.headings Qulipta Welireg
"""
import json
import re
import sys

from . import outline, section
from .fetch import Fetcher

BEFORE, AFTER, MAX_LINES = 2, 12, 60
_HEADLIKE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+[A-Z]")


def heading_lines(pages, first, last):
    """[(page, line, is_toc)] heading-like lines on pages first..last."""
    out = []
    for pno, ln in section._heading_lines(pages):
        if first <= pno <= last and (_HEADLIKE.match(ln) or outline._HEADING.match(ln)):
            out.append((pno, ln.strip(), bool(section._TOC_LINE.search(ln))))
    return out


def report(name, pages):
    n = len(pages)
    lines = section._heading_lines(pages)
    hits = [(p, ln.strip(), bool(section._TOC_LINE.search(ln)))
            for p, ln in lines if outline._HEADING.match(ln)]
    loc = section.from_headings(pages)
    print("== %s: %d pages, located %s" % (name, n, loc))
    print("title matches (page, toc-filtered, line):")
    for p, ln, toc in hits:
        print("  p%d %s %s" % (p, "TOC" if toc else "   ", ln))
    start = loc[0][0][0] if loc else 1
    end = loc[0][-1][1] if loc else n
    print("heading-like lines p%d-p%d (start=p%d, end=p%d):"
          % (max(1, start - BEFORE), min(n, start + AFTER), start, end))
    for p, ln, toc in heading_lines(pages, max(1, start - BEFORE),
                                    min(n, start + AFTER))[:MAX_LINES]:
        print("  p%d %s %s" % (p, "TOC" if toc else "   ", ln))


def main(argv):
    f = Fetcher()
    sample = json.loads((f.root / "derived" / "sample.json").read_text())
    for st in sample:
        for r in st["picked"]:
            if r["name"] in argv:
                report(r["name"], section.load_pages(f.path_for(r["url"])))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
