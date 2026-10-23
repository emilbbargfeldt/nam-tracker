"""Does an Integrated Review have a non-clinical section?

Decided from PDF bookmarks, else from heading-like lines only. Returns a
verdict and counts; no text leaves this module.
"""
import re
import subprocess

# Section-title words only (not codebook words). A bookmark counts when it
# names a non-clinical section or the pharmacology/toxicology pair; "Clinical
# Pharmacology" alone does not count. The pair may be joined by "/", "and", "&",
# a comma, a hyphen or only a space ("Pharmacology Toxicology: Additional
# Information", seen in an Integrated Review appendix).
_PAIR = r"pharmacology\s*(?:/|,|-|and|&)?\s*toxicology"
_TITLE = re.compile(r"non-?clinical|" + _PAIR, re.I)
_HEADING = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?"
    r"(?:non-?clinical|" + _PAIR + r")\b", re.I)
_ITEM = re.compile(r"<item[^>]*>(.*?)</item>", re.S)
MAX_HEADING_LEN = 90


def title_matches(title):
    return bool(_TITLE.search(title))


def outline_titles(xml):
    return [re.sub(r"<[^>]+>", "", m).strip() for m in _ITEM.findall(xml)]


def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError("%s failed" % cmd[0])
    return proc.stdout.decode("utf8", "replace")


def check(pdf_path):
    """Return {"verdict": "yes"|"no"|"unknown", "basis": ..., "n_items": int,
    "n_matches": int}."""
    xml = _run(["pdftohtml", "-xml", "-stdout", "-i", "-q", str(pdf_path)])
    titles = outline_titles(xml)
    if titles:
        n = sum(1 for t in titles if title_matches(t))
        return {"verdict": "yes" if n else "no", "basis": "bookmarks",
                "n_items": len(titles), "n_matches": n}
    text = _run(["pdftotext", "-enc", "UTF-8", str(pdf_path), "-"])
    lines = [ln for ln in text.splitlines()
             if 0 < len(ln.strip()) <= MAX_HEADING_LEN]
    n = sum(1 for ln in lines if _HEADING.match(ln))
    if not text.strip():
        return {"verdict": "unknown", "basis": "no text layer",
                "n_items": 0, "n_matches": 0}
    return {"verdict": "yes" if n else "no", "basis": "headings",
            "n_items": len(lines), "n_matches": n}
