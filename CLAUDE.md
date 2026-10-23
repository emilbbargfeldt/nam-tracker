# nam-tracker

## Purpose

Measure how often FDA- and EMA-approved drugs mention animal-free methods
(NAMs) in their public nonclinical assessments, using LLM extraction with
verified quotes.

## Rules

- Read-only: only read public sources; never modify or write back to them.
- Quote verification: every extracted quote must pass `core.quotecheck.verify_quote`
  against the source page text before it is counted.
- Nothing sensitive in the repo: no secrets, credentials, hostnames, absolute
  paths or IP addresses. Machine-specific notes go in `CLAUDE.local.md`
  (gitignored).
- Test before commit: the pre-commit hook must pass (gitleaks, denylist, pytest).
- Never push.
- Code and comments in English, ASCII only.
