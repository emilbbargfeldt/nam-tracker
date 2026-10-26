import json

import pytest

from studies.nam.inventory.fetch import Fetcher
from studies.nam.pilot import spikein_draw as sd


class FakePubMed:
    """Canned E-utilities: every year slice holds 5 records."""

    def __init__(self):
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        if "esearch" in url:
            q = sd.urllib.parse.parse_qs(sd.urllib.parse.urlparse(url).query)
            year = int(q["term"][0].split(" AND ")[-1].split("[")[0])
            retstart = int(q["retstart"][0])
            retmax = int(q["retmax"][0])
            ids = ["%d%03d" % (year, retstart + i) for i in range(retmax)]
            return json.dumps({"esearchresult": {"count": "5", "idlist": ids}}).encode()
        pmid = sd.urllib.parse.parse_qs(sd.urllib.parse.urlparse(url).query)["id"][0]
        return ("<PubmedArticleSet><PubmedArticle><MedlineCitation><Article><Abstract>"
                "<AbstractText Label='A'>text %s</AbstractText>"
                "<AbstractText>more</AbstractText></Abstract></Article>"
                "</MedlineCitation></PubmedArticle></PubmedArticleSet>" % pmid).encode()


def fetcher(tmp_path, opener):
    return Fetcher(root=tmp_path, opener=opener, min_free=0, sleep=lambda s: None)


def test_query_has_only_mesh_and_filters_no_text_term():
    q = sd.query(["Microphysiological Systems", "Lab-On-A-Chip Devices"], 2020)
    assert q == ('("Microphysiological Systems"[MeSH Terms] OR '
                 '"Lab-On-A-Chip Devices"[MeSH Terms]) AND humans[MeSH Terms] '
                 'AND english[Language] AND hasabstract AND 2020[pdat]')


def test_rate_is_at_most_three_calls_per_second(tmp_path):
    sleeps, now = [], [0.0]

    def sleep(x):
        sleeps.append(x)
        now[0] += x

    f = Fetcher(root=tmp_path, opener=FakePubMed(), min_free=0,
                min_interval=sd.MIN_INTERVAL_S, clock=lambda: now[0], sleep=sleep)
    sd.esearch(f, sd.query(["Organoids"], 2020))
    sd.esearch(f, sd.query(["Organoids"], 2021))
    assert sum(sleeps) >= 1 / 3 - 1e-9


def test_user_agent_is_sent(monkeypatch):
    seen = {}

    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return b""

    def fake(req, timeout=0):
        seen["ua"] = req.get_header("User-agent")
        return R()

    monkeypatch.setattr("urllib.request.urlopen", fake)
    Fetcher._urlopen(sd.esearch_url("x"))
    assert seen["ua"] and "nam-tracker" in seen["ua"]


def test_query_uses_pdat_slices():
    assert "[pdat]" in sd.query(["Organoids"], 2020)
    assert "[dp]" not in sd.query(["Organoids"], 2020)


def test_locate_maps_global_index_to_year_and_offset():
    counts = {y: 0 for y in sd.YEARS}
    counts[2015], counts[2016] = 3, 4
    assert sd.locate(counts, 0) == (2015, 0)
    assert sd.locate(counts, 3) == (2016, 0)
    assert sd.locate(counts, 6) == (2016, 3)
    with pytest.raises(IndexError):
        sd.locate(counts, 7)


def test_abstract_of_joins_labelled_parts():
    xml = (b"<S><PubmedArticle><MedlineCitation><Article><Abstract>"
           b"<AbstractText Label='BACKGROUND'>one <i>two</i></AbstractText>"
           b"<AbstractText>three</AbstractText></Abstract></Article>"
           b"</MedlineCitation></PubmedArticle>"
           b"<PubmedArticle><MedlineCitation><Article><Abstract>"
           b"<AbstractText>second</AbstractText></Abstract></Article>"
           b"</MedlineCitation></PubmedArticle></S>")
    assert sd.abstract_of(xml) == "BACKGROUND: one two\n\nthree"
    assert sd.abstract_of(b"<S/>") == ""
    other = (b"<S><PubmedArticle><MedlineCitation><OtherAbstract>"
             b"<AbstractText>plain</AbstractText></OtherAbstract>"
             b"</MedlineCitation></PubmedArticle></S>")
    assert sd.abstract_of(other) == ""


def test_error_json_and_missing_phrase_are_refused(tmp_path):
    f = fetcher(tmp_path, lambda u: b'{"error": "rate limit"}')
    with pytest.raises(RuntimeError):
        sd.esearch(f, "x")
    warn = {"esearchresult": {"count": "3", "idlist": [],
                              "warninglist": {"phrasesnotfound": ["Foo"]}}}
    g = fetcher(tmp_path / "g", lambda u: json.dumps(warn).encode())
    with pytest.raises(RuntimeError):
        sd.esearch(g, "x")


