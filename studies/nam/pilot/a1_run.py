"""Run: NAM_DATA=~/nam-data python -m studies.nam.pilot.a1_run prepare|run

a1 test (DECISIONS 2026-11-05 (d), (e), (h)): the 15 layer 1 pages coded A = 1
in a1_codes.csv. (i) keyword step: the page is an A candidate. (ii) full
pipeline: the chunks of windows.window_chunks (computed on the whole document)
that hold the drawn page are sent to the model; a finding counts only if
windows.check_window_finding accepts it and it lies on the drawn page.

Chunks without the drawn page are not sent: the real pipeline gives the same
answer for the drawn page, because chunks and their texts are identical,
calls are independent and check_window_finding accepts only pages that are in
the chunk. Rejection counts therefore cover the sent chunks only.

prepare: writes a manifest (no model call). run: refuses a dirty tree, a
changed HEAD, keywords.py, prompt, model or codes file, and a repeat
(totals.json exists). The Claude Code version is recorded in the manifest but
is not locked (a self-update must not block a resume). A chunk that was
answered is stored and is not sent again, so a stopped run (usage limit)
resumes without double counting. A call error is retried on the next run, at
most MAX_ATTEMPTS attempts per chunk; after that the chunk counts as "not
found" and in call_errors. Per-page results go to scores.json; the terminal
shows aggregates only. Never run the a1 drawing or coding tools (pool
exhausted).
"""
import csv
import io
import json
import re
import sys
from pathlib import Path

from studies.nam.extract import candidates, cli, prompt, run, spikein, windows

CODES = "studies/nam/pilot/a1_codes.csv"
MAX_ATTEMPTS = 3
ID = re.compile(r"[A-Za-z0-9_]+")


class A1Error(RuntimeError):
    pass


def read_a1(path=None):
    """[(doc, page)] of the rows coded A = 1."""
    path = Path(path) if path else candidates.REPO / CODES
    rows = csv.DictReader(io.StringIO(path.read_text()))
    return [(r["doc"], int(r["page"])) for r in rows if r["A"] == "1"]


def keyword_hit(page, pages, numbers):
    """Test (i): the page is an A candidate (candidates.candidate_pages). The
    page must hold an A hit line exactly when it is a candidate."""
    per_code, _ = candidates.candidate_pages(pages, numbers)
    hit = page in per_code["A"]
    if hit != bool(candidates.a_hit_lines(pages[page - 1])):
        raise A1Error("candidate_pages and a_hit_lines disagree")
    return hit


def selected_chunks(pages, numbers, drawn, max_chars=windows.MAX_CHARS):
    """The chunks of windows.window_chunks (whole document) that hold a drawn
    page; index and hash as in the full pipeline."""
    return [c for c in windows.window_chunks(pages, numbers, max_chars)
            if set(c["pages"]) & set(drawn)]


def by_doc(pairs):
    out = {}
    for doc, page in pairs:
        out.setdefault(doc, set()).add(page)
    return out


def load_drawn(drawn, items, load):
    """{doc: (pages, numbers)} for the drawn documents. A document outside the
    non-pilot universe, without layer 1 text, or a drawn page that is not a
    layer 1 page is an error."""
    loaded = {}
    for doc, pages_drawn in sorted(by_doc(drawn).items()):
        if doc not in items or not ID.fullmatch(doc):
            raise A1Error("document is not in the non-pilot universe")
        result = load(doc)
        if result is None:
            raise A1Error("no layer 1 text for a drawn document")
        if not pages_drawn <= set(result[1]):
            raise A1Error("drawn page is not a layer 1 page")
        loaded[doc] = result
    return loaded


def prepare(out_dir, items, load, drawn, head, version, dirty, codes_md5=None,
            max_chars=windows.MAX_CHARS, keywords_path=spikein.KEYWORDS):
    """Write manifest.jsonl (one row per drawn page); return the rows."""
    out_dir = Path(out_dir)
    if dirty:
        raise spikein.SpikeError("uncommitted changes in the code base")
    if (out_dir / "manifest.jsonl").exists():
        raise A1Error("manifest exists: prepare is not repeated")
    loaded = load_drawn(drawn, items, load)
    base = {"git_head": head, "keywords_md5": spikein.md5_of(keywords_path),
            "prompt_hash": prompt.prompt_hash(), "model": cli.MODEL,
            "claude_code": version, "codes_md5": codes_md5,
            "design": windows.DESIGN, "max_chars": max_chars}
    rows = []
    for doc, page in sorted(set(drawn)):
        pages, numbers = loaded[doc]
        hashes = [c["hash"] for c in selected_chunks(pages, numbers, {page}, max_chars)]
        rows.append(dict(base, doc=doc, page=page, chunk_hashes=hashes))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return rows


