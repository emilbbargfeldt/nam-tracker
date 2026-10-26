"""Known positives for PREREG v8 (a1): local term search in the layer 1 text.

Terms: studies/nam/pilot/a1_terms.txt (one term per line, blank lines and lines
starting with # ignored; literal, case-insensitive, any whitespace). The file
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


def compile_terms(terms):
    return [re.compile(r"\s+".join(re.escape(t) for t in term.split()), re.IGNORECASE)
            for term in terms]


def hit_pages(pages, numbers, regexes):
    return [n for n in sorted(numbers)
            if 1 <= n <= len(pages) and any(rx.search(pages[n - 1]) for rx in regexes)]


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
    """[(doc, page)] of batch N (1-based)."""
    order = draw_order(index, seed)
    chosen = order[BATCH * (batch - 1):BATCH * batch]
    if len(chosen) < BATCH:
        raise A1Error("not enough documents" if batch == 1
                      else "batch cannot be drawn")
    return [(doc, pick_page(doc, index[doc], seed)) for doc in chosen]


def context(page_text, terms, lines=CONTEXT_LINES):
    """+-lines lines around the first match on the page."""
    first = None
    for rx in compile_terms(terms):
        m = rx.search(page_text)
        if m and (first is None or m.start() < first):
            first = m.start()
    if first is None:
        return []
    rows = page_text.split("\n")
    at = page_text[:first].count("\n")
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
