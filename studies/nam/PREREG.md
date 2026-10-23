# NAM-tracker: pre-registration

Approved: 2026-10-23 (Emil Bargfeldt). Version 1.

**Status: pre-registered before any document was downloaded.** Changes after approval need a new
dated version under "Changes", a written reason, and must not be chosen from results.

## Questions

1. **Descriptive (primary):** What share of new drugs approved by the FDA (CDER, new molecular
   entities and new therapeutic biologics) and the EMA (new active substances) have a public
   non-clinical assessment that mentions data from advanced human in vitro models (category A)?
   Per approval year.
2. **Change (secondary):** Is the share higher for drugs approved after the FDA Modernization
   Act 2.0 (signed 2022-12-29) than before?
3. **Descriptive (secondary):** Which animal species and other method categories (B-D) are used,
   and how often is the omission of a standard animal study justified?

Expectation written before data: the effect of the law is small or not yet measurable, because
non-clinical studies are usually done years before approval. Question 2 is mainly a baseline.

## Known limits (written before data)

- IND applications are not public; most NAM use is there. Only approved drugs are measured.
- Public reviews are redacted and incomplete. "Not mentioned" does not mean "not used".
- No judgement of whether a method was good or decisive for approval; only whether it is
  mentioned as a data source.

## Codebook (locked; examples are added in the pilot, categories do not change)

Unit: one drug at first approval as a new active substance. The same substance at FDA and EMA is
coded separately and linked.

| Code | Category | Included | Excluded |
|---|---|---|---|
| A | Advanced human in vitro models | Organoids, spheroids and other 3D cultures; organ-on-chip / microphysiological systems; iPSC-derived cells (e.g. cardiomyocytes) | Plain 2D cell lines |
| B | In silico as evidence | PBPK used to omit a study or set a dose instead of a study; QSAR outside ICH M7 | QSAR for impurities under ICH M7 (routine) |
| C | Routine in vitro | hERG, Ames, in vitro chromosome aberration, receptor binding, 2D cytotoxicity | - |
| D | Omitted animal study | A standard animal study is omitted with an explicit reason (NAM, weight of evidence, or no relevant species) | Studies that are simply not mentioned |
| S | Animal species | Rat, mouse, dog, minipig, rabbit, non-human primate, other | - |

Primary outcome: A mentioned as a data source (yes/no) per drug.

## Extraction rules (locked)

1. The language model only reads values; it never judges the drug. The prompt contains only the
   document text.
2. Every finding has file name, page and verbatim quote. `core/quotecheck.py` checks that the
   quote is on that page: similarity >= 0.95 after normalisation, and every token containing a
   digit and every negation word must match exactly. Findings without a verified quote are
   rejected.
3. No finding = "not mentioned", never "no".
4. A keyword pre-filter before the model is allowed only if the pilot shows it loses no A findings.
5. Approval date from the agency, not the document date.

## Accuracy (reference independent of the model)

- Pilot: 30 drugs drawn at random (seed 20261101), stratified: at least 10 EMA, at least 10 FDA,
  at least 10 approved after 2022.
- Emil first codes 15 of them himself without seeing the model output; then they are compared.
  The other 15 are checked against the model's quotes.
- Requirements per drug for category A: sensitivity >= 90 %, specificity >= 95 %, 0 quotes that
  are not in the document.
- If the pilot fails, extraction may be improved on these 30, but is approved only on 30 new
  drugs (new seed, logged).

## Phase 0: inventory (no coding, no shares seen)

- Sources: Drugs@FDA (approval packages, pharmacology/toxicology and multi-discipline reviews),
  FDA lists of novel approvals per year, EMA EPAR data and lists of new active substances.
- Per year and agency: number of drugs, share with a public non-clinical section, share needing
  OCR, typical page count.
- Licence and reuse terms (FDA, EMA), including publication of derived data.
- Cost: time and model usage per document, measured on 3 documents outside the pilot.
- **Model choice** (local model, Claude, or a combination) is decided here from the pilot
  requirements and cost, not from results.
- **Power:** with Phase 0 counts per period, the minimum detectable difference for question 2
  (80 % power, alpha 0.05) is computed and written down before Phase 2.

Period: approved 2015 to 2026. Before = approved before 2023-01-01; after = approved 2024-01-01 or
later (2023 excluded as transition year).

**Go criteria (locked):** public non-clinical section for >= 80 % of drugs per agency, terms that
allow publishing derived data, and projected usage that fits within at most 3 months without
blocking other work. If only one agency meets them, continue with that agency.

## Analysis and reporting

- Questions 1 and 3: descriptive tables and figures per year and agency with 95 % intervals. No
  verdict.
- Question 2: logistic regression of A (yes/no) on period (before/after) with agency as covariate;
  one-sided p < 0.05.
- If power is below 50 % for a doubling of the share, question 2 is reported as information only.
- The dataset (coding, quotes, links to sources) is published if terms allow; otherwise coding and
  links only.
- Ongoing updates: new approvals are coded with the locked codebook and extraction version. Any
  change is a new dated version, and earlier years are recoded with it.

## Order

1. Approved 2026-10-23.
2. Repo skeleton built 2026-10-23 (no data). From 2026-11-01: Phase 0 inventory ->
   `docs/INVENTORY.md`.
3. Emil decides on continuing by the go criteria; model choice and power are written in.
4. Pilot (30 drugs) and accuracy check.
5. Full coding, analysis, publication.

## Changes

- 2026-10-23 version 1: first approved version. Before approval: numbers and negations must match
  exactly in the quote check; repo skeleton built before approval (no data).
