# nam-tracker

Measures how often FDA- and EMA-approved drugs mention animal-free methods
(new approach methodologies, NAMs) in their public nonclinical assessments.
Mentions are extracted with an LLM, and every extracted quote is verified
against the source page text.

## Status

Pre-registration, no data yet.

## Structure

- `core/` - shared code (quote verification in `core/quotecheck.py`)
- `studies/nam/` - the NAM study (pre-registration to be added)
- `docs/` - documentation
- `tests/` - pytest suite
- `scripts/` - helper scripts (`precommit.sh`)

## Development

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.lock.txt
    .venv/bin/pytest -q

### Pre-commit hook

`scripts/precommit.sh` runs, on staged changes only: gitleaks, a denylist
scan of `git diff --cached`, and pytest. Any finding blocks the commit.
The denylist is a local file, one fixed string per line, read from
`~/.config/nam-tracker/denylist` (override with `NAM_DENYLIST`). It is never
committed; if it is missing, the commit is blocked.

Install the hook as a symlink:

    ln -sf ../../scripts/precommit.sh .git/hooks/pre-commit
