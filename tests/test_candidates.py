import csv
import json

import pytest

from studies.nam.extract import candidates, keywords, ocr

FILLER = "This page has enough plain words to count as a text page. " * 4


def page(extra=""):
    return FILLER + extra


def test_hyphen_line_break_gives_A_on_the_right_page():
    pages = [page(), page("The organ-\non-a-chip model was used."), page()]
    per_code, union = candidates.candidate_pages(pages, [1, 2, 3])
    assert per_code["A"] == [2]
    assert union == [2]


def test_page_without_hit_is_no_candidate():
    pages = [page(), page()]
    per_code, union = candidates.candidate_pages(pages, [1, 2])
    assert all(v == [] for v in per_code.values())
    assert union == []


def test_codes_are_separate_and_union_counts_a_page_once():
    pages = [page("organoid and rat"), page("rat"), page()]
    per_code, union = candidates.candidate_pages(pages, [1, 2, 3])
    assert per_code["A"] == [1]
    assert per_code["S"] == [1, 2]
    assert union == [1, 2]


def test_only_layer1_numbers_are_searched():
    pages = [page("organoid"), page("organoid"), page("organoid")]
    per_code, _ = candidates.candidate_pages(pages, [2, 3])
    assert per_code["A"] == [2, 3]


def test_page_numbers_are_one_based_on_a_real_pdf(tmp_path):
    from tests.test_inventory_measure import make_pdf
    pdf = tmp_path / "doc.pdf"
    make_pdf(pdf, [page(), page(), "Cardiomyocytes were used. " + FILLER])
    item = {"id": "x", "name": "Drug", "authority": "FDA", "year": 2024,
            "format": "pharmtox"}
    out = tmp_path / "out"
    out.mkdir()
    res = candidates.process_document(item, pdf, tmp_path / "ocr", out)
    assert res["pages"] == 3 and res["candidates"] == 1 and res["missing"] == []
    lines = [json.loads(x) for x in
             (out / (candidates.doc_id_of(item) + ".jsonl")).read_text().splitlines()]
    a = [x for x in lines if x["code"] == "A"][0]
    assert a["pages"] == [3] and a["n"] == 1
    assert set(a) == {"doc", "id", "code", "pages", "n"}


def test_missing_ocr_is_logged_not_an_error(tmp_path):
    from tests.test_inventory_measure import make_pdf
    pdf = tmp_path / "doc.pdf"
    make_pdf(pdf, [page(), "", page("organoid")])
    item = {"id": "x", "name": "Drug", "authority": "FDA", "year": 2024,
            "format": "pharmtox"}
    out = tmp_path / "out"
    out.mkdir()
    res = candidates.process_document(item, pdf, tmp_path / "ocr", out)
    assert res["missing"] == [2]
    # cached OCR text replaces the empty page
    folder = ocr._folder(pdf, tmp_path / "ocr")
    folder.mkdir(parents=True)
    (folder / "page_0002.txt").write_text("Spheroids " * 20)
    res = candidates.process_document(item, pdf, tmp_path / "ocr", out)
    assert res["missing"] == [] and res["candidates"] == 2


def test_no_pdf_in_cache_is_reported(tmp_path):
    item = {"id": "x", "name": "Drug", "authority": "FDA", "year": 2024,
            "format": "pharmtox"}
    res = candidates.process_document(item, tmp_path / "none", tmp_path, tmp_path)
    assert res == {"reason": "no pdf in cache"}


CODERS = ["d%d" % i for i in range(15)]


@pytest.fixture
def coders(monkeypatch):
    monkeypatch.setattr(candidates, "pilot_coder_names", lambda: CODERS)


def _coding(value="1", at=None):
    """All coder rows with value, or all 0 except column B of row `at`."""
    rows = ["drug,agency,year,A,B,C,D"]
    for i, name in enumerate(CODERS):
        vals = [value] * 4 if at is None else ["0"] * 4
        if at == i:
            vals[1] = value
        rows.append("%s,EMA,2020,%s" % (name, ",".join(vals)))
    return "\n".join(rows) + "\n"


def test_correct_codings_accepted(coders):
    candidates.check_blind_codings(lambda: _coding("1"))
    candidates.check_blind_codings(lambda: _coding("0"))
    candidates.check_blind_codings(lambda: _coding(" 1 "))


