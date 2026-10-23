"""EMA universe: new active substances by definition B (PREREG version 2).

Human, authorised at some point (has an approval date), Generic = No,
Biosimilar = No, and at least one normalised active substance not present in
an earlier human product of the table. Later withdrawn products are included.
"""
import re
import unicodedata
from datetime import datetime

TABLE_URL = "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines-report_en.xlsx"
HEADER_FIRST = "Category"
REQUIRED = {
    "category": "Category",
    "name": "Name of medicine",
    "status": "Medicine status",
    "substance": "Active substance",
    "generic": "Generic",
    "biosimilar": "Biosimilar",
    "ma_date": "Marketing authorisation date",
    "ec_date": "European Commission decision date",
    "url": "Medicine URL",
    "opinion_date": "Opinion adopted date",
}
# Status values for products that were authorised at some point.
EVER_AUTHORISED = {"Authorised", "Withdrawn", "Expired", "Lapsed", "Revoked",
                   "Suspended"}
SALT_WORDS = {
    "hydrochloride", "dihydrochloride", "hydrobromide", "sodium", "potassium",
    "calcium", "magnesium", "bromide", "chloride", "sulfate", "sulphate",
    "phosphate", "mesilate", "mesylate", "maleate", "fumarate", "tartrate",
    "besilate", "acetate", "succinate", "citrate", "monohydrate", "dihydrate",
    "trihydrate", "hydrate", "anhydrous", "tosilate", "tosylate", "nitrate",
    "disodium", "lysine", "hemihydrate", "pamoate", "oxalate", "lactate",
}


KNOWN_STATUS = EVER_AUTHORISED | {
    "Application withdrawn", "Opinion", "Opinion under re-examination",
    "Refused", "Withdrawn from rolling review"}


class EmaTableError(ValueError):
    pass


def find_header(rows):
    for i, r in enumerate(rows):
        if r and r[0].strip() == HEADER_FIRST:
            return i
    raise EmaTableError("header row not found")


def load_table(rows):
    """Return a list of dicts keyed by the REQUIRED short names."""
    h = find_header(rows)
    header = [c.replace("\n", " ").strip() for c in rows[h]]
    idx = {}
    for key, title in REQUIRED.items():
        if title not in header:
            raise EmaTableError("column missing: %s" % title)
        idx[key] = header.index(title)
    out = []
    for r in rows[h + 1:]:
        if not any(c.strip() for c in r):
            continue
        r = r + [""] * (len(header) - len(r))
        out.append({k: r[i].strip() for k, i in idx.items()})
    return out


