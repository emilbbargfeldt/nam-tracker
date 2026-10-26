"""General page search over a corpus of PDFs (not tied to one study).

Corpus = a folder with PDFs and a metadata.json ({"name": ..., optional
"documents": {file name: {...}}}). Patterns = a text file, one regular
expression per line (optionally "label<TAB>regex"; blank lines and lines
starting with "#" are ignored). Matching is case-insensitive on the page text
after core.quotecheck._normalize. Output = a JSONL file with one line per hit
(document, 1-based page, label, short excerpt of the normalized text); stdout
shows counts only.

Blinding: the NAM corpus must not be searched before the pilot verdict. A
corpus is refused if it has no metadata.json, if a word of its metadata name
starts with "nam" (any case; "N.A.M." too), or if the corpus folder or any of
its PDFs (symlinks resolved) lies inside $NAM_DATA (which must be set). The
refusal comes before any corpus file is read. It is lifted only by
allow_nam=True (CLI flag
--nam-after-pilot-verdict), and only if VERDICT is tracked in git HEAD (not the
working copy).

Usage: python -m core.search CORPUS PATTERNS OUT.jsonl [--nam-after-pilot-verdict]
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from core.quotecheck import _normalize

REPO = Path(__file__).resolve().parents[1]
VERDICT = "studies/nam/pilot/VERDICT.md"
SNIPPET_CHARS = 80


class CorpusRefused(RuntimeError):
    """The corpus may not be searched (blinding or missing metadata)."""


def verdict_in_head(run=subprocess.run):
    try:
        proc = run(["git", "show", "HEAD:" + VERDICT], cwd=REPO,
                   capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and bool(proc.stdout.strip())


def _inside(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def nam_root():
    """Resolved $NAM_DATA (~ expanded, as in inventory.fetch). Unset is an
    error: without it the NAM data folder cannot be recognised."""
    raw = os.environ.get("NAM_DATA")
    if not raw:
        raise CorpusRefused("NAM_DATA is not set")
    return Path(raw).expanduser().resolve()


def _nam_name(name):
    """True if any word of the name starts with "nam", or the letters of the
    whole name do ("NAM", "NAMs", "nam_corpus", "N.A.M. tracker")."""
    words = [w.lower() for w in re.split(r"[^A-Za-z]+", name) if w]
    letters = "".join(words)
    return letters.startswith("nam") or any(w.startswith("nam") for w in words)


def check_corpus(corpus, allow_nam=False, verdict=verdict_in_head):
    """Return the metadata dict, or raise CorpusRefused. Reads metadata.json
    only; no PDF is touched."""
    corpus = Path(corpus).resolve()
    meta_path = corpus / "metadata.json"
    if not meta_path.is_file():
        raise CorpusRefused("corpus has no metadata.json")
    try:
        meta = json.loads(meta_path.read_text())
        name = str(meta["name"])
    except (ValueError, KeyError, TypeError):
        raise CorpusRefused("metadata.json needs a name") from None
    root = nam_root()
    pdfs = [p.resolve() for p in corpus.glob("*.pdf")]
    is_nam = _nam_name(name) or any(
        _inside(x, root) for x in [corpus] + pdfs)
    if is_nam:
        if not allow_nam:
            raise CorpusRefused("NAM corpus refused before the pilot verdict")
        if not verdict():
            raise CorpusRefused("pilot verdict is not in git HEAD")
    return meta


def read_patterns(path):
    """[(label, compiled regex)] from a pattern file."""
    out = []
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        label, _, rx = line.partition("\t")
        if not rx:
            label, rx = line, line
        out.append((label, re.compile(rx, re.IGNORECASE)))
    return out


def load_pages(pdf):
    """Text per page, page n at index n - 1."""
    proc = subprocess.run(["pdftotext", "-enc", "UTF-8", str(pdf), "-"],
                          capture_output=True, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError("pdftotext failed")
    pages = proc.stdout.decode("utf8", "replace").split("\f")
    if pages and pages[-1] == "":
        pages = pages[:-1]
    return pages


def search_pages(pages, patterns):
    """[(page number, label, excerpt)] for the hits on the pages."""
    hits = []
    for n, text in enumerate(pages, 1):
        norm = _normalize(text)
        for label, rx in patterns:
            for m in rx.finditer(norm):
                lo = max(0, m.start() - SNIPPET_CHARS)
                hits.append((n, label, norm[lo:m.end() + SNIPPET_CHARS]))
    return hits


def search_corpus(corpus, patterns_file, out_file, allow_nam=False,
                  verdict=verdict_in_head, pages_of=load_pages):
    """Search every PDF of the corpus; write hits to out_file. Returns
    (documents, hits)."""
    meta = check_corpus(corpus, allow_nam, verdict)
    patterns = read_patterns(patterns_file)
    docs_meta = meta.get("documents") or {}
    n_docs = n_hits = 0
    out = Path(out_file)
    tmp = out.with_name(out.name + ".tmp")
    with open(tmp, "w") as fh:
        for pdf in sorted(Path(corpus).resolve().glob("*.pdf")):
            n_docs += 1
            for page, label, excerpt in search_pages(pages_of(pdf), patterns):
                n_hits += 1
                fh.write(json.dumps({"doc": pdf.name,
                                     "meta": docs_meta.get(pdf.name),
                                     "page": page, "label": label,
                                     "excerpt": excerpt}) + "\n")
    tmp.replace(out)
    return n_docs, n_hits


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    allow = "--nam-after-pilot-verdict" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 3:
        print("usage: python -m core.search CORPUS PATTERNS OUT.jsonl "
              "[--nam-after-pilot-verdict]")
        return 2
    try:
        docs, hits = search_corpus(args[0], args[1], args[2], allow_nam=allow)
    except CorpusRefused as e:
        print("refused: %s" % e)
        return 2
    print("documents: %d, hits: %d" % (docs, hits))
    return 0


if __name__ == "__main__":
    sys.exit(main())
