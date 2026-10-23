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


def test_exact_match():
    assert verify_quote(PAGE, "in vitro studies using human hepatocytes", RATIO)


def test_match_across_line_break():
    assert verify_quote(PAGE, "studies using human hepatocytes. Genotoxicity", RATIO)


def test_match_across_hyphenation():
    page = "A physiologically based pharmaco-\nkinetic model was used."
    assert verify_quote(page, "based pharmacokinetic model", RATIO)


def test_typographic_quotes_and_dashes():
    page = "The sponsor said \u201cno animal testing\u201d \u2013 it\u2019s new."
    assert verify_quote(page, "\"no animal testing\" - it's new", RATIO)


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
