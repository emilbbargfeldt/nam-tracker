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

## 2026-10-23: Layer 1 takes all title-matched sections (one rule)

Integrated Reviews keep a short non-clinical summary in the main body and the
detailed non-clinical assessment in a later section/appendix; layer 1 takes all
title-matched sections. The numbered-first rule is dropped. Diagnosis of the
three short sections (Qulipta, Welireg, Pombiliti), from heading lines and page
numbers only: the end rule was right in all three (a sub-heading does not end a
section, the next heading at the same or a higher level does). The cause was
the start choice. In Qulipta and Pombiliti the numbered match was sub-section
5.1 of one page; in Welireg it was a labelling-table line ("13. Nonclinical")
chosen over the section heading on page 32.

Rule, the same for every format except separate reviews (the whole document):
the section is the union of every title match; table of contents lines do not
count; a bookmark title over 90 characters does not count (the same limit as
heading lines; a first run with the union let one long cover bookmark in
Pemazyre run to the last page, 202 of 202 pages). Each match ends at the next
heading at the same or a higher level (bookmarks: same or shallower; headings:
numbered, first number at most one higher), for an unnumbered heading at the
next heading beginning with "Clinical", else at the last page. Overlapping and
adjacent ranges are merged. Result on the 48 sample documents: 15 changed,
none under 3 pages, none not found; section pages 1,899 to 2,263 of 8,943
document pages (FDA 1,502 to 1,838, EMA 397 to 425); Qulipta 1 to 101,
Welireg 1 to 52, Pombiliti 1 to 83; estimated input 20.7 M to 25.8 M tokens.
Known cost: signature and team lists with a title word add one or two pages
each. Layer 1 sees no codebook word and no outcome.

## 2026-10-23: Pilot draw (seed 20261101)

30 drugs, drawn from the unit lists of Phase 0: FDA = drugs on CDER's novel
approvals lists with a non-clinical document (priority separate review, then
multi-discipline, then Integrated Review; the year is the list year), EMA =
drugs whose EPAR states new active substance status ("yes" only, PREREG v4).
Quotas: at least 10 EMA, at least 10 FDA, at least 10 approved after 2022 (year
2023 or later). The sorted candidates are shuffled with
`random.Random(20261101)` and taken in that order as long as the quotas stay
reachable (`studies/nam/pilot/draw.py`). The phase 0 sample documents are not
excluded. Result: 13 EMA, 17 FDA, 10 from 2023 or later; no FDA candidate
without a document was met in the draw order. `pilot.json` is committed before
any extraction. The same substance at FDA and EMA is coded separately
(Loargys is in the pilot twice).

## 2026-10-23: Emil's blind coding of 15 pilot drugs

15 of the 30 are chosen with the derived seed string `20261101|coder`, with at
least 5 EMA and 5 FDA among them (result: 6 EMA, 9 FDA), marked `coder` in
`pilot.json`. `coding_template.csv` has one row per drug and the columns drug,
agency, year, A, B, C, D (yes/no), A_pages, B_pages, C_pages, D_pages, species
(semicolon list), species_pages, notes. For each drug the layer 1 pages are
written to one PDF in `$NAM_DATA/pilot/emil/` (488 pages in all, none over 150
pages; Vyvgart is only 2 pages, the shortest section). The remaining 15 are
checked against the model's quotes (PREREG, accuracy). PREREG is not changed:
A is the pre-registered plan.

## 2026-10-23: Blinding of pilot extraction

Extraction on the pilot drugs may run, but the output is saved only in
`$NAM_DATA/extract/` and is not shown, summarised or counted (not even the
number of findings or rejected quotes) until Emil's 15 codings are committed.
The tool prints only done, skipped or quota per chunk. Reason: the model output
must not influence the reference coding. The rule is also in `CLAUDE.local.md`.

## 2026-10-23: Model and call: Claude Code headless on Pro, no tools

