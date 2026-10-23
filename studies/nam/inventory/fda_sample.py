"""FDA sample: URL of the chosen review PDF and the stratified draw."""
import re

from .fda_titles import TocParseError, parse_flags

# Document priority per drug: the most specific non-clinical document.
PRIORITY = (("pharmR", "pharmtox", "PharmR"),
            ("multidisciplineR", "multidisc", "MultidisciplineR"),
            ("integratedR", "integrated", "IntegratedR"))
_NAME = re.compile(r'var\s+pdfBaseName\s*=\s*"([^"]+)"')
_APPNO = re.compile(r'var\s+applicationNumber\s*=\s*"([^"]+)"')
_FILES = re.compile(r'(\w+)\s*:\s*"([^"]+\.pdf)"', re.I)


def choose_doc(flags):
    """(flag, category, suffix) of the document to sample, or None."""
    for flag, cat, suffix in PRIORITY:
        if flags.get(flag) == 1:
            return flag, cat, suffix
    return None


def doc_url(toc_url, page, flag, suffix):
    """PDF URL next to the TOC page, from pdfFilenames or the base name."""
    folder = toc_url.rsplit("/", 1)[0] + "/"
    for key, name in _FILES.findall(page):
        if key.lower() == flag.lower():
            return folder + name
    m = _NAME.search(page)
    if m:
        return folder + m.group(1) + suffix + ".pdf"
    m = _APPNO.search(page)
    return folder + m.group(1) + suffix + ".pdf" if m else None


def resolve_candidate(name, tocs):
    """Status of one drug for the sample.

    tocs: list of (toc_url, page_or_None) for its ORIG approval-package pages.
    Returns ("ok", (name, pdf_url, category)), ("none", None) when the package
    is read and has no non-clinical document (or there is no package), or
    ("error", reason) when a TOC page is missing or unreadable so that the
    answer is unknown (also when the best document found has a lower priority
    than the top one and a page could not be read).
    """
    if not tocs:
        return "none", None
    errors = []
    found = {}
    for url, page in tocs:
        if page is None:
            errors.append("toc_missing")
            continue
        try:
            flags = parse_flags(page)
        except TocParseError:
            errors.append("toc_unparsed")
            continue
        choice = choose_doc(flags)
        if choice and choice[0] not in found:
            u = doc_url(url, page, choice[0], choice[2])
            if u:
                found[choice[0]] = (u, choice[1])
            else:
                errors.append("doc_url_missing")
    for rank, (flag, _cat, _suffix) in enumerate(PRIORITY):
        if flag in found:
            if errors and rank > 0:
                # an unreadable page might hold a higher-priority document
                return "error", errors[0]
            u, cat = found[flag]
            return "ok", (name, u, cat)
    return ("error", errors[0]) if errors else ("none", None)
