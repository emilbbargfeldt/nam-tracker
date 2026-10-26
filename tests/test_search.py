import json

import pytest

from core import search


@pytest.fixture(autouse=True)
def nam_data(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("NAM_DATA", str(tmp_path_factory.mktemp("namdata")))


def make_corpus(tmp_path, name="devices", pages=("alpha\nbeta", "Organ-\non-a-chip and gamma")):
    c = tmp_path / "corpus"
    c.mkdir()
    (c / "metadata.json").write_text(json.dumps(
        {"name": name, "documents": {"a.pdf": {"source": "test"}}}))
    (c / "a.pdf").write_bytes(b"%PDF fake")
    return c


def pages_of(pdf):
    return ["alpha\nbeta", "Organ-\non-a-chip and gamma"]


def pats(tmp_path, text):
    p = tmp_path / "pats.txt"
    p.write_text(text)
    return p


def test_search_pages_known_answer():
    patterns = [("chip", search.re.compile(r"organon-a-chip", search.re.I)),
                ("g", search.re.compile("gamma"))]
    hits = search.search_pages(pages_of(None), patterns)
    assert [(n, lab) for n, lab, _ in hits] == [(2, "chip"), (2, "g")]
    assert "gamma" in hits[1][2]
    assert search.search_pages(["nothing here"], patterns) == []


def test_pattern_file_labels_comments_blank(tmp_path):
    p = pats(tmp_path, "# c\n\nplain\nlab\tx+y\n")
    got = search.read_patterns(p)
    assert [lab for lab, _ in got] == ["plain", "lab"]
    assert got[1][1].search("XXY")


def test_search_corpus_writes_file_and_counts_only(tmp_path):
    c = make_corpus(tmp_path)
    out = tmp_path / "out.jsonl"
    docs, hits = search.search_corpus(
        c, pats(tmp_path, "chip\torgan.?on.?a.?chip\ngamma"), out,
        pages_of=pages_of)
    assert (docs, hits) == (1, 2)
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert rows[0]["page"] == 2 and rows[0]["doc"] == "a.pdf"
    assert rows[0]["meta"] == {"source": "test"}


def test_main_prints_counts_only(tmp_path, monkeypatch, capsys):
    c = make_corpus(tmp_path)
    monkeypatch.setattr(search, "load_pages", pages_of)
    monkeypatch.setattr(search, "search_corpus", lambda *a, **k: (1, 2))
    assert search.main([str(c), str(pats(tmp_path, "x")), str(tmp_path / "o")]) == 0
    assert capsys.readouterr().out.strip() == "documents: 1, hits: 2"


# Blinding

def test_corpus_without_metadata_refused(tmp_path):
    c = tmp_path / "c"
    c.mkdir()
    with pytest.raises(search.CorpusRefused):
        search.check_corpus(c)
    (c / "metadata.json").write_text("{}")
    with pytest.raises(search.CorpusRefused):
        search.check_corpus(c)


@pytest.mark.parametrize("name", ["nam", "NAM", "NAM tracker", "the nam corpus",
                                  "nam_corpus", "NAMs", "namtracker",
                                  "N.A.M. tracker", "NAM-x"])
def test_nam_corpus_refused_by_name(tmp_path, name):
    c = make_corpus(tmp_path, name=name)
    with pytest.raises(search.CorpusRefused):
        search.check_corpus(c)
    with pytest.raises(search.CorpusRefused):
        search.check_corpus(c, allow_nam=False, verdict=lambda: True)


@pytest.mark.parametrize("name", ["devices", "dynamic", "EMA assessments"])
def test_other_names_pass(tmp_path, name):
    assert search.check_corpus(make_corpus(tmp_path, name=name))["name"] == name


def test_unset_nam_data_refuses_everything(tmp_path, monkeypatch):
    c = make_corpus(tmp_path, name="devices")
    monkeypatch.delenv("NAM_DATA")
    with pytest.raises(search.CorpusRefused):
        search.check_corpus(c)


def test_quoted_tilde_nam_data_is_expanded(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "d").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("NAM_DATA", "~/d")
    c = home / "d" / "corpus"
    c.mkdir()
    (c / "metadata.json").write_text('{"name": "devices"}')
    with pytest.raises(search.CorpusRefused):
        search.check_corpus(c)


def test_symlinked_pdf_into_nam_data_refused(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "x.pdf").write_bytes(b"%PDF")
    monkeypatch.setenv("NAM_DATA", str(data))
    c = tmp_path / "corpus"
    c.mkdir()
    (c / "metadata.json").write_text('{"name": "devices"}')
    (c / "x.pdf").symlink_to(data / "x.pdf")
    with pytest.raises(search.CorpusRefused):
        search.check_corpus(c)


def test_nam_data_folder_refused_even_with_other_name(tmp_path, monkeypatch):
    monkeypatch.setenv("NAM_DATA", str(tmp_path))
    c = make_corpus(tmp_path, name="innocent")  # lies inside NAM_DATA
    with pytest.raises(search.CorpusRefused):
        search.check_corpus(c)
    link = tmp_path.parent / (tmp_path.name + "_link")
    link.symlink_to(c)
    try:
        with pytest.raises(search.CorpusRefused):
            search.check_corpus(link)
    finally:
        link.unlink()


def test_refusal_comes_before_any_pdf_is_read(tmp_path):
    c = make_corpus(tmp_path, name="nam")
    calls = []
    with pytest.raises(search.CorpusRefused):
        search.search_corpus(c, pats(tmp_path, "x"), tmp_path / "o",
                             pages_of=lambda p: calls.append(p) or [])
    assert calls == [] and not (tmp_path / "o").exists()


def test_flag_needs_verdict_in_head(tmp_path):
    c = make_corpus(tmp_path, name="nam")
    with pytest.raises(search.CorpusRefused):
        search.check_corpus(c, allow_nam=True, verdict=lambda: False)
    assert search.check_corpus(c, allow_nam=True, verdict=lambda: True)["name"] == "nam"


def test_verdict_reads_git_head_not_working_copy():
    seen = []

    class P:
        returncode, stdout = 0, "verdict text"

    def run(cmd, **kw):
        seen.append(cmd)
        return P()
    assert search.verdict_in_head(run) is True
    assert seen[0][:2] == ["git", "show"] and seen[0][2].startswith("HEAD:")
    P.returncode = 128
    assert search.verdict_in_head(run) is False
    P.returncode, P.stdout = 0, "  \n"
    assert search.verdict_in_head(run) is False

    def boom(cmd, **kw):
        raise FileNotFoundError("git")
    assert search.verdict_in_head(boom) is False


def test_no_verdict_file_in_head_today():
    # the real repo has no pilot verdict yet: the NAM corpus stays closed
    assert search.verdict_in_head() is False


def test_cli_refuses_nam_without_flag(tmp_path, capsys):
    c = make_corpus(tmp_path, name="nam")
    rc = search.main([str(c), str(pats(tmp_path, "x")), str(tmp_path / "o")])
    assert rc == 2 and "refused" in capsys.readouterr().out


def test_mutant_name_and_path_checks_removed_would_open_nam(tmp_path, monkeypatch):
    c = make_corpus(tmp_path, name="nam")
    with pytest.raises(search.CorpusRefused):
        search.check_corpus(c)
    monkeypatch.setattr(search, "_nam_name", lambda name: False)
    # mutant: with the name check gone this corpus is opened, so the tests
    # above that expect a refusal have teeth
    assert search.check_corpus(c)["name"] == "nam"


def test_ascii_only():
    open(search.__file__, encoding="ascii").read()
    open(__file__, encoding="ascii").read()