Extraction uses `claude -p` (Claude Code on the Pro plan, no API key) with the
model set explicitly to `claude-sonnet-5-5`; the chunk is sent on stdin and the
answer is read as JSON (`--output-format json`, structured output with
`--json-schema`). Flags checked against `claude --help` (version 2.1.309): all
built-in tools off (`--tools ""`), no MCP servers (`--strict-mcp-config`), no
skills (`--disable-slash-commands`), no settings files (`--setting-sources ""`),
no saved session (`--no-session-persistence`), the system prompt replaced
(`--system-prompt`). `--bare` is not used because it switches off the login of
the Pro plan. The working directory is an empty folder, so no CLAUDE.md is
read. The model is chosen from the pilot requirements and cost (input list price
about 0.50 times Opus), not from results; it is a choice for the pilot, and a
failed pilot may change it (PREREG, accuracy). One smoke call on a made-up
two-page text confirmed the flags and the answer format: a good structured
answer has `stop_reason` "tool_use", so success is decided by subtype success,
no error, terminal reason completed and a `structured_output` with the right
fields; only `max_tokens` is a cut-off answer.

## 2026-10-23: Extraction input, prompt and quote check

The input is the layer 1 pages with absolute page numbers (`=== Page N ===`).
The system prompt is fixed reading rules plus the codebook table (A-D and S)
read verbatim from PREREG.md; its hash is stored. It holds no drug name,
agency or year. Output is a list of {code, page, quote}. Every finding is
checked with `core.quotecheck.verify_quote` (0.95) against the page it names
(code in A-D or S, page inside the chunk, non-empty quote); rejected findings
are kept in `rejected.jsonl` with the reason and never counted. Text comes from
the text layer; OCR is not installed, so low-text pages give little text until
it is (PREREG v3 c).

## 2026-10-23: Chunks, idempotence, errors and logging

Sections are split into chunks of at most 200,000 characters (about 50,000
tokens at 4 characters per token) with one page of overlap; a page above the
limit is a chunk of its own. Output per chunk is saved in
`$NAM_DATA/extract/<prompt hash>/<document>/` and not run again (the chunk text
hash is stored; a changed text is run again). A call that is cut off, not valid
JSON, incomplete, malformed or failed is status "error": it is logged, the chunk
is not saved as done and is run again next time; it never counts as an empty
list (only a complete answer with an empty list means nothing found). A usage or
rate limit stops the run with status "quota" and no half file; the run resumes
where it stopped. Per call `calls.jsonl` has time, document, chunk, model, Claude
Code version, prompt hash, chunk hash, tokens (usage), model time, wall time,
status and the error class. Duplicates from the overlap are removed on (code,
page, quote).

## 2026-10-23: Title words: Pharmacology Toxicology without a separator

Vyvgart (pilot, Integrated Review) had only two layer 1 pages (5.1 on page 30
and 7.1 on page 48, each a one-page sub-section that ends on the same page at
the next heading). The bookmarks show why: the detailed section is appendix 13,
"Pharmacology Toxicology: Additional Information and Assessment" (pages 96-102),
and the title words of `outline.py` required "/", "and" or "&" between the two
words. The end rule was right; the title words were too narrow. The pair may now
be joined by "/", ",", "-", "and", "&" or only a space; "Pharmacology" or
"Toxicology" alone and "Clinical Pharmacology" do not match. These are section
title words, not codebook words. Effect on the 48 sample documents, from page
numbers only: 6 Integrated Reviews gain the appendix (for example Vonjo 6 to
41 pages, Voyxact 5 to 21), nothing else changes; section pages 2,263 to
2,385. The earlier yes/no verdicts for a non-clinical section of Integrated
Reviews were all yes and are not rerun. Vyvgart now has 10 layer 1 pages (30,
48, 96-103); the 15 pages of Emil's material were regenerated (652 pages in
all, none over 150), the pilot list is unchanged.

## 2026-10-23: Smoke test with the final prompt

One call with the final `prompt.py` and `build_argv` on a made-up three-page
document (`studies/nam/extract/smoke.py`): status done, 3 findings accepted,
0 rejected, codes A, C and S as expected, no finding on the page without a
finding. Output is in `$NAM_DATA/extract/smoke/`.

## 2026-10-23: OCR for layer 1 pages below the threshold; pilot count

Pages below 100 non-blank characters inside layer 1, counted for the 30 pilot
drugs (numbers only): 137 pages in 12 drugs. EMA: Reagila 2, Refixia 2,
Elzonris 3. FDA: Praxbind 25, Strensiq 24, Doptelet 21, Augtyro 30, Loargys 14,
Izervay 12, Vyvgart 2, Palynziq 1, Accrufer 1. The other 18 have none.

