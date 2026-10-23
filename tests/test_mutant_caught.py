"""Meta-test: the suite must fail against deliberately broken verify_quote versions."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _mutated_source(old, new):
    text = (ROOT / "core" / "quotecheck.py").read_text()
    assert old in text, old
    return text.replace(old, new, 1)


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
    "no_negation_before_check": (
        _PATCH.format(patch="q._negated_before = lambda page, lo, quote: False"),
        {"test_negation_before_exact_match_is_rejected",
         "test_contraction_before_exact_match_is_rejected",
         "test_negation_before_fuzzy_match_is_rejected"},
    ),
    "no_sentence_boundary": (
        _PATCH.format(patch=(
            "q._SENTENCE_END = ''\n"
            "q._window_tokens = lambda page, lo: page[:lo].split()[-3:]")),
        {"test_negation_in_previous_sentence_is_ignored",
         "test_negation_in_previous_sentence_is_ignored_fuzzy"},
    ),
    "old_negation_list": (
        _PATCH.format(patch=(
            "q._NEGATIONS = frozenset(['not', 'no', 'none', 'without', 'never', "
            "'neither', 'nor', 'absence', 'absent', 'lack', 'lacked', 'lacking', "
            "'cannot'])")),
        {"test_failed_to_show_toxicity_is_rejected",
         "test_extended_negation_words_before_match_are_rejected"},
    ),
    "no_non_prefix": (
        _PATCH.format(patch="import re\nq._NON_PREFIX = re.compile(r'(?!x)x')"),
        {"test_non_prefix_inside_exact_span_is_rejected"},
    ),
    "no_exact_negation_compare": (
        _mutated_source("if (_digits_ok(quote, span) and _negations_ok(quote, span)",
                        "if (_digits_ok(quote, span)"),
        {"test_non_prefix_inside_exact_span_is_rejected"},
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
