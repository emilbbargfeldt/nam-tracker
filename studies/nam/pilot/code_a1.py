"""Run: NAM_DATA=~/nam-data python -m studies.nam.pilot.code_a1

Interactive terminal coding of the a1 draw (blind, one page at a time).

Shows only what the for_coding file holds (document, page, text) with the
matched a1 terms highlighted. Asks "A? [1/0/?]" and a free note per page and
writes studies/nam/pilot/a1_codes.csv after every answer (atomic). Pages that
already have a 0/1 code are skipped, so Ctrl+C and a later restart is safe.
Prints no counts and no other data.

Usage: NAM_DATA=~/nam-data python -m studies.nam.pilot.code_a1 [--batch N]

At the A? prompt "v" shows the whole layer 1 page text (same highlighting) and
asks again; it writes nothing.
"""
import csv
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from studies.nam.extract import candidates
from studies.nam.pilot import a1_draw

COLUMNS = ["doc", "page", "A", "pages", "notes"]
CODES = candidates.REPO / a1_draw.CODES
TERMS = candidates.REPO / a1_draw.TERMS
HEADER = re.compile(r"^(\S+) \| page (\d+) \| ")
ON, OFF = "\x1b[1;31m", "\x1b[0m"
ANSWERS = ("1", "0", "?")
VIEW = "v"


class CodeError(RuntimeError):
    pass


def parse_for_coding(text):
    """{(doc, page): [text lines]} from the for_coding file."""
    out, cur = {}, None
    for ln in text.split("\n"):
        m = HEADER.match(ln)
        if m:
            cur = (m.group(1), int(m.group(2)))
            out[cur] = []
        elif cur is not None and ln.startswith("    "):
            out[cur].append(ln[4:])
    return out


def highlight(lines, regexes):
    """Lines with every term match in ANSI. A match that cannot be placed
    inside its line (folding changed the length, or it spans a line break)
    highlights the whole line."""
    flagged = set()
    for folded, line_of in a1_draw.folded_variants("\n".join(lines)):
        for rx in regexes:
            for m in rx.finditer(folded):
                if m.end() > m.start():
                    flagged.update(line_of[m.start():m.end()])
    out = []
    for i, ln in enumerate(lines):
        folded = a1_draw.fold_line(ln)
        spans = []
        if len(folded) == len(ln):
            spans = [m.span() for rx in regexes for m in rx.finditer(folded)
                     if m.end() > m.start()]
        if spans:
            mask = [False] * len(ln)
            for a, b in spans:
                mask[a:b] = [True] * (b - a)
            buf, prev = [], False
            for ch, on in zip(ln, mask):
                if on != prev:
                    buf.append(ON if on else OFF)
                    prev = on
                buf.append(ch)
            out.append("".join(buf) + (OFF if prev else ""))
        elif i in flagged:
            out.append(ON + ln + OFF)
        else:
            out.append(ln)
    return out


def read_codes(path):
    """[row dicts] of the codes file (empty if it does not exist)."""
    if not path.exists():
        return []
    return list(csv.DictReader(io.StringIO(path.read_text())))


def write_codes(path, rows):
    """Whole file to a temp file in the same folder, then renamed over."""
    buf = io.StringIO()
    w = csv.DictWriter(buf, COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    text = buf.getvalue()
    if not text.isascii():
        raise CodeError("non-ASCII text (nothing written)")
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".a1_codes.")
    try:
        with os.fdopen(fd, "w", newline="") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def ask(prompt, valid=None, ascii_only=False):
    """Prompt until the answer is accepted; returns it stripped."""
    while True:
        ans = input(prompt).strip()
        if valid is not None and ans not in valid:
            print("invalid: type one of %s" % "/".join(valid))
        elif ascii_only and not ans.isascii():
            print("ASCII only")
        else:
            ans = re.sub(r"[\x00-\x1f\x7f]+|\s+", " ", ans).strip()
            return ans


def show(lines, regexes):
    lines = [re.sub(r"[\x00-\x1f\x7f]", " ", ln) for ln in lines]
    for ln in highlight(lines, regexes):
        print("    " + ln)


def code_pages(draws, texts, regexes, path, full_page=None):
    """Ask for every draw without a 0/1 code. The pages field is always
    left empty (the unit is the drawn page). `full_page(doc, page)`
    returns the whole page text for the answer "v"."""
    rows = read_codes(path)
    for draw in draws:
        draw = dict(draw, page=int(draw["page"]))
        key = (draw["doc"], str(draw["page"]))
        done = [r for r in rows if (r["doc"], r["page"]) == key]
        if done and done[0]["A"] in ("0", "1"):
            continue
        lines = texts.get((draw["doc"], draw["page"]))
        if lines is None:
            raise CodeError("draw missing in the for_coding file")
        print("\n%s | page %s" % key)
        show(lines, regexes)
        while True:
            a = ask("A? [1/0/?] ", ANSWERS + (VIEW,))
            if a != VIEW:
                break
            try:
                if full_page is None:
                    raise CodeError("full page not available")
                text = full_page(draw["doc"], draw["page"])
            except CodeError as exc:
                print(exc)
                continue
            print("\n--- full page ---")
            show(text.split("\n"), regexes)
            print("--- end of page ---")
        row = {"doc": key[0], "page": key[1], "A": a, "pages": "", "notes": ""}
        if done:
            rows[rows.index(done[0])] = row
        else:
            rows.append(row)
        done = [row]
        write_codes(path, rows)
        note = ask("note (Enter = none): ", ascii_only=True)
        row["notes"] = note
        write_codes(path, rows)


def page_reader():
    """full_page(doc, page): the layer 1 page from the read-only cache; the
    loader is built on first use."""
    state = {}

    def full_page(doc, page):
        try:
            if "load" not in state:
                from studies.nam.extract import spikein
                from studies.nam.inventory.fetch import Fetcher
                f = spikein.read_only_fetcher(Fetcher)()
                state["load"] = spikein.real_loader(f)[1]
            loaded = state["load"](doc)
            return loaded[0][page - 1]
        except Exception:
            raise CodeError("page text unavailable")
    return full_page


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    batch = "1"
    if argv:
        if (len(argv) != 2 or argv[0] != "--batch"
                or argv[1] not in map(str, range(1, a1_draw.MAX_BATCHES + 1))):
            print("usage: code_a1 [--batch 1..%d]" % a1_draw.MAX_BATCHES)
            return 2
        batch = argv[1]
    root = os.environ.get("NAM_DATA")
    if not root:
        print("NAM_DATA not set")
        return 2
    folder = Path(root).expanduser() / "a1"
    try:
        draws = json.loads((folder / ("batch%s.json" % batch)).read_text())["draws"]
        texts = parse_for_coding(
            (folder / ("batch%s_for_coding.txt" % batch)).read_text())
        regexes = a1_draw.compile_terms(a1_draw.read_terms(TERMS.read_text()))
        code_pages(draws, texts, regexes, CODES, page_reader())
    except (OSError, KeyError, ValueError, CodeError, a1_draw.A1Error) as exc:
        print("%s (stopped)" % exc)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("\nstopped; answers so far are saved")
        return 130
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
