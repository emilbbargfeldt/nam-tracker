"""a1 run (DECISIONS 2026-11-05 (d), (e), (h)). Fake callers only: no network,
no model call, no real data."""
import json
import re
from pathlib import Path

import pytest

from studies.nam.extract import candidates, cli, prompt, spikein, windows
from studies.nam.pilot import a1_run

LINE_2 = "Human iPSC-derived cardiomyocytes were used in this assay."
LINE_7 = "Human iPSC-derived hepatocytes were used in this other assay."
HEAD = "a" * 40
VERSION = "9.9.9"


def filler(tag, n_lines=15):
    return "\n".join("Group %03d-%02d animals received the vehicle control by "
                     "oral gavage once daily for four weeks." % (tag, i)
                     for i in range(n_lines))


def page_with(tag, line, at=7):
    rows = filler(tag).split("\n")
    rows[at] = line
    return "\n".join(rows)


def make_doc(n_pages=9):
    pages = [filler(n) for n in range(1, n_pages + 1)]
    pages[1] = page_with(2, LINE_2)
    pages[6] = page_with(7, LINE_7)
    return pages, list(range(1, n_pages + 1))


class Fake:
    """Answers with an A finding for every known hit line in the chunk."""

    def __init__(self, table=((LINE_2, 2), (LINE_7, 7)), script=None, model=None):
        self.table, self.calls, self.script = table, [], list(script or [])
        self.model = model or cli.MODEL

    def __call__(self, text):
        self.calls.append(text)
        if self.script:
            step = self.script.pop(0)
            if step == "quota":
                raise cli.QuotaExhausted("limit")
            if step == "error":
                raise cli.CallError("answer incomplete")
        return {"findings": [{"code": "A", "page": p, "quote": line, "why": "x"}
                             for line, p in self.table if line in text],
                "model": self.model, "usage": {}, "duration_ms": 1}


@pytest.fixture
def env(tmp_path):
    docs = {"DOC1": make_doc()}
    items = {"DOC1": {}}
    load = lambda doc_id: docs[doc_id]
    return tmp_path / "a1", items, load, [("DOC1", 2)]


def prepared(env, **kw):
    out, items, load, drawn = env
    a1_run.prepare(out, items, load, drawn, HEAD, VERSION, [], codes_md5="c" * 32, **kw)
    return out


def run_all(out, env, caller, **kw):
    lines = []
    status = a1_run.measure(out, env[2], caller, say=lines.append, head=HEAD,
                            dirty=[], **kw)
    return status, lines


def scores(out):
    return json.loads((Path(out) / "scores.json").read_text())


def test_read_a1_takes_only_a_equals_1(tmp_path):
    csv_path = tmp_path / "codes.csv"
    csv_path.write_text("doc,page,A,pages,notes\nD1,5,1,,\nD2,6,0,,x\nD3,7,1,,\n")
    assert a1_run.read_a1(csv_path) == [("D1", 5), ("D3", 7)]


# keyword step ---------------------------------------------------------------

def test_keyword_step_follows_candidate_pages():
    pages, numbers = make_doc()
    assert a1_run.keyword_hit(2, pages, numbers) is True
    assert a1_run.keyword_hit(3, pages, numbers) is False


def test_keyword_step_inconsistency_is_an_error(monkeypatch):
    pages, numbers = make_doc()
    monkeypatch.setattr(candidates, "a_hit_lines", lambda text: set())
    with pytest.raises(a1_run.A1Error):
        a1_run.keyword_hit(2, pages, numbers)


# chunk selection and equivalence ---------------------------------------------

def test_only_chunks_with_the_drawn_page_are_sent(env):
    out = prepared(env)
    fake = Fake()
    status, _ = run_all(out, env, fake)
    pages, numbers = env[2]("DOC1")
    allc = windows.window_chunks(pages, numbers)
    sent = [c for c in allc if 2 in c["pages"]]
    assert status == "done"
    assert len(sent) < len(allc)
    assert fake.calls == [c["text"] for c in sent]


def test_neighbour_page_window_is_included(env):
    pages, numbers = env[2]("DOC1")
    sel = a1_run.selected_chunks(pages, numbers, {1})
    assert sel and all(1 in c["pages"] for c in sel)
    assert any(c["pages"] != [1] for c in sel)  # window runs on to page 2


def test_split_window_sends_only_the_chunk_with_the_page():
    pages, numbers = make_doc()
    small = 500  # the window is split between pages: one chunk per page
    full = windows.window_chunks(pages, numbers, small)
    sel = a1_run.selected_chunks(pages, numbers, {2}, small)
    assert len(full) >= 4
    assert len(sel) == 1 and sel[0]["pages"] == [2]
    assert [c["hash"] for c in sel] == [c["hash"] for c in full if 2 in c["pages"]]
    assert [c["index"] for c in sel] == [c["index"] for c in full if 2 in c["pages"]]
    wide = a1_run.selected_chunks(pages, numbers, {1, 2, 3}, small)
    assert [c["pages"] for c in wide] == [[1], [2], [3]]