def test_empty_abstract_and_empty_idlist_stop_the_draw(tmp_path):
    class NoAbstract(FakePubMed):
        def __call__(self, url):
            if "efetch" in url:
                return b"<S><PubmedArticle><MedlineCitation><Article/></MedlineCitation></PubmedArticle></S>"
            return super().__call__(url)

    with pytest.raises(RuntimeError):
        sd.draw_term(fetcher(tmp_path / "a", NoAbstract()), ["Organoids"], set())

    class NoIds(FakePubMed):
        def __call__(self, url):
            if "esearch" in url and "retmax=1" in url:
                return json.dumps({"esearchresult": {"count": "5", "idlist": []}}).encode()
            return super().__call__(url)

    with pytest.raises(RuntimeError):
        sd.draw_term(fetcher(tmp_path / "b", NoIds()), ["Organoids"], set())


def test_draw_ends_with_error_when_records_are_exhausted(tmp_path):
    everything = set()
    sd.draw_term(fetcher(tmp_path / "a", FakePubMed()), ["Organoids"], everything)
    pool = {"%d%03d" % (y, i) for y in sd.YEARS for i in range(5)}
    with pytest.raises(RuntimeError):
        sd.draw_term(fetcher(tmp_path / "b", FakePubMed()), ["Organoids"], set(pool))


def test_rows_carry_index_offset_and_query(tmp_path):
    rows, _ = sd.draw_term(fetcher(tmp_path, FakePubMed()), ["Organoids"], set())
    for r in rows:
        assert r["query"] == sd.query(["Organoids"], r["year"])
        assert r["pmid"] == "%d%03d" % (r["year"], r["offset"])
        assert 0 <= r["offset"] < 5


def test_year_slice_over_paging_limit_is_refused(tmp_path):
    def opener(url):
        return json.dumps({"esearchresult": {"count": "10000", "idlist": []}}).encode()
    with pytest.raises(RuntimeError):
        sd.year_counts(fetcher(tmp_path, opener), ["Organoids"])


def test_draw_is_deterministic_distinct_and_per_term(tmp_path):
    a, _ = sd.draw_term(fetcher(tmp_path / "a", FakePubMed()), ["Organoids"], set())
    b, _ = sd.draw_term(fetcher(tmp_path / "b", FakePubMed()), ["Organoids"], set())
    assert [r["pmid"] for r in a] == [r["pmid"] for r in b]
    assert len(a) == sd.PER_TERM and len({r["pmid"] for r in a}) == sd.PER_TERM
    assert all(r["abstract"].startswith("A: text") for r in a)


def test_seed_changes_the_draw(tmp_path):
    a, _ = sd.draw_term(fetcher(tmp_path / "a", FakePubMed()), ["Organoids"], set(), seed=1)
    b, _ = sd.draw_term(fetcher(tmp_path / "b", FakePubMed()), ["Organoids"], set(), seed=2)
    assert [r["pmid"] for r in a] != [r["pmid"] for r in b]


def test_pmid_taken_by_earlier_term_is_not_drawn_again(tmp_path):
    first, _ = sd.draw_term(fetcher(tmp_path / "a", FakePubMed()), ["Organoids"], set())
    taken = {r["pmid"] for r in first}
    before = set(taken)
    again, _ = sd.draw_term(fetcher(tmp_path / "b", FakePubMed()), ["Organoids"], taken)
    assert not before & {r["pmid"] for r in again}


