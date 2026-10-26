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
    assert sd.main() == 0
    rows = [json.loads(l) for l in (tmp_path / "spikeins" / "abstracts.jsonl").open()]
    assert len(rows) == 20 and len({r["pmid"] for r in rows}) == 20
    assert (tmp_path / "spikeins" / "draw.json").exists()
    assert "drew 20 abstracts" in capsys.readouterr().out
