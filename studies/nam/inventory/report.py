"""Write docs/INVENTORY.md from the derived files in $NAM_DATA.

Usage: NAM_DATA=... python -I -m studies.nam.inventory.report > docs/INVENTORY.md
"""
import json
import random
import statistics as st
import sys
import zipfile

from . import claim80, ema, estimates, fda, measure, report_step2
from .fetch import Fetcher
from .xlsx import read_xlsx

FDA_TERMS_URL = "https://www.fda.gov/about-fda/about-website/website-policies"
FDA_TERMS_QUOTE = "may be republished, reprinted and otherwise used freely by anyone"
EMA_TERMS_URL = "https://www.ema.europa.eu/en/about-us/about-website/legal-notice"
EMA_TERMS_QUOTE = ("for non-commercial and commercial purposes, provided that EMA "
                   "is always acknowledged as the source")
HIGHLIGHT_URLS = ("https://www.ema.europa.eu/en/about-us/what-we-do/"
                  "authorisation-medicines/medicine-evaluation-figures")


def a(s):
    return str(s).encode("ascii", "replace").decode()


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(a(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def open_section(w, yc, epar, samp, cc, ema_py):
    """Open for decision: counts only, no outcome."""
    w("## Open for decision\n")
    # 1 EMA definition
    hl = sum(v["highlights"] for v in cc["crosscheck"].values())
    dev = sum(v["dev_opinion"] for v in cc["crosscheck"].values())
    w("1. **EMA definition B over-counts by about %.0f %% against EMA's own counts** "
      "(%+d on %d, 2015-2025, counted by opinion year). Resolved by PREREG v3 (a): "
      "the unit is the EPAR's own statement of new active substance status; B is a "
      "candidate list only. See the section 'EMA unit' for the effect and the "
      "unknown share per year. The 2021 EMA figure (54) still needs a manual check.\n"
      % (100.0 * dev / hl, dev, hl))
    # 2 scope
    w("2. **Scope: total pages in the universe.** Estimated from the sample mean pages "
      "per year and authority times the number of documents that year (FDA: drugs with "
      "a non-clinical document; EMA: drugs with a public EPAR). One document per drug "
      "only; n = 2 per stratum, so the figures are rough.\n")
    rows = []
    for au in ("FDA", "EMA"):
        recs = [r for s in samp if s["authority"] == au for r in s["picked"]]
        means = {}
        for s in samp:
            if s["authority"] == au and s["picked"]:
                means[s["year"]] = st.mean(r["pages"] for r in s["picked"])
        if au == "FDA":
            counts = {y: yc[y].get("nonclinical", 0) for y in yc}
        else:
            counts = {y: sum(1 for r in epar if r["year"] == y and r["report"])
                      for y in range(2015, 2027)}
        total, band = estimates.page_estimate(means, counts,
                                              st.stdev([r["pages"] for r in recs]), len(recs))
        n = sum(counts.values())
        rows.append([au, n, "%.0f" % (total / n), "%d" % round(total, -3),
                     "%d-%d" % (round(total - band, -3), round(total + band, -3))])
    w(table(["Authority", "Documents", "Mean pages per document", "Estimated pages",
             "Approx. +-2 SE range"], rows))
    tot = sum(int(r[3]) for r in rows)
    w("About %s pages in total for one non-clinical document per drug. Reading that "
      "volume with a model is large, so the coarse pre-filter allowed by extraction rule 4 "
      "(only if the pilot shows it loses no A findings) is needed.\n"
      % format(tot, ","))
    # 3 OCR
    w("3. **OCR.** Decided in PREREG v3 (c): every page below the threshold is OCR'd, "
      "all years and both agencies. The scope is in the section 'OCR scope'. OCR "
      "software is not installed yet and text quality after OCR is measured in the "
      "pilot.\n")
    # 4 power
    w("4. **Power for question 2** (one-sided z test, alpha 0.05, power 80 %, normal "
      "approximation; counts only). Before = approved 2015-2022, after = approved "
      "2024-2026 (2023 excluded). Counts are the universe (EMA: unit yes by approval year, "
      "PREREG v4; FDA: drugs on the novel list), not the analysable subset. With a low baseline and few "
      "expected events the approximation is rough.\n")
    nb_e = sum(ema_py[y] for y in range(2015, 2023))
    na_e = sum(ema_py[y] for y in (2024, 2025, 2026))
    nb_f = sum(yc[y]["listed"] for y in range(2015, 2023))
    na_f = sum(yc[y]["listed"] for y in (2024, 2025, 2026))
    rows = []
    for label, nb, na in (("EMA alone", nb_e, na_e), ("FDA alone", nb_f, na_f),
                          ("Combined", nb_e + nb_f, na_e + na_f)):
        for p0 in (0.02, 0.05, 0.10):
            d = estimates.min_detectable(p0, nb, na)
            dbl = estimates.power(p0, 2 * p0, nb, na)
            rows.append([label, nb, na, "%.0f %%" % (100 * p0),
                         ("%.1f %%" % (100 * d)) if d else "none",
                         ("%+.1f points" % (100 * (d - p0))) if d else "-",
                         "%.0f %%" % (100 * dbl)])
    w(table(["Group", "n before", "n after", "Assumed share before",
             "Smallest detectable share after", "Difference", "Power for a doubling"], rows))
    w("PREREG: if power is below 50 % for a doubling of the share, question 2 is "
      "reported as information only. The last column is that power.\n")
    # 5 missing
    w("5. **Still missing from Phase 0:** model speed and quality (measured in the "
      "pilot and, for a local model, on the second machine) and the choice of model. "
      "Token counts and API prices are in the section 'Cost'.\n")


def main():
    f = Fetcher()
    der = f.root / "derived"
    fdac = json.loads((der / "fda_counts.json").read_text())
    yc = {int(y): v["counts"] for y, v in fdac["years"].items()}
    epar = json.loads((der / "ema_epar.json").read_text())
    samp = json.loads((der / "sample.json").read_text())
    cc = json.loads((der / "ema_crosscheck.json").read_text())
    tab = ema.load_table(read_xlsx(f.get_bytes(ema.TABLE_URL)))
    nas, elog = ema.new_active_substances(tab)
    ema_py = ema.per_year(nas)
    out = []
    w = out.append
    w("# Phase 0 inventory\n")
    w("Counts, page numbers and text-layer share only; no outcome and no share of any "
      "codebook category has been seen. No document text was stored or printed. The only "
      "text-level steps are the per-page character count (text layer) and, for FDA "
      "Integrated Reviews, a yes/no test of bookmarks or heading-like lines for the "
      "section-title words non-clinical and pharmacology/toxicology. Generated by "
      "`studies/nam/inventory/report.py` from raw data kept outside the repository.\n")
    w("A text layer does not mean good text quality (scanned, redacted or edited "
      "reviews can still carry a text layer). Quality is measured in the pilot.\n")

    # FDA
    w("## FDA (CDER novel approvals 2015-2026; 2026 is a part year)\n")
    w("Universe: all drugs on CDER's yearly novel-approvals lists, including later "
      "withdrawn ones, joined to the Drugs@FDA data files on application number. "
      "Document titles come from the link flags of each approval-package TOC page "
      "(titles only). Non-clinical (PREREG v2) = Non-Clinical Review, "
      "Multi-Discipline Review or Integrated Review. Strict = the first two.\n")
    rows = []
    for y in range(2015, 2027):
        c = yc[y]
        rows.append([y, c["listed"], c.get("in_drugsatfda", 0), c.get("with_review_docs", 0),
                     c.get("toc_ok", 0), c.get("nonclinical", 0), c.get("strict_nonclinical", 0),
                     c.get("format_separate", 0), c.get("format_multidisc", 0),
                     c.get("format_integrated", 0)])
    tot = [sum(r[i] for r in rows) for i in range(1, 10)]
    rows.append(["all"] + tot)
    w(table(["Year", "Drugs", "In Drugs@FDA", "With review docs", "TOC read", "Non-clinical doc",
             "Strict", "Fmt separate", "Fmt multidisc", "Fmt integrated"], rows))
    w("Format per drug: integrated if an Integrated Review exists, else multidisc, "
      "else separate (priority fixed in `fda_titles.format_of`).\n")
    notread = {y: yc[y]["listed"] - yc[y].get("toc_ok", 0) for y in yc}
    w("Drugs without a read TOC (not in Drugs@FDA, no application number, no TOC, or "
      "dead TOC link) count as having no document in the 80 %% calculation: %s.\n"
      % ", ".join("%d: %d" % (y, n) for y, n in notread.items() if n))

    # repairs
    data = fda.load_datafiles(f.path_for(fda.DATAFILES_URL))
    products = fda.read_tsv(zipfile.ZipFile(f.path_for(fda.DATAFILES_URL)), "Products.txt")
    log = []
    for y in range(2015, 2027):
        raw = fda.parse_novel_page(fda.decode_body(f.path_for(fda.year_url(y)).read_bytes()))
        res = fda.resolve_rows(raw, y, products, data["applications"], data["submissions"])
        for r0, r in zip(raw, res):
            if r["notes"]:
                log.append((y, r0, r))
    w("### Repaired rows (%d)\n" % len(log))
    w("Rows where the list had no usable application number, name or date. "
      "The application number is filled from a unique name or active-ingredient match "
      "in Drugs@FDA (NDA/BLA, ORIG approval in the list year); an implausible list "
      "date is replaced by the Drugs@FDA ORIG approval date or left empty.\n")
    w(table(["Year", "No", "Name", "Repair", "Appl no", "List date", "Date used"],
            [[y, r0["no"], r0["name"] or "(empty)", "; ".join(r["notes"]), r["appl_no"],
              r0["approved"], r["approved"]] for y, r0, r in log]))
    pick = random.Random("20261023|repair-spotcheck").sample(log, 5)
    w("Spot check of 5 repaired rows (seed 20261023): the novel-approvals page row "
      "(ingredient, date) against the Drugs@FDA record of the matched application.\n")
    chk = []
    for y, r0, r in pick:
        ing = sorted({p["ActiveIngredient"] for p in products if p["ApplNo"] == r["appl_no"]})
        d = fda.orig_approval_date(data["submissions"], r["appl_no"]) if r["appl_no"] else None
        flat = lambda x: "".join(ch for ch in x.lower() if ch.isalnum())
        ok = (bool(ing) and flat(ing[0]) == flat(r0["ingredient"])
              and d is not None and d == r0["approved"])
        chk.append([y, r0["no"], r0["name"] or "(empty)", r0["ingredient"],
                    ing[0] if ing else "-", r0["approved"], d, "match" if ok else "NO MATCH"])
    w(table(["Year", "No", "Name", "Page ingredient", "Drugs@FDA ingredient",
             "Page date", "Drugs@FDA ORIG date", "Result"], chk))
    w("Comparison ignores case, spaces and punctuation. A mismatch would only mean the "
      "date or substance differs between the two sources; it does not change the counts above.\n")

    # EMA
    w("## EMA (medicines table, new active substances by definition B)\n")
    w("Table columns used: Category (Human), Medicine status, Active substance, "
      "Generic, Biosimilar, Marketing authorisation date (else European Commission "
      "decision date), Opinion adopted date, Medicine URL. The table has no "
      "new-active-substance column, so definition B (PREREG v2) is applied: human, "
      "authorised at some point, not generic, not biosimilar, and at least one "
      "normalised active substance not in an earlier human product. Later "
      "withdrawn products are included. Normalisation: lower case, no accents, "
      "split on ';', common salt and hydrate words removed.\n")
    rows = []
    for y in range(2015, 2027):
        e = [r for r in epar if r["year"] == y]
        n, d = claim80.ema_claim(e)[1:]
        rows.append([y, ema_py[y], n, d - n])
    rows.append(["all", sum(ema_py.values()), sum(r[2] for r in rows), sum(r[3] for r in rows)])
    w(table(["Approval year", "New active substances (B)", "With EPAR assessment report", "Without"], rows))
    w("Date field: marketing authorisation date is the source for %d of %d human rows "
      "with a date; the European Commission decision date is the fallback for %d "
      "(status authorised at some point). Where both dates exist (%d rows) the two "
      "differ in %d rows; the EC date is on or after the authorisation date in %d of "
      "them, so it looks like a later decision, which is an observation and not "
      "verified against EMA's column description. Unparsable dates: %d. Unknown "
      "statuses: %s. Rows without a substance: %d (empty in the source); parts made "
      "only of salt words are kept unchanged: %d row(s). Substances with same-day "
      "sibling products: %d (such ties count as new for both products, which "
      "inflates definition B). The %d fallback-dated rows (%s) may be dated too late if the EC "
      "date is a later decision; they are listed here and not removed.\n"
      % (elog["ma_sourced"], elog["human_with_date"], elog["date_from_ec"],
         elog["both_dates"], elog["ma_ec_differ"], elog["ec_on_or_after_ma"],
         elog["unparsable_dates"], elog["unknown_status"] or "none",
         elog["no_substance"], elog["salt_only_parts"], elog["same_day_siblings"],
         len(elog["ec_fallback_rows"]),
         "; ".join("%s %s %s" % tuple(x) for x in elog["ec_fallback_rows"])))
    w("### Cross-check against EMA annual overviews\n")
    w("EMA counts medicines recommended with a new active substance per opinion year "
      "(source: %s and the yearly overview PDFs). Definition B counted by opinion "
      "year is compared; deviations are logged, not corrected. The 2021 figure was "
      "read as 541 by the page reader and is taken as 54 (to be checked). The 2022 "
      "figure is EMA's update of 2026-03-03.\n" % HIGHLIGHT_URLS)
    rows = [[y, v["highlights"], v["b_by_opinion_year"], v["dev_opinion"],
             v["b_by_approval_year"]] for y, v in sorted(cc["crosscheck"].items(), key=lambda kv: int(kv[0]))]
    w(table(["Year", "EMA overview", "B by opinion year", "Deviation", "B by approval year"], rows))
    dev = [v["dev_opinion"] for v in cc["crosscheck"].values()]
    w("Definition B is above EMA's own count in %d of %d years (sum of deviations %+d). "
      "Likely causes (not yet examined row by row): duplicate or informed-consent "
      "applications, new combinations of known substances, substances authorised "
      "nationally before, and the opinion-to-approval timing.\n"
      % (sum(1 for x in dev if x > 0), len(dev), sum(dev)))
    w("Route from medicine to public assessment report: the table column "
      "`Medicine URL` gives the EPAR page; the page links to "
      "`/en/documents/assessment-report/<name>-epar-public-assessment-report_en.pdf`. "
      "Only a link of that name counts; other assessment-report links (for "
      "example variations) are ignored.\n")

    # sample
    w("## Page numbers and text layer (stratified sample)\n")
    w("Seed %d (not the pilot seed). 2 documents per year per authority. Text-layer "
      "threshold fixed before measurement: a page has a text layer at >= %d "
      "non-whitespace characters. FDA: non-clinical review (priority separate, "
      "multidisc, integrated), EMA: the EPAR public assessment report.\n"
      % (20261023, measure.TEXT_LAYER_MIN_CHARS))
    summ = []
    for au in ("FDA", "EMA"):
        recs = [r for s in samp if s["authority"] == au for r in s["picked"]]
        tp = sum(r["text_pages"] for r in recs)
        tt = sum(r["pages"] for r in recs)
        summ.append([au, len(recs), st.median([r["pages"] for r in recs]),
                     min(r["pages"] for r in recs), max(r["pages"] for r in recs),
                     "%.3f" % (tp / tt), sum(1 for r in recs if r["text_share"] < 0.9),
                     sum(1 for r in recs if r["text_share"] == 0),
                     "%.1f" % st.median([r["size_bytes"] / 1e6 for r in recs])])
    w(table(["Authority", "Docs", "Median pages", "Min", "Max", "Pooled text-layer share",
             "Docs < 0.9", "Docs with no text layer", "Median MB"], summ))
    label = {"pharmtox": "separate", "multidisc": "multidisc",
             "integrated": "integrated", "epar": "epar"}
    rows = [[r["authority"], r["year"], r["name"], label[r["format"]], r["pages"],
             "%.2f" % r["text_share"], "%.1f" % (r["size_bytes"] / 1e6),
             (r.get("nonclinical_section") or {}).get("verdict", "-") + (
                 "/" + r["nonclinical_section"]["basis"] if r.get("nonclinical_section") else "")]
            for s in samp for r in s["picked"]]
    w(table(["Authority", "Year", "Drug", "Format", "Pages", "Text share", "MB",
             "Non-clinical section (integrated only)"], rows))
    w("Drugs met in the draw order: without the document ('none') %d; unreadable "
      "package page or failed download ('error', logged and replaced) %d. FDA drugs "
      "left out of the draw because they are not in Drugs@FDA or have no application "
      "number: %d.\n"
      % (sum(len(s["none"]) for s in samp), sum(len(s["errors"]) for s in samp),
         sum(s.get("not_in_drugsatfda", 0) for s in samp)))
    w("The `Format` column here is the sampled document, chosen with the priority "
      "separate review, then multi-discipline, then integrated. The FDA table above "
      "gives the format of each drug with the priority integrated first. A drug with "
      "both a separate review and an Integrated Review therefore appears as "
      "'integrated' in the table but is sampled through its separate review, so "
      "integrated-format drugs are under-represented in this sample.\n")
    w("Known limitation: `run_sample` saves results per stratum, but a crash inside a "
      "stratum loses that stratum; a rerun is cheap because every download is cached.\n")
    w("Integrated Reviews: whether a non-clinical section exists was decided from PDF "
      "bookmarks, else heading-like lines (basis shown). 'yes' means a bookmark or "
      "heading with a section-title word was found; no text was read beyond that.\n")

    # terms
    w("## Terms for reuse and publication of derived data\n")
    w("- FDA: \"%s\" ([FDA website policies](%s)). Applies to fda.gov content 'unless "
      "otherwise noted'; the review PDFs are partly redacted agency documents and may "
      "contain third-party material. Derived data (coding, quotes, links) is not "
      "addressed explicitly.\n" % (FDA_TERMS_QUOTE, FDA_TERMS_URL))
    w("- EMA: \"%s\" ([EMA legal notice](%s)). Third-party material is excluded. "
      "Derived data is not addressed explicitly; acknowledging EMA as the source is "
      "required.\n" % (EMA_TERMS_QUOTE, EMA_TERMS_URL))
    w("Both permit reuse with attribution; whether quotes of reasonable length and "
      "coding tables count as permitted reuse is a reading of these terms, not a legal "
      "opinion.\n")

    # claim 80
    fs, fn, fd = claim80.fda_claim(yc)
    fs2, fn2, fd2 = claim80.fda_claim({y: c for y, c in yc.items() if y < 2026})
    es, en, ed = claim80.ema_claim(epar)
    w("## Requirement: public non-clinical document for >= 80 % of drugs\n")
    w(table(["Authority", "With document", "Drugs", "Share", "Met"],
            [["FDA (2015-2026)", fn, fd, "%.1f %%" % (100 * fs), "yes" if claim80.meets(fs) else "no"],
             ["FDA (2015-2025)", fn2, fd2, "%.1f %%" % (100 * fs2), "yes" if claim80.meets(fs2) else "no"],
             ["EMA (2015-2026)", en, ed, "%.1f %%" % (100 * es), "yes" if claim80.meets(es) else "no"]]))
    w("This measures that a document of the right type exists, not that it contains "
      "usable non-clinical content (redaction, scans). The FDA 2026 part year is "
      "included, and the %d FDA drugs without a read TOC count as missing. FDA counts Integrated Reviews "
      "(PREREG v2); on the strict definition the share is %.1f %%. EMA is based on "
      "the existence of the public assessment-report link on the medicine page; %d "
      "medicine pages could not be fetched and count as missing.\n"
      % (sum(yc[y]["listed"] - yc[y].get("toc_ok", 0) for y in yc),
         100 * sum(c.get("strict_nonclinical", 0) for c in yc.values()) / fd,
         sum(1 for r in epar if r["error"])))

    nas_epar = json.loads((der / "ema_nas_epar.json").read_text())
    layer1 = json.loads((der / "layer1.json").read_text())
    report_step2.ema_unit_section(w, nas_epar, cc)
    report_step2.layer1_section(w, layer1)
    fda_counts = {y: yc[y].get("nonclinical", 0) for y in range(2015, 2027)}
    ema_yes = {y: sum(1 for r in nas_epar if r["year"] == y and r["verdict"] == "yes")
               for y in range(2015, 2027)}
    ema_b = {y: sum(1 for r in epar if r["year"] == y and r["report"])
             for y in range(2015, 2027)}
    ema_yu = {y: sum(1 for r in nas_epar if r["year"] == y
                     and r["verdict"] in ("yes", "unknown")) for y in range(2015, 2027)}
    report_step2.cost_section(w, layer1, fda_counts, ema_yes, ema_b, ema_yu)
    report_step2.ocr_section(w, samp, layer1, fda_counts, ema_yes)
    open_section(w, yc, epar, samp, cc, ema_yes)
    sys.stdout.write("\n".join(out))


if __name__ == "__main__":
    sys.exit(main())