def parse_date(s):
    try:
        return datetime.strptime(s.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def approval_date(row):
    """Marketing authorisation date, else EC decision date (the fallback only
    for an authorised-at-some-point status). Returns (date, source) or
    (None, None)."""
    d = parse_date(row["ma_date"])
    if d:
        return d, "ma"
    if row["status"] not in EVER_AUTHORISED:
        return None, None
    d = parse_date(row["ec_date"])
    return (d, "ec") if d else (None, None)


def norm_substances(text):
    """Normalised set of active substances (';' separates substances)."""
    out = set()
    for part in text.split(";"):
        part = unicodedata.normalize("NFKD", part)
        part = "".join(c for c in part if not unicodedata.combining(c)).lower()
        words = [w for w in re.split(r"[\s,]+", part.strip())
                 if w and w not in SALT_WORDS]
        if not words:  # the part is only salt words (e.g. sodium chloride)
            words = part.split()
        s = " ".join(words)
        if s:
            out.add(s)
    return out


def has_salt_only_part(text):
    """True if some ';'-part consists only of salt words (kept as it is)."""
    for part in text.split(";"):
        words = [w for w in re.split(r"[\s,]+", part.strip().lower()) if w]
        if words and all(w in SALT_WORDS for w in words):
            return True
    return False


def new_active_substances(table):
    """Apply definition B. Returns (nas_rows, log)."""
    human = []
    for r in table:
        if r["category"] != "Human":
            continue
        d, src = approval_date(r)
        if d is None:
            continue
        human.append(dict(r, date=d, date_src=src,
                          subs=norm_substances(r["substance"])))
    first = {}
    for r in human:
        for s in r["subs"]:
            if s not in first or r["date"] < first[s]:
                first[s] = r["date"]
    bad_dates = sum(1 for r in table
                    for k in ("ma_date", "ec_date", "opinion_date")
                    if r[k] and parse_date(r[k]) is None)
    log = {"human_with_date": len(human),
           "unparsable_dates": bad_dates,
           "unknown_status": sorted({r["status"] for r in table
                                     if r["status"] not in KNOWN_STATUS}),
           "ec_fallback_rows": [(r["name"], str(r["date"]), r["status"])
                                for r in human if r["date_src"] == "ec"],
           "ma_sourced": sum(1 for r in human if r["date_src"] == "ma"),
           "both_dates": sum(1 for r in human if parse_date(r["ma_date"])
                             and parse_date(r["ec_date"])),
           "ec_on_or_after_ma": sum(1 for r in human if parse_date(r["ma_date"])
                                    and parse_date(r["ec_date"])
                                    and parse_date(r["ec_date"]) >= parse_date(r["ma_date"])),
           "no_substance": sum(1 for r in human if not r["subs"]),
           "salt_only_parts": sum(1 for r in human
                                  if has_salt_only_part(r["substance"])),
           "date_from_ec": sum(1 for r in human if r["date_src"] == "ec"),
           "ma_ec_differ": sum(1 for r in human if r["date_src"] == "ma"
                               and parse_date(r["ec_date"])
                               and parse_date(r["ec_date"]) != r["date"]),
           "same_day_siblings": 0}
    nas = []
    for r in human:
        if r["generic"] != "No" or r["biosimilar"] != "No":
            continue
        new = [s for s in r["subs"] if first[s] >= r["date"]]
        if not new:
            continue
        r["new_subs"] = sorted(new)
        nas.append(r)
    by_sub = {}
    for r in nas:
        for s in r["new_subs"]:
            by_sub.setdefault(s, []).append(r)
    for s, rs in by_sub.items():
        first_day = min(x["date"] for x in rs)
        if len({x["name"] for x in rs if x["date"] == first_day}) > 1:
            log["same_day_siblings"] += 1
    return nas, log


def per_year(nas, first=2015, last=2026, by="date"):
    """Count per year by approval date, or by CHMP opinion date (by="opinion")."""
    out = {y: 0 for y in range(first, last + 1)}
    for r in nas:
        d = r["date"] if by == "date" else parse_date(r["opinion_date"])
        if d and d.year in out:
            out[d.year] += 1
    return out


# EMA annual overviews ("Human medicines highlights" / "Human medicines in
# YYYY"): medicines recommended and recommended with a new active substance,
# counted at the CHMP opinion. 2021 NAS read as "541" by the page reader, taken
# as 54 plus a footnote marker (to be checked); 2022 is the figure updated on
# 2026-03-03 (earlier 41).
HIGHLIGHTS_NAS = {2015: 39, 2016: 27, 2017: 35, 2018: 42, 2019: 30, 2020: 39,
                  2021: 54, 2022: 42, 2023: 39, 2024: 46, 2025: 38}


def crosscheck(nas):
    """Per year: highlights vs definition B counted by opinion year and by
    approval year. Deviations are reported, not corrected."""
    by_op = per_year(nas, by="opinion")
    by_ma = per_year(nas)
    return {y: {"highlights": n, "b_by_opinion_year": by_op[y],
                "b_by_approval_year": by_ma[y],
                "dev_opinion": by_op[y] - n, "dev_approval": by_ma[y] - n}
            for y, n in HIGHLIGHTS_NAS.items()}
