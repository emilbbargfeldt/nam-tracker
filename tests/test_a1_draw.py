import json
import random

import pytest

from studies.nam.extract import keywords
from studies.nam.pilot import a1_draw as a1

TERMS = ["tissue chip", "Gut  Model"]


def page(tag, extra=None, n=12):
    lines = ["Line %02d-%02d of ordinary report text without special words." % (tag, i)
             for i in range(n)]
    if extra:
        lines[extra[0]] = extra[1]
    return "\n".join(lines)


def make_docs(n_docs=25, hit_docs=None):
    """Document d has pages 1..3; documents in hit_docs have a hit on page 2
    (and some on page 3)."""
    hit_docs = set(range(n_docs)) if hit_docs is None else set(hit_docs)
    docs = {}
    for d in range(n_docs):
        pages = [page(d * 10 + p) for p in (1, 2, 3)]
        if d in hit_docs:
            pages[1] = page(d * 10 + 2, (5, "A tissue   chip was used here."))
            if d % 2:
                pages[2] = page(d * 10 + 3, (7, "A GUT model, also."))
        docs["DOC%02d" % d] = (pages, [1, 2, 3])
    return docs


def test_read_terms_skips_blank_and_comments():
    assert a1.read_terms("# c\n\n a b \nc\n") == ["a b", "c"]
    with pytest.raises(a1.A1Error):
        a1.read_terms("# only\n\n")