OCR (`studies/nam/extract/ocr.py`) renders such a page with `pdftoppm` (300 dpi,
grey) and reads it with `tesseract` (English), command line only. The text of
each page is kept in `$NAM_DATA/ocr/` and made once; OCR text replaces the text
layer only if it is longer. Per document `ocr.json` records the tesseract
version, dpi, language, the low pages and the replaced pages. OCR text is the
page text the model sees and that quotes are checked against. If a document has
low pages and OCR is missing or fails, the tool does not extract that document
("skipped: pages need OCR"), and the run ends with a non-zero code. A failed
OCR command is never stored as an empty page; an empty result for a blank page
is valid. Tests use a mocked `pdftoppm` and `tesseract` and a mutant (OCR not
applied, missing tesseract ignored); one test with the real tools is skipped
until tesseract is installed.

## 2026-10-23: OCR run on the pilot drugs (numbers only)

Tesseract 5.5.0 (English) was installed and the test with the real tools
passes. OCR of the layer 1 pages below 100 characters of the 30 pilot drugs:
137 pages, 132 replaced by OCR text, 7 still below 100 characters after OCR
(Praxbind 3, Strensiq 1, Palynziq 1, Accrufer 1, Izervay 1; all other drugs
0). The 7 were not read; they may be blank or nearly blank pages. Emil's PDFs
are page images and do not change with OCR. Pilot extraction requires the flag
`--blind`; without it the tool stops.

## 2026-10-26: Layer 2 keyword filter introduced (PREREG version 5)

