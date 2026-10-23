import importlib
import os

import pytest

verify_quote = importlib.import_module(
    os.environ.get("NAM_QUOTECHECK_MODULE", "core.quotecheck")
).verify_quote

PAGE = (
    "Nonclinical assessment. The applicant submitted in vitro studies using\n"
    "human hepatocytes. Genotoxicity was evaluated with an organ-on-chip\n"
    "model; in addition, a physiologically based pharmacokinetic model was\n"
    "used to support the first-in-human dose."
)
RATIO = 0.9
EXACT = 1.0  # ratio 1.0 means exact only


def test_exact_match():
    assert verify_quote(PAGE, "in vitro studies using human hepatocytes", RATIO)


def test_match_across_line_break():
    assert verify_quote(PAGE, "studies using human hepatocytes. Genotoxicity", EXACT)


def test_match_across_hyphenation():
    page = "A physiologically based pharmaco-\nkinetic model was used."
    assert verify_quote(page, "based pharmacokinetic model", EXACT)


def test_typographic_quotes_and_dashes():
    page = "The sponsor said \u201cno animal testing\u201d \u2013 it\u2019s new."
    assert verify_quote(page, "\"no animal testing\" - it's new", EXACT)


def test_ocr_deviation_above_threshold():
    ocr = "physiologicaly based pharmacokinetlc model was used"
    assert verify_quote(PAGE, ocr, 0.9)


def test_ocr_deviation_below_threshold():
    ocr = "phvsiologicaly bascd pharmacokinetlc rnodel vvas used"
    assert not verify_quote(PAGE, ocr, 0.95)


def test_quote_not_on_page():
    assert not verify_quote(PAGE, "carcinogenicity was assessed in transgenic mice", RATIO)


@pytest.mark.parametrize("quote", ["", "   ", "\n\t"])
def test_empty_quote_raises(quote):
    with pytest.raises(ValueError):
        verify_quote(PAGE, quote, RATIO)


def test_min_ratio_is_required():
    with pytest.raises(TypeError):
        verify_quote(PAGE, "human hepatocytes")


@pytest.mark.parametrize("ratio", [0, -1, 1.5])
def test_invalid_min_ratio_raises(ratio):
    with pytest.raises(ValueError):
        verify_quote(PAGE, "human hepatocytes", ratio)


def test_ratio_one_requires_exact():
    assert not verify_quote(PAGE, "human hepatocytez", 1.0)


def test_empty_page():
    assert not verify_quote("", "human hepatocytes", RATIO)


def test_large_page_is_fast():
    import time
    page = (PAGE + " ") * 1500
    start = time.monotonic()
    assert not verify_quote(page, "carcinogenicity was assessed in transgenic mice " * 3, 0.8)
    assert time.monotonic() - start < 5


# --- numbers ---------------------------------------------------------------

def test_changed_number_is_rejected():
    assert not verify_quote("The dose of 100 mg/kg was given.", "dose of 10 mg/kg", 0.8)


def test_number_inside_longer_number_is_rejected_by_word_boundary():
    assert not verify_quote("A dose of 110 mg/kg", "10 mg/kg", RATIO)


def test_same_number_passes_with_fuzzy_noise():
    assert verify_quote("The dosage of 10 mg/kg was given.", "dose of 10 mg/kg was given", 0.8)


def test_number_with_trailing_punctuation_passes():
    assert verify_quote("Dose was 10 mg/kg.", "Dose was 10 mg/kg", RATIO)


# --- negation --------------------------------------------------------------

def test_missing_negation_in_quote_is_rejected():
    assert not verify_quote("The effect was not observed in any animal.",
                            "The effect was observed in any animal", 0.8)


def test_extra_negation_in_quote_is_rejected():
    assert not verify_quote("An effect was observed in all animals.",
                            "effect was not observed in all animals", 0.8)


def test_contraction_negation_is_rejected():
    assert not verify_quote("The effect wasn't observed here.", "The effect was observed here", 0.8)


def test_same_negation_passes():
    assert verify_quote("There was no effect observed.", "There was no effect observed", RATIO)


# --- hyphenation variants --------------------------------------------------

def test_real_hyphen_broken_at_line_end_matches():
    assert verify_quote("a well-\nknown effect", "a well-known effect", EXACT)


def test_hyphenation_joined_word_still_matches():
    assert verify_quote("a pharmaco-\nkinetic model", "a pharmacokinetic model", EXACT)


# --- normalization ---------------------------------------------------------

def test_ligature_matches():
    assert verify_quote("The e\ufb03cacy was shown.", "The efficacy was shown", EXACT)


def test_soft_hyphen_mid_word_matches():
    assert verify_quote("pharmaco\u00adkinetic model", "pharmacokinetic model", EXACT)


def test_soft_hyphen_at_line_end_matches():
    assert verify_quote("pharmaco\u00ad\nkinetic model", "pharmacokinetic model", EXACT)


def test_zero_width_characters_are_ignored():
    assert verify_quote("hepato\u200bcytes\ufeff were used", "hepatocytes were used", EXACT)


@pytest.mark.parametrize("page, quote", [
    ("The dose was 10.5 mg", "The dose was 10"),
    ("a dose of 0.5 mg daily", "5 mg daily"),
    ("count 10,000 cells", "count 10"),
    ("dose 10-20 mg", "dose 10"),
])
def test_exact_substring_of_longer_number_is_rejected(page, quote):
    assert not verify_quote(page, quote, RATIO)


def test_number_followed_by_sentence_period_passes():
    assert verify_quote("The dose was 10. Then", "The dose was 10", RATIO)


def test_ratio_one_does_not_match_inside_a_word():
    assert not verify_quote("pianos", "ano", 1.0)
    assert not verify_quote("no effect", "no effec", 1.0)


def test_bool_min_ratio_is_rejected():
    with pytest.raises(ValueError):
        verify_quote(PAGE, "human hepatocytes", True)


def test_repetitive_page_with_long_quote_is_fast():
    import time
    page = "aaaa " * 40000
    start = time.monotonic()
    verify_quote(page, "aaaa " * 40 + "b", 0.8)
    assert time.monotonic() - start < 10


def _word(i):
    letters = "abcdefghijklmnopqrstuvwxyz"
    return letters[i % 26] + letters[i // 26 % 26] + letters[i // 676 % 26] + "x"


def test_long_quote_fuzzy_hit_is_fast_and_found():
    import time
    words = [_word(i) for i in range(30000)]
    page = " ".join(words)
    quote = " ".join(words[5000:5150]).replace("x", "y", 3)
    start = time.monotonic()
    assert verify_quote(page, quote, 0.9)
    assert time.monotonic() - start < 10
