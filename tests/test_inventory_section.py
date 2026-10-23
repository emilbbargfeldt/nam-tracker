import re
import shutil

import pytest

from studies.nam.inventory import section
from tests.test_inventory_measure import make_pdf

XML = """<outline>
<item page="2">1 Executive Summary</item>
<item page="10">2 Therapeutic Context</item>
<outline>
<item page="11">2.1 Nonclinical overview</item>
</outline>
<item page="20">5 Nonclinical Pharmacology/Toxicology</item>
<outline>
<item page="21">5.1 Studies</item>
<item page="25">5.2 Summary</item>
</outline>
<item page="30">6 Clinical Pharmacology</item>
</outline>"""


def test_parse_outline_levels_and_pages():
    items = section.parse_outline(XML)
    assert [(lv, pg) for lv, pg, _ in items] == [
        (1, 2), (1, 10), (2, 11), (1, 20), (2, 21), (2, 25), (1, 30)]


def test_bookmarks_known_range():
    items = section.parse_outline(XML)
    # shallowest matching level wins over the earlier, deeper match
    assert section.from_bookmarks(items, 100) == (20, 30, 2)


def test_bookmarks_last_section_runs_to_end():
    items = section.parse_outline(
        "<outline><item page=\"3\">Nonclinical</item></outline>")
    assert section.from_bookmarks(items, 40) == (3, 40, 1)


def test_bookmarks_none_when_no_title_word():
    items = section.parse_outline(
        "<outline><item page=\"3\">Clinical Pharmacology</item></outline>")
    assert section.from_bookmarks(items, 40) is None


def test_bookmarks_next_section_on_same_page_gives_one_page():
    items = section.parse_outline(
        "<outline><item page=\"7\">Nonclinical</item>"
        "<item page=\"7\">Clinical</item></outline>")
    assert section.from_bookmarks(items, 40) == (7, 7, 1)


PAGES = [
    "Contents\n5 Nonclinical Pharmacology/Toxicology ........ 3\n6 Clinical X ... 9",
    "Intro text",
    "5 Nonclinical Pharmacology/Toxicology\nmore",
    "5.1 Studies\ntext",
    "text",
    "6 Clinical Pharmacology\nafter",
    "tail",
]


def test_headings_skip_toc_and_end_at_next_numbered_heading():
    assert section.from_headings(PAGES) == (3, 6, 1)


def test_headings_numbered_start_ignores_subsections_and_deeper_numbers():
    pages = ["2.3 Non-clinical aspects", "2.3.1 Intro", "2.3.2 Pharmacology",
             "2.4 Clinical aspects", "end"]
    assert section.from_headings(pages) == (1, 4, 1)


def test_headings_unnumbered_start_ends_at_clinical_heading():
    pages = ["Nonclinical Pharmacology", "text", "Clinical Pharmacology", "x"]
    assert section.from_headings(pages) == (1, 3, 1)


def test_headings_none():
    assert section.from_headings(["abc", "def"]) is None


def test_separate_review_is_whole_document():
    loc = section.locate("separate", "", ["a", "b", "c"])
    assert (loc["found"], loc["basis"], loc["start"], loc["end"]) == (
        True, "document type", 1, 3)


def test_not_found_passes_whole_document():
    loc = section.locate("integrated", "", ["a", "b", "c"])
    assert (loc["found"], loc["basis"], loc["start"], loc["end"]) == (
        False, "not found", 1, 3)


def test_bookmarks_take_precedence_over_headings():
    xml = "<outline><item page=\"2\">Nonclinical</item></outline>"
    loc = section.locate("multidisc", xml, ["Nonclinical x", "y", "z"])
    assert loc["basis"] == "bookmarks" and loc["start"] == 2


def test_summarize_counts():
    pages = ["a" * 150, "b " * 100, "c" * 10, "d" * 500]
    loc = {"found": True, "basis": "headings", "start": 2, "end": 3,
           "n_matches": 1}
    s = section.summarize(loc, pages)
    assert s["pages"] == 4 and s["section_pages"] == 2
    assert s["chars"] == 199 + 10
    assert s["chars_nonblank"] == 100 + 10
    assert s["low_text_pages"] == 1  # the 10-character page; 100 counts as text
    assert s["chars_low"] == 10


def test_found_share_by_group():
    recs = [{"format": "a", "found": True}, {"format": "a", "found": False},
            {"format": "b", "found": True}]
    assert section.found_share(recs, "format") == {"a": (1, 2), "b": (1, 1)}


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="poppler")
def test_pdf_end_to_end_no_text_in_result(tmp_path):
    p = tmp_path / "a.pdf"
    make_pdf(p, ["Cover", "5 Nonclinical Pharmacology", "body Secretword",
                 "6 Clinical Pharmacology", "end"])
    res = section.analyse_pdf(p, "multidisc")
    assert (res["start"], res["end"], res["basis"]) == (2, 4, "headings")
    assert "Secretword" not in str(res)


# Deliberate faults: the known-answer tests must catch each one.
def test_mutant_toc_lines_not_skipped_is_caught(monkeypatch):
    monkeypatch.setattr(section, "_TOC_LINE", re.compile(r"(?!x)x"))
    assert section.from_headings(PAGES) != (3, 6, 1)


def test_mutant_end_equals_start_is_caught(monkeypatch):
    monkeypatch.setattr(section, "_number", lambda line: None)
    monkeypatch.setattr(section, "_CLINICAL", re.compile(r"(?!x)x"))
    assert section.from_headings(PAGES) != (3, 6, 1)


def test_headings_numbered_beats_earlier_unnumbered_cover_line():
    pages = ["Nonclinical Reviewer: signature", "x", "5 Nonclinical Pharmacology",
             "text", "6 Clinical Pharmacology", "end"]
    assert section.from_headings(pages) == (3, 5, 2)


def test_bookmarks_numbered_beats_earlier_unnumbered():
    items = section.parse_outline(
        "<outline><item page=\"1\">Nonclinical reviewer</item>"
        "<item page=\"9\">5 Nonclinical Pharmacology</item>"
        "<item page=\"15\">6 Clinical</item></outline>")
    assert section.from_bookmarks(items, 40) == (9, 15, 2)


def test_pharmtox_format_is_whole_document():
    loc = section.locate("pharmtox", "", ["a", "b"])
    assert (loc["found"], loc["basis"], loc["end"]) == (True, "document type", 2)


def test_mutant_unnumbered_first_is_caught(monkeypatch):
    monkeypatch.setattr(section, "_number", lambda line: None)
    pages = ["Nonclinical Reviewer: signature", "x", "5 Nonclinical Pharmacology",
             "text", "6 Clinical Pharmacology", "end"]
    assert section.from_headings(pages) != (3, 5, 2)
