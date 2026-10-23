"""Title rules for Drugs@FDA approval-package TOC pages.

Only the link titles of a TOC page are used (read from its pdfFiles flags);
no document is opened. The rules are fixed before any count is made.

Categories:
  pharmtox     flag pharmR            "Non-Clinical Review(s)" (earlier
                                      "Pharmacology/Toxicology Review")
  multidisc    flag multidisciplineR  "Multi-Discipline Review"
  integrated   flag integratedR       "Integrated Review" (kept apart)
Strict nonclinical = pharmtox or multidisc. Integrated reviews are reported
separately and are not counted as nonclinical until decided.
"""
import re

FLAG_TO_CATEGORY = {
    "pharmR": "pharmtox",
    "multidisciplineR": "multidisc",
    "integratedR": "integrated",
}
STRICT = ("pharmtox", "multidisc")

_BLOCK = re.compile(r"var\s+pdfFiles\s*=\s*\{(.*?)\}\s*;", re.S)
_FLAG = re.compile(r"^\s*(\w+)\s*:\s*([01])\s*,?\s*$", re.M)


class TocParseError(ValueError):
    pass


def parse_flags(page):
    """Return {flag: 0/1} from a TOC page; raise TocParseError if absent."""
    block = _BLOCK.search(page)
    if not block:
        raise TocParseError("no pdfFiles block")
    flags = {k: int(v) for k, v in _FLAG.findall(block.group(1))}
    missing = [f for f in FLAG_TO_CATEGORY if f not in flags]
    if missing:
        raise TocParseError("flags missing: %s" % ", ".join(missing))
    return flags


def categories(flags):
    return {cat for flag, cat in FLAG_TO_CATEGORY.items() if flags.get(flag) == 1}


def has_strict_nonclinical(cats):
    return any(c in cats for c in STRICT)
