import re
import shutil

import pytest

from studies.nam.inventory import fda_sample, outline
from tests.test_inventory_measure import make_pdf

NEW = 'var pdfBaseName = "761269Orig1s000";\nvar applicationNumber = "761269";'
OLD = ('var pdfFilenames = {\n pharmr: "209360Orig1s000PharmR.pdf",\n'
       ' memo: "209360Orig1s000ODMemo.pdf"\n};')


def test_choose_doc_priority():
    assert fda_sample.choose_doc({"pharmR": 1, "integratedR": 1})[1] == "pharmtox"
    assert fda_sample.choose_doc({"multidisciplineR": 1, "integratedR": 1})[1] == "multidisc"
    assert fda_sample.choose_doc({"integratedR": 1})[1] == "integrated"
    assert fda_sample.choose_doc({"pharmR": 0}) is None


def test_doc_url_from_base_name_and_from_filenames():
    toc = "https://h/nda/2023/761269Orig1s000TOC.html"
    assert fda_sample.doc_url(toc, NEW, "pharmR", "PharmR") == \
        "https://h/nda/2023/761269Orig1s000PharmR.pdf"
    toc2 = "http://h/nda/2017/209360Orig1s000TOC.html"
    assert fda_sample.doc_url(toc2, OLD, "pharmR", "PharmR").endswith("209360Orig1s000PharmR.pdf")
    assert fda_sample.doc_url(toc2, "x", "pharmR", "PharmR") is None


def test_outline_titles_parse():
    xml = "<outline><item page='1'>1 Intro</item><item page='3'>Nonclinical Pharmacology</item></outline>"
    t = outline.outline_titles(xml)
    assert t == ["1 Intro", "Nonclinical Pharmacology"]
    assert any(outline.title_matches(x) for x in t)


def test_clinical_pharmacology_bookmark_alone_is_not_a_match():
    assert not outline.title_matches("6 Clinical Pharmacology")
    assert not outline.title_matches("Pharmacology")
    assert outline.title_matches("4.2 Pharmacology/Toxicology")
    assert outline.title_matches("Nonclinical Studies")
    assert outline.title_matches("Non-Clinical Summary")


@pytest.mark.parametrize("title", [
    "13. Pharmacology Toxicology: Additional Information and Assessment",
    "Pharmacology and Toxicology", "Pharmacology & Toxicology",
    "Pharmacology, Toxicology", "Pharmacology-Toxicology",
    "NONCLINICAL PHARMACOLOGY/TOXICOLOGY"])
def test_pharmacology_toxicology_pair_variants_match(title):
    assert outline.title_matches(title)
    assert outline._HEADING.match(title.split(" ", 1)[1] if title[0].isdigit() else title)


@pytest.mark.parametrize("title", [
    "14. Clinical Pharmacology: Additional Information and Assessment",
    "Pharmacology", "Toxicology", "Pharmacology of the drug",
    "Safety Pharmacology"])
def test_pharmacology_alone_does_not_match(title):
    assert not outline.title_matches(title)


def test_mutant_old_pair_pattern_is_caught(monkeypatch):
    monkeypatch.setattr(outline, "_TITLE", re.compile(
        r"non-?clinical|pharmacology\s*(?:/|and|&)\s*toxicology", re.I))
    assert not outline.title_matches("13. Pharmacology Toxicology: Additional")


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="poppler missing")
def test_heading_fallback_yes_and_no(tmp_path):
    a = tmp_path / "a.pdf"
    make_pdf(a, ["7.1 Nonclinical Pharmacology"])
    b = tmp_path / "b.pdf"
    make_pdf(b, ["1 Introduction and clinical background"])
    ra, rb = outline.check(a), outline.check(b)
    assert ra["basis"] == "headings" and ra["verdict"] == "yes"
    assert rb["verdict"] == "no"


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="poppler missing")
def test_pdf_without_text_is_unknown(tmp_path):
    p = tmp_path / "c.pdf"
    make_pdf(p, [""])
    assert outline.check(p)["verdict"] == "unknown"


def test_long_line_is_not_a_heading():
    line = "Nonclinical " + "x" * 200
    assert not (len(line) <= outline.MAX_HEADING_LEN and outline._HEADING.match(line))


TOC_OK = ("var pdfFiles = {\n pharmR: 0,\n multidisciplineR: 1,\n integratedR: 0\n};\n"
          'var pdfBaseName = "111111Orig1s000";')


TOC_PHARM = TOC_OK.replace("pharmR: 0", "pharmR: 1")


