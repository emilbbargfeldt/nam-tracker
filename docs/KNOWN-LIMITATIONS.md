# Known limitations

Unresolved findings from independent review, and why they are accepted.
Fixed in the code: ASCII-only source, large-page speed, min_ratio validation,
hook failure handling, digit and negation checks, hyphenation variants,
Unicode normalization.

## quotecheck

- **Candidate search uses 8-character k-grams.** Fuzzy candidates are located
  through shared 8-character substrings (shorter for quotes under 8
  characters). A quote with no intact 8-gram on the page is reported as not
  found, even if its overall ratio would pass. Accepted: this keeps large
  pages fast, and the error direction is a false "not found", which is the
  safe one for verified quotes.
- **Sampled windows.** Windows start at multiples of n/20 and have three sizes
  (n, 0.9n, 1.1n), so a true match can fall between them and be missed. Same
  safe error direction; accepted for speed over an exact approximate-substring
  algorithm.
- **Case sensitivity.** Matching is case-sensitive. Accepted: a differing case
  is rare in extracted quotes, and the miss is a false "not found". Negation
  words are compared case-insensitively.
- **Ratio is length-relative.** Short or long quotes can differ in a few
  characters and still pass. The digit and negation checks cover the most
  harmful cases (numbers, polarity); other single-word substitutions (for
  example a different drug name) can still pass at a low min_ratio. Mitigation:
  choose a high min_ratio.
- **Exact matches use whole-token boundaries only at the quote edges.** A quote
  that starts or ends at a non-alphanumeric character can still sit inside a
  longer phrase. Digit tokens are checked against the whole surrounding word
  (so "10" does not match "10.5" or "10,000").
- **Truncated quotes.** A quote that stops before a trailing "not" still
  matches exactly ("The effect was" in "The effect was not seen"); see
  "Negation after the quote" below. Quotes should be full sentences or clauses.
- **Negation false alarms.** "No." in "Study No. 5" or "Nor-" in
  "Nor-epinephrine" count as negations and can cause a false "not found"
  (safe direction). On the exact path negations are compared on the
  whitespace-widened span too; a quote that contains the same word, such as
  "Study No. 5", still matches.
- **Normalization gaps.** NFKC turns a vulgar fraction into "1/2" with a
  fraction slash and a superscript into a plain digit ("10" + superscript 2
  becomes "102"). U+2060, U+200E and U+200F are not stripped. Accepted; revisit
  when real pages show them.
- **min_ratio = 1.0 means exact only** (after normalization); the fuzzy path
  is skipped.
- **Candidate cap.** At most 300 candidate windows (best by k-gram votes) and
  50 positions per k-gram are examined, which bounds time on repetitive text
  and very long quotes. On highly repetitive pages a true match can be missed
  (safe direction). Timing: 200k-char page, long quote, a few seconds.
- **Negation after the quote is not checked.** A quote cut off before a
  trailing "not" still passes ("The effect was" in "The effect was not seen").
- **Negation 4 or more tokens before the match is not seen.** The window is
  3 tokens ("did not, in the end, show toxicity" passes for "show toxicity").
- **Abbreviations shorten the window.** A token ending in . ; : ! ? ends the
  window, so abbreviations ("e.g.", "Fig.", "No.")
  cut it short and a negation before them is missed (unsafe direction).
- **Negations are compared as sets.** One "not" in the quote hides a
  different "not" earlier in the matched place or before it
  ("was not seen; effect was not toxic" passes for "effect was not toxic").
- **"non-" counts as the negation "non"**, also in "non-clinical". A page
  "non-clinical" with a quote "clinical ..." is rejected (safe direction).
  "Nonclinical" without hyphen is not a negation.
- **Negation scope.** Only the listed negation words and the "non-" prefix
  are compared; other polarity changes (for example "free of", "unremarkable")
  are not detected.
- **Digit tokens must match exactly**, so OCR damage inside a number makes the
  quote fail even if the rest matches. Accepted: wrong numbers must not pass.

## Tests and hook

- **pytest runs on the working tree**, not on the staged content. A commit can
  pass with tests that differ from what is staged. Accepted: stashing in a hook
  is riskier than the gap.
- **Commit messages are not scanned** by the denylist, and NAM_DENYLIST can be
  overridden from the environment (used by the tests).
- **Pure renames and mode changes** to a non-ASCII file name produce diff lines
  without a leading "+", so the ASCII check misses them (the denylist scan
  still sees them). Rare; accepted.
- **Denylist scan covers text diffs only.** Binary files are blocked outright,
  but file names are only seen through the diff headers.
- **Mutant coverage is partial.** The meta-tests cover always-true,
  always-false, no normalization, no empty-quote check, no digit check, no
  negation check, no check for negation before the match, no sentence
  boundary, the old negation list, no "non-" prefix and no negation compare on
  the exact path; not every possible defect.

## EPAR new-active-substance rule (version 2)

- **Negation window is 4 tokens.** "The CHMP cannot agree that X is a new
  active substance" counts as positive because "cannot" is 6 tokens before the
  phrase. Accepted by design (version 1 let any earlier negation count and
  produced many conflicts); the error direction is a false "yes".
- **"known active substance" anywhere is a no-signal.** It also fires in
  unrelated contexts (for example a known active substance used as a
  comparator). With a positive conclusion in the same report the verdict is
  unknown, otherwise "no".
- **Last conclusion wins.** A late sentence about a different substance in the
  same report (combination products) can decide the verdict.
- **Applicant words exclude a sentence** even when the CHMP agrees in the same
  sentence ("the applicant claimed ..., which the CHMP considers correct").
  That sentence is not a match; the verdict then relies on other sentences.
- **Link rule.** A medicine page whose initial assessment report is filed only
  under variation reports (Evkeeza) has no EPAR link and is unknown.
- **Far negations give false "yes".** "The CHMP did not consider that X is a
  new active substance" is positive ("not" is 5 tokens back), as is "cannot
  agree". "no" and "without" are not in the negation list ("no new active
  substance" is positive).
- **Only the first phrase of a sentence is classified.** "X is a new active
  substance, whereas Y is not a new active substance" is positive.
- **"well-known active substance"** also matches the no-signal.
- **Tier 4 of the link rule accepts the variation-report folder** when the file
  is named like the public EPAR (Tuzulby); other variation-style names never
  count in fallback tiers. Evkeeza's initial report is filed only under a
  variation-style name and is left unknown.

