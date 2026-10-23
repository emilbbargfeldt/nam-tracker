"""Verify that an extracted quote actually appears in a page of source text."""

import difflib
import re

_TRANSLATION = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2015": "-", "\u2212": "-",
})


def _normalize(text: str) -> str:
    text = text.translate(_TRANSLATION)
    text = re.sub(r"-[ \t]*\r?\n[ \t]*", "", text)  # hyphenation at line break
    return re.sub(r"\s+", " ", text).strip()


def verify_quote(page_text: str, quote: str, min_ratio: float) -> bool:
    """Return True if quote is found in page_text.

    An exact match after normalization passes; otherwise the best fuzzy
    match (difflib) must reach min_ratio. Fuzzy candidates are located via
    shared character k-grams, so a quote with no intact k-gram on the page
    is reported as not found.

    Known limits: matching is case-sensitive, and the ratio test is
    length-relative, so a changed digit in a long quote can still pass.
    """
    if not 0 < min_ratio <= 1:
        raise ValueError("min_ratio must be in (0, 1]")
    q = _normalize(quote)
    if not q:
        raise ValueError("quote is empty")
    page = _normalize(page_text)
    if q in page:
        return True
    n = len(q)
    if not page:
        return False
    k = min(8, n)
    grams = {}
    for j in range(n - k + 1):
        grams.setdefault(q[j:j + k], []).append(j)
    step = max(1, n // 20)
    starts = set()
    for i in range(len(page) - k + 1):
        for j in grams.get(page[i:i + k], ()):
            starts.add(max(0, i - j) // step * step)
    matcher = difflib.SequenceMatcher(autojunk=False)
    matcher.set_seq2(q)
    # Windows slightly shorter and longer than the quote tolerate OCR
    # insertions and deletions.
    for start in sorted(starts):
        for size in (n, n - n // 10, n + n // 10):
            matcher.set_seq1(page[start:start + size])
            if matcher.real_quick_ratio() < min_ratio or matcher.quick_ratio() < min_ratio:
                continue
            if matcher.ratio() >= min_ratio:
                return True
    return False
