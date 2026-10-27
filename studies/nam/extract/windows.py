"""v6 window reader (PREREG v6 a, v8): the model reads the A windows only.

For a document the A windows of candidates.a_windows (+-10 lines around every
A keyword hit, merged, continuing across page edges) are sent to the model, one
window per call (a window above MAX_CHARS is split at page boundaries), with
the existing system prompt. A finding is accepted only if it has code A, lies
on a page of the window, and its quote passes core.quotecheck.verify_quote
against that page and against the lines of the window on that page (a quote
outside the window is rejected). Findings of other codes are rejected (v6 reads
category A only). Results go to <root>/<design dir>/<doc id>/ with one file per
window, findings.json and rejected.jsonl (as run.collect), and
<root>/<design dir>/manifest.json (design v6-windows, prompt hash, git HEAD, md5
of keywords.py, PREREG version, radius, size limit). The design dir name holds
the prompt hash and the first 8 characters of the md5 of keywords.py, so a
changed prompt or keyword list gives a new dir (the PREREG version is logged,
not compared). Resumable: a finished
window with the same hash is skipped; a usage limit stops the run as in run.py.

The roots never include the archive of the old design (extract_v5_fulllayer1)
and never the cache. Pilot documents are read blind: only done/skipped/quota
lines per window are printed.

Usage: NAM_DATA=... python -m studies.nam.extract.windows pilot --blind | spiked
(spiked: the test copies of spikein.py, output under $NAM_DATA/spiked/extract)
"""
import hashlib
import json
import re
import sys
import time
from pathlib import Path

from core.quotecheck import verify_quote

from studies.nam.extract import candidates, chunks, cli, keywords, prompt, run

DESIGN = "v6-windows"
MAX_CHARS = chunks.MAX_CHARS
ARCHIVE = "extract_v5_fulllayer1"
MIN_RATIO = run.MIN_RATIO


class WindowError(RuntimeError):
    pass


def check_root(root, cache=None):
    """The output must not be in the archive of the old design or the cache."""
    resolved = Path(root).resolve()
    if ARCHIVE in resolved.parts or any(p.name == ARCHIVE for p in resolved.parents):
        raise WindowError("the archive of the old design is never written")
    if cache is not None:
        c = Path(cache).resolve()
        if resolved == c or c in resolved.parents:
            raise WindowError("the cache is never written")


def render_segments(segments):
    return "".join(chunks.render(page, "\n".join(lines))
                   for page, _, lines in segments)


def split_window(window, max_chars=MAX_CHARS):
    """A window as a list of chunks of segments, split only between segments
    (a single segment above the limit is a chunk of its own)."""
    parts, cur, size = [], [], 0
    for seg in window:
        n = len(render_segments([seg]))
        if cur and size + n > max_chars:
            parts.append(cur)
            cur, size = [], 0
        cur.append(seg)
        size += n
    if cur:
        parts.append(cur)
    return parts


def window_chunks(pages, numbers, max_chars=MAX_CHARS):
    """[{"index", "pages", "segments", "text", "hash"}] for the A windows."""
    out = []
    for window in candidates.a_windows(pages, numbers):
        for part in split_window(window, max_chars):
            text = render_segments(part)
            out.append({"index": len(out) + 1,
                        "pages": sorted({p for p, _, _ in part}),
                        "segments": [[p, i, list(lines)] for p, i, lines in part],
                        "text": text,
                        "hash": hashlib.sha256(text.encode()).hexdigest()})
    return out


def page_window_text(chunk, page):
    return "\n".join("\n".join(lines) for p, _, lines in chunk["segments"] if p == page)


def check_window_finding(finding, chunk, pages):
    """None if accepted, else the reason for rejection."""
    if finding["code"] != "A":
        return "code outside v6 scope"
    if finding["page"] not in chunk["pages"]:
        return "page outside the chunk"
    try:
        if not verify_quote(pages[finding["page"] - 1], finding["quote"], MIN_RATIO):
            return "quote not verified"
        if not verify_quote(page_window_text(chunk, finding["page"]),
                            finding["quote"], MIN_RATIO):
            return "quote outside window"
    except ValueError:
        return "empty quote"
    return None


def design_fields(radius=candidates.WINDOW_LINES, max_chars=MAX_CHARS,
                  keywords_path=None):
    return {"design": DESIGN, "prompt_hash": prompt.prompt_hash(),
            "keywords_md5": candidates.md5_of(keywords_path or keywords.__file__),
            "radius": radius, "max_chars": max_chars}


def design_dir(root, keywords_path=None):
    return Path(root) / ("%s-%s-%s" % (
        DESIGN, prompt.prompt_hash()[:12],
        candidates.md5_of(keywords_path or keywords.__file__)[:8]))


def write_manifest(root, head, version, fields=None):
    """Create the manifest, or check that the design fields are unchanged and
    append this run. A changed design needs a new design dir (a new prompt gives
    one by itself)."""
    fields = fields or design_fields()
    d = design_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "manifest.json"
    run_info = {"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "git_head": head,
                "claude_code": version, "prereg_version": candidates.prereg_version()}
    if path.exists():
        try:
            manifest = json.loads(path.read_text())
            old = {k: manifest.get(k) for k in fields}
            manifest["runs"].append(run_info)
        except (ValueError, KeyError, AttributeError, TypeError):
            raise WindowError("manifest unreadable") from None
        if old != fields:
            raise WindowError("design changed since the first run: use a new directory")
    else:
        if any(d.iterdir()):
            raise WindowError("results without a manifest: not continued")
        manifest = dict(fields, first_git_head=head,
                        prereg_version=candidates.prereg_version(), runs=[run_info])
    run._write_atomic(path, manifest)
    return manifest


