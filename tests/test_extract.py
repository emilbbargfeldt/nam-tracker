import json
import re
import subprocess

import pytest

from studies.nam.extract import chunks, cli, prompt, run

PAGES = [
    "Cover page text.",
    "The sponsor evaluated cardiac safety in iPSC-derived cardiomyocytes grown "
    "as 3D spheroids. Dogs received the compound for 28 days.",
    "No further studies are described. The NOAEL was 5 mg/kg.",
]
NUMBERS = [1, 2, 3]
REAL = {"code": "A", "page": 2,
        "quote": "iPSC-derived cardiomyocytes grown as 3D spheroids"}


class Caller:
    """Stands in for the Claude Code call; one canned answer per call."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def __call__(self, text):
        self.calls += 1
        ans = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(ans, Exception):
            raise ans
        return {"findings": ans, "model": "m", "usage": {"input_tokens": 1},
                "duration_ms": 5}


def go(tmp_path, caller, pages=PAGES, numbers=NUMBERS, **kw):
    return run.extract_document("doc", pages, numbers, caller, tmp_path, "v1", **kw)


def doc_dir(tmp_path):
    return tmp_path / prompt.prompt_hash()[:12] / "doc"


def findings(tmp_path):
    return json.loads((doc_dir(tmp_path) / "findings.json").read_text())


def rejected(tmp_path):
    text = (doc_dir(tmp_path) / "rejected.jsonl").read_text()
    return [json.loads(ln) for ln in text.splitlines()]


# --- quote check on synthetic documents with a known answer
def test_real_finding_is_accepted(tmp_path):
    assert go(tmp_path, Caller([REAL])) == "done"
    assert findings(tmp_path) == [REAL] and rejected(tmp_path) == []


def test_invented_quote_is_rejected(tmp_path):
    fake = dict(REAL, quote="organ-on-chip liver model was used for hepatotoxicity")
    go(tmp_path, Caller([fake]))
    assert findings(tmp_path) == []
    assert rejected(tmp_path)[0]["reason"] == "quote not verified"


def test_wrong_page_is_rejected(tmp_path):
    go(tmp_path, Caller([dict(REAL, page=3)]))  # the quote is on page 2
    assert findings(tmp_path) == []
    assert rejected(tmp_path)[0]["reason"] == "quote not verified"


def test_page_outside_chunk_and_unknown_code_are_rejected(tmp_path):
    go(tmp_path, Caller([dict(REAL, page=9), dict(REAL, code="Z")]))
    assert [r["reason"] for r in rejected(tmp_path)] == [
        "page outside the chunk", "unknown code"]


def test_empty_quote_is_rejected(tmp_path):
    go(tmp_path, Caller([dict(REAL, quote="  ")]))
    assert rejected(tmp_path)[0]["reason"] == "empty quote"


def test_no_finding_is_a_valid_empty_result(tmp_path):
    caller = Caller([])
    assert go(tmp_path, caller) == "done"
    assert findings(tmp_path) == [] and rejected(tmp_path) == []
    assert (doc_dir(tmp_path) / "chunk_01.json").exists()


def test_changed_number_is_rejected(tmp_path):
    go(tmp_path, Caller([{"code": "S", "page": 3, "quote": "The NOAEL was 50 mg/kg."}]))
    assert findings(tmp_path) == []


# --- idempotence, errors and quota
def test_second_run_does_not_call_again(tmp_path):
    caller = Caller([REAL])
    go(tmp_path, caller)
    go(tmp_path, caller)
    assert caller.calls == 1


def test_changed_chunk_text_is_called_again(tmp_path):
    caller = Caller([])
    go(tmp_path, caller)
    go(tmp_path, caller, pages=PAGES[:2] + ["changed text"])
    assert caller.calls == 2


@pytest.mark.parametrize("exc", [cli.CallError("answer incomplete"),
                                 cli.CallError("answer is not JSON"),
                                 cli.CallError("timeout")])
def test_error_is_not_saved_and_is_rerun(tmp_path, exc):
    caller = Caller(exc, [REAL])
    assert go(tmp_path, caller) == "error"
    assert not (doc_dir(tmp_path) / "chunk_01.json").exists()
    assert not (doc_dir(tmp_path) / "findings.json").exists()
    assert go(tmp_path, caller) == "done" and caller.calls == 2
    assert findings(tmp_path) == [REAL]


def test_mutant_error_as_empty_list_is_caught(tmp_path, monkeypatch):
    def error_as_empty(caller, text):
        try:
            return caller(text)
        except cli.CallError:
            return {"findings": [], "model": None, "usage": {}, "duration_ms": 0}
    monkeypatch.setattr(run, "_call", error_as_empty)
    caller = Caller(cli.CallError("answer incomplete"))
    go(tmp_path, caller)
    # the tests above require status error and no saved chunk; the mutant breaks both
    assert (doc_dir(tmp_path) / "chunk_01.json").exists()


def test_quota_stops_and_resume_continues(tmp_path):
    pages = ["a " * 30, "b " * 30, "c " * 30, "d " * 30]
    nums = [1, 2, 3, 4]
    limit = len(chunks.render(1, pages[0])) * 2  # two pages per chunk
    caller = Caller([], cli.QuotaExhausted("limit"))
    assert go(tmp_path, caller, pages, nums, max_chars=limit) == "quota"
    assert (doc_dir(tmp_path) / "chunk_01.json").exists()
    assert not (doc_dir(tmp_path) / "chunk_02.json").exists()
    assert caller.calls == 2  # chunk 3 was not tried after the quota stop
    ok = Caller([])
    assert go(tmp_path, ok, pages, nums, max_chars=limit) == "done"
    assert ok.calls == 2  # chunk 1 skipped, chunks 2 and 3 called


def test_overlap_duplicate_is_removed(tmp_path):
    pages = ["a " * 30, "x quote here. " + "b " * 30, "c " * 30]
    limit = len(chunks.render(1, pages[0])) * 2 + 30
    both = [{"code": "S", "page": 2, "quote": "x quote here."}]
    go(tmp_path, Caller(both), pages, [1, 2, 3], max_chars=limit)
    assert len(findings(tmp_path)) == 1


def test_log_has_the_fields_per_call(tmp_path):
    go(tmp_path, Caller([REAL]))
    rec = json.loads((tmp_path / "calls.jsonl").read_text().splitlines()[0])
    assert rec["model"] == "m" and rec["claude_code"] == "v1"
    assert rec["prompt_hash"] == prompt.prompt_hash() and rec["status"] == "ok"
    assert rec["usage"] == {"input_tokens": 1} and rec["duration_ms"] == 5
    assert rec["wall_s"] >= 0 and rec["chunk_hash"] and rec["time"]


def test_log_is_written_for_error_and_quota(tmp_path):
    go(tmp_path, Caller(cli.CallError("x")))
    go(tmp_path, Caller(cli.QuotaExhausted("x")))
    status = [json.loads(ln)["status"] for ln in
              (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert status == ["error", "quota"]


def test_say_prints_only_status_words(tmp_path):
    lines = []
    go(tmp_path, Caller([REAL]), say=lines.append)
    assert lines == ["doc chunk 1 done"]


# --- mutant: without the quote check the invented-quote tests must fail
def test_mutant_no_quote_check_is_caught(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "verify_quote", lambda *a, **k: True)
    fake = dict(REAL, quote="organ-on-chip liver model was used for hepatotoxicity")
    go(tmp_path, Caller([fake, dict(REAL, page=3)]))
    assert len(findings(tmp_path)) == 2  # test_invented_quote / wrong_page expect 0


# --- chunks
def pg(n):
    return "p%d " % n + "x" * 50


def test_chunks_overlap_one_page_known_answer():
    pages = [pg(i) for i in range(1, 6)]
    limit = len(chunks.render(1, pages[0])) * 2
    got = chunks.chunk_pages(pages, [1, 2, 3, 4, 5], limit)
    assert [c["pages"] for c in got] == [[1, 2], [2, 3], [3, 4], [4, 5]]
    assert got[1]["text"].startswith("=== Page 2 ===")


def test_chunks_one_chunk_when_small():
    got = chunks.chunk_pages([pg(1), pg(2)], [1, 2])
    assert [c["pages"] for c in got] == [[1, 2]]


def test_chunks_gaps_in_page_numbers_keep_absolute_numbers():
    pages = [pg(i) for i in range(1, 11)]
    limit = len(chunks.render(1, pages[0])) * 2
    got = chunks.chunk_pages(pages, [3, 4, 8, 9], limit)
    assert [c["pages"] for c in got] == [[3, 4], [4, 8], [8, 9]]
    assert "=== Page 8 ===" in got[1]["text"]


def test_chunks_oversized_page_is_its_own_chunk():
    pages = [pg(1), "y" * 500, pg(3)]
    got = chunks.chunk_pages(pages, [1, 2, 3], 200)
    assert [c["pages"] for c in got] == [[1], [2], [3]]


def test_chunks_empty():
    assert chunks.chunk_pages(["a"], []) == []


# --- prompt
def test_prompt_has_the_codebook_rows_verbatim():
    text = open(prompt.PREREG).read()
    rows = [ln for ln in text.splitlines()
            if re.match(r"\| (Code|A|B|C|D|S) \|", ln)]
    assert len(rows) == 6
    for ln in rows:
        assert ln in prompt.system_prompt()


def test_prompt_has_no_drug_agency_or_year():
    p = prompt.system_prompt()
    for word in ("FDA", "EMA", "Drugs@", "2015", "2026"):
        assert word not in prompt.RULES
    assert "=== Page N ===" in p


def test_prompt_hash_changes_with_the_text():
    assert prompt.prompt_hash("a") != prompt.prompt_hash("b")
    assert prompt.prompt_hash() == prompt.prompt_hash(prompt.system_prompt())


# --- the call
def test_argv_has_model_no_tools_and_json_output():
    argv = cli.build_argv()
    assert argv[:2] == ["claude", "-p"]
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5-5"
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--setting-sources") + 1] == ""
    for flag in ("--strict-mcp-config", "--disable-slash-commands",
                 "--no-session-persistence", "--json-schema", "--system-prompt"):
        assert flag in argv
    assert argv[argv.index("--system-prompt") + 1] == prompt.system_prompt()
    assert "--bare" not in argv


def ok_json(**over):
    """Shaped like the answer of the smoke call (ids removed)."""
    data = {"type": "result", "subtype": "success", "is_error": False,
            "terminal_reason": "completed", "stop_reason": "tool_use",
            "duration_ms": 2798,
            "usage": {"input_tokens": 2, "output_tokens": 126},
            "modelUsage": {"claude-sonnet-5-5": {"inputTokens": 2}},
            "structured_output": {"findings": [REAL]}}
    data.update(over)
    return json.dumps(data)


def test_parse_success_with_tool_use_stop_reason():
    got = cli.parse_response(ok_json())
    assert got["findings"] == [REAL] and got["model"] == "claude-sonnet-5-5"
    assert got["usage"]["output_tokens"] == 126 and got["duration_ms"] == 2798


def test_parse_empty_findings_is_valid():
    assert cli.parse_response(ok_json(structured_output={"findings": []}))["findings"] == []


@pytest.mark.parametrize("stdout", [
    ok_json(stop_reason="max_tokens"),
    ok_json(is_error=True),
    ok_json(subtype="error_max_turns"),
    ok_json(terminal_reason="aborted"),
    ok_json(structured_output=None),
    ok_json(structured_output={}),
    ok_json(structured_output={"findings": [{"code": "A", "page": "2", "quote": "q"}]}),
    ok_json(structured_output={"findings": [{"code": "A", "page": 2}]}),
    ok_json(type="system"),
    "not json at all",
    "",
])
def test_parse_incomplete_answers_are_errors(stdout):
    with pytest.raises(cli.CallError):
        cli.parse_response(stdout)


def test_parse_nonzero_exit_is_an_error():
    with pytest.raises(cli.CallError):
        cli.parse_response(ok_json(), "", 1)


@pytest.mark.parametrize("stdout,stderr", [
    (ok_json(is_error=True, result="Claude usage limit reached"), ""),
    (ok_json(is_error=True, api_error_status=429), ""),
    ("", "Error: rate limit exceeded"),
])
def test_parse_limits_are_quota(stdout, stderr):
    with pytest.raises(cli.QuotaExhausted):
        cli.parse_response(stdout, stderr, 1)


def test_quota_word_in_a_good_answer_is_not_quota():
    quote = {"code": "S", "page": 2, "quote": "the quota of animals"}
    got = cli.parse_response(ok_json(structured_output={"findings": [quote]}))
    assert got["findings"] == [quote]


def test_call_claude_passes_stdin_and_cwd(tmp_path):
    seen = {}

    def fake_run(argv, **kw):
        seen.update(argv=argv, **kw)
        return subprocess.CompletedProcess(argv, 0, ok_json(), "")
    got = cli.call_claude("chunk text", tmp_path, run=fake_run)
    assert seen["input"] == "chunk text" and seen["cwd"] == str(tmp_path)
    assert got["findings"] == [REAL]


def test_call_claude_timeout_is_an_error(tmp_path):
    def fake_run(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 1)
    with pytest.raises(cli.CallError):
        cli.call_claude("x", tmp_path, run=fake_run)


def test_main_refuses_without_blind_flag(capsys):
    assert run.main([]) == 2
    assert "--blind" in capsys.readouterr().out