def test_resolve_candidate_ok_none_and_error():
    rc = fda_sample.resolve_candidate
    assert rc("A", [("https://h/n/111111Orig1s000TOC.html", TOC_OK)]) == \
        ("ok", ("A", "https://h/n/111111Orig1s000MultidisciplineR.pdf", "multidisc"))
    no_doc = TOC_OK.replace("multidisciplineR: 1", "multidisciplineR: 0")
    assert rc("A", [("u/TOC.html", no_doc)]) == ("none", None)
    assert rc("A", []) == ("none", None)
    assert rc("A", [("u/TOC.html", None)]) == ("error", "toc_missing")
    assert rc("A", [("u/TOC.html", "<html></html>")]) == ("error", "toc_unparsed")
    # an unreadable page next to the top-priority document still yields it
    assert rc("A", [("u/TOC.html", None), ("https://h/n/TOC.html", TOC_PHARM)])[0] == "ok"
    # but not next to a lower-priority one: the unreadable page might hold more
    assert rc("A", [("u/TOC.html", None), ("https://h/n/TOC.html", TOC_OK)])[0] == "error"


def test_run_stratum_skips_none_logs_errors_and_replaces_failures():
    from studies.nam.inventory.run_sample import run_stratum
    cands = {"a": ("none", None), "b": ("error", "toc_missing"),
             "c": ("ok", ("C", "u/c.pdf", "multidisc")),
             "d": ("ok", ("D", "u/d.pdf", "multidisc")),
             "e": ("ok", ("E", "u/e.pdf", "integrated")),
             "f": ("ok", ("F", "u/f.pdf", "multidisc"))}

    def fetch(url):
        if url == "u/d.pdf":
            raise OSError("dead")
        return url

    def meas(path):
        return {"pages": 10, "text_pages": 9, "text_share": 0.9,
                "size_bytes": 1, "chars_per_page": [1] * 10}

    res = run_stratum("FDA", 2020, cands, fetch, meas,
                      lambda p: {"verdict": "yes"}, k=10)
    assert sorted(r["id"] for r in res["picked"]) == ["c", "e", "f"]
    assert res["none"] == ["a"]
    assert sorted((e["id"], e["error"]) for e in res["errors"]) == [
        ("b", "toc_missing"), ("d", "OSError")]
    e_rec = [r for r in res["picked"] if r["id"] == "e"][0]
    assert e_rec["nonclinical_section"] == {"verdict": "yes"}
    assert "nonclinical_section" not in [r for r in res["picked"] if r["id"] == "c"][0]


def test_run_stratum_stops_after_k():
    from studies.nam.inventory.run_sample import run_stratum
    cands = {x: ("ok", (x, "u/" + x, "multidisc")) for x in "abcdef"}
    res = run_stratum("FDA", 2020, cands, lambda u: u,
                      lambda p: {"pages": 1, "text_pages": 1, "text_share": 1.0,
                                 "size_bytes": 1, "chars_per_page": [1]},
                      lambda p: {}, k=2)
    assert len(res["picked"]) == 2


def test_run_stratum_error_is_not_counted_as_none():
    from studies.nam.inventory.run_sample import run_stratum
    res = run_stratum("FDA", 2020, {"b": ("error", "toc_missing")},
                      lambda u: u, lambda p: {}, lambda p: {})
    assert res["none"] == [] and res["errors"] == [{"id": "b", "error": "toc_missing"}]


def test_lower_priority_doc_with_unreadable_page_is_error_not_ok():
    integ = ("var pdfFiles = {\n pharmR: 0,\n multidisciplineR: 0,\n integratedR: 1\n};\n"
             'var pdfBaseName = "1Orig1s000";')
    st, _ = fda_sample.resolve_candidate(
        "A", [("h/a/TOC.html", integ), ("h/b/TOC.html", None)])
    assert st == "error"
    assert fda_sample.resolve_candidate("A", [("h/a/TOC.html", TOC_PHARM),
                                              ("h/b/TOC.html", None)])[0] == "ok"


def test_failed_outline_check_keeps_the_document_with_verdict_unknown():
    from studies.nam.inventory.run_sample import run_stratum

    def bad_outline(path):
        raise RuntimeError("pdftohtml failed")

    res = run_stratum("FDA", 2020, {"a": ("ok", ("A", "u/a", "integrated"))},
                      lambda u: u,
                      lambda p: {"pages": 1, "text_pages": 1, "text_share": 1.0,
                                 "size_bytes": 1, "chars_per_page": [1]},
                      bad_outline, k=1, excluded=3)
    assert len(res["picked"]) == 1 and res["errors"] == []
    assert res["picked"][0]["nonclinical_section"]["verdict"] == "unknown"
    assert res["not_in_drugsatfda"] == 3


def test_heading_accepts_ampersand():
    assert outline._HEADING.match("7 Pharmacology & Toxicology")