def read_document(doc_id, pages, numbers, caller, root, version="",
                  max_chars=MAX_CHARS, say=lambda line: None):
    """Read the A windows of one document. Returns "done", "error" or "quota"."""
    if not re.fullmatch(r"[A-Za-z0-9_]+", doc_id):
        raise WindowError("document id with other characters")
    p_hash = prompt.prompt_hash()
    doc_dir = design_dir(root) / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    status = "done"
    current = window_chunks(pages, numbers, max_chars)
    for chunk in current:
        path = doc_dir / ("chunk_%03d.json" % chunk["index"])
        if chunk_done(path, chunk):
            say("%s window %d skipped" % (doc_id, chunk["index"]))
            continue
        started = time.monotonic()
        root_dir = design_dir(root)
        try:
            result = caller(chunk["text"])
        except cli.QuotaExhausted:
            run.log_call(root_dir, run._record(doc_id, chunk, p_hash, version,
                                               "quota", started))
            say("%s window %d quota" % (doc_id, chunk["index"]))
            return "quota"
        except cli.CallError as exc:
            run.log_call(root_dir, run._record(doc_id, chunk, p_hash, version,
                                               "error", started, error=str(exc)))
            say("%s window %d error" % (doc_id, chunk["index"]))
            status = "error"
            continue
        accepted, rejected = [], []
        for f in result["findings"]:
            reason = check_window_finding(f, chunk, pages)
            (rejected.append(dict(f, reason=reason)) if reason else accepted.append(f))
        run._write_atomic(path, {"hash": chunk["hash"], "index": chunk["index"],
                                 "pages": chunk["pages"], "model": result["model"],
                                 "accepted": accepted, "rejected": rejected})
        run.log_call(root_dir, run._record(doc_id, chunk, p_hash, version, "ok",
                                           started, result))
        say("%s window %d done" % (doc_id, chunk["index"]))
    if status == "done":
        collect_current(doc_dir, current)
    return status


def collect_current(doc_dir, current):
    """findings.json and rejected.jsonl from the files of the current windows
    only (a file of an older window set, other hash or index, is ignored)."""
    seen, findings, rejected = set(), [], []
    for chunk in current:
        path = Path(doc_dir) / ("chunk_%03d.json" % chunk["index"])
        data = json.loads(path.read_text())
        if data.get("hash") != chunk["hash"]:
            raise WindowError("window file does not match the window")
        for f in data["accepted"]:
            key = (f["code"], f["page"], f["quote"])
            if key not in seen:
                seen.add(key)
                findings.append(f)
        rejected.extend(dict(r, chunk=data["index"]) for r in data["rejected"])
    run._write_atomic(Path(doc_dir) / "findings.json", findings)
    with open(Path(doc_dir) / "rejected.jsonl", "w") as fh:
        for r in rejected:
            fh.write(json.dumps(r) + "\n")


def chunk_done(path, chunk):
    return path.exists() and json.loads(path.read_text()).get("hash") == chunk["hash"]


def run_documents(docs, load, caller, root, cache, head, version, say=print,
                  max_chars=MAX_CHARS):
    """Read the documents in order. Returns "done", "error" or "quota"."""
    check_root(root, cache)
    write_manifest(root, head, version)
    overall = "done"
    for doc_id in sorted(docs):
        try:
            loaded = load(doc_id)
        except (OSError, IndexError, KeyError, ValueError, RuntimeError):
            say("%s skipped: unreadable" % doc_id)
            overall = "error"
            continue
        if loaded is None:
            say("%s skipped: no layer 1 text" % doc_id)
            continue
        pages, numbers = loaded
        status = read_document(doc_id, pages, numbers, caller, root, version,
                               max_chars, say)
        if status == "quota":
            return "quota"
        if status == "error":
            overall = "error"
    return overall


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv not in (["pilot", "--blind"], ["spiked"]):
        print("usage: windows pilot --blind | spiked (nothing run)")
        return 2
    from studies.nam.extract import spikein
    from studies.nam.inventory.fetch import Fetcher
    f = spikein.read_only_fetcher(Fetcher)()
    version = cli.claude_version()
    head = candidates.git_head()
    if argv[0] == "pilot":
        from studies.nam.pilot import draw
        items = {candidates.doc_id_of(i): i
                 for i in json.loads(draw.OUT.read_text())["items"]}
        load = spikein.make_loader(f, items)
        root, docs = f.root / "extract", items
    else:
        out = f.root / "spiked"
        manifest = [json.loads(x) for x in (out / "manifest.jsonl").open()]
        docs = sorted({r["doc"] for r in manifest})
        load = lambda doc: spikein.load_copy(out, doc)
        root = out / "extract"
    cwd = root / "cwd"
    check_root(root, f.cache)
    cwd.mkdir(parents=True, exist_ok=True)
    caller = lambda text: cli.call_claude(text, cwd)
    status = run_documents(docs, load, caller, root, f.cache, head, version)
    if status == "quota":
        print("stopped: usage limit; run again later to resume")
        return 2
    return 3 if status == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
