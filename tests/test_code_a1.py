import builtins
import csv

import pytest

from studies.nam.pilot import a1_draw
from studies.nam.pilot import code_a1 as ca

TERMS = ["tissue chip", "Gut  Model"]
RX = a1_draw.compile_terms(TERMS)
DRAWS = [{"doc": "D%d" % i, "page": 2} for i in range(3)]
TEXTS = {
    ("D0", 2): ["plain line", "uses a Tissue Chip here"],
    ("D1", 2): ["gut model first", "second line"],
    ("D2", 2): ["a tissue", "chip across lines"],
}


def feed(monkeypatch, answers):
    it = iter(answers)

    def fake(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise KeyboardInterrupt
    monkeypatch.setattr(builtins, "input", fake)


def rows(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def session(monkeypatch, path, answers):
    feed(monkeypatch, answers)
    try:
        ca.code_pages(DRAWS, TEXTS, RX, path)
    except KeyboardInterrupt:
        pass


def check_writes(monkeypatch, path):
    session(monkeypatch, path, ["1", "good", "0", "", "?", ""])
    got = rows(path)
    assert [(r["doc"], r["page"], r["A"], r["pages"], r["notes"])
            for r in got] == [("D0", "2", "1", "", "good"),
                              ("D1", "2", "0", "", ""),
                              ("D2", "2", "?", "", "")]
    assert path.read_text().splitlines()[0] == "doc,page,A,pages,notes"
    assert path.read_text().isascii()


def check_resume(monkeypatch, path):
    session(monkeypatch, path, ["1", "a", "0", "b"])  # then Ctrl+C
    assert [r["doc"] for r in rows(path)] == ["D0", "D1"]
    session(monkeypatch, path, ["0", "c"])  # only D2 is asked
    got = rows(path)
    assert [(r["doc"], r["A"], r["notes"]) for r in got] == [
        ("D0", "1", "a"), ("D1", "0", "b"), ("D2", "0", "c")]


def test_writes_rows(monkeypatch, tmp_path):
    check_writes(monkeypatch, tmp_path / "c.csv")


def test_resume_skips_coded(monkeypatch, tmp_path):
    check_resume(monkeypatch, tmp_path / "c.csv")


def test_saved_after_each_answer(monkeypatch, tmp_path):
    path = tmp_path / "c.csv"
    session(monkeypatch, path, ["1", "n", "0"])  # interrupted mid-page
    assert [(r["doc"], r["A"]) for r in rows(path)] == [("D0", "1"), ("D1", "0")]


def test_unsure_is_asked_again(monkeypatch, tmp_path):
    path = tmp_path / "c.csv"
    session(monkeypatch, path, ["?", ""])
    session(monkeypatch, path, ["1", "", "0", ""])
    assert [(r["doc"], r["A"]) for r in rows(path)] == [
        ("D0", "1"), ("D1", "0")]


def test_invalid_answer_rejected(monkeypatch, tmp_path, capsys):
    path = tmp_path / "c.csv"
    session(monkeypatch, path, ["2", "yes", "1", ""])
    assert "invalid" in capsys.readouterr().out
    assert [r["A"] for r in rows(path)] == ["1"]


def test_non_ascii_note_rejected(monkeypatch, tmp_path, capsys):
    path = tmp_path / "c.csv"
    session(monkeypatch, path, ["0", "\xe6", "ok"])
    assert "ASCII only" in capsys.readouterr().out
    assert rows(path)[0]["notes"] == "ok"


def test_pages_never_asked_and_left_empty(monkeypatch, tmp_path, capsys):
    path = tmp_path / "c.csv"
    feed(monkeypatch, ["1", "n"])
    ca.code_pages([{"doc": "D0", "page": 2, "pages": "2-3"}], TEXTS, RX, path)
    assert rows(path)[0]["pages"] == ""
    assert "pages" not in capsys.readouterr().out


def test_shows_only_text_with_highlight(monkeypatch, tmp_path, capsys):
    path = tmp_path / "c.csv"
    session(monkeypatch, path, ["0", ""])
    out = capsys.readouterr().out
    assert "D0 | page 2" in out
    assert "uses a " + ca.ON + "Tissue Chip" + ca.OFF + " here" in out
    assert "plain line" in out and ca.ON not in out.split("plain line")[0]


def test_highlight_line_break_match():
    out = ca.highlight(TEXTS[("D2", 2)], RX)
    assert ca.ON in out[0] and ca.ON in out[1]


def test_answer_saved_before_note(monkeypatch, tmp_path):
    path = tmp_path / "c.csv"
    session(monkeypatch, path, ["1"])  # Ctrl+C at the note prompt
    assert [(r["doc"], r["A"]) for r in rows(path)] == [("D0", "1")]


def test_control_characters_removed(monkeypatch, tmp_path, capsys):
    path = tmp_path / "c.csv"
    texts = {("D0", 2): ["bad \x1b[31m text"]}
    feed(monkeypatch, ["0", "n\x1bote"])
    ca.code_pages([DRAWS[0]], texts, RX, path)
    assert "\x1b[31m" not in capsys.readouterr().out
    assert rows(path)[0]["notes"] == "n ote"


def test_string_page_in_batch(monkeypatch, tmp_path):
    feed(monkeypatch, ["0", ""])
    ca.code_pages([{"doc": "D0", "page": "2"}], TEXTS, RX, tmp_path / "c.csv")


def test_parse_for_coding():
    text = ("batch 1\n\nD0 | page 2 | http://x\n    a\n      b\n\n"
            "D1 | page 5 | http://y\n    c")
    assert ca.parse_for_coding(text) == {("D0", 2): ["a", "  b"],
                                         ("D1", 5): ["c"]}


def test_missing_text_stops(monkeypatch, tmp_path):
    feed(monkeypatch, ["1"])
    with pytest.raises(ca.CodeError):
        ca.code_pages([{"doc": "X", "page": 1}], TEXTS, RX, tmp_path / "c.csv")


def test_bad_args(capsys):
    assert ca.main(["--batch", "9"]) == 2
    assert ca.main(["--oops"]) == 2


def test_mutant_no_resume_is_caught(monkeypatch, tmp_path):
    """A resume that re-asks coded pages must make the resume check fail."""
    monkeypatch.setattr(ca, "read_codes", lambda path: [])
    with pytest.raises(AssertionError):
        check_resume(monkeypatch, tmp_path / "c.csv")


def test_mutant_wrong_column_is_caught(monkeypatch, tmp_path):
    """Swapped columns must make the write check fail."""
    monkeypatch.setattr(ca, "COLUMNS", ["doc", "page", "pages", "A", "notes"])
    with pytest.raises(AssertionError):
        check_writes(monkeypatch, tmp_path / "c.csv")


def test_unsure_row_fully_overwritten(monkeypatch, tmp_path):
    path = tmp_path / "c.csv"
    session(monkeypatch, path, ["?", "old note"])
    assert rows(path)[0]["A"] == "?" and rows(path)[0]["notes"] == "old note"
    session(monkeypatch, path, ["0", "new"])
    first = rows(path)[0]
    assert (first["A"], first["pages"], first["notes"]) == ("0", "", "new")
    assert len(rows(path)) == 1


def test_v_shows_full_page_writes_nothing(monkeypatch, tmp_path, capsys):
    path = tmp_path / "c.csv"
    full = "head line\nmiddle Gut Model text\ntail line\x1b[31m"
    calls = []

    def full_page(doc, page):
        calls.append((doc, page))
        return full
    feed(monkeypatch, ["v", "v"])
    with pytest.raises(KeyboardInterrupt):
        ca.code_pages(DRAWS, TEXTS, RX, path, full_page)
    out = capsys.readouterr().out
    assert calls == [("D0", 2), ("D0", 2)]
    assert "tail line" in out and "middle " + ca.ON + "Gut Model" + ca.OFF in out
    assert "\x1b[31m" not in out and "tail line [31m" in out
    assert not path.exists()


def test_v_then_answer(monkeypatch, tmp_path):
    path = tmp_path / "c.csv"
    feed(monkeypatch, ["v", "0", ""])
    ca.code_pages(DRAWS[:1], TEXTS, RX, path, lambda d, p: "x")
    assert [(r["doc"], r["A"]) for r in rows(path)] == [("D0", "0")]


def test_v_without_reader_asks_again(monkeypatch, tmp_path, capsys):
    path = tmp_path / "c.csv"
    feed(monkeypatch, ["v", "0", ""])
    ca.code_pages(DRAWS[:1], TEXTS, RX, path)
    assert "not available" in capsys.readouterr().out
    assert rows(path)[0]["A"] == "0"


def test_page_reader_indexing_and_errors(monkeypatch):
    from studies.nam.extract import spikein
    built = []
    pages = {"D0": (["p1", "p2", "p3"], None), "D1": None}

    def real_loader(f):
        built.append(f)
        return {}, pages.get
    monkeypatch.setattr(spikein, "read_only_fetcher", lambda cls: lambda: "F")
    monkeypatch.setattr(spikein, "real_loader", real_loader)
    full_page = ca.page_reader()
    assert built == []
    assert full_page("D0", 2) == "p2"
    assert full_page("D0", 3) == "p3" and built == ["F"]
    with pytest.raises(ca.CodeError):
        full_page("D1", 1)
    with pytest.raises(ca.CodeError):
        full_page("D0", 9)


def test_v_leaves_existing_csv_unchanged(monkeypatch, tmp_path):
    path = tmp_path / "c.csv"
    session(monkeypatch, path, ["1", "n"])
    before = path.read_bytes()
    feed(monkeypatch, ["v", "v"])
    with pytest.raises(KeyboardInterrupt):
        ca.code_pages(DRAWS, TEXTS, RX, path, lambda d, p: "x")
    assert path.read_bytes() == before


def test_invalid_pages_in_unsure_row_cleared(monkeypatch, tmp_path):
    path = tmp_path / "c.csv"
    first = DRAWS[0]
    path.write_text("doc,page,A,pages,notes\n%s,%s,?,abc;9,old\n"
                    % (first["doc"], first["page"]))
    session(monkeypatch, path, ["1", ""])
    r = rows(path)[0]
    assert (r["A"], r["pages"], r["notes"]) == ("1", "", "")
