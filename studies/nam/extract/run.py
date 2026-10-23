"""Extraction per document and chunk: idempotent, resumable, quote-verified.

Output per chunk is kept in $NAM_DATA/extract/<prompt hash>/<doc id>/chunk_NN.json
and is not redone. A chunk whose call failed or was cut off is not saved, so
it is called again on the next run; it is never counted as an empty list.
Every finding must pass core.quotecheck.verify_quote (0.95) against the page it
names; the others are kept as rejected. For pilot drugs nothing is shown or
counted (see DECISIONS, blinding): only done, skipped, quota or error per chunk.

Usage: NAM_DATA=... python -I -m studies.nam.extract.run   (reads pilot.json)
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from core.quotecheck import verify_quote

from . import chunks, cli, ocr, prompt

MIN_RATIO = 0.95


def document_dir(root, doc_id):
    return Path(root) / prompt.prompt_hash()[:12] / doc_id


def _call(caller, text):
    return caller(text)


def _write_atomic(path, obj):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    os.replace(tmp, path)


def check_finding(finding, chunk, pages):
    """None if accepted, else the reason for rejection."""
    if finding["code"] not in prompt.CODES:
        return "unknown code"
    if finding["page"] not in chunk["pages"]:
        return "page outside the chunk"
    try:
        ok = verify_quote(pages[finding["page"] - 1], finding["quote"], MIN_RATIO)
    except ValueError:
        return "empty quote"
    return None if ok else "quote not verified"


def log_call(root, record):
    with open(root / "calls.jsonl", "a") as fh:
        fh.write(json.dumps(record) + "\n")


def _record(doc_id, chunk, p_hash, version, status, started, result=None, error=None):
    rec = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "doc": doc_id, "chunk": chunk["index"], "chunk_hash": chunk["hash"],
           "prompt_hash": p_hash, "claude_code": version, "status": status,
           "wall_s": round(time.monotonic() - started, 2),
           "model": None, "usage": None, "duration_ms": None, "error": error}
    if result:
        rec.update(model=result["model"], usage=result["usage"],
                   duration_ms=result["duration_ms"])
    return rec


def extract_document(doc_id, pages, page_numbers, caller, root, version="",
                     max_chars=chunks.MAX_CHARS, say=lambda line: None):
    """Process the chunks of one document. Returns "done", "error" or "quota"."""
    p_hash = prompt.prompt_hash()
    doc_dir = document_dir(root, doc_id)
    doc_dir.mkdir(parents=True, exist_ok=True)
    status = "done"
    for chunk in chunks.chunk_pages(pages, page_numbers, max_chars):
        path = doc_dir / ("chunk_%02d.json" % chunk["index"])
        if path.exists() and json.loads(path.read_text()).get("hash") == chunk["hash"]:
            say("%s chunk %d skipped" % (doc_id, chunk["index"]))
            continue
        started = time.monotonic()
        try:
            result = _call(caller, chunk["text"])
        except cli.QuotaExhausted:
            log_call(Path(root), _record(doc_id, chunk, p_hash, version, "quota", started))
            say("%s chunk %d quota" % (doc_id, chunk["index"]))
            return "quota"
        except cli.CallError as exc:
            log_call(Path(root), _record(doc_id, chunk, p_hash, version, "error",
                                         started, error=str(exc)))
            say("%s chunk %d error" % (doc_id, chunk["index"]))
            status = "error"
            continue
        accepted, rejected = [], []
        for f in result["findings"]:
            reason = check_finding(f, chunk, pages)
            (rejected.append(dict(f, reason=reason)) if reason else accepted.append(f))
        _write_atomic(path, {"hash": chunk["hash"], "index": chunk["index"],
                             "pages": chunk["pages"], "model": result["model"],
                             "accepted": accepted, "rejected": rejected})
        log_call(Path(root), _record(doc_id, chunk, p_hash, version, "ok", started, result))
        say("%s chunk %d done" % (doc_id, chunk["index"]))
    if status == "done":
        collect(doc_dir)
    return status


def collect(doc_dir):
    """findings.json (accepted, overlap duplicates removed) and rejected.jsonl."""
    seen, findings, rejected = set(), [], []
    for path in sorted(Path(doc_dir).glob("chunk_*.json")):
        data = json.loads(path.read_text())
        for f in data["accepted"]:
            key = (f["code"], f["page"], f["quote"])
            if key not in seen:
                seen.add(key)
                findings.append(f)
        rejected.extend(dict(r, chunk=data["index"]) for r in data["rejected"])
    _write_atomic(Path(doc_dir) / "findings.json", findings)
    with open(Path(doc_dir) / "rejected.jsonl", "w") as fh:
        for r in rejected:
            fh.write(json.dumps(r) + "\n")


def doc_id_of(item):
    slug = re.sub(r"[^A-Za-z0-9]+", "_", item["name"]).strip("_")
    return "%s_%s_%s" % (item["authority"], item["year"], slug)


def prepare_document(path, fmt, ocr_dir, run=ocr.subprocess.run):
    """(pages, page numbers of layer 1, OCR info or None). Pages of layer 1
    below the text-layer threshold are OCR'd; if that cannot be done OcrError
    is raised and the document must not be extracted."""
    from studies.nam.inventory import section
    loc, pages = section.locate_pdf(path, fmt)
    low = section.low_pages(loc, pages)
    pages, info = ocr.apply_ocr(path, pages, low, ocr_dir, run)
    numbers = [p for lo, hi in loc["ranges"] for p in range(lo, hi + 1)]
    return pages, numbers, info


def main():
    from studies.nam.inventory.fetch import Fetcher
    from studies.nam.inventory.fetch_tocs import get_with_retry
    from studies.nam.pilot import draw
    f = Fetcher()
    root = f.root / "extract"
    root.mkdir(parents=True, exist_ok=True)
    cwd = root / "cwd"
    cwd.mkdir(exist_ok=True)
    version = cli.claude_version()
    caller = lambda text: cli.call_claude(text, cwd)
    no_ocr = 0
    for item in json.loads(draw.OUT.read_text())["items"]:
        doc_id = doc_id_of(item)
        path = get_with_retry(f, item["url"])
        try:
            pages, numbers, info = prepare_document(path, item["format"], f.root / "ocr")
        except ocr.OcrError:
            print("%s skipped: pages need OCR and OCR is not available" % doc_id)
            no_ocr += 1
            continue
        if info:
            document_dir(root, doc_id).mkdir(parents=True, exist_ok=True)
            _write_atomic(document_dir(root, doc_id) / "ocr.json", info)
        status = extract_document(doc_id, pages, numbers, caller, root, version,
                                  say=print)
        if status == "quota":
            print("stopped: usage limit; run again later to resume")
            return 2
    return 3 if no_ocr else 0


if __name__ == "__main__":
    sys.exit(main())
