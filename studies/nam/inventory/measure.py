"""Per-PDF measures: page count, text-layer share, file size. Nothing else.

The text itself is never printed or stored; only per-page character counts
leave this module. A text layer says nothing about text quality (scanned or
redacted reviews); quality is measured in the pilot.
"""
import subprocess
from pathlib import Path

# Fixed before any measurement. A page counts as having a text layer when it
# has at least this many non-whitespace characters.
TEXT_LAYER_MIN_CHARS = 100


class MeasureError(RuntimeError):
    pass


def chars_per_page(pdf_path):
    """Non-whitespace characters per page, via pdftotext (form feed = page)."""
    try:
        proc = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", str(pdf_path), "-"],
            capture_output=True, timeout=300)
    except subprocess.TimeoutExpired as exc:
        raise MeasureError("pdftotext timed out") from exc
    if proc.returncode != 0:
        raise MeasureError("pdftotext failed with code %d" % proc.returncode)
    text = proc.stdout.decode("utf8", "replace")
    pages = text.split("\f")
    if pages and pages[-1] == "":
        pages = pages[:-1]
    return [len("".join(p.split())) for p in pages]


def page_count(pdf_path):
    try:
        proc = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True,
                              timeout=60)
    except subprocess.TimeoutExpired as exc:
        raise MeasureError("pdfinfo timed out") from exc
    if proc.returncode != 0:
        raise MeasureError("pdfinfo failed with code %d" % proc.returncode)
    for line in proc.stdout.decode("utf8", "replace").splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1])
    raise MeasureError("no Pages line")


def measure(pdf_path, threshold=TEXT_LAYER_MIN_CHARS):
    pdf_path = Path(pdf_path)
    pages = page_count(pdf_path)
    counts = chars_per_page(pdf_path)
    if len(counts) != pages:
        raise MeasureError("page count mismatch: %d vs %d" % (len(counts), pages))
    with_text = sum(1 for c in counts if c >= threshold)
    return {
        "pages": pages,
        "text_pages": with_text,
        "text_share": with_text / pages if pages else 0.0,
        "size_bytes": pdf_path.stat().st_size,
        "chars_per_page": counts,
    }
