import json
import re
import shutil

import pytest

from studies.nam.inventory import epar_nas
from tests.test_inventory_measure import make_pdf

SINCE = ("Since X is not a constituent of a medicinal product previously "
         "authorised, the CHMP considers X a new active substance.")
APPLICANT = "The applicant requested X to be considered as a new active substance."
KNOWN = "X is a known active substance."
NEG = "The CHMP considers that X is not a new active substance."
DOES_NOT = "The CHMP does not consider X to be a new active substance."
DID_NOT = "The CHMP did not consider that X is a new active substance."
KNOWN_VALSARTAN = "Valsartan is a known active substance."
POS_SACUBITRIL = "The CHMP considers sacubitril to be a new active substance."
NO_CHMP = "It is considered that X is a new active substance."
NO_VERB = "The CHMP listed X among new active substances."
FOREIGN = "A new active substance is a substance not authorised before."

# (sentence, expected classification of the sentence)
CASES = [
    (SINCE, "positive"),
    (NO_CHMP, "positive"),
    ("The Committee concluded that X qualifies as a new active substance.",
     "positive"),
    (NEG, "negative"),
    (DOES_NOT, "negative"),
    (DID_NOT, "negative"),
    ("The CHMP cannot agree that X is a new active substance.", "negative"),
    ("X was not considered a new active substance.", "negative"),
    (APPLICANT, None),
    ("The applicant claimed that X is a new active substance, which the CHMP "
     "considers correct.", None),
    ("X was declared a new active substance and agreed so.", None),
    ("The CHMP indicated that X is considered a new active substance.", None),
    (FOREIGN, None),
    (NO_VERB, None),
    (KNOWN, None),
]


@pytest.mark.parametrize("sentence,expected", CASES)
def test_classify_known_sentences(sentence, expected):
    assert epar_nas.classify(sentence) == expected


def failures():
    """Cases the current rule gets wrong (empty for the real rule)."""
    return [s for s, want in CASES if epar_nas.classify(s) != want]


def verdict_of(*pages):
    return epar_nas.analyse(list(pages))["verdict"]


def test_real_rule_has_no_failures():
    assert failures() == []


def test_the_four_stated_examples():
    assert verdict_of(SINCE) == "yes"
    res = epar_nas.analyse([APPLICANT])
    assert res["matches"] == [] and res["verdict"] == "unknown"
    assert res["unmatched"] == [{"page": 1, "sentence": 1}]
    assert verdict_of(KNOWN) == "no"
    assert verdict_of(NEG) == "no"


def test_negation_far_before_the_phrase_is_ignored():
    # "not" is more than 4 tokens before the phrase
    assert epar_nas.classify(SINCE) == "positive"


def test_negation_before_the_verb_counts():
    assert epar_nas.classify(DOES_NOT) == "negative"
    assert epar_nas.classify(DID_NOT) == "negative"
    assert verdict_of(DOES_NOT) == "no"
    assert verdict_of(DID_NOT) == "no"


def test_verb_negation_window_boundary_is_two_tokens():
    assert epar_nas.classify(
        "The CHMP did not really consider X a new active substance.") == "negative"
    assert epar_nas.classify(
        "The CHMP did not really truly consider X a new active substance."
    ) == "positive"


def test_negation_window_boundary_is_four_tokens():
    # "not" as the 4th token before the phrase counts, as the 5th it does not
    assert epar_nas.classify(
        "It is considered not to be a new active substance.") == "negative"
    assert epar_nas.classify(
        "It is considered not to be so a new active substance.") == "positive"


def test_negation_just_before_the_phrase_counts():
    assert epar_nas.classify(
        "The CHMP considers X no longer a new active substance.") == "negative"


def test_last_conclusion_match_wins():
    assert verdict_of(SINCE, NEG) == "no"
    assert verdict_of(NEG, SINCE) == "yes"
    assert verdict_of(SINCE + " " + NEG) == "no"


def test_positive_conclusion_wins_over_known_signal():
    assert verdict_of(KNOWN_VALSARTAN, POS_SACUBITRIL) == "yes"
    assert verdict_of(POS_SACUBITRIL, KNOWN_VALSARTAN) == "yes"
    assert verdict_of(KNOWN_VALSARTAN + " " + POS_SACUBITRIL) == "yes"


def test_known_signal_with_negative_match_is_no():
    assert verdict_of(KNOWN, NEG) == "no"


def test_unknown_when_nothing_matches():
    assert verdict_of("Nothing about it.") == "unknown"
    assert verdict_of(FOREIGN) == "unknown"


