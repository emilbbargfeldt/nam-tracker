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
