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
