"""Known positives for PREREG v8 (a1): local term search in the layer 1 text.

Terms: studies/nam/pilot/a1_terms.txt (one term per line, blank lines and lines
starting with # ignored). Matching: core's text normalization on terms and text,
lower case, Greek letters as names; hyphen, space and line break are the same
separator (organ on a chip = organ-on-a-chip), a hyphen at a line end is also
tried as hyphenation (tis-/sue = tissue); a first token a, b, g or d followed by
a hyphen also matches alpha, beta, gamma, delta (b-TCP = beta-TCP). The file
must be committed (equal to git HEAD). keywords.py is not used (no keyword logic is imported or called). The layer 1
text is the text layer plus cached OCR text of all non-pilot documents, read
from the local cache (nothing is fetched or written there).

A hit is a (document, layer 1 page) pair with at least one term match. The
draw takes documents uniformly among those with a hit (seed order; batch N
shows draws 10 (N-1) + 1 .. 10 N of that order) and in each one hit page
uniformly. Only document, page, url and +-3 lines around the first match are
printed: no number of hits, no distribution. The hit index is rebuilt on
every run (never stored); each batch record in $NAM_DATA/a1/ (not in the repo)
holds a fingerprint of it, and a later batch is refused if the fingerprint
differs (so batches always continue the same order).

Fill rule: batch N > 1 is only drawn if studies/nam/pilot/a1_codes.csv is in git
HEAD with a 0/1 code for every row of the earlier batches and fewer than 10 rows
with A = 1; at most 5 batches (50 draws).

Usage: NAM_DATA=... python -m studies.nam.pilot.a1_draw --batch N
"""
import csv
import hashlib
import io
import json
import random
import re
import sys
from pathlib import Path

from core.quotecheck import _normalize

from studies.nam.extract import candidates, spikein

SEED = 20261031
BATCH = 10
MAX_BATCHES = 5
TARGET = 10
CONTEXT_LINES = 3
TERMS = "studies/nam/pilot/a1_terms.txt"
CODES = "studies/nam/pilot/a1_codes.csv"


class A1Error(RuntimeError):
    pass