The pilot extraction (full model reading of layer 1 for the pilot drugs,
about 5 % of the universe's layer 1 tokens) used one week of the plan's
usage quota, which breaks the Phase 0 cost criterion. Layer 2 is a local
keyword search (`studies/nam/extract/keywords.py`, codes A, B, C, D, S) that
selects candidate pages; the model reads only those. PREREG version 5 records
the design and the sensitivity requirement for A.

The first draft of the list used "[- ]" as separator. Before this commit it was
replaced by SEP = "[-\u2010\u2011\u2013\s]?" (optional), because the
quotecheck normalization joins words split by a hyphen at a line end
("organ-<newline>on-a-chip" becomes "organon-a-chip") and PDF text also splits
words at line ends without a hyphen. Gaps in A were closed at the same time
(3D, iPS, iPS-CMs, cardiomyocyte, CiPA, air-liquid interface, ALI, ex vivo
human, human explants, "<word> chip"). B, C, D and S changed only in the
separator. Tests: known answers per code, per-pattern tests for A, A in 11
spelling forms, two mutants (A list empty; rigid separator "[- ]" checked per
pattern), pin tests on `core.quotecheck._normalize`, and an ASCII check of the
file.

Unicode hyphens and dashes (U+2010, U+2011, U+2013) and the soft hyphen (U+00AD)
are already handled by the quotecheck normalization, which runs before
matching. The Unicode characters in SEP are therefore defence in depth, and a
rigid separator cannot be caught by those forms (documented in a test). U+00AD
was checked and is removed by the normalization, so it was not added to SEP.

Review before commit found quadratic backtracking in \w+SEPchips?\b (20,000
chars: 8.2 s); quantifier bounded to \w{1,40}. Same coverage for real words.
A timing test runs all patterns on 20,000 characters of "a", "a-", "a " and
"chip" repeated (limit 0.5 s).

No outcome has been seen. The pilot extraction output in `$NAM_DATA/extract/`
has not been viewed, counted or evaluated; it stays blinded until Emil's 15
blind codings are committed.

## 2026-10-26: Layer 2 run (candidate pages)

`studies/nam/extract/candidates.py` runs keywords.py per layer 1 page (text
layer, plus OCR text from the cache where it is longer; no OCR is started, no
network) and writes only page numbers and counts per document and code to
`$NAM_DATA/candidates/`: one JSONL file per document, `manifest.json` (md5 of
keywords.py, PREREG version, git HEAD, time, aggregates) and
`missing_text.jsonl`. Page numbers are 1-based as in layer 1. The pilot drugs
are skipped; stdout shows "pilot skipped: N of 30", and a normal run with N
below 30 stops before any candidate file is written (error shows N only). `--pilot` runs only if coding_template.csv in git HEAD (not the
working copy) has A-D exactly 0 or 1 for all 15 coder drugs (errors name row
and column, never the value). Blind coding values: 1 = mentioned, 0 = not
mentioned. the result goes to
`$NAM_DATA/candidates_pilot/` and nothing about it is printed. stdout shows
aggregates only: documents, layer 1 pages, candidate pages (union of the
codes), tokens lower and upper, share of pages without text, documents without
layer 1 text. Documents without a PDF or with missing OCR are logged, not
errors.

Tokens = chars/4 (same method as 27.3 M, which also used whitespace-folded
characters); manifest shows a lower bound (raw candidate pages) and an upper
bound (+ imputed tokens for all low-text pages without OCR, as if all become
candidates; imputation = median over documents of the mean characters per text
page, same authority, pooled if the authority has none). Phase 0 cost is judged on the upper bound. The run is repeated
after OCR has been run on the full set (after 2026-10-31). No outcome has been seen.

## 2026-10-26: Scope to category A (PREREG v6); search building blocks

Keyword candidates covered 82 % of layer 1 pages, so PREREG version 6 reduces
the scope to the primary outcome: the model reads only A windows (+-10 lines
around each A hit, overlapping windows merged, a window near a page edge
continuing onto the adjacent layer 1 page); category S is recorded by keyword
only; B, C and D are dropped from this version. Blind coding covers A only
(1 = mentioned, 0 = not mentioned); the `--pilot` guard in candidates.py
requires A = 0 or 1 for all 15 coder drugs in git HEAD and ignores B-D.
`candidates.py --v6-tokens` prints one pair of token bounds (lower, upper) for
the window design, writes nothing, and is refused with `--pilot`; unknown
options stop the run.

`core/search.py` is the study-independent page search (corpus = PDFs plus
metadata.json, pattern file, JSONL output, counts on stdout). A NAM corpus is
refused by metadata name, by path (symlinks resolved; NAM_DATA must be set) and
without the flag `--nam-after-pilot-verdict`, which in turn needs
`studies/nam/pilot/VERDICT.md` in git HEAD. Tested on artificial data only.
The plan for the wider system is in `docs/PLAN-search-system.md` (no code yet).
Known limits: a direct call of `search_corpus` with a custom verdict function
bypasses the guard (convention); any non-empty VERDICT.md in HEAD unlocks it.

No outcome has been seen; only aggregate counts across all codes were viewed.


## 2026-10-26: Fetcher limits; blind coding doubt rule

The data cap of the fetcher is raised from 5 GiB to 15 GiB (the 500 FDA PDFs
missing from the cache are estimated at about 7 GB), and the fetcher now also
stops when free space on the filesystem of the data directory is below 10 GiB.
Both limits are tested with artificially low values.

Blind coding doubt rule: code by best judgement (0/1); write UNSURE: <reason>
in notes. The pilot reports A sensitivity with and without UNSURE rows; the
requirement applies to all rows.

## 2026-10-26: Codebook clarifications before unblinding

Claude chat saw some layer 1 text from pilot documents while Emil asked about
model types; it gave general rules only, no codes. Not A: in vivo animals incl.
knockout/transgenic/xenograft; unspecified 'in vitro'/'cells'/'tissues';
microbial culture systems (chemostat, hollow-fiber, biofilm); standard
genotoxicity battery (Ames, 2D micronucleus/chromosome aberration, in vivo
micronucleus); 3T3 NRU phototoxicity; recombinant enzymes; engineered 2D cell
lines; ion channel panels in transfected cells; isolated animal cardiomyocytes.
A: organoids incl. PDO; spheroids/3D cultures; organ-on-chip/MPS; iPSC-derived
cells incl. cardiomyocytes; reconstructed human tissue incl. 3D skin
micronucleus and 3D skin phototoxicity. Redacted sections coded on visible text
only. Emil coded all 15 himself.

## 2026-10-26: PREREG version 7 (sensitivity measurement for category A)

All 15 pilot codings are A = 0, so A sensitivity cannot be measured on them.
PREREG version 7 measures it on two separate sets: (a1) the first 10 known
positives Emil finds with an external search engine (queries and date
committed before extraction), coded by Emil, and (a2) spike-ins from 20 PubMed
abstracts drawn at random (seed committed; 4 per MeSH term; Emil codes each,
only A = 1 used; if fewer than 20 are A = 1, batches of 5 are drawn
and coded with the same seed until 20 are A = 1 or 60 are drawn), inserted in
test copies of random non-pilot documents. Sensitivity on a2 is measured at
the keyword step and as an A finding whose verified quote overlaps the
inserted abstract text on the spiked page; drug relevance is not assessed.
Spike pages are chosen only among layer 1 pages that are not A candidates
before the insertion, so a hit cannot be due to existing text. The requirement of >= 90 % applies to each set;
specificity and unverified quotes are measured on the 15 pilot drugs.
Limitations: a1 is partly circular (term-based search), the MeSH term choice
for a2 was proposed by Claude chat, a2 tests wording only. keywords.py is not
changed on the basis of the spike-ins before the result is reported. Running the pipeline on
a separate document directory is a separate change, not yet made. No pilot
extraction output has been viewed or counted.

## 2026-10-26: Spike-in coding rule (reviews)

Spike-in coding: reviews or general overviews of a technology without a
concrete in vitro experiment are coded 0 (background mention). Rule made
explicit after row 26; rows 1-25 re-checked by Emil against it; changed rows
are marked 'revised: review rule'.

Spike-in coding rules made explicit during coding: (1) reviews or general
overviews of a technology without a concrete in vitro experiment are coded 0
(background mention); (2) reports that only generate and characterize a model
or product (e.g. iPSC lines, implants, grafts, cell sources for therapy)
without using it as an in vitro test system are coded 0; (3) agents used only
to differentiate or build a model are not a test; (4) background statements
about earlier in vivo work do not affect the code. Rows coded before a rule
was made explicit were re-checked by Emil; changed rows are marked 'revised:
<rule>'. The re-check resulted in no changes.

Spike-in set outcome: 4 batches (40 abstracts) were drawn and coded under the
fill rule; 21 have A = 1 and all 21 are used, from all drawn batches, with no
exclusions.

## 2026-10-26: Spike-in code details (PREREG v7 a2)

Eligible pages are layer 1 pages with a text layer (at least 100 non-blank
characters) that are not A candidates. Documents that cannot be read or have no
eligible page are skipped in seed order; this is the only text-dependent part of
the selection, so pages with little text are unreachable. A keyword find also
requires an A hit in the inserted text itself. A model find requires an A
finding on the spiked page whose verified quote lies at least 50 % inside the
inserted text (PREREG v8); every occurrence of the quote on the page is checked, and a
fuzzy match is located by its best cluster of matching blocks. The run writes
totals only (totals.json), not per-spike results, and refuses if keywords.py or
the extraction prompt changed since prepare. Prepare refuses with uncommitted
changes under studies, tests or docs, and the cache is read only (nothing is
fetched). A window is sent as one prompt without chunking.

## 2026-10-26: PREREG version 8 (a1 by local term search; 50 % rule)

Known positives (a1) are no longer found with an external search engine: a
Google search gave few and noisy hits, while a local full-text search of the
layer 1 text is reproducible and runs on the study universe itself. Emil's
terms are in a committed file (a1_terms.txt); keywords.py is not used. One
draw per document (a document uniformly among those with a hit, then one hit
page uniformly), unit = the drawn page, and the script shows no counts. For
a2, the model step counts as found only if at least 50 % of the quote lies
inside the inserted abstract text, because a one-character overlap or a
generic phrase in the inserted text could otherwise count as found. Fill
rule for a1: 10 more documents per batch while fewer than 10 are A = 1, at
most 50 draws; a batch is only drawn if the codes of the earlier batches are
committed.
The a1 search matches the terms literally (case-insensitive, any whitespace
between words); hyphenated line breaks, ligatures and hyphen/space variants are
not matched, which only narrows the universe the draw is taken from. The hit
index is rebuilt on every run and stored nowhere; a later batch is refused if
the search result differs from that of the earlier batches.

## 2026-10-26: Pilot extraction of the old design archived unopened

The pilot extraction made with the full layer 1 design (before PREREG v5 and
v6) is archived unopened as $NAM_DATA/extract_v5_fulllayer1 (moved from
$NAM_DATA/extract). 112 files. Run 2026-10-23 to 2026-10-26, prompt hash
f15802f1f9e6 (the same as the current prompt), model claude-sonnet-5-5 (Claude
Code 2.1.309 and 2.1.310), design: whole layer 1 in chunks of at most 200,000
characters. A sha256 list of every file is in
$NAM_DATA/extract_v5_fulllayer1.sha256 (sha256 of the list file:
20b5d683e4a4b6fed479d1c450080eb5fa73c3c201fb29204453343f35a97df1); the list and
the folder are write-protected and were verified against the list after the
move. The content has not been opened, shown, summarised or counted. It is kept
as the v5(c) reference: candidate pages must contain every A finding of the full
layer 1 model extraction already run. A new pilot extraction (v6 windows) goes
to a new $NAM_DATA/extract, so the old chunks cannot be overwritten.

## 2026-10-27: a1 terms and matching rule

a1 terms: Emil's own (organoid, spheroid, organ on a chip, 3D culture, b-TCP,
hydrogel, a-TCP, bioreactor); three added by Claude chat with Emil's approval
(iPSC-derived, induced pluripotent stem cell, reconstructed human epidermis).
The file (11 terms) is committed as a1_terms.txt.

