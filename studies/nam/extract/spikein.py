"""Spike-in test of the A pipeline (PREREG v7 a2).

prepare: the PubMed abstracts coded A = 1 (spikein_codes.csv) are inserted, one
per document, on a random layer 1 page of a random non-pilot document, in test
copies under $NAM_DATA/spiked/. Document, page and line come from the seed, and
only pages that are not A candidates before the insertion are eligible. A
manifest line per spike records pmid, document, page, character positions of
the inserted text, seed, git HEAD and the md5 of keywords.py.

run: on the test copies, (i) the keyword step (the spiked page is an A
candidate and an A window holds inserted lines) and (ii) the model step (an A
finding on the spiked page whose quote passes verify_quote on the spiked page
and lies at least 50 % inside the inserted text; the model reads only the windows that hold
inserted lines). Drug relevance is not assessed. stdout has totals only.

The cache and everything else under $NAM_DATA/cache is only read, never
changed; the PDFs and OCR text are read from the local cache, nothing is
fetched. Usage: NAM_DATA=... python -m studies.nam.extract.spikein prepare|run
"""
import csv
import difflib
import hashlib
import io
import json
import random
import re
import subprocess
import sys
from pathlib import Path

from studies.nam.extract import candidates, chunks, cli, keywords, prompt, run
from studies.nam.inventory import measure

SEED = 20261030
REPO = candidates.REPO
CODES_CSV = "studies/nam/pilot/spikein_codes.csv"
KEYWORDS = Path(keywords.__file__)
MIN_SPAN_BLOCK = 5
CLUSTER_GAP = 20
OVERLAP_SHARE = 0.5


class SpikeError(RuntimeError):
    pass


def check_out_dir(out_dir, cache_dir):
    """The test copies must never be written into the cache."""
    out, cache = Path(out_dir).resolve(), Path(cache_dir).resolve()
    if out == cache or cache in out.parents or out in cache.parents:
        raise SpikeError("test copies must not be in or around the cache")


def text_chars(text):
    return len("".join(text.split()))


def eligible_pages(pages, numbers):
    """Layer 1 pages with a text layer that are not A candidates."""
    per_code, _ = candidates.candidate_pages(pages, numbers)
    banned = set(per_code["A"])
    return [n for n in sorted(numbers)
            if n not in banned
            and text_chars(pages[n - 1]) >= measure.TEXT_LAYER_MIN_CHARS]


def insert_abstract(text, abstract, line_index):
    """(new page text, (start, end) of the inserted text, number of lines)."""
    if not abstract.strip():
        raise SpikeError("empty abstract")
    lines = text.split("\n")
    if not 0 <= line_index <= len(lines):
        raise SpikeError("line index outside the page")
    block = abstract.split("\n")
    new = "\n".join(lines[:line_index] + block + lines[line_index:])
    start = len("\n".join(lines[:line_index])) + (1 if line_index else 0)
    end = start + len(abstract)
    if new[start:end] != abstract:
        raise SpikeError("inserted text not found at its position")
    return new, (start, end), len(block)


def choose(doc_ids, abstracts, seed, load):
    """[{"pmid", "doc", "page", "line"}] from the seed. load(doc_id) gives
    (pages, numbers) or None. Documents come in seed order and are skipped when
    they cannot be read or have no eligible page; each abstract gets its own."""
    rng = random.Random("%d:spikein" % seed)
    order = sorted(doc_ids)
    rng.shuffle(order)
    docs = iter(order)
    out = []
    for pmid in sorted(abstracts):
        for doc in docs:
            loaded = load(doc)
            if loaded is None:
                continue
            pages, numbers = loaded
            eligible = eligible_pages(pages, numbers)
            if not eligible:
                continue
            page = rng.choice(eligible)
            line = rng.randint(0, len(pages[page - 1].split("\n")))
            out.append({"pmid": pmid, "doc": doc, "page": page, "line": line})
            break
        else:
            raise SpikeError("not enough documents with an eligible page")
    return out