def report_prepare(rows, say=print):
    say("pages: %d" % len(rows))
    say("chunks to send: %d" % len({(r["doc"], h) for r in rows for h in r["chunk_hashes"]}))


def read_manifest(out_dir):
    return [json.loads(x) for x in (Path(out_dir) / "manifest.jsonl").open()]


def check_state(out_dir, head, dirty, keywords_path=spikein.KEYWORDS, codes_md5=None):
    """spikein.check_run_state (manifest, no totals.json, clean tree, HEAD) and
    the keywords, prompt, model and codes locks."""
    spikein.check_run_state(out_dir, head, dirty)
    for row in read_manifest(out_dir):
        if row["keywords_md5"] != spikein.md5_of(keywords_path):
            raise A1Error("keywords.py changed since prepare")
        if row["prompt_hash"] != prompt.prompt_hash():
            raise A1Error("extraction prompt changed since prepare")
        if row["model"] != cli.MODEL:
            raise A1Error("model differs from the manifest")
        if codes_md5 is not None and row["codes_md5"] != codes_md5:
            raise A1Error("codes file changed since prepare")


def _send(chunk, pages, caller, doc_dir, attempts, out_dir, say):
    """One attempt on one chunk. Returns "done", "error" or "quota"."""
    path = doc_dir / ("chunk_%03d.json" % chunk["index"])
    if windows.chunk_done(path, chunk):
        say("chunk skipped")
        return "done"
    try:
        result = caller(chunk["text"])
    except cli.QuotaExhausted:
        say("chunk quota")
        return "quota"
    except cli.CallError as exc:
        n = attempts.get(chunk["hash"], 0) + 1
        attempts[chunk["hash"]] = n
        run._write_atomic(out_dir / "attempts.json", attempts)
        if n < MAX_ATTEMPTS:
            say("chunk error")
            return "error"
        run._write_atomic(path, {"hash": chunk["hash"], "index": chunk["index"],
                                 "pages": chunk["pages"], "model": None,
                                 "accepted": [], "rejected": [], "gave_up": True,
                                 "attempts": n, "error": str(exc)})
        say("chunk error (given up)")
        return "done"
    reported = result.get("model")
    if reported is not None and not str(reported).startswith(cli.MODEL):
        raise A1Error("the model that answered differs from %s" % cli.MODEL)
    accepted, rejected = [], []
    for f in result["findings"]:
        reason = windows.check_window_finding(f, chunk, pages)
        if reason:
            rejected.append(dict(f, reason=reason))
        else:
            accepted.append(f)
    run._write_atomic(path, {"hash": chunk["hash"], "index": chunk["index"],
                             "pages": chunk["pages"], "model": reported,
                             "accepted": accepted, "rejected": rejected})
    say("chunk done")
    return "done"


def _count(table, key):
    table[key] = table.get(key, 0) + 1


def finalize(out_dir, loaded, manifest, max_chars):
    """scores.json (per page) and totals.json (the lock against a repeat)."""
    out_dir = Path(out_dir)
    rows, seen, rejected_by_reason, models = [], {}, {}, set()
    for m in manifest:
        pages, numbers = loaded[m["doc"]]
        chunks = selected_chunks(pages, numbers, {m["page"]}, max_chars)
        row = {"doc": m["doc"], "page": m["page"],
               "keyword": keyword_hit(m["page"], pages, numbers),
               "accepted": [], "rejected_on_page": {}, "call_errors": 0,
               "chunks": [c["hash"] for c in chunks]}
        for chunk in chunks:
            path = out_dir / m["doc"] / ("chunk_%03d.json" % chunk["index"])
            data = json.loads(path.read_text())
            if data["hash"] != chunk["hash"]:
                raise A1Error("chunk file does not match the chunk")
            if data.get("gave_up"):
                row["call_errors"] += 1
            if data.get("model"):
                models.add(data["model"])
            row["accepted"] += [f for f in data["accepted"] if f["page"] == m["page"]]
            for r in data["rejected"]:
                if r["page"] == m["page"]:
                    _count(row["rejected_on_page"], r["reason"])
            if (m["doc"], chunk["hash"]) not in seen:
                seen[(m["doc"], chunk["hash"])] = data
                for r in data["rejected"]:
                    _count(rejected_by_reason, r["reason"])
        row["n_accepted_on_page"] = len(row["accepted"])
        row["model"] = bool(row["accepted"])
        rows.append(row)
    run._write_atomic(out_dir / "scores.json", rows)
    totals = {"pages": len(rows), "chunks": len(seen),
              "keyword_found": sum(r["keyword"] for r in rows),
              "model_found": sum(r["model"] for r in rows),
              "call_errors": sum(1 for d in seen.values() if d.get("gave_up")),
              "rejected_by_reason": rejected_by_reason,
              "models": sorted(models)}
    run._write_atomic(out_dir / "totals.json", totals)
    return totals


