"""INVENTORY sections for the second Phase 0 step: EMA unit via the EPAR
statement, layer 1 (section finder), token cost and OCR scope.

Counts, page numbers and character counts only; no document text.
"""
import random
import statistics as st
from collections import Counter

from . import cost, measure, section

UNKNOWN_STOP = 0.10  # stop rule: unknown above this share in any year
PRICE_SOURCE_NOTE = cost.SOURCE
# Tokens per Claude Code Pro five-hour session are NOT published (the pricing
# page says there is no fixed message count); these are labelled assumptions.
PRO_SESSION_ASSUMPTIONS_MTOK = (1, 3, 10)


def a(s):
    return str(s).encode("ascii", "replace").decode()


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(a(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def ema_unit_rows(recs, highlights, b_by_opinion):
    """Per year: candidates, yes/no/unknown and the opinion-year comparison."""
    rows = []
    for y in range(2015, 2027):
        yr = [r for r in recs if r["year"] == y]
        c = Counter(r["verdict"] for r in yr)
        n = len(yr)
        op_yes = sum(1 for r in recs if r["verdict"] == "yes"
                     and r.get("opinion_year") == y)
        op_unk = sum(1 for r in recs if r["verdict"] == "unknown"
                     and r.get("opinion_year") == y)
        rows.append({"year": y, "n": n, "yes": c["yes"], "no": c["no"],
                     "unknown": c["unknown"],
                     "unknown_share": c["unknown"] / n if n else 0.0,
                     "yes_by_opinion": op_yes,
                     "yes_unknown_by_opinion": op_yes + op_unk,
                     "highlights": highlights.get(y),
                     "b_by_opinion": b_by_opinion.get(y)})
    return rows


def stop_years(rows):
    return [r["year"] for r in rows if r["unknown_share"] > UNKNOWN_STOP]


def unknown_reason(r):
    if r.get("error"):
        return "no report or error"
    if r["unmatched"]:
        return "phrase present, no qualifying sentence"
    return "phrase absent from the report"


def spot_text(r):
    """Positions only: the decisive match, else the first occurrences."""
    if r["matches"]:
        m = r["matches"][-1]
        return "decisive p%d s%d (%s)" % (m["page"], m["sentence"], m["polarity"])
    if r["known"]:
        return "known-signal p%d s%d" % (r["known"][0]["page"], r["known"][0]["sentence"])
    if r["unmatched"]:
        return "phrase at " + ", ".join("p%d s%d" % (m["page"], m["sentence"])
                                        for m in r["unmatched"][:3])
    return "none"


def ema_unit_section(w, recs, cc):
    hl = {int(y): v["highlights"] for y, v in cc["crosscheck"].items()}
    bop = {int(y): v["b_by_opinion_year"] for y, v in cc["crosscheck"].items()}
    rows = ema_unit_rows(recs, hl, bop)
    w("## EMA unit: new active substance status from the EPAR (PREREG v3 a, v4)\n")
    w("Rule `epar_nas.py` version 2.1, committed before the run (versions 1 and 2 were "
      "revised after the 10 %% unknown stop rule; see DECISIONS): a sentence with "
      "'new active substance', a conclusion verb (consider, qualif, conclud, agree) "
      "and no applicant word (applicant, requested, claim, declared, indicated) is a "
      "conclusion match; it is negative if a negation stands within 4 tokens before "
      "the phrase or within 2 tokens before a verb. The last conclusion match in "
      "document order decides (yes/no); with no conclusion sentence, 'known active "
      "substance' anywhere gives no; otherwise unknown. Primary EMA unit: yes only "
      "(PREREG v4); unknown is a sensitivity analysis. Only the verdict and page and "
      "sentence numbers were stored. Rule version in the data: %s.\n"
      % sorted({str(r["rule"]) for r in recs}))
    body = []
    for r in rows:
        body.append([r["year"], r["n"], r["yes"], r["no"], r["unknown"],
                     "%.0f %%" % (100 * r["unknown_share"])])
    tot = [sum(r[k] for r in rows) for k in ("n", "yes", "no", "unknown")]
    body.append(["all"] + tot + ["%.0f %%" % (100 * tot[3] / tot[0])])
    w(table(["Approval year", "B candidates", "yes", "no", "unknown", "Unknown share"],
            body))
    bad = stop_years(rows)
    w("Stop rule (unknown above %d %% in any year): %s. PREREG v4 records that no "
      "further rule changes are made.\n"
      % (100 * UNKNOWN_STOP, ("TRIGGERED for " + ", ".join(map(str, bad))) if bad
         else "not triggered"))
    comp = Counter(unknown_reason(r) for r in recs if r["verdict"] == "unknown")
    w("What the unknown candidates are (PREREG v4 states that they are mainly EPARs "
      "that do not reproduce the CHMP conclusion; this table is the count behind "
      "that statement, the wording of those reports has not been read):\n")
    w(table(["Unknown because", "Candidates"], sorted(comp.items())))
    cmp_rows, s_hl, s_b, s_y, s_u = [], 0, 0, 0, 0
    for r in rows:
        if r["highlights"] is None:
            continue
        s_hl += r["highlights"]
        s_b += r["b_by_opinion"]
        s_y += r["yes_by_opinion"]
        s_u += r["yes_unknown_by_opinion"]
        cmp_rows.append([r["year"], r["highlights"], r["b_by_opinion"],
                         "%+d" % (r["b_by_opinion"] - r["highlights"]),
                         r["yes_by_opinion"],
                         "%+d" % (r["yes_by_opinion"] - r["highlights"]),
                         r["yes_unknown_by_opinion"],
                         "%+d" % (r["yes_unknown_by_opinion"] - r["highlights"])])

    def tot_cell(x):
        return x, "%+d (%+.0f %%)" % (x - s_hl, 100 * (x - s_hl) / s_hl)
    if s_hl:
        cmp_rows.append(["2015-2025", s_hl, *tot_cell(s_b), *tot_cell(s_y), *tot_cell(s_u)])
    w("Comparison with EMA's own counts by CHMP opinion year (candidates counted by "
      "their opinion date; %d candidates have no opinion date and are in no row, "
      "which lowers yes and unknown). The comparison with EMA's counts was first seen "
      "after rule version 2.\n" % sum(1 for r in recs if not r.get("opinion_year")))
    w(table(["Year", "EMA overview", "B", "B deviation", "yes", "yes deviation",
             "yes + unknown", "yes + unknown deviation"], cmp_rows))
    rng = random.Random("20261023|epar-spotcheck-v2.1")
    pick = []
    for v in ("yes", "no", "unknown"):
        pool = [r for r in recs if r["verdict"] == v]
        pick += [(v, r) for r in rng.sample(pool, min(5, len(pool)))]
    spot = [[v, r["name"], r["year"], r["report"] or r["url"], spot_text(r)]
            for v, r in pick]
    w("Spot check (seed 20261023): look up the page and sentence number in the report "
      "(sentences counted per page from 1, split after . ; ! ? before a capital "
      "letter). 'decisive' is the last conclusion match.\n")
    w(table(["Verdict", "Drug", "Approval year", "EPAR", "Position"], spot))
    only_known = sum(1 for r in recs if r["verdict"] == "no" and not r["matches"])
    w("Verdicts 'no' that rest on the known-signal alone (no conclusion sentence): "
      "%d of %d.\n" % (only_known, sum(1 for r in recs if r["verdict"] == "no")))
    return rows


def layer1_section(w, recs):
    w("## Layer 1: non-clinical section of the sample (PREREG v3 b)\n")
    w("Located by bookmarks, else heading-like lines, with the section-title words of "
      "`outline.py`; a numbered match beats an unnumbered one (cover and signature "
      "pages carry unnumbered matches; added after a first run, from page numbers "
      "only). Separate non-clinical reviews are the section as a whole. Characters "
      "are counted with whitespace folded. 'Low' = pages in the section below the "
      "text-layer threshold (%d characters). Short sections (under 3 pages) are "
      "marked: they may be right (integrated reviews are brief) or a heading found "
      "next to its successor; they are not corrected and should be checked by page "
      "number.\n" % measure.TEXT_LAYER_MIN_CHARS)
    label = {"pharmtox": "separate"}
    rows = [[r["authority"], r["year"], r["name"], label.get(r["format"], r["format"]),
             r["pages"], r["section_pages"], "yes" if r["found"] else "no", r["basis"],
             "%d-%d" % (r["start"], r["end"]), r["chars"], r["low_text_pages"],
             "short" if r["section_pages"] < 3 and r["basis"] != "document type" else ""]
            for r in recs]
    w(table(["Authority", "Year", "Drug", "Format", "Pages", "Section pages", "Found",
             "Basis", "Pages (from-to)", "Characters", "Low", "Flag"], rows))
    fmt = section.found_share([dict(r, format=label.get(r["format"], r["format"]))
                               for r in recs], "format")
    bas = section.found_share(recs, "basis")
    w("Found by format:\n")
    w(table(["Format", "Found", "Documents", "Share"],
            [[k, v[0], v[1], "%.0f %%" % (100 * v[0] / v[1])] for k, v in sorted(fmt.items())]))
    w("Documents by basis:\n")
    w(table(["Basis", "Documents", "Share of all"],
            [[k, v[1], "%.0f %%" % (100 * v[1] / len(recs))] for k, v in sorted(bas.items())]))
    for au in ("FDA", "EMA"):
        rs = [r for r in recs if r["authority"] == au]
        w("%s: median section %.0f of %.0f pages; sections of integrated/multidisc/"
          "epar documents (excluding whole-document cases): median %.0f pages.\n"
          % (au, st.median(r["section_pages"] for r in rs),
             st.median(r["pages"] for r in rs),
             st.median([r["section_pages"] for r in rs
                        if r["basis"] != "document type"] or [0])))


def cost_section(w, layer1, fda_counts, ema_yes_counts, ema_b_counts, ema_yu_counts):
    w("## Cost: input tokens after layer 1 (PREREG v3 d)\n")
    w("Tokens = characters / %d, over the located section only (whole document when "
      "not found). Low-text pages are imputed with the pooled median characters per "
      "text page of the same authority. Projection = stratum mean times documents "
      "that year; n = 2 per stratum, so the +-2 SE bands are rough and do not cover "
      "the choice of one document per drug. EMA documents = drugs with unit 'yes' "
      "(sensitivity: yes plus unknown, PREREG v4; upper bound: all B candidates with an "
      "EPAR). Local model: tokens only, "
      "speed is measured later on the second machine.\n" % cost.CHARS_PER_TOKEN)
    rows, totals = [], {}
    for au, counts_list in (("FDA", [("FDA", fda_counts)]),
                            ("EMA", [("EMA (unit yes)", ema_yes_counts),
                                     ("EMA (yes + unknown)", ema_yu_counts),
                                     ("EMA (all B with EPAR)", ema_b_counts)])):
        recs = [r for r in layer1 if r["authority"] == au]
        per = cost.median_text_page_chars(recs)
        for label, counts in counts_list:
            tot, band = cost.project(
                recs, counts, lambda r: cost.tokens(cost.effective_chars(r, per)))
            totals[label] = tot
            rows.append([label, sum(counts.values()), "%.0f" % per,
                         "%.1f M" % (tot / 1e6),
                         "%.1f-%.1f M" % ((tot - band) / 1e6, (tot + band) / 1e6)])
    w(table(["Authority", "Documents", "Median chars per text page (imputation)",
             "Input tokens", "Approx. +-2 SE"], rows))
    both = totals["FDA"] + totals["EMA (unit yes)"]
    w("FDA plus EMA (unit yes): %.1f M input tokens.\n" % (both / 1e6))
    biggest = max(cost.tokens(cost.effective_chars(
        r, cost.median_text_page_chars([x for x in layer1 if x["authority"] == r["authority"]])))
        for r in layer1)
    w("Claude API list prices, USD per million tokens (source: %s). Haiku 5.5 is "
      "priced by prompt length (0.10 up to 100,000 tokens per prompt; 0.50 above). "
      "The largest sampled section (low-text pages imputed) is %.0f tokens, %s "
      "Batch processing is 50 %% cheaper on the same page.\n"
      % (PRICE_SOURCE_NOTE, biggest,
         "above that threshold, so the Haiku figure is a lower bound." if biggest > 100000
         else "below that threshold; a document outside the sample may not be, and "
              "then the Haiku figure is a lower bound."))
    price_rows = []
    for m, p in cost.INPUT_USD_PER_MTOK.items():
        price_rows.append([m, "%.2f" % p,
                           "%.0f" % cost.price_usd(totals["FDA"], p),
                           "%.0f" % cost.price_usd(totals["EMA (unit yes)"], p),
                           "%.0f" % cost.price_usd(both, p),
                           "%.0f" % (cost.price_usd(both, p) * cost.BATCH_DISCOUNT)])
    w(table(["Model", "Input USD/MTok", "FDA USD", "EMA USD", "Total USD",
             "Total USD, batch"], price_rows))
    w("Input only. Output tokens (the extracted findings and quotes) and the "
      "instruction text per request are not included; output costs %s USD/MTok for "
      "Haiku/Sonnet/Opus respectively, so a few findings per drug add little next to "
      "the input.\n"
      % "/".join("%.2f" % v for v in cost.OUTPUT_USD_PER_MTOK.values()))
    w("Claude Code Pro: the pricing page states that Claude Code is included in Pro, "
      "shares the plan's usage limits, that limits reset on a rolling five-hour "
      "window, and that there is no fixed message count. **No token quota per session "
      "is published, so the number of sessions cannot be derived from a source.** "
      "Under assumed capacities (assumptions, not facts) the total input of %.1f M "
      "tokens would need:\n" % (both / 1e6))
    w(table(["Assumed input tokens per five-hour session", "Sessions"],
            [["%d M" % m, "%.0f" % (both / 1e6 / m)] for m in PRO_SESSION_ASSUMPTIONS_MTOK]))
    return totals


def ocr_section(w, sample, layer1, fda_counts, ema_counts):
    w("## OCR scope (PREREG v3 c)\n")
    w("Pages below the text-layer threshold (%d characters), measured in the stratified "
      "sample and projected to the universe as stratum mean times documents that year "
      "(n = 2 per stratum, rough). 'Whole' = all pages of the sampled document; "
      "'Section' = pages inside the layer 1 range. No OCR has been run. EMA documents "
      "= drugs with unit 'yes'.\n" % measure.TEXT_LAYER_MIN_CHARS)
    sec = {(r["authority"], r["year"], r["name"]): r for r in layer1}
    recs = []
    for s in sample:
        for r in s["picked"]:
            l1 = sec[(r["authority"], r["year"], r["name"])]
            recs.append({"authority": r["authority"], "year": r["year"],
                         "pages": r["pages"],
                         "low_whole": cost.low_pages_whole(r, measure.TEXT_LAYER_MIN_CHARS),
                         "low_section": l1["low_text_pages"],
                         "section_pages": l1["section_pages"]})
    rows = []
    for au, counts in (("FDA", fda_counts), ("EMA", ema_counts)):
        rs = [r for r in recs if r["authority"] == au]
        for y in range(2015, 2027):
            ys = [r for r in rs if r["year"] == y]
            n = counts.get(y, 0)
            if not ys:
                continue
            lw = st.mean(r["low_whole"] for r in ys)
            ls = st.mean(r["low_section"] for r in ys)
            pg = st.mean(r["pages"] for r in ys)
            rows.append([au, y, n, "%.0f" % pg, "%.0f %%" % (100 * lw / pg),
                         "%.0f" % (lw * n), "%.0f" % (ls * n)])
    w(table(["Authority", "Year", "Documents", "Mean pages", "Low share (whole)",
             "Low pages whole (projected)", "Low pages in section (projected)"], rows))
    out = []
    for au, counts in (("FDA", fda_counts), ("EMA", ema_counts)):
        rs = [r for r in recs if r["authority"] == au]
        tw, bw = cost.project(rs, counts, lambda r: r["low_whole"])
        ts, bs = cost.project(rs, counts, lambda r: r["low_section"])
        out.append([au, "%.0f" % tw, "%.0f-%.0f" % (tw - bw, tw + bw),
                    "%.0f" % ts, "%.0f-%.0f" % (ts - bs, ts + bs)])
    w(table(["Authority", "Whole: pages", "Whole: approx. +-2 SE", "Section: pages",
             "Section: approx. +-2 SE"], out))
    w("Scope is the OCR load if layer 1 is applied first (Section) or not (Whole). "
      "Pages inside the section of a document whose section was not found count "
      "as the whole document.\n")
