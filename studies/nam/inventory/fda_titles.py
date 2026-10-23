"""Title rules for Drugs@FDA approval-package TOC pages.

Only the link titles of a TOC page are used (read from its pdfFiles flags);
no document is opened. The rules are fixed before any count is made.

Categories:
  pharmtox     flag pharmR            "Non-Clinical Review(s)" (earlier
                                      "Pharmacology/Toxicology Review")
  multidisc    flag multidisciplineR  "Multi-Discipline Review"
  integrated   flag integratedR       "Integrated Review" (kept apart)
Strict nonclinical = pharmtox or multidisc. Since PREREG version 2 an
integrated review also counts as a non-clinical document (has_nonclinical);
the strict count is kept for comparison.

Document format per drug (format_of): integrated if an Integrated Review
exists, else multidisc if a Multi-Discipline Review exists, else separate if
a Non-Clinical Review exists, else none.
"""
import re

FLAG_TO_CATEGORY = {
    "pharmR": "pharmtox",
    "multidisciplineR": "multidisc",
    "integratedR": "integrated",
}
STRICT = ("pharmtox", "multidisc")

_BLOCK = re.compile(r"var\s+pdfFiles\s*=\s*\{(.*?)\}\s*;", re.S)
_FLAG = re.compile(r"(?<![\w.])(\w+)\s*:\s*([01])(?=\s*[,}\s])")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_COMMENT = re.compile(r"(?<![:\w/])//[^\n]*")


class TocParseError(ValueError):
    pass


def parse_flags(page):
    """Return {flag: 0/1} from a TOC page; raise TocParseError if absent."""
    block = _BLOCK.search(page)
    if not block:
        raise TocParseError("no pdfFiles block")
    body = _COMMENT.sub("", _BLOCK_COMMENT.sub("", block.group(1)))
    flags = {}
    for k, v in _FLAG.findall(body):
        if k in flags and flags[k] != int(v):
            raise TocParseError("conflicting duplicate flag %s" % k)
        flags[k] = int(v)
    missing = [f for f in FLAG_TO_CATEGORY if f not in flags]
    if missing:
        raise TocParseError("flags missing: %s" % ", ".join(missing))
    return flags


def categories(flags):
    return {cat for flag, cat in FLAG_TO_CATEGORY.items() if flags.get(flag) == 1}


def has_strict_nonclinical(cats):
    return any(c in cats for c in STRICT)


def has_nonclinical(cats):
    return has_strict_nonclinical(cats) or "integrated" in cats


def format_of(cats):
    for cat, label in (("integrated", "integrated"), ("multidisc", "multidisc"),
                       ("pharmtox", "separate")):
        if cat in cats:
            return label
    return "none"