def measure(out_dir, load, caller, say=print, head=None, dirty=None,
            max_chars=windows.MAX_CHARS, keywords_path=spikein.KEYWORDS,
            codes_md5=None):
    """One run: one attempt per unanswered chunk. Returns "done", "error" or
    "quota". totals.json is written only when every chunk is answered or given
    up. Prints aggregates only."""
    out_dir = Path(out_dir)
    check_state(out_dir, head, dirty, keywords_path, codes_md5)
    manifest = read_manifest(out_dir)
    drawn = [(m["doc"], m["page"]) for m in manifest]
    loaded = load_drawn(drawn, {m["doc"]: None for m in manifest}, load)
    attempts = {}
    if (out_dir / "attempts.json").exists():
        attempts = json.loads((out_dir / "attempts.json").read_text())
    failed, sent = 0, set()
    for doc, pages_drawn in sorted(by_doc(drawn).items()):
        pages, numbers = loaded[doc]
        doc_dir = out_dir / doc
        doc_dir.mkdir(parents=True, exist_ok=True)
        for chunk in selected_chunks(pages, numbers, pages_drawn, max_chars):
            if (doc, chunk["hash"]) in sent:
                continue
            sent.add((doc, chunk["hash"]))
            outcome = _send(chunk, pages, caller, doc_dir, attempts, out_dir, say)
            if outcome == "quota":
                say("stopped: usage limit; run again later to resume")
                return "quota"
            if outcome == "error":
                failed += 1
    if failed:
        say("%d chunks failed; run again to retry (at most %d attempts per chunk)"
            % (failed, MAX_ATTEMPTS))
        return "error"
    totals = finalize(out_dir, loaded, manifest, max_chars)
    n = totals["pages"]
    say("pages: %d" % n)
    say("chunks: %d" % totals["chunks"])
    say("keyword step: found %d, not found %d"
        % (totals["keyword_found"], n - totals["keyword_found"]))
    say("model step: found %d, not found %d (call errors %d)"
        % (totals["model_found"], n - totals["model_found"], totals["call_errors"]))
    say("quote check: %d rejected as not verified"
        % totals["rejected_by_reason"].get("quote not verified", 0))
    return "done"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in ("prepare", "run"):
        print("usage: a1_run prepare|run (nothing run)")
        return 2
    from studies.nam.inventory.fetch import Fetcher
    f = spikein.read_only_fetcher(Fetcher)()
    out_dir = f.root / "a1_run"
    items, load = spikein.real_loader(f)
    head, dirty = candidates.git_head(), spikein.git_dirty()
    codes_md5 = spikein.md5_of(candidates.REPO / CODES)
    try:
        if argv[0] == "prepare":
            rows = prepare(out_dir, items, load, read_a1(), head,
                           cli.claude_version(), dirty, codes_md5)
            report_prepare(rows)
            return 0
        cwd = out_dir / "cwd"
        cwd.mkdir(parents=True, exist_ok=True)
        status = measure(out_dir, load, lambda text: cli.call_claude(text, cwd),
                         head=head, dirty=dirty, codes_md5=codes_md5)
    except (spikein.SpikeError, A1Error) as exc:
        print("%s (nothing run)" % exc)
        return 2
    return {"done": 0, "quota": 2, "error": 3}[status]


if __name__ == "__main__":
    sys.exit(main())
