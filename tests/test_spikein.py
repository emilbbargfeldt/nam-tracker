import hashlib
import json
import random
import re
from pathlib import Path

import pytest

from studies.nam.extract import candidates, cli, keywords, spikein


def filler(n_lines=15, tag=0):
    return "\n".join("Group %02d-%02d animals received the vehicle control by "
                     "oral gavage once daily for four weeks." % (tag, i)
                     for i in range(n_lines))


def make_doc(n_pages=3, a_pages=()):
    pages = []
    for n in range(1, n_pages + 1):
        text = filler(tag=n)
        if n in a_pages:
            text += "\nHuman iPSC-derived cardiomyocytes were used in this assay."
        pages.append(text)
    return pages, list(range(1, n_pages + 1))


def abstract_for(pmid):
    return ("Study %s: Human iPSC-derived cardiomyocytes and liver organoids were "
            "exposed to the compound.\nContractility was measured on a "
            "microphysiological system." % pmid)


SENTENCE = "Human iPSC-derived cardiomyocytes and liver organoids were exposed to the compound."


@pytest.fixture
def world(tmp_path):
    docs = {"DOC%02d" % i: make_doc() for i in range(12)}
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "x").write_bytes(b"cached pdf")
    abstracts = {p: abstract_for(p) for p in ("111", "222", "333")}
    return tmp_path, cache, docs, abstracts


