import json
import shutil

import pytest

from studies.nam.inventory import epar_nas
from tests.test_inventory_measure import make_pdf

POS = "The CHMP considered that X is a new active substance."
NEG = "The CHMP did not consider that X is a new active substance."
APPLICANT = "The applicant considered that X is a new active substance."
FOREIGN = "A new active substance is a substance not authorised before."

# (sentence, expected classification)
CASES = [
    (POS, "positive"),
    ("The Committee concluded that X qualifies as a new active substance.",
     "positive"),
    ("The CHMP, based on the data, is of the opinion that X is to be qualified "
     "as a new active substance in itself.", "positive"),
    (NEG, "negative"),
    ("The CHMP concluded that X is not a new active substance.", "negative"),
    ("The CHMP cannot agree that X is a new active substance.", "negative"),
    (APPLICANT, None),
    (FOREIGN, None),
    ("The CHMP discussed the quality of X.", None),
    ("The CHMP listed X among new active substances.", None),
]


@pytest.mark.parametrize("sentence,expected", CASES)
def test_classify_known_sentences(sentence, expected):
    assert epar_nas.classify(sentence) == expected


def failures():
    """Cases the current rule gets wrong (empty for the real rule)."""
    return [s for s, want in CASES if epar_nas.classify(s) != want]


def test_real_rule_has_no_failures():
    assert failures() == []


def test_verdicts():
    assert epar_nas.analyse([POS])["verdict"] == "yes"
    assert epar_nas.analyse([NEG])["verdict"] == "no"
    assert epar_nas.analyse([POS + " " + NEG])["verdict"] == "unknown"
    assert epar_nas.analyse(["Nothing about it."])["verdict"] == "unknown"
    assert epar_nas.analyse([APPLICANT])["verdict"] == "unknown"


def test_positions_are_page_and_sentence_numbers():
    res = epar_nas.analyse(["First one. Second one.",
                            "Intro. " + FOREIGN + " " + POS])
    assert res["matches"] == [{"page": 2, "sentence": 3, "polarity": "positive"}]
    assert res["unmatched"] == [{"page": 2, "sentence": 2}]


def test_unmatched_occurrence_is_listed_not_counted():
    res = epar_nas.analyse([APPLICANT])
    assert res["matches"] == []
    assert res["unmatched"] == [{"page": 1, "sentence": 1}]


def test_hyphenation_and_line_breaks_are_joined():
    text = "The CHMP considered that X is a new ac-\ntive   substance."
    assert epar_nas.classify(epar_nas.split_sentences(text)[0]) == "positive"


def test_abbreviation_does_not_split_sentence():
    parts = epar_nas.split_sentences("Items, e.g. Foo, were seen. Next one.")
    assert len(parts) == 2


def test_result_holds_only_numbers_and_labels():
    res = epar_nas.analyse(["Secret text. " + POS])
    blob = json.dumps(res)
    assert "Secret" not in blob and "CHMP" not in blob


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="poppler")
def test_pdf_end_to_end(tmp_path):
    p = tmp_path / "a.pdf"
    make_pdf(p, ["Nothing here.", "Intro. The CHMP considered X a new active substance."])
    res = epar_nas.analyse(epar_nas.pdf_pages(p))
    assert res["verdict"] == "yes"
    assert res["matches"] == [{"page": 2, "sentence": 2, "polarity": "positive"}]


# Deliberate faults: the known-answer cases must catch each one.
def test_mutant_without_chmp_requirement_is_caught(monkeypatch):
    monkeypatch.setattr(epar_nas, "_has_chmp", lambda s: True)
    assert APPLICANT in failures()
    assert epar_nas.analyse([APPLICANT])["verdict"] == "yes"  # the harm


def test_mutant_ignoring_negation_is_caught(monkeypatch):
    monkeypatch.setattr(epar_nas, "_negated", lambda s, pos: False)
    assert NEG in failures()


def test_mutant_without_verb_requirement_is_caught(monkeypatch):
    monkeypatch.setattr(epar_nas, "_has_verb", lambda s: True)
    assert "The CHMP listed X among new active substances." in failures()
