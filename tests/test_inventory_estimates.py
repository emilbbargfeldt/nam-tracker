import pytest

from studies.nam.inventory.estimates import min_detectable, page_estimate, power


def test_known_answer_two_groups_of_65_give_about_80_percent():
    # classic: p 0.2 vs 0.4, alpha 0.05 one-sided, n = 65 per group -> ~80 %
    assert 0.77 < power(0.2, 0.4, 65, 65) < 0.83


def test_power_increases_with_n_and_with_effect():
    assert power(0.1, 0.2, 400, 150) > power(0.1, 0.2, 200, 75)
    assert power(0.1, 0.3, 200, 75) > power(0.1, 0.2, 200, 75)


def test_min_detectable_reaches_target_and_shrinks_with_n():
    d = min_detectable(0.05, 400, 130)
    assert abs(power(0.05, d, 400, 130) - 0.80) < 1e-3
    assert min_detectable(0.05, 800, 270) < d


def test_min_detectable_none_when_impossible():
    assert min_detectable(0.5, 3, 3) is None


def test_power_rejects_wrong_direction():
    with pytest.raises(ValueError):
        power(0.2, 0.1, 100, 100)


def test_page_estimate_known_answer():
    total, band = page_estimate({2020: 100.0, 2021: 200.0}, {2020: 10, 2021: 5},
                                pooled_sd=50.0, n_docs=4)
    assert total == 2000.0
    assert abs(band - 2 * 15 * 50.0 / 2) < 1e-9
