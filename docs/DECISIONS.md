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
