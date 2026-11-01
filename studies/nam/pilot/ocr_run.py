"""OCR the low-text layer 1 pages listed in an ocr_list manifest (a1, then a2).

Fills the OCR cache $NAM_DATA/ocr/ (same cache and rules as extract.ocr). An
existing cache page is never overwritten, so a rerun resumes where it stopped.
PDFs and the manifest are only read. Prints numbers only, never any text.

Per part, when the part is finished: pages below the threshold before OCR,
pages replaced by OCR text, pages still below the threshold after OCR.

Stops cleanly between pages at --stop-at (default 02:15, next occurrence in
local time): exit 3. A tesseract/pdftoppm failure stops the run with document
and page: exit 1. --max-pages N is a timing mode: OCR at most N pages not yet
in the cache, print seconds per page and an estimate for the rest, exit 0.

The a2 document list depends on the OCR cache: after the run, run ocr_list
again with a new tag until the list no longer changes (at most 2 rounds).

A lock file in the OCR cache directory keeps a second run from starting while
one is running. Errors print the exception type and part/doc/page only, never
a message that could hold a path or text (except the fixed OcrError messages).

Usage: NAM_DATA=... PYTHONPATH=. nice python -m studies.nam.pilot.ocr_run <tag>
       [--stop-at HH:MM] [--max-pages N]
"""
import datetime
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from studies.nam.extract import ocr
from studies.nam.inventory import measure, section
from studies.nam.inventory.fetch import data_dir

PARTS = ("a1", "a2")
DEFAULT_STOP = "02:15"


def stop_time(text, now):
    """Next occurrence of HH:MM after now."""
    hh, mm = text.split(":")
    t = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    if t <= now:
        t += datetime.timedelta(days=1)
    return t


def pdf_path(cache, name):
    if not name or name != Path(name).name:
        raise ValueError("bad pdf name in manifest")
    return Path(cache) / name


def part_pages(rows, cache, ocr_dir):
    """[(doc, pdf path, page, in cache)] for the low pages of a part, in order."""
    out = []
    for row in rows:
        if row.get("missing") or not row["low"]:
            continue
        path = pdf_path(cache, row["pdf"])
        have = ocr.cached_pages(path, row["low"], ocr_dir)
        out += [(row["doc"], path, p, p in have) for p in row["low"]]
    return out


def describe(exc):
    """Fixed OcrError messages as they are; any other error by type only."""
    return str(exc) if isinstance(exc, ocr.OcrError) else type(exc).__name__


def uncached(pages):
    """Distinct (pdf, page) of the pages not in the cache."""
    return {(path, p) for _, path, p, cached in pages if not cached}


def report(rows, cache, ocr_dir, threshold, where=None):
    """(before, replaced, still below) from the text layer and the OCR cache."""
    before = replaced = still = 0
    for row in rows:
        if row.get("missing") or not row["low"]:
            continue
        if where is not None:
            where["doc"], where["page"] = row["doc"], None
        path = pdf_path(cache, row["pdf"])
        layer = section.load_pages(path)
        texts = ocr.cached_pages(path, row["low"], ocr_dir)
        for p in row["low"]:
            before += 1
            best = ocr._chars(layer[p - 1])
            if ocr._chars(texts[p]) > best:
                replaced += 1
                best = ocr._chars(texts[p])
            if best < threshold:
                still += 1
    return before, replaced, still


def hm(seconds):
    s = int(round(seconds))
    return "%d:%02d" % (s // 3600, s % 3600 // 60)


def main(argv=None, run=subprocess.run, now=datetime.datetime.now,
         mono=time.monotonic, root=None, nice=os.nice):
    argv = list(sys.argv[1:] if argv is None else argv)
    stop_text, max_pages = DEFAULT_STOP, None
    try:
        while "--stop-at" in argv:
            i = argv.index("--stop-at")
            stop_text = argv[i + 1]
            del argv[i:i + 2]
        while "--max-pages" in argv:
            i = argv.index("--max-pages")
            max_pages = int(argv[i + 1])
            del argv[i:i + 2]
        deadline = stop_time(stop_text, now())
    except (IndexError, ValueError):
        argv = []
    if len(argv) != 1 or not (argv[0].isascii() and argv[0].isalnum()) \
            or (max_pages is not None and max_pages < 1):
        print("usage: ocr_run <tag> [--stop-at HH:MM] [--max-pages N]")
        return 2
    where = {"part": None, "doc": None, "page": None}
    try:
        return execute(argv[0], deadline, max_pages, run, now, mono,
                       Path(root) if root is not None else data_dir(), nice, where)
    except Exception as exc:  # stop cleanly; never print exception text
        print("stopped by error %s: part %s doc %s page %s"
              % (type(exc).__name__, where["part"], where["doc"], where["page"]))
        return 1


def execute(tag, deadline, max_pages, run, now, mono, root, nice, where):
    manifest = root / "pilot" / ("ocr_manifest_%s.json" % tag)
    if not manifest.exists():
        print("no manifest for this tag (nothing run)")
        return 2
    data = json.loads(manifest.read_text())
    threshold = data.get("min_chars", measure.TEXT_LAYER_MIN_CHARS)
    cache, ocr_dir = root / "cache", root / "ocr"
    ocr_dir.mkdir(parents=True, exist_ok=True)
    lock = open(ocr_dir / ".ocr_run.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("another ocr_run holds the lock (nothing run)")
        return 2
    try:
        nice(19)
    except OSError:
        pass
    try:
        version = ocr.tesseract_version(run)
    except ocr.OcrError as exc:
        print("%s (nothing run)" % exc)
        return 1
    print("%s, %d dpi, %s" % (version, ocr.DPI, ocr.LANG))

    done, seconds = 0, 0.0
    for part in PARTS:
        where.update(part=part, doc=None, page=None)
        rows = data["parts"][part]
        pages = part_pages(rows, cache, ocr_dir)
        for k, (doc, path, p, cached) in enumerate(pages):
            if cached:
                continue
            where.update(doc=doc, page=p)
            if now() >= deadline:
                left = len(uncached(pages[k:]))
                print("stopped at %s in %s, doc %s page %d; %d pages left in %s, "
                      "rerun to resume" % (now().strftime("%H:%M"), part, doc, p,
                                           left, part))
                return 3
            if max_pages is not None and done >= max_pages:
                todo = uncached(pages[k:])
                for q in PARTS[PARTS.index(part) + 1:]:
                    todo |= uncached(part_pages(data["parts"][q], cache, ocr_dir))
                per = seconds / done
                print("timing: %d pages OCR'd, %.1f s total, %.1f s/page; "
                      "%d pages left, about %s (h:mm)"
                      % (done, seconds, per, len(todo), hm(per * len(todo))))
                return 0
            t0 = mono()
            try:
                ocr.ocr_pages(path, [p], ocr_dir, run)
            except (ocr.OcrError, subprocess.TimeoutExpired) as exc:
                print("OCR stopped: %s doc %s page %d: %s"
                      % (part, doc, p, describe(exc)))
                return 1
            seconds += mono() - t0
            done += 1
        where.update(doc=None, page=None)
        b, r, s = report(rows, cache, ocr_dir, threshold, where)
        print("%s | below %d chars before: %d | replaced by OCR: %d | "
              "still below after: %d" % (part, threshold, b, r, s))
    if max_pages is not None and done:
        print("timing: %d pages OCR'd, %.1f s total, %.1f s/page; 0 pages left"
              % (done, seconds, seconds / done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
