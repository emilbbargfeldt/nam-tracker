"""Token, price and OCR-scope projections from counts. No text is used.

Tokens are estimated as characters / 4. Pages below the text-layer threshold
carry (almost) no characters, so they are imputed with the pooled median
characters per text page of the same authority; otherwise scanned documents
would look free. All projections multiply a per-year sample mean by the number
of documents that year (same approach as estimates.page_estimate; n = 2
documents per stratum, so the figures are rough).
"""
import statistics as st

from . import estimates

CHARS_PER_TOKEN = 4

# List prices, USD per million input tokens, from the Anthropic pricing pages
# (https://platform.claude.com/docs/en/about-claude/pricing and
# https://claude.com/pricing), fetched 2026-10-23. Haiku 5.5 is priced by
# prompt length: 0.10 up to 100,000 tokens, 0.50 above.
SOURCE = ("https://platform.claude.com/docs/en/about-claude/pricing and "
          "https://claude.com/pricing, fetched 2026-10-23")
INPUT_USD_PER_MTOK = {"Haiku 5.5": 0.10, "Sonnet 5.5": 2.0, "Opus 5.5": 4.0}
OUTPUT_USD_PER_MTOK = {"Haiku 5.5": 0.50, "Sonnet 5.5": 10.0, "Opus 5.5": 20.0}
BATCH_DISCOUNT = 0.5


def tokens(chars):
    return chars / CHARS_PER_TOKEN


def median_text_page_chars(recs):
    """Pooled median characters per text page in the located sections."""
    vals = [(r["chars"] - r["chars_low"]) / (r["section_pages"] - r["low_text_pages"])
            for r in recs if r["section_pages"] > r["low_text_pages"]]
    return st.median(vals)


def effective_chars(rec, per_text_page):
    """Characters of a section with low-text pages imputed."""
    return rec["chars"] - rec["chars_low"] + rec["low_text_pages"] * per_text_page


def project(recs, counts, value):
    """Projected total of value(rec) over the universe, with approx. +-2 SE.

    recs: sample records with "year"; counts: {year: documents that year}.
    """
    by_year = {}
    for r in recs:
        by_year.setdefault(r["year"], []).append(value(r))
    means = {y: st.mean(v) for y, v in by_year.items()}
    sd = st.stdev([value(r) for r in recs])
    missing = sorted(y for y, n in counts.items() if n and y not in means)
    if missing:
        raise ValueError("no sampled documents for years %s" % missing)
    use = {y: n for y, n in counts.items() if y in means}
    return estimates.page_estimate(means, use, sd, len(recs))


def price_usd(total_tokens, usd_per_mtok):
    return total_tokens / 1e6 * usd_per_mtok


def low_pages_whole(rec, threshold):
    """Pages below the threshold in a whole sampled document."""
    return sum(1 for c in rec["chars_per_page"] if c < threshold)
