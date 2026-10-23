import pytest

from studies.nam.inventory import cost


def rec(year, chars, chars_low=0, pages=10, low=0):
    return {"year": year, "chars": chars, "chars_low": chars_low,
            "section_pages": pages, "low_text_pages": low}


def test_tokens_are_chars_over_four():
    assert cost.tokens(4000) == 1000


def test_median_text_page_chars_excludes_low_pages():
    recs = [rec(2020, 1000, 0, 10, 0),        # 100 per page
            rec(2020, 1500, 100, 10, 5),      # (1500-100)/5 = 280
            rec(2020, 400, 0, 4, 0)]          # 100 per page
    assert cost.median_text_page_chars(recs) == 100


def test_effective_chars_imputes_low_pages():
    r = rec(2020, 1100, 100, 10, 4)           # 1000 chars on 6 text pages
    assert cost.effective_chars(r, 150) == 1000 + 4 * 150


def test_without_imputation_scanned_document_looks_cheaper():
    r = rec(2016, 100, 100, 10, 10)
    assert cost.effective_chars(r, 200) == 2000 > r["chars"]


def test_project_known_total():
    recs = [rec(2020, 100), rec(2020, 300), rec(2021, 1000), rec(2021, 1000)]
    total, band = cost.project(recs, {2020: 10, 2021: 5}, lambda r: r["chars"])
    assert total == 200 * 10 + 1000 * 5
    assert band > 0


def test_project_ignores_years_with_zero_documents_and_no_sample():
    recs = [rec(2020, 100), rec(2020, 300)]
    total, _ = cost.project(recs, {2020: 2, 1999: 0}, lambda r: r["chars"])
    assert total == 400


def test_price_known_values():
    assert cost.price_usd(2_500_000, 2.0) == pytest.approx(5.0)
    assert cost.price_usd(1_000_000, cost.INPUT_USD_PER_MTOK["Haiku 5.5"]) == pytest.approx(0.10)


def test_price_table_matches_documented_list_prices():
    assert cost.INPUT_USD_PER_MTOK == {"Haiku 5.5": 0.10, "Sonnet 5.5": 2.0,
                                       "Opus 5.5": 4.0}


def test_low_pages_whole_uses_threshold_exclusive():
    r = {"chars_per_page": [0, 99, 100, 500]}
    assert cost.low_pages_whole(r, 100) == 2


# Deliberate faults
def test_mutant_wrong_divisor_is_caught(monkeypatch):
    monkeypatch.setattr(cost, "CHARS_PER_TOKEN", 3)
    assert cost.tokens(4000) != 1000


def test_mutant_no_imputation_is_caught(monkeypatch):
    monkeypatch.setattr(cost, "effective_chars", lambda r, p: r["chars"])
    r = rec(2016, 100, 100, 10, 10)
    assert cost.effective_chars(r, 200) != 2000


def test_project_refuses_a_year_with_documents_but_no_sample():
    recs = [rec(2020, 100), rec(2020, 300)]
    with pytest.raises(ValueError):
        cost.project(recs, {2020: 2, 2021: 5}, lambda r: r["chars"])