def tree_md5(path):
    h = hashlib.md5()
    for p in sorted(Path(path).rglob("*")):
        h.update(str(p).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def prep(world, seed=spikein.SEED):
    tmp, cache, docs, abstracts = world
    out = tmp / "spiked"
    manifest = spikein.prepare(out, cache, docs, abstracts, docs.get, "h" * 40, seed)
    return out, manifest


def page_of_marker(text, index):
    return int(re.findall(r"=== Page (\d+) ===", text[:index])[-1])


def good_caller(text):
    """Quote the inserted sentence on the page it is on."""
    i = text.find("Study ")
    if i < 0:
        return {"findings": []}
    return {"findings": [{"code": "A", "page": page_of_marker(text, i),
                          "quote": SENTENCE}]}


def outside_caller(text):
    """Quote a filler line of the spiked page that is not inserted text."""
    i = text.find("Study ")
    page = page_of_marker(text, i)
    start = text.rfind("=== Page %d ===" % page, 0, i)
    line = next(ln for ln in text[start:].split("\n") if ln.startswith("Group"))
    return {"findings": [{"code": "A", "page": page, "quote": line}]}


def test_filler_has_no_a_hits_and_abstract_has():
    pages, numbers = make_doc()
    per_code, _ = candidates.candidate_pages(pages, numbers)
    assert per_code["A"] == []
    assert keywords.match_page(abstract_for("1"))["A"]


def test_seed_constant_is_fixed():
    assert spikein.SEED == 20261030


def test_insert_abstract_positions():
    text = filler(4)
    for line in (0, 2, 4):
        new, (s, e), n = spikein.insert_abstract(text, abstract_for("9"), line)
        assert new[s:e] == abstract_for("9") and n == 2
        assert new.split("\n")[line] == abstract_for("9").split("\n")[0]
    with pytest.raises(spikein.SpikeError):
        spikein.insert_abstract(text, "  ", 0)
    with pytest.raises(spikein.SpikeError):
        spikein.insert_abstract(text, "x", 5)


def test_eligible_pages_skip_candidates_and_low_text_pages():
    pages, numbers = make_doc(4, a_pages=(2,))
    pages[2] = "short"
    assert spikein.eligible_pages(pages, numbers) == [1, 4]


def test_choose_is_deterministic_distinct_and_from_the_seed(world):
    _, _, docs, abstracts = world
    a = spikein.choose(docs, abstracts, 5, docs.get)
    b = spikein.choose(docs, abstracts, 5, docs.get)
    assert a == b and len({p["doc"] for p in a}) == 3
    order = sorted(docs)
    random.Random("5:spikein").shuffle(order)
    assert a[0]["doc"] == order[0]
    assert spikein.choose(docs, abstracts, 6, docs.get) != a


def test_choose_only_eligible_pages_and_skips_unusable_docs(world):
    _, _, docs, abstracts = world
    docs["DOC00"] = make_doc(3, a_pages=(1, 2))
    docs["DOC01"] = make_doc(3, a_pages=(1, 2, 3))
    loads = dict(docs, DOC02=None)
    for seed in range(20):
        for pl in spikein.choose(docs, abstracts, seed, loads.get):
            assert pl["doc"] not in ("DOC01", "DOC02")
            if pl["doc"] == "DOC00":
                assert pl["page"] == 3


def test_choose_fails_when_documents_run_out(world):
    _, _, docs, abstracts = world
    few = {k: docs[k] for k in sorted(docs)[:2]}
    with pytest.raises(spikein.SpikeError):
        spikein.choose(few, abstracts, 1, few.get)


def test_prepare_writes_copies_and_manifest(world):
    out, manifest = prep(world)
    assert len(manifest) == 3
    keys = {"pmid", "doc", "page", "char_start", "char_end", "line_start",
            "line_count", "seed", "git_head", "keywords_md5", "prompt_hash"}
    for row in manifest:
        assert keys <= set(row)
        assert row["seed"] == spikein.SEED and row["git_head"] == "h" * 40
        assert row["keywords_md5"] == spikein.md5_of(spikein.KEYWORDS)
        pages, numbers = spikein.load_copy(out, row["doc"])
        page = pages[row["page"] - 1]
        assert page[row["char_start"]:row["char_end"]] == abstract_for(row["pmid"])
    lines = [json.loads(x) for x in (out / "manifest.jsonl").open()]
    assert lines == manifest


def test_prepare_never_changes_the_cache_and_refuses_cache_paths(world):
    tmp, cache, docs, abstracts = world
    before = tree_md5(cache)
    prep(world)
    assert tree_md5(cache) == before
    with pytest.raises(spikein.SpikeError):
        spikein.prepare(cache / "spiked", cache, docs, abstracts, docs.get, "h")
    with pytest.raises(spikein.SpikeError):
        spikein.prepare(cache, cache, docs, abstracts, docs.get, "h")
    with pytest.raises(spikein.SpikeError):
        spikein.prepare(tmp, cache, docs, abstracts, docs.get, "h")
    assert tree_md5(cache) == before


def test_prepare_does_not_overwrite(world):
    prep(world)
    with pytest.raises(spikein.SpikeError):
        prep(world)


def test_run_finds_all_and_prints_totals_only(world):
    out, manifest = prep(world)
    cache_before = tree_md5(world[1])
    lines = []
    k, m, n = spikein.measure_all(out, good_caller, say=lines.append)
    assert (k, m, n) == (3, 3, 3)
    text = "\n".join(lines)
    assert "keyword step: found 3, not found 0" in text
    assert "model step: found 3, not found 0" in text
    assert not any(row["pmid"] in text or row["doc"] in text for row in manifest)
    assert tree_md5(world[1]) == cache_before
    assert not (out / "results.jsonl").exists()
    totals = (out / "totals.json").read_text()
    assert json.loads(totals) == {"spike_ins": 3, "keyword_found": 3,
                                  "model_found": 3, "call_errors": 0}
    assert not any(row["pmid"] in totals or row["doc"] in totals for row in manifest)


def test_model_step_needs_a_verified_quote_on_the_spiked_page_that_overlaps(world):
    out, manifest = prep(world)

    outside = outside_caller

    def wrong_code(text):
        r = good_caller(text)
        r["findings"][0]["code"] = "C"
        return r

    def wrong_page(text):
        r = good_caller(text)
        r["findings"][0]["page"] += 1
        return r

    def invented(text):
        r = good_caller(text)
        r["findings"][0]["quote"] = "organoids cured every animal in the study"
        return r

    for caller in (outside, wrong_code, wrong_page, invented, lambda t: {"findings": []}):
        k, m, n = spikein.measure_all(out, caller, say=lambda s: None)
        assert (k, m, n) == (3, 0, 3)


def test_call_errors_are_counted_not_found(world):
    out, _ = prep(world)

    def broken(text):
        raise cli.CallError("boom")

    lines = []
    assert spikein.measure_all(out, broken, say=lines.append) == (3, 0, 3)
    assert "call errors 3" in "\n".join(lines)


def test_mutant_keywords_without_a_patterns_is_caught(world, monkeypatch):
    out, _ = prep(world)
    clean = spikein.measure_all(out, good_caller, say=lambda s: None)
    assert clean == (3, 3, 3)
    mutant = keywords._build(keywords.SEP, {**keywords.TEMPLATES, "A": []})
    monkeypatch.setattr(keywords, "_COMPILED", mutant)
    assert spikein.measure_all(out, good_caller, say=lambda s: None) == (0, 0, 3)


def test_mutant_overlap_always_true_is_caught(world, monkeypatch):
    out, _ = prep(world)

    outside = outside_caller

    assert spikein.measure_all(out, outside, say=lambda s: None)[1] == 0
    monkeypatch.setattr(spikein, "overlaps", lambda spans, s, e: True)
    assert spikein.measure_all(out, outside, say=lambda s: None)[1] == 3


def test_mutant_eligibility_ignoring_candidates_is_caught(monkeypatch):
    pages, numbers = make_doc(3, a_pages=(1, 2))
    assert spikein.eligible_pages(pages, numbers) == [3]
    monkeypatch.setattr(candidates, "candidate_pages",
                        lambda p, n: ({c: [] for c in keywords.CODES}, []))
    assert spikein.eligible_pages(pages, numbers) == [1, 2, 3]


def test_run_refuses_changed_keywords_or_prompt(world, monkeypatch):
    out, _ = prep(world)
    monkeypatch.setattr(spikein, "md5_of", lambda p: "0" * 32)
    with pytest.raises(spikein.SpikeError):
        spikein.measure_all(out, good_caller, say=lambda s: None)
    monkeypatch.undo()
    monkeypatch.setattr(spikein.prompt, "prompt_hash", lambda p=None: "x")
    with pytest.raises(spikein.SpikeError):
        spikein.measure_all(out, good_caller, say=lambda s: None)


def test_a1_pmids_need_committed_file_and_complete_codes(tmp_path):
    f = tmp_path / "c.csv"
    text = "pmid,A,notes\n1,1,\n2,0,\n3,1,UNSURE: x\n"
    f.write_text(text)
    assert spikein.a1_pmids(f, committed=text) == ["1", "3"]
    with pytest.raises(spikein.SpikeError):
        spikein.a1_pmids(f, committed=text + "4,1,\n")
    with pytest.raises(spikein.SpikeError):
        spikein.a1_pmids(f, committed=None)
    blank = "pmid,A,notes\n1,,\n"
    f.write_text(blank)
    with pytest.raises(spikein.SpikeError):
        spikein.a1_pmids(f, committed=blank)


def test_load_abstracts(tmp_path):
    (tmp_path / "abstracts.jsonl").write_text(
        json.dumps({"pmid": "1", "abstract": "a"}) + "\n"
        + json.dumps({"pmid": "2", "abstract": "b"}) + "\n")
    (tmp_path / "abstracts_batch1.jsonl").write_text(
        json.dumps({"pmid": "3", "abstract": "c"}) + "\n")
    assert spikein.load_abstracts(tmp_path, {"1", "3"}) == {"1": "a", "3": "c"}
    with pytest.raises(spikein.SpikeError):
        spikein.load_abstracts(tmp_path, {"9"})
    (tmp_path / "abstracts_batch2.jsonl").write_text(
        json.dumps({"pmid": "1", "abstract": "a"}) + "\n")
    with pytest.raises(spikein.SpikeError):
        spikein.load_abstracts(tmp_path, {"1"})


def test_locate_quote_exact_all_occurrences_and_fuzzy_cluster():
    page = "alpha beta\ngamma delta epsilon zeta\nalpha beta"
    assert spikein.locate_quote(page, "alpha beta") == [(0, 10), (36, 46)]
    assert spikein.locate_quote(page, "beta gamma") == [(6, 16)]
    spans = spikein.locate_quote(page, "gamma delta epsilonn zeta")
    assert len(spans) == 1 and page[spans[0][0]:spans[0][1]].startswith("gamma")
    assert spikein.locate_quote(page, "") == []
    assert spikein.locate_quote("abc", "qqqqqqqq") == []


def test_fuzzy_span_is_not_stretched_over_distant_common_blocks():
    page = "the cells were fixed. " + "x" * 300 + " the cells were measured."
    spans = spikein.locate_quote(page, "the cells were fixd.")
    assert len(spans) == 1 and spans[0][1] < 60


def test_quote_occurring_twice_counts_if_the_inserted_copy_overlaps():
    page = "Same sentence here.\n" + filler(2) + "\nSame sentence here.\nend"
    spans = spikein.locate_quote(page, "Same sentence here.")
    assert len(spans) == 2
    last = spans[1]
    assert spikein.overlaps(spans, last[0], last[1])
    assert not spikein.overlaps([spans[0]], last[0], last[1])


def test_overlap_needs_half_of_the_quote_inside_the_inserted_text():
    assert not spikein.overlaps([(10, 30)], 29, 50)      # 1 character
    assert not spikein.overlaps([(10, 30)], 21, 50)      # 9 of 20
    assert spikein.overlaps([(10, 30)], 20, 50)          # exactly 50 %
    assert spikein.overlaps([(10, 30)], 0, 50)           # fully inside
    assert spikein.overlaps([(0, 4), (20, 30)], 20, 50)  # one occurrence is enough
    assert not spikein.overlaps([], 0, 5)
    assert not spikein.overlaps([(5, 5)], 0, 10)


def test_quote_with_one_character_inside_is_not_found(world):
    out, manifest = prep(world)

    def edge(text):
        i = text.find("Study ")
        page = page_of_marker(text, i)
        start = text.rfind("=== Page %d ===" % page, 0, i)
        pre = [ln for ln in text[start:i].split("\n") if ln.startswith("Group")]
        last = pre[-1] if pre else "Group"
        return {"findings": [{"code": "A", "page": page, "quote": last}]}

    assert spikein.measure_all(out, edge, say=lambda s: None)[1] == 0


@pytest.mark.parametrize("where", ["first", "last"])
def test_insertion_at_first_and_last_line_and_multiparagraph(where):
    text = filler(4)
    line = 0 if where == "first" else 4
    abstract = "Para one about organoids.\n\nPara two.\r\nPara three."
    new, (s, e), n = spikein.insert_abstract(text, abstract, line)
    assert new[s:e] == abstract and n == 4


def test_keyword_step_needs_a_hit_in_the_inserted_text_itself(world):
    tmp, cache, docs, _ = world
    plain = {"111": "Study 111: nothing relevant was measured at all in this note."}
    out = tmp / "spiked"
    spikein.prepare(out, cache, docs, plain, docs.get, "h", 1)
    assert spikein.measure_all(out, good_caller, say=lambda s: None)[0] == 0


def test_mutant_locate_returning_whole_page_is_caught(world, monkeypatch):
    out, _ = prep(world)
    assert spikein.measure_all(out, outside_caller, say=lambda s: None)[1] == 0
    monkeypatch.setattr(spikein, "locate_quote", lambda page, quote: [(0, len(page))])
    assert spikein.measure_all(out, outside_caller, say=lambda s: None)[1] == 0
    monkeypatch.setattr(spikein, "locate_quote",
                        lambda page, quote: [(page.find("Study "), page.find("Study ") + 9)])
    assert spikein.measure_all(out, outside_caller, say=lambda s: None)[1] == 3


def test_a1_pmids_handles_multiline_notes(tmp_path):
    f = tmp_path / "c.csv"
    text = 'pmid,A,notes\n1,1,"two\nlines"\n2,0,\n'
    f.write_text(text)
    assert spikein.a1_pmids(f, committed=text) == ["1"]


def test_git_dirty_reports_changes_in_a_repo(tmp_path):
    import subprocess
    run = lambda *a: subprocess.run(a, cwd=tmp_path, check=True, capture_output=True)
    run("git", "init", "-q")
    (tmp_path / "studies").mkdir()
    (tmp_path / "studies" / "a.py").write_text("x")
    assert spikein.git_dirty(("studies",), tmp_path) != []
    run("git", "add", "studies")
    run("git", "-c", "user.email=a@b", "-c", "user.name=n", "commit", "-q", "-m", "m")
    assert spikein.git_dirty(("studies",), tmp_path) == []
    (tmp_path / "studies" / "a.py").write_text("y")
    assert len(spikein.git_dirty(("studies",), tmp_path)) == 1


def test_read_only_fetcher_serves_the_cache_and_never_fetches(tmp_path):
    from studies.nam.inventory.fetch import Fetcher
    calls = []
    ro = spikein.read_only_fetcher(Fetcher)(root=tmp_path,
                                            opener=lambda u: calls.append(u) or b"x")
    with pytest.raises(spikein.SpikeError):
        ro.get("http://example/a")
    assert calls == [] and list(ro.cache.glob("*")) == []
    path = ro.path_for("http://example/b")
    path.write_bytes(b"cached")
    assert ro.get("http://example/b") == path


def _old_a_window_chars(pages, numbers, radius=10):
    """Frozen copy of the pre-refactor a_window_chars."""
    total = 0
    for run in candidates._runs(numbers):
        lines, hits = [], []
        for n in run:
            page_lines = pages[n - 1].split("\n")
            hits += [len(lines) + i for i in candidates.a_hit_lines(pages[n - 1])]
            lines += page_lines
        merged = []
        for h in sorted(hits):
            lo, hi = max(0, h - radius), min(len(lines) - 1, h + radius)
            if merged and lo <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], hi)
            else:
                merged.append([lo, hi])
        for lo, hi in merged:
            total += candidates.folded_chars("\n".join(lines[lo:hi + 1]))
    return total