Matching rule of a1_draw.py (replaces the literal rule of the PREREG v8 entry
above, before any a1 search was run): core's text normalization (NFKC, dash
variants, invisible characters, whitespace) on terms and text, lower case,
Greek letters as names; hyphen, space and line break are the same separator
(organ on a chip = organ-on-a-chip, 3D culture = 3D-culture), a hyphen at a
line end is also tried as hyphenation (organ-/oid = organoid); a first token a,
b, g or d followed by a hyphen also matches alpha, beta, gamma, delta, and the
reverse, with a boundary on the left (b-TCP = beta-TCP, not sub-TCP). Terms
match inside longer words (organoid in organoids, iPSC-derived in
hiPSC-derived); a soft hyphen at a line end is hyphenation. Not matched: terms
written without a separator (bTCP), and variants that are not in the term file
(organs-on-chips, organ-chip, iPSCs-derived, iPS-derived, three-dimensional
culture, beta-tricalcium phosphate); the independent review of the matching
listed these as limits of the term file, not of the rule.

## 2026-10-27: a1 term variants

Spelling variants of Emil's terms suggested by the independent review, added
before any draw was seen; first draw stopped unseen. Added (7): organs on
chips, organ chip, iPSCs, iPS-derived, three-dimensional culture,
beta-tricalcium phosphate, alpha-tricalcium phosphate. The term file now has 18
terms.