def md5_of(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def git_text(relpath, head="HEAD"):
    proc = subprocess.run(["git", "show", "%s:%s" % (head, relpath)], cwd=REPO,
                          capture_output=True, text=True, timeout=60)
    return proc.stdout if proc.returncode == 0 else None


def git_dirty(paths=("studies", "tests", "docs", "core"), repo=REPO):
    """Changed or untracked files under paths (empty: the tree is clean)."""
    proc = subprocess.run(["git", "status", "--porcelain", "--"] + list(paths),
                          cwd=repo, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise SpikeError("git status failed")
    return [line for line in proc.stdout.splitlines() if line.strip()]


def read_only_fetcher(cls):
    """A Fetcher that serves cached files only and never fetches or writes."""
    class ReadOnly(cls):
        def get(self, url):
            path = self.path_for(url)
            if not path.exists():
                raise SpikeError("not in the cache (nothing is fetched)")
            return path
    return ReadOnly


def a1_pmids(csv_path=None, committed=None):
    """PMIDs coded A = 1. The codes file must equal its git HEAD version."""
    path = Path(csv_path or REPO / CODES_CSV)
    text = path.read_text()
    head = committed if committed is not None else git_text(CODES_CSV)
    if head != text:
        raise SpikeError("spikein_codes.csv differs from git HEAD")
    rows = list(csv.DictReader(io.StringIO(text, newline="")))
    bad = [r["pmid"] for r in rows if r["A"] not in ("0", "1")]
    if bad:
        raise SpikeError("rows without a 0/1 code")
    return [str(r["pmid"]).strip() for r in rows if r["A"] == "1"]


def load_abstracts(spikeins_dir, pmids):
    """{pmid: abstract}; PMIDs are strings everywhere (ints in a file are
    converted)."""
    pmids = {str(p).strip() for p in pmids}
    found = {}
    for path in sorted(Path(spikeins_dir).glob("abstracts*.jsonl")):
        for line in path.open():
            row = json.loads(line)
            pmid = str(row["pmid"]).strip()
            if pmid in pmids:
                if pmid in found:
                    raise SpikeError("PMID drawn twice")
                found[pmid] = row["abstract"]
    missing = pmids - set(found)
    if missing:
        raise SpikeError("%d abstracts not found" % len(missing))
    return found


def prepare(out_dir, cache_dir, doc_ids, abstracts, load, head, seed=SEED,
            keywords_path=KEYWORDS):
    """Write test copies and manifest.jsonl to out_dir; returns the manifest."""
    check_out_dir(out_dir, cache_dir)
    out_dir = Path(out_dir)
    if (out_dir / "manifest.jsonl").exists():
        raise SpikeError("manifest exists: nothing written")
    placements = choose(doc_ids, list(abstracts), seed, load)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for pl in placements:
        pages, numbers = load(pl["doc"])
        text, (start, end), n_lines = insert_abstract(
            pages[pl["page"] - 1], abstracts[pl["pmid"]], pl["line"])
        copy = {n: pages[n - 1] for n in numbers}
        copy[pl["page"]] = text
        (out_dir / (pl["doc"] + ".json")).write_text(json.dumps(
            {"doc": pl["doc"], "numbers": sorted(numbers),
             "pages": {str(n): t for n, t in copy.items()}}))
        manifest.append({"pmid": pl["pmid"], "doc": pl["doc"], "page": pl["page"],
                         "char_start": start, "char_end": end,
                         "line_start": pl["line"], "line_count": n_lines,
                         "seed": seed, "git_head": head,
                         "keywords_md5": md5_of(keywords_path),
                         "prompt_hash": prompt.prompt_hash()})
    with open(out_dir / "manifest.jsonl", "w") as fh:
        for row in manifest:
            fh.write(json.dumps(row) + "\n")
    return manifest


def load_copy(out_dir, doc):
    data = json.loads((Path(out_dir) / (doc + ".json")).read_text())
    numbers = data["numbers"]
    pages = [""] * max(numbers)
    for n, text in data["pages"].items():
        pages[int(n) - 1] = text
    return pages, numbers


def locate_quote(page, quote):
    """List of (start, end) places of the quote in the page text. Exact: every
    occurrence, whitespace-flexible. Fuzzy (only if there is none): the
    cluster of matching blocks (>= MIN_SPAN_BLOCK characters, gaps up to
    CLUSTER_GAP) with the most matched characters, so scattered short blocks
    cannot stretch a span over other text."""
    tokens = quote.split()
    if not tokens:
        return []
    rx = re.compile(r"\s+".join(re.escape(t) for t in tokens), re.IGNORECASE)
    spans = [(m.start(), m.end()) for m in rx.finditer(page)]
    if spans:
        return spans
    blocks = sorted((b.a, b.a + b.size) for b in difflib.SequenceMatcher(
        None, page, quote, autojunk=False).get_matching_blocks()
        if b.size >= MIN_SPAN_BLOCK)
    clusters = []
    for lo, hi in blocks:
        if clusters and lo - clusters[-1][1] <= CLUSTER_GAP:
            clusters[-1][1] = max(clusters[-1][1], hi)
            clusters[-1][2] += hi - lo
        else:
            clusters.append([lo, hi, hi - lo])
    if not clusters:
        return []
    best = max(clusters, key=lambda c: c[2])
    return [(best[0], best[1])]


def overlaps(spans, start, end):
    """True if at least OVERLAP_SHARE of a located quote lies inside [start, end)
    (PREREG v8: at least 50 % of the quote's characters)."""
    return any(hi > lo and (min(hi, end) - max(lo, start)) >= OVERLAP_SHARE * (hi - lo)
               for lo, hi in spans)


def inserted_windows(pages, numbers, row):
    """A windows that hold inserted lines of the spiked page."""
    lo, hi = row["line_start"], row["line_start"] + row["line_count"]
    out = []
    for window in candidates.a_windows(pages, numbers):
        for page, first, lines in window:
            if page == row["page"] and first < hi and first + len(lines) > lo:
                out.append(window)
                break
    return out


def window_text(window):
    return "".join(chunks.render(page, "\n".join(lines))
                   for page, _, lines in window)


def check_row(row, pages, numbers, caller):
    """({"keyword": bool, "model": bool, "errors": int})."""
    per_code, _ = candidates.candidate_pages(pages, numbers)
    windows = inserted_windows(pages, numbers, row)
    inserted = pages[row["page"] - 1][row["char_start"]:row["char_end"]]
    result = {"keyword": (row["page"] in per_code["A"] and bool(windows)
                          and bool(candidates.a_hit_lines(inserted))),
              "model": False, "errors": 0}
    for window in windows:
        try:
            answer = caller(window_text(window))
        except cli.CallError:
            result["errors"] += 1
            continue
        window_pages = [page for page, _, _ in window]
        for f in answer["findings"]:
            if f["code"] != "A" or f["page"] != row["page"]:
                continue
            if run.check_finding(f, {"pages": window_pages}, pages) is not None:
                continue
            spans = locate_quote(pages[row["page"] - 1], f["quote"])
            if overlaps(spans, row["char_start"], row["char_end"]):
                result["model"] = True
    return result


def check_run_state(out_dir, head, dirty):
    """Refuse a run on a changed code base or a repeated run."""
    out_dir = Path(out_dir)
    if not (out_dir / "manifest.jsonl").exists():
        raise SpikeError("no manifest: run prepare first")
    if (out_dir / "totals.json").exists():
        raise SpikeError("totals.json exists: the run is not repeated")
    if dirty:
        raise SpikeError("uncommitted changes in the code base")
    for line in (out_dir / "manifest.jsonl").open():
        if json.loads(line)["git_head"] != head:
            raise SpikeError("git HEAD differs from the manifest")


def measure_all(out_dir, caller, say=print, keywords_path=KEYWORDS):
    """Run (i) and (ii) on the test copies; prints totals only."""
    out_dir = Path(out_dir)
    manifest = [json.loads(line) for line in (out_dir / "manifest.jsonl").open()]
    for row in manifest:
        if row["keywords_md5"] != md5_of(keywords_path):
            raise SpikeError("keywords.py changed since prepare")
        if row["prompt_hash"] != prompt.prompt_hash():
            raise SpikeError("extraction prompt changed since prepare")
    results = []
    for row in manifest:
        pages, numbers = load_copy(out_dir, row["doc"])
        results.append(check_row(row, pages, numbers, caller))
    n = len(results)
    k = sum(r["keyword"] for r in results)
    m = sum(r["model"] for r in results)
    (out_dir / "totals.json").write_text(json.dumps(
        {"spike_ins": n, "keyword_found": k, "model_found": m,
         "call_errors": sum(r["errors"] for r in results)}))
    say("spike-ins: %d" % n)
    say("keyword step: found %d, not found %d" % (k, n - k))
    say("model step: found %d, not found %d (call errors %d)"
        % (m, n - m, sum(r["errors"] for r in results)))
    return k, m, n


def real_loader(f):
    """({doc id: unit} without the pilot drugs, load(doc id)). load gives
    (layer 1 pages, layer 1 page numbers) from the local cache (PDF text layer
    and cached OCR text) or None. Nothing is fetched or written."""
    from studies.nam.inventory import section
    from studies.nam.extract import ocr
    from studies.nam.pilot import draw
    units, _ = draw.universe(f)
    keys = candidates.pilot_keys()
    items = {candidates.doc_id_of(u): u for k, u in units.items() if k not in keys}

    def load(doc_id):
        item = items[doc_id]
        path = f.path_for(item["url"])
        if not path.exists():
            return None
        loc, pages = section.locate_pdf(path, item["format"])
        numbers = [p for lo, hi in loc["ranges"] for p in range(lo, hi + 1)]
        if not pages or not numbers:
            return None
        low = section.low_pages(loc, pages)
        pages, _ = candidates.apply_cached_ocr(
            pages, low, ocr.cached_pages(path, low, f.root / "ocr"))
        return pages, numbers

    return items, load


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in ("prepare", "run"):
        print("usage: spikein prepare|run (nothing run)")
        return 2
    from studies.nam.inventory.fetch import Fetcher
    f = read_only_fetcher(Fetcher)()
    out_dir = f.root / "spiked"
    if argv[0] == "run":
        try:
            check_run_state(out_dir, candidates.git_head(), git_dirty())
        except SpikeError as exc:
            print("%s (nothing run)" % exc)
            return 2
        cwd = out_dir / "cwd"
        cwd.mkdir(parents=True, exist_ok=True)
        try:
            measure_all(out_dir, lambda text: cli.call_claude(text, cwd))
        except cli.QuotaExhausted:
            print("stopped: usage limit; nothing written")
            return 2
        return 0
    dirty = git_dirty()
    if dirty:
        print("uncommitted changes under studies, tests or docs (nothing run)")
        return 2
    items, load = real_loader(f)
    abstracts = load_abstracts(f.root / "spikeins", a1_pmids())
    manifest = prepare(out_dir, f.cache, items, abstracts, load,
                       candidates.git_head())
    print("spike-ins prepared: %d" % len(manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
