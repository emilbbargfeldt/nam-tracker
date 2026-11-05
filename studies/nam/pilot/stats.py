"""Exact binomial confidence interval and point-estimate verdict
(DECISIONS 2026-11-05 (a)): pass/fail is the point estimate k/n against the
threshold; the exact Clopper-Pearson interval is reported for every rate and
is not a criterion. Standard library only."""
from fractions import Fraction
from math import comb

ITERATIONS = 60
MAX_N = 1000


def _check(k, n, alpha, sided):
    if isinstance(k, bool) or isinstance(n, bool) \
            or not isinstance(k, int) or not isinstance(n, int):
        raise ValueError("k and n must be integers")
    if n < 1:
        raise ValueError("n must be at least 1")
    if n > MAX_N:
        raise ValueError("n must be at most %d" % MAX_N)
    if not 0 <= k <= n:
        raise ValueError("k must satisfy 0 <= k <= n")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    if sided not in ("two", "lower", "upper"):
        raise ValueError("sided must be 'two', 'lower' or 'upper'")


def _pmf_sum(lo, hi, n, p):
    q = 1.0 - p
    return sum(comb(n, i) * p ** i * q ** (n - i) for i in range(lo, hi + 1))


def _bisect(func, target, increasing):
    """p in [0, 1] with func(p) == target for a monotone func."""
    lo, hi = 0.0, 1.0
    for _ in range(ITERATIONS):
        mid = (lo + hi) / 2
        if (func(mid) < target) == increasing:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def clopper_pearson(k, n, alpha=0.05, sided="two"):
    """(lower, upper) exact interval. sided "two" uses alpha/2 in each tail;
    "lower" gives (lower, 1.0) and "upper" gives (0.0, upper) at level alpha."""
    _check(k, n, alpha, sided)
    a = alpha / 2 if sided == "two" else alpha
    lower, upper = 0.0, 1.0
    if sided in ("two", "lower") and k > 0:
        # P(X >= k | p) rises with p; solve for a.
        lower = _bisect(lambda p: _pmf_sum(k, n, n, p), a, True)
    if sided in ("two", "upper") and k < n:
        # P(X <= k | p) falls with p; solve for a.
        upper = _bisect(lambda p: _pmf_sum(0, k, n, p), a, False)
    return lower, upper


def rate_verdict(k, n, threshold):
    """{"k", "n", "rate", "ci", "passed"}. passed is exactly k/n >= threshold
    (decimal value of threshold, no tolerance); the interval is not used."""
    if isinstance(threshold, bool):
        raise ValueError("threshold must be a number")
    try:
        limit = Fraction(str(threshold))
    except ValueError:
        raise ValueError("threshold must be a number") from None
    if not 0 <= limit <= 1:
        raise ValueError("threshold must be in [0, 1]")
    ci = clopper_pearson(k, n)
    return {"k": k, "n": n, "rate": k / n, "ci": ci,
            "passed": Fraction(k, n) >= limit}