## 2026-10-28: a1 coding, tables of contents

Decided during batch 1, before any counting: a page that is a table of
contents is coded A = 0 (it is not a data source on that page), with the note
"TOC".

## 2026-10-28: a1 pool has fewer than 30 documents with term hits, so batch 3 cannot be a full batch.

Rule (set before batch 3 is drawn; reason is the pool size, not the count of A=1): a1 ends at >=10 A=1, 50 draws, or when the pool is exhausted. Batch 3 = all remaining documents (fewer than 10).

## 2026-10-29: Pilot run lock (model, OCR precondition, combination of a1/a2)

Set before the pilot extraction is run and before any outcome was seen.

(a) Model. The pilot uses model claude-sonnet-5-5 with the frozen prompt
(studies/nam/extract/prompt.py) and keywords.py. A change of model is a new
pilot (rule set in this entry, not in PREREG). The a1 pool is exhausted (28 of
28 drawn; 10 + 10 + 8 draws, commits 3e79ed1, c5614d1, 49ece01); how a1 and
spike-ins are handled in any new pilot is decided in a new PREREG version
before that pilot is run and logged before any outcome of that pilot is seen.

(b) OCR precondition. The pilot is run only after OCR (extract/ocr.py,
tesseract, cached) has been run on every layer 1 page below the text-layer
threshold (100 non-blank characters) in all three parts: the 30 pilot drugs
(PREREG, section Pilot; 15 blind-coded, 15 checked against quotes), (a1) the 28 coded
a1 documents, and (a2) the documents that receive spike-ins. Counts before
OCR, layer 1 pages without text: pilot drugs 137 (already OCR'd, see the
entries of 2026-10-23 above, so unchanged; of the 137, 132 were replaced by
OCR text and 7 are still under 100 characters after OCR, and the two groups
overlap by 2 pages (derived: 132 + 7 - 137), i.e. replaced but still short), a2 documents 172 of 1574 pages (local measurement, not in git)
(21 spike-in abstracts, provisional placement in 21 distinct documents from
the current cache, counted 2026-10-29; placement depends on the OCR cache), a1 documents 371 of 2452 pages (28 documents; local measurement, not in git). Spike-in placement
(spikein prepare) is made after OCR, so the pilot matches the real pipeline.
The page counts are re-measured after OCR and logged as aggregates.

(c) Combination. PREREG v8 (b) already states that the requirement is
sensitivity >= 90 % on a1 and, separately, >= 90 % on a2.
This is followed unchanged: a1 and a2 are each tested against 90 % with exact
binomial confidence intervals for their own n. A pooled a1+a2 figure may be
reported as a supplement, but has no pass/fail status.