def read_terms(text):
    terms = [ln.strip() for ln in text.splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    if not terms:
        raise A1Error("no terms")
    return terms


def committed_terms(path=None, committed=None):
    """The terms of a1_terms.txt, which must equal its git HEAD version."""
    path = Path(path or candidates.REPO / TERMS)
    if not path.exists():
        raise A1Error("a1_terms.txt is missing")
    text = path.read_text()
    head = committed if committed is not None else spikein.git_text(TERMS)
    if head != text:
        raise A1Error("a1_terms.txt differs from git HEAD")
    return read_terms(text)


GREEK = {"\u03b1": "alpha", "\u03b2": "beta", "\u03b3": "gamma", "\u03b4": "delta"}
LETTER = {"a": "alpha", "b": "beta", "g": "gamma", "d": "delta"}
NAME = {v: k for k, v in LETTER.items()}


def fold_line(line):
    """core's text normalization (NFKC, dash variants, invisible characters,
    whitespace), lower case, Greek letters as names."""
    line = re.sub("\u00ad[ \t\r]*$", "-", line)  # soft hyphen at a line end
    text = _normalize(line).lower()
    for letter, name in GREEK.items():
        text = text.replace(letter, name)
    return text


def folded_variants(text):
    """[(folded text, line index of every character)]: the lines joined with a
    space, and joined with end-of-line hyphens dropped (hyphenation)."""
    pieces = [fold_line(ln) for ln in text.split("\n")]
    out = []
    for drop in (False, True):
        chars, line_of = [], []
        for i, piece in enumerate(pieces):
            if chars and not (drop and chars[-1] == "-" and piece):
                chars.append(" ")
                line_of.append(i)
            elif chars and drop:
                chars.pop()
                line_of.pop()
            chars.extend(piece)
            line_of.extend([i] * len(piece))
        out.append(("".join(chars), line_of))
    return out


def term_regex(term):
    """Regex for one term on folded text: hyphen, space and line break are the
    same separator; a first token a, b, g or d followed by a hyphen also
    matches alpha, beta, gamma, delta (and the reverse), with a boundary on the
    left."""
    folded = fold_line(term)
    tokens = [t for t in re.split(r"[-\s]+", folded) if t]
    if not tokens:
        raise A1Error("empty term")
    patterns, prefix = [re.escape(t) for t in tokens], ""
    first = tokens[0]
    has_hyphen = bool(re.match(r"[a-z]+-", folded))
    if has_hyphen and (first in LETTER or first in NAME):
        letter = first if first in LETTER else NAME[first]
        patterns[0] = "(?:%s|%s)" % (letter, LETTER[letter])
        prefix = "(?<![a-z0-9])"
    return re.compile(prefix + r"[-\s]+".join(patterns))


def compile_terms(terms):
    return [term_regex(t) for t in terms]


def page_matches(text, regexes):
    """Line indices (0-based, raw lines) of the matches on a page."""
    out = []
    for folded, line_of in folded_variants(text):
        for rx in regexes:
            out.extend(line_of[m.start()] for m in rx.finditer(folded))
    return sorted(set(out))


def hit_pages(pages, numbers, regexes):
    return [n for n in sorted(numbers)
            if 1 <= n <= len(pages) and page_matches(pages[n - 1], regexes)]


def build_index(doc_ids, load, terms):
    """{doc id: [hit pages]} for the documents with at least one hit."""
    regexes = compile_terms(terms)
    index = {}
    for doc in sorted(doc_ids):
        loaded = load(doc)
        if loaded is None:
            continue
        pages, numbers = loaded
        hits = hit_pages(pages, numbers, regexes)
        if hits:
            index[doc] = hits
    return index


def draw_order(docs, seed=SEED):
    order = sorted(docs)
    random.Random("%d:a1" % seed).shuffle(order)
    return order


def pick_page(doc, hits, seed=SEED):
    return random.Random("%d:a1:%s" % (seed, doc)).choice(sorted(hits))


def draw_batch(index, batch, seed=SEED):
    """[(doc, page)] of batch N (1-based). A later batch with fewer than
    BATCH documents left takes all of them (DECISIONS 2026-10-28)."""
    order = draw_order(index, seed)
    chosen = order[BATCH * (batch - 1):BATCH * batch]
    if batch == 1 and len(chosen) < BATCH:
        raise A1Error("not enough documents")
    if not chosen:
        raise A1Error("batch cannot be drawn")
    return [(doc, pick_page(doc, index[doc], seed)) for doc in chosen]


def context(page_text, terms, lines=CONTEXT_LINES):
    """+-lines raw lines around the first match on the page."""
    hits = page_matches(page_text, compile_terms(terms))
    if not hits:
        return []
    rows = page_text.split("\n")
    at = hits[0]
    return rows[max(0, at - lines):at + lines + 1]


def check_fill_rule(batch, codes_text, committed, earlier):
    """Batch N > 1 needs the committed codes of exactly the drawn (document,
    page) pairs of the earlier batches (`earlier`), each coded 0/1, and fewer
    than TARGET with A = 1."""
    if not 1 <= batch <= MAX_BATCHES:
        raise A1Error("batch out of range")
    if batch == 1:
        return
    if committed is None or committed != codes_text:
        raise A1Error("a1_codes.csv is not committed")
    try:
        rows = list(csv.DictReader(io.StringIO(codes_text, newline="")))
        pairs = [(r["doc"], int(r["page"])) for r in rows]
        codes = [r["A"] for r in rows]
    except (KeyError, ValueError, TypeError):
        raise A1Error("a1_codes.csv has the wrong columns") from None
    if len(pairs) != len(set(pairs)) or sorted(pairs) != sorted(earlier):
        raise A1Error("codes do not match the earlier batches")
    if any(c not in ("0", "1") for c in codes):
        raise A1Error("rows without a 0/1 code")
    if sum(c == "1" for c in codes) >= TARGET:
        raise A1Error("enough A = 1 already")


def render(batch, draws, urls, load, terms):
    out = ["batch %d" % batch]
    for doc, page in draws:
        loaded = load(doc)
        if loaded is None:
            raise A1Error("document unavailable")
        pages, _ = loaded
        out.append("")
        out.append("%s | page %d | %s" % (doc, page, urls[doc]))
        out.extend("    " + ln for ln in context(pages[page - 1], terms))
    return "\n".join(out)


def md5_text(text):
    return hashlib.md5(text.encode()).hexdigest()


def index_md5(index, terms):
    return md5_text(json.dumps([terms, sorted(index.items())]))


def run(batch, out_dir, items, load, terms, codes_text, codes_committed, head):
    """Draw batch N; returns the text to print. The record is written last."""
    out_dir = Path(out_dir)
    earlier, fingerprints = [], set()
    for k in range(1, batch):
        path = out_dir / ("batch%d.json" % k)
        if not path.exists():
            raise A1Error("an earlier batch is missing")
        rec = json.loads(path.read_text())
        earlier += [(d["doc"], d["page"]) for d in rec["draws"]]
        fingerprints.add(rec["index_md5"])
    check_fill_rule(batch, codes_text, codes_committed, earlier)
    record = out_dir / ("batch%d.json" % batch)
    if record.exists():
        raise A1Error("batch exists: not drawn again")
    index = build_index(items, load, terms)
    key = index_md5(index, terms)
    if fingerprints - {key}:
        raise A1Error("the search result changed since the earlier batches")
    draws = draw_batch(index, batch)
    text = render(batch, draws, {d: items[d]["url"] for d, _ in draws}, load, terms)
    out_dir.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(
        {"seed": SEED, "git_head": head, "index_md5": key,
         "terms_md5": md5_text("\n".join(terms)),
         "draws": [{"doc": d, "page": p} for d, p in draws]}))
    return text


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if (len(argv) != 2 or argv[0] != "--batch"
            or argv[1] not in map(str, range(1, MAX_BATCHES + 1))):
        print("usage: a1_draw --batch 1..%d (nothing run)" % MAX_BATCHES)
        return 2
    batch = int(argv[1])
    from studies.nam.inventory.fetch import Fetcher
    f = spikein.read_only_fetcher(Fetcher)()
    try:
        if spikein.git_dirty():
            raise A1Error("uncommitted changes in the code base")
        terms = committed_terms()
        codes_file = candidates.REPO / CODES
        codes_text = codes_file.read_text() if codes_file.exists() else ""
        items, load = spikein.real_loader(f)
        text = run(batch, f.root / "a1", items, load, terms, codes_text,
                   spikein.git_text(CODES), candidates.git_head())
    except (A1Error, spikein.SpikeError) as exc:
        print("%s (nothing drawn)" % exc)
        return 2
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
