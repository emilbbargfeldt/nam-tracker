"""Clopper-Pearson interval and point-estimate verdict (DECISIONS 2026-11-05 (a)).
Known values from PREREG v7 and the pilot design."""
import pytest

from studies.nam.pilot import stats


def close(pair, lo, hi, tol=1e-3):
    return abs(pair[0] - lo) <= tol and abs(pair[1] - hi) <= tol


def test_10_of_10_one_sided_lower():
    lower, upper = stats.clopper_pearson(10, 10, alpha=0.05, sided="lower")
    assert lower == pytest.approx(0.741, abs=5e-4)
    assert upper == 1.0


def test_15_of_15():
    assert close(stats.clopper_pearson(15, 15), 0.782, 1.0)


def test_14_of_15():
    assert close(stats.clopper_pearson(14, 15), 0.681, 0.998)


def test_21_of_21():
    assert close(stats.clopper_pearson(21, 21), 0.839, 1.0)


def test_19_of_21():
    assert close(stats.clopper_pearson(19, 21), 0.696, 0.988)


def test_upper_sided():
    lower, upper = stats.clopper_pearson(0, 10, alpha=0.05, sided="upper")
    assert lower == 0.0
    assert upper == pytest.approx(1 - 0.05 ** (1 / 10), abs=1e-6)


def test_k_zero_and_k_n_edges():
    lower, upper = stats.clopper_pearson(0, 15)
    assert lower == 0.0 and 0.0 < upper < 1.0
    lower, upper = stats.clopper_pearson(15, 15)
    assert upper == 1.0 and 0.0 < lower < 1.0


@pytest.mark.parametrize("k,n", [(0, 0), (1, 0), (-1, 5), (6, 5)])
def test_invalid_counts(k, n):
    with pytest.raises(ValueError):
        stats.clopper_pearson(k, n)


def test_invalid_sided_and_alpha():
    with pytest.raises(ValueError):
        stats.clopper_pearson(5, 10, sided="both")
    with pytest.raises(ValueError):
        stats.clopper_pearson(5, 10, alpha=0.0)


@pytest.mark.parametrize("n", [15, 10])
def test_closed_form_lower_k_equals_n(n):
    lower, upper = stats.clopper_pearson(n, n)
    assert lower == pytest.approx((0.05 / 2) ** (1 / n), abs=1e-9)
    assert upper == 1.0


def test_closed_form_upper_k_zero():
    lower, upper = stats.clopper_pearson(0, 10)
    assert lower == 0.0
    assert upper == pytest.approx(1 - (0.05 / 2) ** (1 / 10), abs=1e-9)


def test_closed_form_one_sided_10_of_10():
    lower, _ = stats.clopper_pearson(10, 10, alpha=0.05, sided="lower")
    assert lower == pytest.approx(0.05 ** (1 / 10), abs=1e-9)


@pytest.mark.parametrize("k,n,passed", [(14, 15, True), (13, 15, False),
                                        (19, 21, True), (18, 21, False),
                                        (9, 10, True), (18, 20, True)])
def test_verdict_boundaries_at_090(k, n, passed):
    v = stats.rate_verdict(k, n, 0.90)
    assert v["passed"] is passed


def test_verdict_fields():
    v = stats.rate_verdict(14, 15, 0.90)
    assert set(v) == {"k", "n", "rate", "ci", "passed"}
    assert v["k"] == 14 and v["n"] == 15
    assert v["rate"] == pytest.approx(14 / 15)
    assert close(v["ci"], 0.681, 0.998)


def test_passed_ignores_ci():
    v = stats.rate_verdict(14, 15, 0.90)
    assert v["passed"] is True
    assert v["ci"][0] < 0.90


def test_verdict_invalid():
    with pytest.raises(ValueError):
        stats.rate_verdict(0, 0, 0.90)


@pytest.mark.parametrize("threshold", [True, -0.1, 1.5, 2, None, "abc"])
def test_verdict_invalid_threshold(threshold):
    with pytest.raises(ValueError):
        stats.rate_verdict(14, 15, threshold)


def test_verdict_threshold_edges():
    assert stats.rate_verdict(15, 15, 1)["passed"] is True
    assert stats.rate_verdict(0, 15, 0)["passed"] is True


def test_n_above_max_rejected():
    with pytest.raises(ValueError):
        stats.clopper_pearson(5, stats.MAX_N + 1)
    stats.clopper_pearson(1, 50)
