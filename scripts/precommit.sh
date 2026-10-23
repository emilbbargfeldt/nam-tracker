#!/usr/bin/env bash
# Pre-commit checks: gitleaks, denylist scan of staged diff, pytest.
# Any finding blocks the commit. The denylist content is never printed.
set -u

ROOT="$(git rev-parse --show-toplevel)" || exit 1
cd "$ROOT" || exit 1
DENYLIST="${NAM_DENYLIST:-$HOME/.config/nam-tracker/denylist}"

# (a) gitleaks on staged changes. Older versions (v8.1x) use "protect --staged",
# newer ones use "git --staged".
if ! command -v gitleaks >/dev/null 2>&1; then
    echo "precommit: gitleaks not found" >&2
    exit 1
fi
if gitleaks git --help >/dev/null 2>&1; then
    gitleaks git --staged --redact --no-banner || { echo "precommit: gitleaks found leaks" >&2; exit 1; }
else
    gitleaks protect --staged --redact --no-banner || { echo "precommit: gitleaks found leaks" >&2; exit 1; }
fi

# (b) denylist scan of the staged diff. Any failure to read the denylist or
# the diff blocks the commit. Blank lines and CR are dropped: an empty
# pattern would match every line.
if [ ! -f "$DENYLIST" ]; then
    echo "precommit: denylist file missing, commit blocked" >&2
    exit 1
fi
if [ ! -r "$DENYLIST" ]; then
    echo "precommit: denylist file unreadable, commit blocked" >&2
    exit 1
fi
PATTERNS="$(/usr/bin/grep -v '^[[:space:]]*$' "$DENYLIST" | tr -d '\r')"
if [ $? -gt 1 ] || [ -z "$PATTERNS" ]; then
    echo "precommit: denylist empty or unreadable, commit blocked" >&2
    exit 1
fi
DIFF="$(git -c core.quotepath=off diff --cached)" || { echo "precommit: git diff failed" >&2; exit 1; }
if printf '%s\n' "$DIFF" | /usr/bin/grep -F -i -q -f <(printf '%s\n' "$PATTERNS"); then
    echo "precommit: staged diff matches the denylist (match not shown)" >&2
    exit 1
fi

# (b2) staged changes must be ASCII only (bytes, any locale; file names too)
if printf '%s\n' "$DIFF" | LC_ALL=C /usr/bin/grep -a -P '^\+' | LC_ALL=C /usr/bin/grep -a -q -P '[^\x00-\x7F]'; then
    echo "precommit: non-ASCII characters in staged changes" >&2
    exit 1
fi

# (b3) no binary files (numstat shows "-" for binary)
NUMSTAT="$(git -c core.quotepath=off diff --cached --numstat)" || { echo "precommit: git diff failed" >&2; exit 1; }
if printf '%s\n' "$NUMSTAT" | /usr/bin/grep -q -P '^-\t-\t'; then
    echo "precommit: binary file in staged changes, commit blocked" >&2
    exit 1
fi

# (c) tests
if [ -x .venv/bin/pytest ]; then
    .venv/bin/pytest -q || { echo "precommit: tests failed" >&2; exit 1; }
else
    echo "precommit: .venv/bin/pytest not found" >&2
    exit 1
fi