@pytest.mark.parametrize("bad", ["?", "ja", "", "2"])
def test_bad_values_rejected_without_the_value(coders, bad):
    with pytest.raises(candidates.BlindingError) as e:
        candidates.check_blind_codings(lambda: _coding(bad, at=3))
    msg = str(e.value)
    assert "row 5 column B" in msg
    if bad:
        assert bad not in msg


def test_missing_file_or_template_rejected(coders):
    for text in (None, "", _coding("")):
        with pytest.raises(candidates.BlindingError):
            candidates.check_blind_codings(lambda t=text: t)


def test_missing_coder_row_rejected(coders):
    text = "\n".join(_coding("1").splitlines()[:-1]) + "\n"
    with pytest.raises(candidates.BlindingError):
        candidates.check_blind_codings(lambda: text)


def test_pilot_refused_without_blind_codings(monkeypatch, capsys):
    def refuse(show=None):
        raise candidates.BlindingError("blind codings are not in git HEAD")
    monkeypatch.setattr(candidates, "check_blind_codings", refuse)
    called = []
    monkeypatch.setattr(candidates, "run_all", lambda *a, **k: called.append(1))
    assert candidates.main(["--pilot"]) == 2
    assert not called
    assert "refused" in capsys.readouterr().out


def _main_with(monkeypatch, tmp_path, n_pilot_found):
    from studies.nam.pilot import draw
    keys = ["FDA|p%d" % i for i in range(30)]
    units = {"FDA|n1": {"id": "n1"}}
    units.update({k: {"id": k} for k in keys[:n_pilot_found]})

    class F:
        root = tmp_path

    monkeypatch.setattr("studies.nam.inventory.fetch.Fetcher", F)
    monkeypatch.setattr(draw, "universe", lambda f: (units, []))
    monkeypatch.setattr(candidates, "pilot_keys", lambda: set(keys))
    written = []

    def fake_run(items, f, out):
        written.append([i["id"] for i in items])
        return {"documents": 1, "pages": 1, "candidate_pages": 0,
                "tokens_lower": 0.0, "tokens_upper": 0.0,
                "pages_without_text": 0, "documents_without_text": 0}
    monkeypatch.setattr(candidates, "run_all", fake_run)
    monkeypatch.setattr(candidates, "write_manifest", lambda *a, **k: written.append("m"))
    return written


def test_normal_run_prints_pilot_skipped_30(monkeypatch, tmp_path, capsys):
    written = _main_with(monkeypatch, tmp_path, 30)
    assert candidates.main([]) == 0
    out = capsys.readouterr().out
    assert "pilot skipped: 30 of 30" in out
    assert written[0] == ["n1"]


def test_normal_run_stops_before_writing_if_pilot_not_all_found(
        monkeypatch, tmp_path, capsys):
    written = _main_with(monkeypatch, tmp_path, 29)
    assert candidates.main([]) == 2
    assert written == []
    assert "29 of 30" in capsys.readouterr().out
    assert not (tmp_path / "candidates").exists()


def test_stdout_has_no_code_distribution_year_or_authority():
    agg = {"documents": 3, "pages": 100, "candidate_pages": 7,
           "tokens_lower": 5000.0, "tokens_upper": 6000.0,
           "pages_without_text": 2, "documents_without_text": 1}
    out = candidates.format_aggregates(agg)
    for word in ("A:", "B:", "C:", "D:", "S:", "FDA", "EMA", "20"):
        assert word not in out.replace("2.0 %", "")
    assert len(out.splitlines()) == 7
    assert "documents: 3" in out and "(2.0 %)" in out


