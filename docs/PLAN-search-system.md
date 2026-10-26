# Plan: regulatory search system (no code yet)

Goal: a general, local search system over regulatory documents. The NAM study
(category A, PREREG v6) is the first corpus and the first user of the same
building blocks (`core/search.py` is the study-independent part).

## Design

- Page index: one row per page (document id, page number, normalized text,
  metadata) in SQLite with FTS5. Text normalization is
  `core.quotecheck._normalize`, so hits can be verified against page text.
- Browse and query: Datasette on the Pi, reached over Tailscale only (no public
  port). Read-only database file; the index is rebuilt from the corpus, never
  edited by hand.
- Claude access: Claude Code now (it reads the SQLite file and the pattern
  output files directly); an MCP server later, only after the read-only query
  surface is stable.
- Search lists: plain pattern files (one regex per line, optional label). Public
  lists live in the repo. Company-specific lists live in a private folder
  outside the repo and are never committed.

## Sources, in order

1. NAM corpus (FDA and EMA nonclinical assessments). Closed until the pilot
   verdict is in git HEAD (blinding rule in `CLAUDE.local.md` and DECISIONS).
2. FDA device documents: 510(k) summaries, De Novo decision summaries, PMA
   SSED.
3. FDA and EMA guidance documents.

Each source gets a corpus folder (PDFs plus `metadata.json` with a name) and a
note on where it was fetched and when. Read-only: public sources only, nothing
written back.

## Study 2 candidate: device demo

- Corpus: FDA 510(k) and De Novo summaries for calcium phosphate bone void
  fillers.
- Questions: which predicates are cited, and which preclinical tests are
  reported.
- Measure: time saved against a manual review of the same documents.
- Company-specific search lists live in a separate private repo, not here.

## Rules that carry over

- Only public documents in the shared index; private lists and results stay
  outside the repo.
- Every excerpt shown must come from the page text it is attributed to.
- A corpus without `metadata.json` is refused; the NAM corpus is refused until
  the verdict (`studies/nam/pilot/VERDICT.md` in git HEAD) exists.

## Open questions

- Chunking: whole page as one FTS row, or windows around hits (as in PREREG v6)?
- How to keep the Datasette copy in sync with the Pi data folder.
- Which fields of `metadata.json` are common to all sources.

## Known issues

- `core/search.py` requires NAM_DATA to be set also outside the NAM study (it
  is how the NAM data folder is recognised). Resolved when `core/` moves to its
  own repo.
