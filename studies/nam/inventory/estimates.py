"""Counts-only estimates: power for question 2 and the page volume.

No outcome is used. Question 2: is the share higher after than before
(one-sided z test of two proportions, normal approximation). With few expected
events (low baseline, small groups) the approximation is rough.
"""
import math
from statistics import NormalDist

_N = NormalDist()


def power(p0, p1, n_before, n_after, alpha=0.05):
    """One-sided power to detect p1 > p0 (after vs before)."""
    if not (0 < p0 < 1 and 0 < p1 < 1) or p1 <= p0:
        raise ValueError("need 0 < p0 < p1 < 1")
    za = _N.inv_cdf(1 - alpha)
    pbar = (n_before * p0 + n_after * p1) / (n_before + n_after)
    se0 = math.sqrt(pbar * (1 - pbar) * (1 / n_before + 1 / n_after))
    se1 = math.sqrt(p0 * (1 - p0) / n_before + p1 * (1 - p1) / n_after)
    return _N.cdf((p1 - p0 - za * se0) / se1)


def min_detectable(p0, n_before, n_after, target=0.80, alpha=0.05):
    """Smallest p1 > p0 with power >= target, or None if even p1 -> 1 fails."""
    lo, hi = p0 + 1e-9, 1 - 1e-9
    if power(p0, hi, n_before, n_after, alpha) < target:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if power(p0, mid, n_before, n_after, alpha) >= target:
            hi = mid
        else:
            lo = mid
    return hi


def page_estimate(year_means, year_counts, pooled_sd, n_docs):
    """Total pages = sum(mean pages per document of a year x documents that
    year). Also returns an approximate +-2 standard error from the pooled
    sample standard deviation (stratification not modelled)."""
    total = sum(year_means[y] * year_counts[y] for y in year_counts)
    n_total = sum(year_counts.values())
    se = n_total * pooled_sd / math.sqrt(n_docs)
    return total, 2 * se