def test_run_all_output_only_in_out_dir_and_aggregates(tmp_path):
    from tests.test_inventory_measure import make_pdf

    class F:
        root = tmp_path / "data"

        def path_for(self, url):
            return tmp_path / url

    make_pdf(tmp_path / "u1", [page("organoid"), page()])
    items = [{"id": "1", "name": "One", "authority": "EMA", "year": 2020,
              "format": "epar", "url": "u1"},
             {"id": "2", "name": "Two", "authority": "FDA", "year": 2021,
              "format": "pharmtox", "url": "u2"}]
    out = tmp_path / "data" / "candidates"
    agg = candidates.run_all(items, F(), out)
    assert agg["documents"] == 1 and agg["documents_without_text"] == 1
    assert agg["candidate_pages"] == 1
    assert agg["tokens_upper"] == agg["tokens_lower"]
    log = [json.loads(x) for x in (out / "missing_text.jsonl").read_text().splitlines()]
    assert log == [{"doc": candidates.doc_id_of(items[1]), "reason": "no pdf in cache"}]
    candidates.write_manifest(out, agg)
    m = json.loads((out / "manifest.json").read_text())
    assert m["keywords_md5"] == candidates.md5_of(keywords.__file__)
    assert m["prereg_version"] == 5 and len(m["git_head"]) == 40
    assert m["time"]


def test_token_estimate_is_chars_over_four():
    pages = ["a" * 40, "bb  \n  cc  dd\n" + "e" * 5]
    assert candidates.estimate_tokens(pages, [1]) == 10.0
    assert candidates.estimate_tokens(pages, [2]) == len("bb cc dd eeeee") / 4


def test_prereg_version_is_five():
    assert candidates.prereg_version() == 5


def test_ascii_only():
    open(candidates.__file__, encoding="ascii").read()
    open(__file__, encoding="ascii").read()


# Mutants: each broken variant must fail a known answer.

def _known_answer_ok(monkeypatch=None):
    pages = [page(), page("The organ-\non-a-chip model."), page()]
    per_code, _ = candidates.candidate_pages(pages, [1, 2, 3])
    return per_code["A"] == [2]


def test_mutant_wrong_normalization_is_caught(monkeypatch):
    monkeypatch.setattr(keywords, "_normalize", lambda text: text)
    pages = [page("The organo-\nid grew.")]
    per_code, _ = candidates.candidate_pages(pages, [1])
    assert per_code["A"] == []  # mutant: line-end hyphen no longer joined


def test_known_answer_with_real_normalization():
    pages = [page("The organo-\nid grew.")]
    per_code, _ = candidates.candidate_pages(pages, [1])
    assert per_code["A"] == [1]


def test_mutant_page_offset_is_caught(monkeypatch):
    def shifted(pages, numbers):
        out, union = {c: [] for c in candidates.CODES}, set()
        for n in sorted(numbers):
            for c in candidates.page_codes(pages[n]) if n < len(pages) else []:
                out[c].append(n)
                union.add(n)
        return out, sorted(union)
    monkeypatch.setattr(candidates, "candidate_pages", shifted)
    assert _known_answer_ok() is False


def test_upper_bound_adds_imputed_pages_without_ocr(tmp_path):
    from tests.test_inventory_measure import make_pdf

    class F:
        root = tmp_path / "data"

        def path_for(self, url):
            return tmp_path / url

    make_pdf(tmp_path / "u1", [page("organoid"), "", page()])
    items = [{"id": "1", "name": "One", "authority": "EMA", "year": 2020,
              "format": "pharmtox", "url": "u1"}]
    agg = candidates.run_all(items, F(), tmp_path / "o1")
    from studies.nam.inventory import section
    texts = section.load_pages(tmp_path / "u1")
    text_chars = (folded_len(texts[0]) + folded_len(texts[2])) / 2
    assert agg["tokens_upper"] > agg["tokens_lower"]
    assert agg["tokens_upper"] == pytest.approx(
        agg["tokens_lower"] + text_chars / 4)
    # with the OCR cached the bounds meet
    folder = ocr._folder(tmp_path / "u1", tmp_path / "data" / "ocr")
    folder.mkdir(parents=True)
    (folder / "page_0002.txt").write_text("blank")
    agg = candidates.run_all(items, F(), tmp_path / "o2")
    assert agg["tokens_upper"] == agg["tokens_lower"]


def folded_len(text):
    return len(" ".join(text.split()))


def test_doc_id_differs_for_same_name_and_year():
    a = {"id": "1", "name": "Same", "authority": "EMA", "year": 2020}
    b = dict(a, id="2")
    assert candidates.doc_id_of(a) != candidates.doc_id_of(b)
    assert len(candidates.doc_id_of(dict(a, name="x" * 500))) < 100