def test_main_writes_outside_repo_and_draws_twenty(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NAM_DATA", str(tmp_path))
    def make(**kw):
        assert kw["min_interval"] == sd.MIN_INTERVAL_S
        return fetcher(tmp_path / "c", FakePubMed())

    monkeypatch.setattr(sd, "Fetcher", make)
    assert sd.main([]) == 0
    rows = [json.loads(l) for l in (tmp_path / "spikeins" / "abstracts.jsonl").open()]
    assert len(rows) == 20 and len({r["pmid"] for r in rows}) == 20
    assert (tmp_path / "spikeins" / "draw.json").exists()
    assert "drew 20 abstracts" in capsys.readouterr().out


def test_first_twenty_are_unchanged_by_batches(tmp_path):
    base0, _, _ = sd.draw_all(fetcher(tmp_path / "a", FakePubMed()))
    base3, batches, _ = sd.draw_all(fetcher(tmp_path / "b", FakePubMed()), batches=3)
    assert [r["pmid"] for r in base0] == [r["pmid"] for r in base3]
    assert len(base0) == 20 and len(batches) == 3
    assert all(len(b) == 5 for b in batches)


def test_batch_has_one_row_per_term_in_fixed_rotation(tmp_path):
    _, batches, _ = sd.draw_all(fetcher(tmp_path, FakePubMed()), batches=2)
    for b in batches:
        assert [r["mesh"] for r in b] == sd.TERMS


def test_batches_are_distinct_from_base_and_each_other(tmp_path):
    base, batches, _ = sd.draw_all(fetcher(tmp_path, FakePubMed()), batches=2)
    pmids = [r["pmid"] for r in base] + [r["pmid"] for b in batches for r in b]
    assert len(pmids) == 30 and len(set(pmids)) == 30


def test_batch_n_is_the_same_whether_drawn_with_n_or_more(tmp_path):
    _, b2, _ = sd.draw_all(fetcher(tmp_path / "a", FakePubMed()), batches=2)
    _, b3, _ = sd.draw_all(fetcher(tmp_path / "b", FakePubMed()), batches=3)
    assert [r["pmid"] for r in b2[1]] == [r["pmid"] for r in b3[1]]


def test_main_batch_writes_only_batch_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("NAM_DATA", str(tmp_path))
    monkeypatch.setattr(sd, "Fetcher",
                        lambda **kw: fetcher(tmp_path / "c", FakePubMed()))
    assert sd.main([]) == 0
    base = (tmp_path / "spikeins" / "abstracts.jsonl").read_text()
    assert sd.main(["--batch", "1"]) == 0
    assert sd.main(["--batch", "1"]) == 2
    assert sd.main([]) == 2
    d = tmp_path / "spikeins"
    assert (d / "abstracts.jsonl").read_text() == base
    rows = [json.loads(l) for l in (d / "abstracts_batch1.jsonl").open()]
    assert len(rows) == 5
    text = (d / "abstracts_batch1_for_coding.txt").read_text()
    assert text.count("PMID ") == 5 and "mesh" not in text
    assert "drew batch 1: 5 abstracts" in capsys.readouterr().out


def test_main_batch_refuses_if_base_set_differs(tmp_path, monkeypatch):
    monkeypatch.setenv("NAM_DATA", str(tmp_path))
    monkeypatch.setattr(sd, "Fetcher",
                        lambda **kw: fetcher(tmp_path / "c", FakePubMed()))
    (tmp_path / "spikeins").mkdir()
    assert sd.main(["--batch", "1"]) == 2
    (tmp_path / "spikeins" / "abstracts.jsonl").write_text('{"pmid": "1"}\n')
    with pytest.raises(RuntimeError):
        sd.main(["--batch", "1"])


def test_main_batch_refuses_if_counts_differ(tmp_path, monkeypatch):
    monkeypatch.setenv("NAM_DATA", str(tmp_path))
    monkeypatch.setattr(sd, "Fetcher",
                        lambda **kw: fetcher(tmp_path / "c", FakePubMed()))
    assert sd.main([]) == 0
    path = tmp_path / "spikeins" / "draw.json"
    record = json.loads(path.read_text())
    record["terms"][0]["counts_by_year"]["2015"] = 4
    path.write_text(json.dumps(record))
    with pytest.raises(RuntimeError):
        sd.main(["--batch", "1"])


def test_batch_8_is_possible_and_exhaustion_stops_a_batch(tmp_path):
    _, batches, _ = sd.draw_all(fetcher(tmp_path / "a", FakePubMed()), batches=8)
    assert len(batches) == 8
    with pytest.raises(RuntimeError):
        sd.draw_all(fetcher(tmp_path / "b", FakePubMed()), batches=12)


class Overlap(FakePubMed):
    """Every term sees the same PMIDs, so cross-term duplicates are frequent."""

    def __call__(self, url):
        if "esearch" in url and "retmax=1" in url:
            q = sd.urllib.parse.parse_qs(sd.urllib.parse.urlparse(url).query)
            year = int(q["term"][0].split(" AND ")[-1].split("[")[0])
            off = int(q["retstart"][0])
            return json.dumps({"esearchresult": {"count": "5",
                              "idlist": ["%d%03d" % (year, off)]}}).encode()
        return super().__call__(url)


def reference_base(fetcher_, terms, seed):
    """The base draw as originally written (one taken set, term by term)."""
    taken, out = set(), []
    for mesh in terms:
        counts = sd.year_counts(fetcher_, mesh)
        total = sum(counts.values())
        rng = sd.random.Random("%d:%s" % (seed, "|".join(mesh)))
        seen, got = set(), 0
        while got < sd.PER_TERM:
            index = rng.randrange(total)
            if index in seen:
                continue
            seen.add(index)
            year, offset = sd.locate(counts, index)
            ids = sd.esearch(fetcher_, sd.query(mesh, year), retstart=offset,
                             retmax=1)["idlist"]
            if ids[0] in taken:
                continue
            taken.add(ids[0])
            out.append(ids[0])
            got += 1
    return out


def test_base_draw_equals_original_algorithm_with_cross_term_duplicates(tmp_path):
    base, _, _ = sd.draw_all(fetcher(tmp_path / "a", Overlap()), batches=2)
    ref = reference_base(fetcher(tmp_path / "b", Overlap()), sd.TERMS, sd.SEED)
    assert [r["pmid"] for r in base] == ref
    assert len(set(ref)) == 20


@pytest.mark.parametrize("args", [["--batch"], ["--batch", "0"], ["--batch", "9"],
                                  ["--batch", "x"], ["--other", "1"]])
def test_main_rejects_bad_arguments(args, capsys):
    assert sd.main(args) == 2
    assert "nothing run" in capsys.readouterr().out