@pytest.mark.parametrize("hits", [(2,), (14,), (1, 3), (0, 2), ()])
def test_a_window_chars_equals_the_frozen_old_function(hits):
    pages = []
    for n in (1, 2, 3):
        lines = filler(15, n).split("\n")
        if n in hits or (n == 2 and hits):
            lines[14 if hits and hits[0] == 14 else 1] = "organoids were used here."
        pages.append("\n".join(lines))
    for numbers in ([1, 2, 3], [1, 3], [2]):
        assert (candidates.a_window_chars(pages, numbers)
                == _old_a_window_chars(pages, numbers))


def test_main_rejects_other_arguments(capsys):
    assert spikein.main([]) == 2
    assert spikein.main(["other"]) == 2
    assert "nothing run" in capsys.readouterr().out


def test_check_run_state_refuses_missing_manifest_repeat_dirty_and_other_head(world):
    out, manifest = prep(world)
    head = manifest[0]["git_head"]
    spikein.check_run_state(out, head, [])
    with pytest.raises(spikein.SpikeError):
        spikein.check_run_state(out, head, [" M x"])
    with pytest.raises(spikein.SpikeError):
        spikein.check_run_state(out, "other", [])
    with pytest.raises(spikein.SpikeError):
        spikein.check_run_state(out / "none", head, [])
    spikein.measure_all(out, good_caller, say=lambda s: None)
    with pytest.raises(spikein.SpikeError):
        spikein.check_run_state(out, head, [])


def test_git_dirty_default_paths_include_core():
    assert "core" in spikein.git_dirty.__defaults__[0]


def test_pmids_are_strings_everywhere(tmp_path):
    (tmp_path / "abstracts.jsonl").write_text(
        json.dumps({"pmid": 111, "abstract": "a"}) + "\n"
        + json.dumps({"pmid": " 222 ", "abstract": "b"}) + "\n")
    assert spikein.load_abstracts(tmp_path, {"111", 222}) == {"111": "a", "222": "b"}
    f = tmp_path / "c.csv"
    text = "pmid,A,notes\n 111 ,1,\n222,0,\n"
    f.write_text(text)
    assert spikein.a1_pmids(f, committed=text) == ["111"]
