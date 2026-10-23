# Decisions

## 2026-10-23: Reject matches negated just before the quote

Quote check rejects a match when a negation word appears within 3 tokens
before it and not in the quote. Reason: a shortened quote can drop "no"/"not"
and reverse the meaning; preferring a false "not found" over a false "found"
(fail closed).

## 2026-10-23: Sentence boundary ends the negation window

The window before a match stops at a token ending in . ; : ! ? (that token is
not counted). Reason: a negation in the previous sentence does not negate the
quote, and "No adverse effects were seen. The NOAEL ..." must not reject valid
quotes. Cost: abbreviations such as "Fig." shorten the window.

## 2026-10-23: Extended negation list including "non-"

Added fail, fails, failed, unable, nothing, nobody, nowhere, and tokens that
start with "non-" count as the negation "non". The exact path now also
compares negations in the whitespace-widened span, not only digits. Reason:
the prefix reverses the meaning in nonclinical texts ("non-toxic" vs
"toxic").

## 2026-10-23: Phase 0 started before 2026-11-01

Phase 0 started before 2026-11-01. It runs on the Pi only, does not touch the screening chain or the second machine, and sees no outcomes (counts, pages and text-layer only).

## 2026-10-23: Integrated Review counts as non-clinical document (FDA)

Integrated Reviews count as non-clinical documents. Document format (separate
review / multidisciplinary / integrated) is recorded per drug. In the sample,
for each Integrated Review it is recorded whether it has a non-clinical
section, from PDF bookmarks or headings only. Reason: FDA moved to Integrated
Reviews around 2020-2021, so format and period cannot be separated.

## 2026-10-23: EMA definition of new active substance (definition B)

Human, has a marketing authorisation date, Generic = No, Biosimilar = No, and
at least one normalised active substance not present in an earlier human
product in the EMA table. Later withdrawn products are included. Cross-checked
against EMA "Human medicines highlights" per year; deviations are logged.
Reason: the EMA table has no new-active-substance column.

## 2026-10-23: EMA date field

Approval date = Marketing authorisation date, else European Commission
decision date. The number of rows where the two differ is logged.

## 2026-10-23: PREREG version 2

PREREG.md version 2 added under "Changes" (text as approved): Integrated
Reviews as non-clinical, format per drug, EMA-only result for question 2 is
the one interpreted as evidence of changed practice, EMA definition fixed.

## 2026-10-23: PREREG version 3

PREREG.md version 3 added under "Changes" (text as approved): EMA unit by the
EPAR statement of new active substance status, layer 1 pre-filter by
non-clinical section, OCR for all pages below the threshold, cost from token
counts. Added before any outcome was seen.

## 2026-10-23: Layer 1 and layer 2 pre-filter, blinding

Layer 1 passes only the pages of the non-clinical section, located from
bookmarks or heading-like lines with the section-title words of outline.py
(`section.py`). It uses no codebook word and sees no outcome. A separate
non-clinical review is the section as a whole; if the section is not found the
whole document is passed and logged. Layer 2 (keyword filter) is allowed only
if the pilot shows it loses no A findings (extraction rule 4). Reason: about
204,000 pages is too much to read, and a title-based cut cannot depend on
the outcome.

## 2026-10-23: EMA unit from the EPAR statement

A definition-B candidate counts only if the EPAR public assessment report has a
sentence naming the CHMP or the Committee, a conclusion verb and "new active
substance", without a negation before the phrase (`epar_nas.py`, rule
version 1, fixed before counting). Output per drug is yes, no or unknown; only
page and sentence numbers are stored. Unknown is excluded and reported per
year. If unknown is more than 10 % of the candidates in any year, work stops
and the positions of unmatched occurrences are reviewed; the rule may only be
changed in a new commit before the next run. Reason: definition B is 16 %
above EMA's own counts.

## 2026-10-23: Data limit 5 GiB

The fetch cap is raised from 2 to 5 GiB for the EPAR reports (disk has 36 GB
free). Everything stays on the Pi and outside the repository.

## 2026-10-23: EPAR rule version 2 and wider link rule

Rule version 1 left 153 of 568 candidates unknown (27 %), above the 10 % stop
rule in every year. Diagnostics (booleans and counts only) showed that few
conclusion sentences name the CHMP, that applicant statements share the
phrase, and that most negations in conflicting reports stood far from the
phrase. Version 2 (chosen from those diagnostics and not from agreement with
EMA's counts, which had not been computed): the CHMP is not required; the
applicant words (applicant, requested, claim, declared, indicated) exclude a
sentence; a negation counts only within 4 tokens before the phrase;
"known active substance" anywhere is a no-signal; the last conclusion match
decides; a no-signal together with a positive match gives unknown. Link rule:
the original rule keeps priority; fallback tiers accept the "-0" suffix, names
without "epar-" or without "public-", and the usual public-assessment-report
name in another folder; variation reports never count. Of the 11 candidates
without a link, 10 are found; Evkeeza stays unknown.

## 2026-10-23: EPAR rule version 2.1

Rule version 2 left 74 of 568 candidates unknown (13 %), above 10 % in 9 of 12
years. Version 2.1 (chosen from sentence wording, not from the comparison with
EMA's counts, which had been seen after version 2): a negation within 2
tokens before a conclusion verb also makes a match negative (in addition to
4 tokens before the phrase), so "did not consider that X is a new active
substance" is a no; a conclusion sentence decides over the "known active
substance" no-signal, which gives "no" only when the report has no conclusion
sentence (combination products such as valsartan with sacubitril). The
far-negation limitation is removed from KNOWN-LIMITATIONS. PREREG version 4
records that no further rule changes are made; primary EMA unit is yes only,
unknown included is a sensitivity analysis.

## 2026-10-23: Layer 1 section finder, numbered match first

First run on the 48 sample documents: unnumbered title matches were mostly
cover, signature and contents lines (sections of one page and 250 characters).
Rule added using page numbers and counts only: a numbered match beats an
unnumbered one, then the shallowest, then the earliest. Separate non-clinical
reviews (format "pharmtox" in the sample) are the section as a whole. All 48
sections were found; three FDA sections of one page (Qulipta, Welireg,
Pombiliti) are flagged as short and are to be checked by page number. Layer 1
sees no codebook word and no outcome.

## 2026-10-23: OCR for every page below the threshold, all years

OCR is applied to every page below 100 characters, in all years and for both
agencies (PREREG v3 c); the earlier open choice to exclude FDA 2015-2017 or
accept lower recall is dropped. Only the scope is measured (sample pages below
the threshold, projected to the universe, whole document and layer 1 section);
no OCR has been run and no OCR software is installed.

## 2026-10-23: Cost from token counts after layer 1

Cost is estimated as characters / 4 over the layer 1 section, with low-text
pages imputed by the median characters per text page of the same authority.
Prices are the Anthropic list prices fetched 2026-10-23 (two Anthropic pages
agree); input only, output and instruction text are not included. The pages
give no token quota for Claude Code Pro, so the number of sessions is shown
only under assumed capacities. Model speed and quality are measured in the
pilot; for a local model only tokens are given.