def test_two_drawn_pages_in_one_chunk_one_call(env):
    out, items, load, _ = env
    drawn = [("DOC1", 1), ("DOC1", 2)]
    a1_run.prepare(out, items, load, drawn, HEAD, VERSION, [], codes_md5="c" * 32)
    fake = Fake()
    run_all(out, env, fake)
    pages, numbers = load("DOC1")
    assert len(fake.calls) == len(a1_run.selected_chunks(pages, numbers, {1, 2}))


def test_equivalent_to_whole_document_pipeline(env):
    out = prepared(env)
    run_all(out, env, Fake())
    pages, numbers = env[2]("DOC1")
    expected = False
    fake = Fake()
    for chunk in windows.window_chunks(pages, numbers):  # the real pipeline
        for f in fake(chunk["text"])["findings"]:
            if windows.check_window_finding(f, chunk, pages) is None and f["page"] == 2:
                expected = True
    row = scores(out)[0]
    assert row["model"] is expected is True
    assert row["keyword"] is True


# acceptance -----------------------------------------------------------------

def test_finding_on_another_page_does_not_count(env):
    out = prepared(env)
    # the model answers page 1 for a quote that is on page 2: rejected anyway
    fake = Fake(table=((LINE_2, 1),))
    run_all(out, env, fake)
    row = scores(out)[0]
    assert row["model"] is False
    assert row["n_accepted_on_page"] == 0


def test_rejection_reasons_are_counted(env):
    out = prepared(env)
    fake = Fake(table=((LINE_2, 2),))
    orig = fake.__call__

    def caller(text):
        answer = orig(text)
        answer["findings"] += [
            {"code": "B", "page": 2, "quote": LINE_2, "why": "x"},
            {"code": "A", "page": 2, "quote": "never written on this page", "why": "x"}]
        return answer

    run_all(out, env, caller)
    totals = json.loads((out / "totals.json").read_text())
    assert totals["rejected_by_reason"]["code outside v6 scope"] >= 1
    assert totals["rejected_by_reason"]["quote not verified"] >= 1
    assert scores(out)[0]["model"] is True


# quota and resume -----------------------------------------------------------

def test_quota_stops_and_resume_counts_each_chunk_once(env, tmp_path):
    out_dir, items, load, _ = env
    small = 500
    drawn = [("DOC1", 1), ("DOC1", 2), ("DOC1", 3)]
    env = (out_dir, items, load, drawn)
    out = prepared(env, max_chars=small)
    pages, numbers = load("DOC1")
    n_chunks = len(a1_run.selected_chunks(pages, numbers, {1, 2, 3}, small))
    assert n_chunks == 3
    fake = Fake(script=["ok", "quota"])
    status, lines = run_all(out, env, fake, max_chars=small)
    assert status == "quota"
    assert not (out / "totals.json").exists()
    assert len(fake.calls) == 2
    again = Fake()
    status, _ = run_all(out, env, again, max_chars=small)
    assert status == "done"
    assert len(again.calls) == n_chunks - 1  # the finished chunk is not repeated
    # same scores as an uninterrupted run
    ref_env = (tmp_path / "ref", items, load, drawn)
    ref = prepared(ref_env, max_chars=small)
    run_all(ref, ref_env, Fake(), max_chars=small)
    assert scores(out) == scores(ref)


def test_quota_is_not_an_attempt(env):
    out = prepared(env)
    run_all(out, env, Fake(script=["quota"]))
    attempts = out / "attempts.json"
    assert not attempts.exists() or json.loads(attempts.read_text()) == {}


# call errors: retry on the next run, at most 3 attempts ----------------------

def test_call_error_retried_on_next_run(env):
    out = prepared(env)
    first = Fake(script=["error"])
    status, _ = run_all(out, env, first)
    assert status == "error"
    assert not (out / "totals.json").exists()
    status, _ = run_all(out, env, Fake())
    assert status == "done"
    assert json.loads((out / "totals.json").read_text())["call_errors"] == 0
    assert scores(out)[0]["model"] is True


def test_three_failed_attempts_give_not_found_and_totals(env):
    out = prepared(env)
    pages, numbers = env[2]("DOC1")
    n = len(a1_run.selected_chunks(pages, numbers, {2}))
    always = Fake(script=["error"] * (3 * n))
    for attempt in (1, 2):
        status, _ = run_all(out, env, always)
        assert status == "error" and not (out / "totals.json").exists()
    status, _ = run_all(out, env, always)
    assert status == "done"
    totals = json.loads((out / "totals.json").read_text())
    assert totals["call_errors"] == n
    assert totals["model_found"] == 0
    row = scores(out)[0]
    assert row["model"] is False and row["call_errors"] == n
    assert len(always.calls) == 3 * n


def test_attempts_survive_between_runs(env):
    out = prepared(env)
    run_all(out, env, Fake(script=["error"] * 50))
    pages, numbers = env[2]("DOC1")
    n = len(a1_run.selected_chunks(pages, numbers, {2}))
    counts = json.loads((out / "attempts.json").read_text())
    assert sorted(counts.values()) == [1] * n


