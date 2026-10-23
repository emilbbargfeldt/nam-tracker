"""Go criterion: share of drugs with a public non-clinical document >= 80 %."""

THRESHOLD = 0.80


def share(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def fda_claim(year_counts):
    """year_counts: {year: counts from fda_count}. Denominator = all listed
    drugs (also those not found in Drugs@FDA or without a readable TOC).
    Returns (share, lower-bound count, total)."""
    num = sum(c.get("nonclinical", 0) for c in year_counts.values())
    den = sum(c.get("listed", 0) for c in year_counts.values())
    return share(num, den), num, den


def ema_claim(epar_rows):
    """epar_rows: list of dicts with a 'report' key (link or None)."""
    num = sum(1 for r in epar_rows if r.get("report"))
    return share(num, len(epar_rows)), num, len(epar_rows)


def meets(s):
    return s >= THRESHOLD
