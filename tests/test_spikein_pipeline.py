"""check_row must use the pilot-30 window handling and acceptance check
(DECISIONS 2026-11-05 (h)): windows.window_chunks and
windows.check_window_finding, never whole windows and never run.check_finding.
Fake callers only: no network, no model call."""
import re

import pytest

from studies.nam.extract import candidates, run, spikein, windows

A_LINE = "Human iPSC-derived cardiomyocytes were used in this assay."
SENTENCE = "Human iPSC-derived cardiomyocytes and liver organoids were exposed to the compound."


def filler(n_lines=15, tag=0):
    return "\n".join("Group %03d-%02d animals received the vehicle control by "
                     "oral gavage once daily for four weeks." % (tag, i)
                     for i in range(n_lines))


def abstract(pmid="111"):
    return ("Study %s: %s\nContractility was measured on a "
            "microphysiological system." % (pmid, SENTENCE))


def spike(pages, page, line, text):
    """(pages with text inserted on page, manifest-like row)."""
    new, (start, end), n = spikein.insert_abstract(pages[page - 1], text, line)
    pages = list(pages)
    pages[page - 1] = new
    return pages, {"page": page, "line_start": line, "line_count": n,
                   "char_start": start, "char_end": end}


def small_doc(a_free=True):
    pages = [filler(tag=n) for n in (1, 2, 3)]
    return pages, [1, 2, 3]


def page_of(text, index):
    return int(re.findall(r"=== Page (\d+) ===", text[:index])[-1])


def quoting(quote, code="A"):
    """Fake caller: the given quote, on the page where the quote is in the text."""
    seen = []

    def caller(text):
        seen.append(text)
        i = text.find(quote)
        if i < 0:
            return {"findings": []}
        return {"findings": [{"code": code, "page": page_of(text, i), "quote": quote}]}

    caller.seen = seen
    return caller


@pytest.fixture
def spy(monkeypatch):
    """Counts and call order of the three functions check_row may use."""
    log = []
    real_chunks = windows.window_chunks
    real_check = windows.check_window_finding
    real_old = run.check_finding
    real_overlaps = spikein.overlaps
    results = []

    def chunks(*a, **k):
        log.append("chunks")
        return real_chunks(*a, **k)

    def check(*a, **k):
        log.append("check")
        r = real_check(*a, **k)
        results.append(r)
        return r

    def old(*a, **k):
        log.append("old")
        return real_old(*a, **k)

    def overlaps(*a, **k):
        log.append("overlap")
        return real_overlaps(*a, **k)

    monkeypatch.setattr(windows, "window_chunks", chunks)
    monkeypatch.setattr(windows, "check_window_finding", check)
    monkeypatch.setattr(run, "check_finding", old)
    monkeypatch.setattr(spikein, "overlaps", overlaps)
    return log, results


def test_check_row_uses_window_chunks_and_window_check_not_run_check_finding(spy):
    log, _ = spy
    pages, numbers = small_doc()
    pages, row = spike(pages, 2, 5, abstract())
    caller = quoting(SENTENCE)
    res = spikein.check_row(row, pages, numbers, caller)
    assert res["model"] is True
    assert "chunks" in log and "check" in log
    assert "old" not in log


def test_the_caller_gets_exactly_the_chunk_texts_of_the_pilot(spy):
    pages, numbers = small_doc()
    pages, row = spike(pages, 2, 5, abstract())
    caller = quoting(SENTENCE)
    spikein.check_row(row, pages, numbers, caller)
    expected = [c["text"] for c in windows.window_chunks(pages, numbers)
                if any(p == 2 for p, _, _ in c["segments"])]
    assert caller.seen == expected and expected


def big_doc(n_pages=170):
    """One A window over all pages (an A line closes every page), above
    MAX_CHARS as a whole."""
    return [filler(tag=n) + "\n" + A_LINE for n in range(1, n_pages + 1)], \
        list(range(1, n_pages + 1))