# locks ----------------------------------------------------------------------

def test_no_manifest(env):
    with pytest.raises(spikein.SpikeError):
        a1_run.check_state(env[0], HEAD, [])


def test_totals_json_blocks_a_repeat(env):
    out = prepared(env)
    run_all(out, env, Fake())
    fake = Fake()
    with pytest.raises(spikein.SpikeError):
        run_all(out, env, fake)
    assert fake.calls == []


def test_dirty_tree_refused(env):
    out = prepared(env)
    with pytest.raises(spikein.SpikeError):
        a1_run.check_state(out, HEAD, [" M studies/x.py"])


def test_other_head_refused(env):
    out = prepared(env)
    with pytest.raises(spikein.SpikeError):
        a1_run.check_state(out, "b" * 40, [])


def test_keywords_change_refused(env, monkeypatch, tmp_path):
    out = prepared(env)
    other = tmp_path / "kw.py"
    other.write_text("changed")
    with pytest.raises(a1_run.A1Error, match="keywords"):
        a1_run.check_state(out, HEAD, [], keywords_path=other)


def test_prompt_change_refused(env, monkeypatch):
    out = prepared(env)
    monkeypatch.setattr(prompt, "prompt_hash", lambda p=None: "0" * 64)
    with pytest.raises(a1_run.A1Error, match="prompt"):
        a1_run.check_state(out, HEAD, [])


def test_codes_change_refused(env):
    out = prepared(env)
    with pytest.raises(a1_run.A1Error, match="codes"):
        a1_run.check_state(out, HEAD, [], codes_md5="d" * 32)


def test_model_in_manifest_and_mismatch_refused(env, monkeypatch):
    out = prepared(env)
    row = json.loads((out / "manifest.jsonl").read_text().splitlines()[0])
    assert row["model"] == cli.MODEL == "claude-sonnet-5-5"
    monkeypatch.setattr(cli, "MODEL", "claude-other")
    with pytest.raises(a1_run.A1Error, match="model"):
        a1_run.check_state(out, HEAD, [])


def test_reported_model_mismatch_stops_without_saving(env):
    out = prepared(env)
    with pytest.raises(a1_run.A1Error, match="model"):
        run_all(out, env, Fake(model="claude-other-1"))
    assert not list(out.glob("DOC1/chunk_*.json"))
    assert not (out / "totals.json").exists()


def test_claude_code_version_is_recorded_not_locked(env):
    out = prepared(env)
    row = json.loads((out / "manifest.jsonl").read_text().splitlines()[0])
    assert row["claude_code"] == VERSION
    # a self-updated Claude Code must not block a resume
    a1_run.check_state(out, HEAD, [])


def test_pilot_drug_refused(env):
    out, items, load, _ = env
    with pytest.raises(a1_run.A1Error):
        a1_run.prepare(out, items, load, [("PILOT_DOC", 2)], HEAD, VERSION, [],
                       codes_md5="c" * 32)


def test_drawn_page_must_be_layer_1(tmp_path):
    docs = {"DOC1": make_doc()}
    docs["DOC1"] = (docs["DOC1"][0], [3, 4, 5])
    with pytest.raises(a1_run.A1Error):
        a1_run.prepare(tmp_path / "x", {"DOC1": {}}, lambda d: docs[d],
                       [("DOC1", 2)], HEAD, VERSION, [], codes_md5="c" * 32)


def test_prepare_refuses_dirty_tree_and_existing_manifest(env):
    out, items, load, drawn = env
    with pytest.raises(spikein.SpikeError):
        a1_run.prepare(out, items, load, drawn, HEAD, VERSION, [" M x"],
                       codes_md5="c" * 32)
    prepared(env)
    with pytest.raises(a1_run.A1Error):
        prepared(env)


# output ---------------------------------------------------------------------

def test_terminal_shows_aggregates_only(env):
    out = prepared(env)
    status, lines = run_all(out, env, Fake())
    text = "\n".join(lines)
    assert "keyword step: found 1, not found 0" in text
    assert "model step: found 1, not found 0 (call errors 0)" in text
    assert "DOC1" not in text and LINE_2 not in text
    assert not re.search(r"page \d", text)
    row = scores(out)[0]
    assert (row["doc"], row["page"]) == ("DOC1", 2)
    assert row["accepted"][0]["quote"] == LINE_2


def test_prepare_prints_counts_only(env):
    out, items, load, drawn = env
    rows = a1_run.prepare(out, items, load, drawn, HEAD, VERSION, [],
                          codes_md5="c" * 32)
    lines = []
    a1_run.report_prepare(rows, say=lines.append)
    shown = "\n".join(lines)
    assert "pages: 1" in shown and "chunks to send: " in shown
    assert "DOC1" not in shown


# source ---------------------------------------------------------------------

def test_source_rules():
    src = Path(a1_run.__file__).read_text()
    assert "a1_draw" not in src and "code_a1" not in src
    assert "run.check_finding" not in src
    assert src.isascii()
    assert not re.search(r"/home/|/Users/", src)
