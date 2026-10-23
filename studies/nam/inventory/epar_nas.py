"""New-active-substance status from the EPAR public assessment report.

Metadata, not an outcome: one verdict per drug (yes / no / unknown) from a
fixed rule on sentences that state the CHMP conclusion. Only page numbers and
sentence numbers leave this module; no text is printed or stored.

Rule (fixed before counting, PREREG v3 a). A sentence is a match when it
 - contains "new active substance(s)",
 - names the CHMP or the Committee, and
 - has a conclusion verb (consider, qualif, conclud, agree).
A match is negative when a negation (not, cannot, no longer, neither, nor,
n't) comes before the phrase in the same sentence, else positive. Verdict:
yes = positive and no negative; no = negative and no positive; unknown =
no match, or both kinds, or no text. Sentences are split on . ; ! ? followed
by a capital letter, per page; numbers are 1-based.

Usage: NAM_DATA=... python -I -m studies.nam.inventory.epar_nas
"""
import json
import re
import subprocess
import sys
import urllib.error

from . import ema, fda
from .fetch import Fetcher
from .fetch_tocs import get_with_retry
from .xlsx import read_xlsx

RULE_VERSION = 1
_NAS = re.compile(r"new\s+active\s+substances?", re.I)
_CHMP = re.compile(r"\b(?:CHMP|Committee)\b", re.I)
_VERB = re.compile(r"\b(?:consider|qualif|conclud|agree)", re.I)
_NEG = re.compile(r"\b(?:not|cannot|no\s+longer|neither|nor)\b|n't", re.I)
_BOUNDARY = re.compile(r"(?<=[.;!?])\s+(?=[A-Z])")
_PROTECTED = ("e.g.", "i.e.", "vs.", "cf.", "approx.", "Fig.", "No.")


def split_sentences(page_text):
    """Sentences of one page; line-end hyphenation joined, whitespace folded."""
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", page_text)
    text = " ".join(text.split())
    for i, abbr in enumerate(_PROTECTED):
        text = text.replace(abbr, "\x00%d\x00" % i)
    parts = _BOUNDARY.split(text)
    out = []
    for p in parts:
        for i, abbr in enumerate(_PROTECTED):
            p = p.replace("\x00%d\x00" % i, abbr)
        out.append(p)
    return out


def _has_chmp(sentence):
    return bool(_CHMP.search(sentence))


def _has_verb(sentence):
    return bool(_VERB.search(sentence))


def _negated(sentence, pos):
    return bool(_NEG.search(sentence[:pos]))


def classify(sentence):
    """None, or 'positive' / 'negative'. Only for a sentence with the phrase."""
    m = _NAS.search(sentence)
    if not m or not _has_chmp(sentence) or not _has_verb(sentence):
        return None
    return "negative" if _negated(sentence, m.start()) else "positive"


def analyse(pages):
    """pages: list of page texts. Returns verdict, matches and phrase
    occurrences that did not match; positions only."""
    matches, unmatched = [], []
    for pno, text in enumerate(pages, 1):
        for sno, s in enumerate(split_sentences(text), 1):
            if not _NAS.search(s):
                continue
            pol = classify(s)
            if pol:
                matches.append({"page": pno, "sentence": sno, "polarity": pol})
            else:
                unmatched.append({"page": pno, "sentence": sno})
    return {"verdict": verdict(matches), "matches": matches,
            "unmatched": unmatched}


def verdict(matches):
    pos = any(m["polarity"] == "positive" for m in matches)
    neg = any(m["polarity"] == "negative" for m in matches)
    if pos and not neg:
        return "yes"
    if neg and not pos:
        return "no"
    return "unknown"


def pdf_pages(path):
    proc = subprocess.run(["pdftotext", "-enc", "UTF-8", str(path), "-"],
                          capture_output=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError("pdftotext failed")
    pages = proc.stdout.decode("utf8", "replace").split("\f")
    if pages and pages[-1] == "":
        pages = pages[:-1]
    return pages


def main():
    f = Fetcher()
    out_path = f.root / "derived" / "ema_nas_epar.json"
    table = ema.load_table(read_xlsx(get_with_retry(f, ema.TABLE_URL).read_bytes()))
    nas, _ = ema.new_active_substances(table)
    opinion = {}
    for r in nas:
        d = ema.parse_date(r["opinion_date"])
        opinion[r["url"]] = d.year if d else None
    epar = json.loads((f.root / "derived" / "ema_epar.json").read_text())
    out = []
    for r in epar:
        rec = {"name": r["name"], "url": r["url"], "report": r["report"],
               "year": r["year"], "opinion_year": opinion.get(r["url"]),
               "rule": RULE_VERSION,
               "verdict": "unknown", "matches": [], "unmatched": [],
               "error": None}
        if not r["report"]:
            rec["error"] = "no report link"
        else:
            try:
                pages = pdf_pages(get_with_retry(f, r["report"]))
                if not any(p.strip() for p in pages):
                    rec["error"] = "no text layer"
                else:
                    rec.update(analyse(pages))
            except (urllib.error.URLError, ValueError, OSError, RuntimeError,
                    subprocess.TimeoutExpired) as exc:
                rec["error"] = type(exc).__name__
        out.append(rec)
        out_path.write_text(json.dumps(out, indent=1))
    print("requests", f.requests, "docs", len(out))


if __name__ == "__main__":
    sys.exit(main())