def test_unknown_active_substance_is_not_a_known_signal():
    assert epar_nas.analyse(["X is an unknown active substance."])["known"] == []


def test_positions_are_page_and_sentence_numbers():
    res = epar_nas.analyse(["First one. Second one.",
                            "Intro. " + KNOWN + " " + SINCE])
    assert res["matches"] == [{"page": 2, "sentence": 3, "polarity": "positive"}]
    assert res["known"] == [{"page": 2, "sentence": 2}]


def test_hyphenation_and_line_breaks_are_joined():
    text = "The CHMP considers X a new ac-\ntive   substance."
    assert epar_nas.classify(epar_nas.split_sentences(text)[0]) == "positive"


def test_abbreviation_does_not_split_sentence():
    parts = epar_nas.split_sentences("Items, e.g. Foo, were seen. Next one.")
    assert len(parts) == 2


def test_result_holds_only_numbers_and_labels():
    res = epar_nas.analyse(["Secret text. " + SINCE + " " + KNOWN])
    blob = json.dumps(res)
    assert "Secret" not in blob and "CHMP" not in blob and "constituent" not in blob


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="poppler")
def test_pdf_end_to_end(tmp_path):
    p = tmp_path / "a.pdf"
    make_pdf(p, ["Nothing here.", "Intro. The CHMP considers X a new active substance."])
    res = epar_nas.analyse(epar_nas.pdf_pages(p))
    assert res["verdict"] == "yes"
    assert res["matches"] == [{"page": 2, "sentence": 2, "polarity": "positive"}]


# Deliberate faults: the known-answer cases must catch each one.
def test_mutant_without_applicant_filter_is_caught(monkeypatch):
    monkeypatch.setattr(epar_nas, "_from_applicant", lambda s: False)
    assert APPLICANT in failures()
    assert verdict_of(APPLICANT) == "yes"  # the harm


def test_mutant_without_verb_requirement_is_caught(monkeypatch):
    monkeypatch.setattr(epar_nas, "_has_verb", lambda s: True)
    assert NO_VERB in failures()


def test_mutant_negation_anywhere_before_is_caught(monkeypatch):
    monkeypatch.setattr(epar_nas, "NEAR_TOKENS", 1000)
    assert SINCE in failures()
    assert verdict_of(SINCE) == "no"  # the harm


def test_mutant_negation_ignored_is_caught(monkeypatch):
    monkeypatch.setattr(epar_nas, "_negated", lambda s, pos: False)
    assert NEG in failures()


def test_mutant_without_known_signal_is_caught(monkeypatch):
    monkeypatch.setattr(epar_nas, "_KNOWN", re.compile(r"(?!x)x"))
    assert verdict_of(KNOWN) == "unknown"  # should be "no"


def test_mutant_first_match_wins_is_caught(monkeypatch):
    def first_wins(matches, known):
        if not matches:
            return "no" if known else "unknown"
        return "yes" if matches[0]["polarity"] == "positive" else "no"
    monkeypatch.setattr(epar_nas, "verdict", first_wins)
    assert verdict_of(SINCE, NEG) == "yes"  # should be "no"


def test_mutant_known_overrides_positive_is_caught(monkeypatch):
    def known_wins(matches, known):
        if known:
            return "no"
        return "yes" if matches and matches[-1]["polarity"] == "positive" else "unknown"
    monkeypatch.setattr(epar_nas, "verdict", known_wins)
    assert verdict_of(KNOWN_VALSARTAN, POS_SACUBITRIL) == "no"  # should be "yes"


def test_mutant_known_with_positive_is_unknown_is_caught(monkeypatch):
    """The version 2 verdict must no longer be what the code does."""
    def v2(matches, known):
        positive = any(m["polarity"] == "positive" for m in matches)
        if known and positive:
            return "unknown"
        if matches:
            return "yes" if matches[-1]["polarity"] == "positive" else "no"
        return "no" if known else "unknown"
    monkeypatch.setattr(epar_nas, "verdict", v2)
    assert verdict_of(KNOWN_VALSARTAN, POS_SACUBITRIL) == "unknown"  # should be "yes"


def test_mutant_verb_negation_window_too_wide_is_caught(monkeypatch):
    monkeypatch.setattr(epar_nas, "VERB_TOKENS", 30)
    assert SINCE in failures()
    assert verdict_of(SINCE) == "no"  # the harm


def test_mutant_verb_negation_ignored_is_caught(monkeypatch):
    monkeypatch.setattr(epar_nas, "_negated_verb", lambda s: False)
    assert DID_NOT in failures() and DOES_NOT in failures()
    assert verdict_of(DID_NOT) == "yes"  # the harm