def test_terms_must_equal_git_head(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("organoid\n")
    assert a1.committed_terms(f, committed="organoid\n") == ["organoid"]
    with pytest.raises(a1.A1Error):
        a1.committed_terms(f, committed="other\n")
    with pytest.raises(a1.A1Error):
        a1.committed_terms(f, committed=None)


def test_hits_use_terms_only_not_keywords():
    pages = ["We used organoids and iPSC-derived cells.", "A tissue chip.", "Gut\nmodel"]
    assert keywords.match_page(pages[0])["A"]
    assert a1.hit_pages(pages, [1, 2, 3], a1.compile_terms(TERMS)) == [2, 3]


def test_hits_are_case_and_whitespace_flexible_literal():
    rx = a1.compile_terms(["tissue chip"])
    assert rx[0].search("TISSUE\n  Chip")
    assert not rx[0].search("tissue-chip")
    assert not a1.compile_terms(["a.c"])[0].search("abc")


def test_index_keeps_only_documents_with_hits_and_skips_unreadable():
    docs = make_docs(6, hit_docs=[0, 1, 4])
    loads = dict(docs, DOC05=None)
    idx = a1.build_index(docs, loads.get, TERMS)
    assert sorted(idx) == ["DOC00", "DOC01", "DOC04"]
    assert idx["DOC00"] == [2] and idx["DOC01"] == [2, 3]


def test_draw_is_deterministic_one_page_per_document_and_a_hit_page():
    idx = a1.build_index(make_docs(), make_docs().get, TERMS)
    a = a1.draw_batch(idx, 1)
    assert a == a1.draw_batch(idx, 1)
    assert len(a) == 10 and len({d for d, _ in a}) == 10
    assert all(p in idx[d] for d, p in a)
    assert a != a1.draw_batch(idx, 1, seed=1)


def test_documents_are_uniform_among_hit_documents_from_the_seed():
    idx = a1.build_index(make_docs(), make_docs().get, TERMS)
    order = sorted(idx)
    random.Random("%d:a1" % a1.SEED).shuffle(order)
    assert [d for d, _ in a1.draw_batch(idx, 1)] == order[:10]
    assert [d for d, _ in a1.draw_batch(idx, 2)] == order[10:20]


def test_page_pick_is_independent_of_other_documents():
    docs = make_docs()
    idx = a1.build_index(docs, docs.get, TERMS)
    fewer = {k: v for k, v in idx.items() if k != "DOC01"}
    full = dict(a1.draw_batch(idx, 1))
    for doc, page in a1.draw_batch(fewer, 1):
        if doc in full:
            assert page == full[doc]
    assert a1.pick_page("DOC03", [2, 3]) in (2, 3)


def test_batches_do_not_overlap_and_too_few_documents_fail():
    idx = a1.build_index(make_docs(), make_docs().get, TERMS)
    docs = {d for d, _ in a1.draw_batch(idx, 1)} | {d for d, _ in a1.draw_batch(idx, 2)}
    assert len(docs) == 20
    few = a1.build_index(make_docs(25, hit_docs=range(9)), make_docs(25, range(9)).get, TERMS)
    with pytest.raises(a1.A1Error):
        a1.draw_batch(few, 1)
    with pytest.raises(a1.A1Error):
        a1.draw_batch(idx, 3)


def test_context_is_plus_minus_three_lines_around_the_first_match():
    text = page(1, (5, "tissue chip"))
    rows = a1.context(text, TERMS)
    assert rows == text.split("\n")[2:9] and rows[3] == "tissue chip"
    text = "tissue chip\n" + page(1)
    assert a1.context(text, TERMS)[0] == "tissue chip"
    assert len(a1.context(text, TERMS)) == 4


def test_render_shows_doc_page_url_and_context_only():
    docs = make_docs()
    idx = a1.build_index(docs, docs.get, TERMS)
    draws = a1.draw_batch(idx, 1)
    urls = {d: "https://example.org/%s.pdf" % d for d, _ in draws}
    text = a1.render(1, draws, urls, docs.get, TERMS)
    assert text.splitlines()[0] == "batch 1"
    assert text.count(" | page ") == 10
    lowered = text.lower()
    for word in ("hits", "documents with", "total", "distribution"):
        assert word not in lowered


PAIRS = [("d%d" % i, 1) for i in range(10)]


def codes_csv(values, pairs=PAIRS):
    return "doc,page,A,notes\n" + "".join(
        "%s,%d,%s,\n" % (d, p, v) for (d, p), v in zip(pairs, values))


def test_fill_rule():
    ok = codes_csv([str(i % 2) for i in range(10)])
    a1.check_fill_rule(1, "", None, [])
    a1.check_fill_rule(2, ok, ok, PAIRS)
    for text, committed, earlier in [
            (ok, None, PAIRS),                                  # not committed
            (ok, ok + "x", PAIRS),                              # differs from HEAD
            (ok, ok, PAIRS + [("e", 1)]),                       # rows missing
            (ok, ok, PAIRS[:9] + [("zz", 1)])]:                 # other documents
        with pytest.raises(a1.A1Error):
            a1.check_fill_rule(2, text, committed, earlier)
    dup = codes_csv(["1"] * 10, PAIRS[:9] + [PAIRS[0]])         # duplicate document
    with pytest.raises(a1.A1Error):
        a1.check_fill_rule(2, dup, dup, PAIRS)
    blank = codes_csv(["", "0", "0", "0", "0", "0", "0", "0", "0", "0"])
    with pytest.raises(a1.A1Error):
        a1.check_fill_rule(2, blank, blank, PAIRS)             # uncoded row
    full = codes_csv(["1"] * 10)
    with pytest.raises(a1.A1Error):
        a1.check_fill_rule(2, full, full, PAIRS)               # 10 A=1 already
    with pytest.raises(a1.A1Error):
        a1.check_fill_rule(6, ok, ok, PAIRS)
    nocol = "doc,page,notes\n" + "".join("d%d,1,\n" % i for i in range(10))
    with pytest.raises(a1.A1Error):
        a1.check_fill_rule(2, nocol, nocol, PAIRS)             # no A column


def test_mutant_search_matching_every_page_is_caught(monkeypatch):
    docs = make_docs(25, hit_docs=range(12))
    clean = a1.build_index(docs, docs.get, TERMS)
    assert len(clean) == 12
    monkeypatch.setattr(a1, "hit_pages", lambda pages, numbers, rx: sorted(numbers))
    assert len(a1.build_index(docs, docs.get, TERMS)) == 25


def test_search_code_does_not_call_keywords():
    import inspect
    src = inspect.getsource(a1)
    assert "match_page" not in src and "keywords." not in src.replace(
        "keywords.py", "")


def test_context_without_match_and_out_of_range_pages():
    assert a1.context("no hit here\nat all", TERMS) == []
    assert a1.hit_pages(["tissue chip"], [1, 2, 5], a1.compile_terms(TERMS)) == [1]


@pytest.fixture
def world(tmp_path):
    docs = make_docs()
    items = {d: {"url": "https://example.org/%s.pdf" % d} for d in docs}
    return tmp_path / "a1", items, docs.get


def test_run_writes_record_last_and_prints_only_the_draw(world):
    out, items, load = world
    text = a1.run(1, out, items, load, TERMS, "", None, "h" * 40)
    rec = json.loads((out / "batch1.json").read_text())
    assert len(rec["draws"]) == 10 and rec["git_head"] == "h" * 40
    assert text.count(" | page ") == 10
    assert not (out / "hits.json").exists()
    assert sorted(p.name for p in out.iterdir()) == ["batch1.json"]
    with pytest.raises(a1.A1Error):
        a1.run(1, out, items, load, TERMS, "", None, "h")        # not drawn again


def test_run_failing_render_leaves_no_record(world):
    out, items, load = world
    docs = make_docs()
    calls = {"n": 0}

    def flaky(doc):
        calls["n"] += 1
        return None if calls["n"] > len(docs) else docs[doc]

    with pytest.raises(a1.A1Error):
        a1.run(1, out, items, flaky, TERMS, "", None, "h")
    assert not (out / "batch1.json").exists()


def test_run_second_batch_continues_the_order_and_checks_codes(world):
    out, items, load = world
    a1.run(1, out, items, load, TERMS, "", None, "h")
    first = [(d["doc"], d["page"]) for d in
             json.loads((out / "batch1.json").read_text())["draws"]]
    codes = codes_csv(["0"] * 10, first)
    text = a1.run(2, out, items, load, TERMS, codes, codes, "h")
    second = [(d["doc"], d["page"]) for d in
              json.loads((out / "batch2.json").read_text())["draws"]]
    assert not {d for d, _ in first} & {d for d, _ in second}
    assert text.count(" | page ") == 10
    with pytest.raises(a1.A1Error):
        a1.run(3, out, items, load, TERMS, codes, codes, "h")    # codes of batch 2 missing
    with pytest.raises(a1.A1Error):
        a1.run(4, out, items, load, TERMS, codes, codes, "h")    # batch 3 missing


def test_run_refuses_a_later_batch_when_the_search_result_changed(world):
    out, items, load = world
    a1.run(1, out, items, load, TERMS, "", None, "h")
    first = [(d["doc"], d["page"]) for d in
             json.loads((out / "batch1.json").read_text())["draws"]]
    codes = codes_csv(["0"] * 10, first)
    docs = make_docs(25, hit_docs=range(24))
    with pytest.raises(a1.A1Error):
        a1.run(2, out, items, docs.get, TERMS, codes, codes, "h")


def test_later_batch_that_cannot_be_drawn_gives_a_generic_message():
    idx = {"D%02d" % i: [1] for i in range(15)}
    with pytest.raises(a1.A1Error) as e:
        a1.draw_batch(idx, 2)
    assert str(e.value) == "batch cannot be drawn"


def test_missing_terms_file_is_a_clean_error(tmp_path):
    with pytest.raises(a1.A1Error):
        a1.committed_terms(tmp_path / "none.txt", committed="x")


def test_main_rejects_bad_arguments(capsys):
    for args in ([], ["--batch"], ["--batch", "0"], ["--batch", "6"], ["x", "1"]):
        assert a1.main(args) == 2
    assert "nothing run" in capsys.readouterr().out


def test_seed_constant():
    assert a1.SEED == 20261031 and a1.BATCH == 10 and a1.MAX_BATCHES == 5
