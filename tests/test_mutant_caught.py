"""Meta-test: the suite must fail against deliberately broken verify_quote versions."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

_PATCH = "import core.quotecheck as q\n{patch}\nverify_quote = q.verify_quote\n"
MUTANTS = {
    "always_true": (
        "def verify_quote(page_text, quote, min_ratio):\n    return True\n",
        {"test_quote_not_on_page", "test_changed_number_is_rejected"},
    ),
    "always_false": (
        "def verify_quote(page_text, quote, min_ratio):\n    return False\n",
        {"test_exact_match", "test_match_across_line_break"},
    ),
    "no_normalization": (
        _PATCH.format(patch="q._normalize = lambda text, keep_hyphen=False: text"),
        {"test_match_across_line_break", "test_ligature_matches"},
    ),
    "no_empty_quote_check": (
        _PATCH.format(patch="q._check_nonempty = lambda quote: None"),
        {"test_empty_quote_raises"},
    ),
    "no_digit_check": (
        _PATCH.format(patch="q._digits_ok = lambda quote, span: True"),
        {"test_changed_number_is_rejected"},
    ),
    "no_negation_check": (
        _PATCH.format(patch="q._negations_ok = lambda quote, span: True"),
        {"test_missing_negation_in_quote_is_rejected",
         "test_extra_negation_in_quote_is_rejected"},
    ),
}


@pytest.mark.parametrize("name", sorted(MUTANTS))
def test_mutant_is_caught(name, tmp_path):
    source, expected = MUTANTS[name]
    (tmp_path / "mutant_quotecheck.py").write_text(source)
    env = dict(os.environ, NAM_QUOTECHECK_MODULE="mutant_quotecheck",
               PYTHONPATH=str(tmp_path) + os.pathsep + str(ROOT))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rf", "-p", "no:cacheprovider",
         str(ROOT / "tests" / "test_quotecheck.py")],
        env=env, capture_output=True, text=True, cwd=str(tmp_path),
    )
    assert result.returncode != 0, result.stdout
    failed = {re.sub(r"\[.*", "", m) for m in
              re.findall(r"^FAILED \S*::(\S+)", result.stdout, re.M)}
    assert expected <= failed, (expected - failed, result.stdout)
    print("MUTANT %s caught by: %s" % (name, ", ".join(sorted(failed))))
