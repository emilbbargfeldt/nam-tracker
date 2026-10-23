"""FDA universe: CDER novel approvals list joined to Drugs@FDA data files."""
import csv
import gzip
import html
import io
import re
import zipfile
from datetime import datetime

FIRST_YEAR = 2015
LAST_YEAR = 2026

LIVE = "https://www.fda.gov/drugs/novel-drug-approvals-fda/novel-drug-approvals-%d"
ARCHIVE = ("https://web.archive.org/web/20240418171144id_/"
           "https://www.fda.gov/drugs/novel-drug-approvals-fda/"
           "novel-drug-approvals-%d")
ARCHIVE_YEARS = range(2015, 2021)
DATAFILES_URL = "https://www.fda.gov/media/89850/download?attachment"

_TAG = re.compile(r"<[^>]+>")
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_HREF = re.compile(r'href="([^"]*)"', re.I)
_APPL = [
    re.compile(r"varApplNo=(\d{6})"),
    re.compile(r"/label/\d{4}/(\d{6})"),
    re.compile(r"/(?:appletter|nda|summary_review)/\d{4}/(\d{6})"),
    re.compile(r"/(\d{6})(?:Orig|s\d|lbl|_)"),
]


def decode_body(body):
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return body.decode("utf8", "replace")


def year_url(year):
    return (ARCHIVE if year in ARCHIVE_YEARS else LIVE) % year


def _text(cell):
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", cell))).strip()


def appl_no_from_links(links):
    for pat in _APPL:
        for link in links:
            m = pat.search(link)
            if m:
                return m.group(1)
    return None


_CELL_TABLE = re.compile(
    r"(<t[dh][^>]*>(?:(?!</t[dh]>|<table).)*?)"
    r"(<table(?:(?!<table|</table>).)*</table>)", re.S | re.I)
_STRUCT = re.compile(r"</?(?:table|tbody|thead|tr|td|th)\b[^>]*>", re.I)


def _flatten_nested(page):
    """Replace a table inside a cell by its content, keeping text and links."""
    return _CELL_TABLE.sub(lambda m: m.group(1) + _STRUCT.sub(" ", m.group(2)), page)


def parse_novel_page(page):
    """Parse one yearly novel-approvals page into a list of dicts."""
    page = _flatten_nested(page)
    rows = []
    for tr in _ROW.findall(page):
        cells = _CELL.findall(tr)
        if len(cells) < 4:
            continue
        no = _text(cells[0]).rstrip(".,")
        if not no.isdigit():
            continue
        date = _text(cells[3])
        try:
            approved = datetime.strptime(date, "%m/%d/%Y").date()
        except ValueError:
            approved = None
        rows.append({
            "no": int(no),
            "name": _text(cells[1]),
            "ingredient": _text(cells[2]),
            "approved": approved,
            "appl_no": appl_no_from_links(_HREF.findall(cells[1])),
        })
    return rows


def read_tsv(zf, name):
    raw = zf.read(name).decode("cp1252", "replace")
    return list(csv.DictReader(io.StringIO(raw), delimiter="\t"))


def load_datafiles(zip_path):
    zf = zipfile.ZipFile(zip_path)
    return {
        "applications": read_tsv(zf, "Applications.txt"),
        "submissions": read_tsv(zf, "Submissions.txt"),
        "docs": read_tsv(zf, "ApplicationDocs.txt"),
        "doctypes": read_tsv(zf, "ApplicationsDocsType_Lookup.txt"),
    }


def orig_approval_date(submissions, appl_no):
    """Earliest ORIG submission approval date (status AP) for an application."""
    dates = []
    for s in submissions:
        if (s["ApplNo"] == appl_no and s["SubmissionType"].strip() == "ORIG"
                and s["SubmissionStatus"].strip() == "AP"):
            try:
                dates.append(datetime.strptime(
                    s["SubmissionStatusDate"][:10], "%Y-%m-%d").date())
            except ValueError:
                pass
    return min(dates) if dates else None


def norm_name(name):
    name = re.sub(r"\(R\)|\(TM\)|[*\u00ae\u2122]", "", name)
    return re.sub(r"[^A-Z0-9 ]", "", name.upper()).strip()


def match_by_name(products, applications, name, year=None, submissions=()):
    """Unique NDA/BLA application number for a proprietary name, else None.

    With year, the candidate's ORIG approval must fall in that year.
    """
    types = {a["ApplNo"]: a["ApplType"].strip() for a in applications}
    want = norm_name(name)
    hits = {p["ApplNo"] for p in products
            if norm_name(p["DrugName"]) == want
            and types.get(p["ApplNo"]) in ("NDA", "BLA")}
    if year is not None:
        keep = set()
        for h in hits:
            d = orig_approval_date(submissions, h)
            if d is not None and d.year == year:
                keep.add(h)
        hits = keep
    return hits.pop() if len(hits) == 1 else None


def validate_page(rows, year):
    """Return a list of problems: empty page, gaps/duplicates in No., duplicate appl_no."""
    if not rows:
        return ["no rows parsed for %d" % year]
    problems = []
    nos = [r["no"] for r in rows]
    if sorted(nos) != list(range(1, len(nos) + 1)):
        problems.append("row numbers are not 1..N for %d" % year)
    seen = set()
    for r in rows:
        a = r["appl_no"]
        if a and a in seen:
            problems.append("duplicate appl_no %s in %d" % (a, year))
        seen.add(a)
    return problems


def resolve_rows(rows, page_year, products, applications, submissions):
    """Fill missing application numbers and repair implausible dates.

    Every repair is recorded in row["notes"]; nothing is dropped silently.
    """
    out = []
    for r in rows:
        r = dict(r, notes=[], year_page=page_year)
        if not r["name"]:
            r["notes"].append("empty name")
        if r["appl_no"] is None and r["name"]:
            found = match_by_name(products, applications, r["name"],
                                  page_year, submissions)
            if found:
                r["appl_no"] = found
                r["notes"].append("appl_no from name match")
        ok = r["approved"] is not None and r["approved"].year == page_year
        if not ok:
            r["notes"].append("list date unusable: %s" % r["approved"])
            alt = (orig_approval_date(submissions, r["appl_no"])
                   if r["appl_no"] else None)
            r["approved_listed"] = r["approved"]
            r["approved"] = alt if alt and alt.year == page_year else None
        out.append(r)
    return out
