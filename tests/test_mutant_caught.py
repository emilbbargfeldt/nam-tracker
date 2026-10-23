"""Meta-test: the suite must fail against a deliberately broken verify_quote."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_always_true_mutant_is_caught(tmp_path):
    (tmp_path / "mutant_quotecheck.py").write_text(
        "def verify_quote(page_text, quote, min_ratio):\n    return True\n"
    )
    env = dict(os.environ, NAM_QUOTECHECK_MODULE="mutant_quotecheck",
               PYTHONPATH=str(tmp_path) + os.pathsep + str(ROOT))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         str(ROOT / "tests" / "test_quotecheck.py")],
        env=env, capture_output=True, text=True, cwd=str(tmp_path),
    )
    assert result.returncode != 0, result.stdout
    assert "failed" in result.stdout
