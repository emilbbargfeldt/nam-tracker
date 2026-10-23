"""Verify that an extracted quote actually appears in a page of source text."""

import difflib
import re
import unicodedata

_TRANSLATION = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-",
    "\u2014": "-", "\u2015": "-", "\u2212": "-",
})
_INVISIBLE = dict.fromkeys(
    [0x00AD, 0x200B, 0x200C, 0x200D, 0xFEFF])
_NEGATIONS = frozenset([
    "not", "no", "none", "without", "never", "neither", "nor", "absence",
    "absent", "lack", "lacked", "lacking", "cannot", "fail", "fails",
    "failed", "unable", "nothing", "nobody", "nowhere",
])
# "non-" reverses the meaning in nonclinical texts ("non-toxic").
_NON_PREFIX = re.compile(r"(?<![a-z])non-[a-z]")
_SENTENCE_END = ".;:!?"
_WINDOW_CHARS = 300
_NEGATION_WINDOW = 3
_MAX_GRAM_POSITIONS = 50
_MAX_CANDIDATES = 300
_EDGE_PUNCT = ".,;:!?()[]{}\"'"


def _normalize(text: str, keep_hyphen: bool = False) -> str:
    """Normalize text for matching.

    keep_hyphen=False joins words split by "-\\n" (hyphenation); True keeps
    the hyphen (a real compound broken at the line end).
    """
    text = unicodedata.normalize("NFKC", text)
    text = re.sub("\u00ad[ \t]*\r?\n[ \t]*", "", text)  # soft hyphen at line end
    text = text.translate(_INVISIBLE).translate(_TRANSLATION)
    text = re.sub(r"-[ \t]*\r?\n[ \t]*", "-" if keep_hyphen else "", text)
    return re.sub(r"\s+", " ", text).strip()


def _check_nonempty(quote: str) -> None:
    if not quote:
        raise ValueError("quote is empty")


def _variants(text: str) -> list:
    out = []
    for keep in (False, True):
        value = _normalize(text, keep)
        if value not in out:
            out.append(value)
    return out


def _tokens(text: str) -> list:
    return [t for t in (w.strip(_EDGE_PUNCT) for w in text.split()) if t]


def _digits_ok(quote: str, span: str) -> bool:
    """Every token with a digit in the quote must occur exactly in the span."""
    span_tokens = set(_tokens(span))
    return all(t in span_tokens for t in _tokens(quote)
               if any(c.isdigit() for c in t))


def _negations(text: str) -> set:
    found = set()
    text = text.lower()
    if _NON_PREFIX.search(text):
        found.add("non")
    for word in re.findall(r"[a-z]+(?:'[a-z]+)?", text):
        if word in _NEGATIONS:
            found.add(word)
        if word.endswith("n't"):
            found.add("n't")
    return found


def _negations_ok(quote: str, span: str) -> bool:
    return _negations(quote) == _negations(span)


def _window_tokens(page: str, lo: int) -> list:
    """Up to 3 tokens before lo; stops at (and omits) a sentence-ending token."""
    start = max(0, lo - _WINDOW_CHARS)
    tokens = page[start:lo].split()
    if start > 0 and tokens:
        tokens = tokens[1:]  # the first token may be cut by the slice
    out = []
    for tok in reversed(tokens):
        if len(out) == _NEGATION_WINDOW or tok[-1] in _SENTENCE_END:
            break
        out.append(tok)
    return out


def _negated_before(page: str, lo: int, quote: str) -> bool:
    """True if the window before page[lo:] holds a negation the quote lacks."""
    before = " ".join(_window_tokens(page, lo))
    return bool(_negations(before) - _negations(quote))


def _find_exact(page: str, quote: str) -> bool:
    """True if quote occurs as whole tokens; digits and negations must match."""
    pos = page.find(quote)
    while pos != -1:
        end = pos + len(quote)
        before_ok = not (quote[0].isalnum() and pos > 0 and page[pos - 1].isalnum())
        after_ok = not (quote[-1].isalnum() and end < len(page) and page[end].isalnum())
        if before_ok and after_ok:
            lo, hi = pos, end
            while lo > 0 and not page[lo - 1].isspace():
                lo -= 1
            while hi < len(page) and not page[hi].isspace():
                hi += 1
            span = page[lo:hi]
            if (_digits_ok(quote, span) and _negations_ok(quote, span)
                    and not _negated_before(page, lo, quote)):
                return True
        pos = page.find(quote, pos + 1)
    return False


def _fuzzy(page: str, q: str, min_ratio: float) -> bool:
    n = len(q)
    k = min(8, n)
    grams = {}
    for j in range(n - k + 1):
        grams.setdefault(q[j:j + k], []).append(j)
    step = max(1, n // 20)
    votes = {}
    for i in range(len(page) - k + 1):
        for j in grams.get(page[i:i + k], ())[:_MAX_GRAM_POSITIONS]:
            start = max(0, i - j) // step * step
            votes[start] = votes.get(start, 0) + 1
    # Keep the best-supported candidate starts only (bounds the work on
    # repetitive text), then scan them in page order.
    starts = sorted(sorted(votes, key=lambda x: -votes[x])[:_MAX_CANDIDATES])
    matcher = difflib.SequenceMatcher(autojunk=False)
    matcher.set_seq2(q)
    # Windows slightly shorter and longer than the quote tolerate OCR
    # insertions and deletions.
    for start in starts:
        for size in (n, n - n // 10, n + n // 10):
            window = page[start:start + size]
            matcher.set_seq1(window)
            if matcher.real_quick_ratio() < min_ratio or matcher.quick_ratio() < min_ratio:
                continue
            if matcher.ratio() < min_ratio:
                continue
            blocks = [b for b in matcher.get_matching_blocks() if b.size]
            if not blocks:
                continue
            # Matched place: first to last matching block, widened to whole words.
            lo = start + blocks[0].a
            hi = start + blocks[-1].a + blocks[-1].size
            while lo > 0 and not page[lo - 1].isspace():
                lo -= 1
            while hi < len(page) and not page[hi].isspace():
                hi += 1
            span = page[lo:hi]
            if (_digits_ok(q, span) and _negations_ok(q, span)
                    and not _negated_before(page, lo, q)):
                return True
    return False


def verify_quote(page_text: str, quote: str, min_ratio: float) -> bool:
    """Return True if quote is found in page_text.

    An exact whole-token match after normalization passes; otherwise the best
    fuzzy match (difflib) must reach min_ratio. In both cases every token of
    the quote containing a digit must occur exactly in the matched place, and
    the set of negation words must be equal in quote and matched place. A
    match is also rejected if up to 3 tokens before it hold a negation word
    that the quote lacks; the window stops at a token ending in . ; : ! ?.
    The exact path compares digits and negations in the whitespace-widened
    span too.
    Line-end hyphens are tried both removed and kept. See
    docs/KNOWN-LIMITATIONS.md.
    """
    if isinstance(min_ratio, bool) or not 0 < min_ratio <= 1:
        raise ValueError("min_ratio must be in (0, 1]")
    quotes = _variants(quote)
    _check_nonempty(quotes[0])
    pages = _variants(page_text)
    for page in pages:
        for q in quotes:
            if _find_exact(page, q):
                return True
    if min_ratio == 1:
        return False  # ratio 1.0 means exact only
    for page in pages:
        if not page:
            continue
        for q in quotes:
            if _fuzzy(page, q, min_ratio):
                return True
    return False