def test_a_window_above_max_chars_is_split_exactly_as_in_the_pilot(spy):
    pages, numbers = big_doc()
    pages, row = spike(pages, 85, 5, abstract())
    whole = candidates.a_windows(pages, numbers)
    assert len(whole) == 1
    assert len(windows.render_segments(whole[0])) > windows.MAX_CHARS
    caller = quoting(SENTENCE)
    res = spikein.check_row(row, pages, numbers, caller)
    pilot = [c for c in windows.window_chunks(pages, numbers)
             if any(p == 85 for p, _, _ in c["segments"])]
    assert len(windows.window_chunks(pages, numbers)) > 1
    assert caller.seen == [c["text"] for c in pilot]
    assert all(len(t) <= windows.MAX_CHARS for t in caller.seen)
    assert res["model"] is True


def test_overlap_rule_runs_after_the_window_check(spy):
    log, _ = spy
    pages, numbers = small_doc()
    pages, row = spike(pages, 2, 5, abstract())
    spikein.check_row(row, pages, numbers, quoting(SENTENCE))
    assert "check" in log and "overlap" in log
    assert log.index("check") < log.index("overlap")


def test_a_rejected_finding_never_reaches_the_overlap_rule(spy, monkeypatch):
    log, _ = spy
    monkeypatch.setattr(windows, "check_window_finding",
                        lambda f, c, p: "rejected for the test")
    pages, numbers = small_doc()
    pages, row = spike(pages, 2, 5, abstract())
    res = spikein.check_row(row, pages, numbers, quoting(SENTENCE))
    assert res["model"] is False
    assert "overlap" not in log


def test_overlap_still_rejects_an_accepted_quote_outside_the_inserted_text(spy):
    log, results = spy
    pages, numbers = small_doc()
    pages, row = spike(pages, 2, 5, abstract())
    outside = "Group 002-00 animals received the vehicle control by oral gavage once daily for four weeks."
    res = spikein.check_row(row, pages, numbers, quoting(outside))
    assert results == [None]       # accepted by the window check (in the window)
    assert "overlap" in log
    assert res["model"] is False   # < 50 % inside the inserted text


def long_abstract():
    """Hit on the first line only; a marker sentence 25 lines further down."""
    lines = ["Study 7: %s" % SENTENCE]
    lines += ["Tail line %02d reports nothing relevant." % i for i in range(1, 30)]
    lines[25] = "Late marker sentence zebra quartz seventeen closes the report."
    return "\n".join(lines)


def test_quote_outside_the_window_is_rejected_even_inside_the_inserted_text(spy):
    _, results = spy
    pages, numbers = small_doc()
    pages, row = spike(pages, 2, 2, long_abstract())
    late = "Late marker sentence zebra quartz seventeen closes the report."
    assert run.check_finding({"code": "A", "page": 2, "quote": late},
                             {"pages": [1, 2]}, pages) is None  # old check: accepted
    # a model that quotes a line it was not shown (the caller cannot see it)
    res = spikein.check_row(row, pages, numbers, lambda t: {"findings": [
        {"code": "A", "page": 2, "quote": late}]})
    assert results == ["quote outside window"]
    assert res["model"] is False


def test_a_quote_inside_the_window_and_the_inserted_text_is_found(spy):
    pages, numbers = small_doc()
    pages, row = spike(pages, 2, 2, long_abstract())
    res = spikein.check_row(row, pages, numbers, quoting("Tail line 05 reports nothing relevant."))
    assert res["model"] is True


@pytest.mark.parametrize("code", ["B", "C", "D", "S"])
def test_code_other_than_a_is_rejected(spy, code):
    _, results = spy
    pages, numbers = small_doc()
    pages, row = spike(pages, 2, 5, abstract())
    res = spikein.check_row(row, pages, numbers, quoting(SENTENCE, code=code))
    assert results == ["code outside v6 scope"]
    assert res["model"] is False


def test_finding_on_another_page_of_the_window_does_not_count(spy):
    pages, numbers = small_doc()
    pages, row = spike(pages, 2, 5, abstract())
    outside = "Group 001-14 animals received the vehicle control by oral gavage once daily for four weeks."
    res = spikein.check_row(row, pages, numbers, quoting(outside))
    assert res["model"] is False
