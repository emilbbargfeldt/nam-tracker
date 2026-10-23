"""OCR for the layer 1 pages below the text-layer threshold (PREREG v3 c).

A page is rendered with pdftoppm and read with tesseract (command line only).
The text of each page is cached in $NAM_DATA/ocr/ and not made again. A page
whose OCR text is longer than its text layer replaces it. If OCR is needed and
cannot run, OcrError is raised: extraction must not run on such a document
without OCR. An empty OCR result for a blank page is valid; a failed command
is not.
"""
import glob
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

DPI = 300
LANG = "eng"


class OcrError(RuntimeError):
    """OCR is missing or a page could not be read."""


def tesseract_version(run=subprocess.run):
    try:
        proc = run(["tesseract", "--version"], capture_output=True, text=True,
                   timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise OcrError("tesseract is not installed") from None
    out = (proc.stdout or proc.stderr or "").strip().splitlines()
    if proc.returncode != 0 or not out:
        raise OcrError("tesseract does not run")
    return out[0]


def ocr_page(pdf, page, run=subprocess.run):
    """Text of one page (1-based) of a PDF, by OCR."""
    with tempfile.TemporaryDirectory() as tmp:
        proc = run(["pdftoppm", "-r", str(DPI), "-f", str(page), "-l", str(page),
                    "-gray", "-png", str(pdf), "%s/p" % tmp],
                   capture_output=True, text=True, timeout=300)
        images = sorted(glob.glob("%s/p-*.png" % tmp))
        if proc.returncode != 0 or len(images) != 1:
            raise OcrError("page %d could not be rendered" % page)
        proc = run(["tesseract", images[0], "stdout", "-l", LANG],
                   capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            raise OcrError("page %d could not be read" % page)
        return proc.stdout


def ocr_pages(pdf, numbers, cache_dir, run=subprocess.run):
    """{page: text}; each page is read once and kept in the cache."""
    folder = Path(cache_dir) / hashlib.sha256(Path(pdf).name.encode()).hexdigest()[:16]
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for p in numbers:
        path = folder / ("page_%04d.txt" % p)
        if not path.exists():
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(ocr_page(pdf, p, run))
            os.replace(tmp, path)
        out[p] = path.read_text()
    return out


def _chars(text):
    return len("".join(text.split()))


def apply_ocr(pdf, pages, low, cache_dir, run=subprocess.run):
    """(pages with the low-text pages OCR'd, info or None). Without low pages
    nothing runs and tesseract is not needed."""
    if not low:
        return list(pages), None
    version = tesseract_version(run)
    texts = ocr_pages(pdf, low, cache_dir, run)
    new = list(pages)
    used = []
    for p in low:
        if _chars(texts[p]) > _chars(new[p - 1]):
            new[p - 1] = texts[p]
            used.append(p)
    return new, {"tesseract": version, "dpi": DPI, "lang": LANG,
                 "low_pages": list(low), "replaced": used}
