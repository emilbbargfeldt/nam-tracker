"""Smoke test of the final prompt and call on a made-up three-page document.

One real call. Output goes to $NAM_DATA/extract/smoke/. Shows status, the
number of accepted and rejected findings and their codes. The text is invented.

Usage: NAM_DATA=... python -I -m studies.nam.extract.smoke
"""
import json
import shutil
import sys

from studies.nam.inventory.fetch import data_dir

from . import chunks, cli, prompt, run

PAGES = [
    "Nonclinical summary. The cardiac effects of the compound were studied in "
    "patient-derived liver organoids cultured in three dimensions for 14 days. "
    "The organoids were exposed to concentrations of 1 to 30 micromolar.",
    "The compound did not inhibit the hERG channel up to 30 micromolar in an "
    "in vitro patch clamp assay. The repeat-dose toxicity study was done in "
    "Sprague-Dawley rats for 28 days.",
    "Section 4. Document history. This version replaces the earlier draft. The "
    "table of contents was updated and the page layout was changed.",
]
EXPECTED = {"A", "C", "S"}


def main():
    root = data_dir() / "extract" / "smoke"
    if root.exists():
        shutil.rmtree(root)
    (root / "cwd").mkdir(parents=True)
    lines = []
    status = run.extract_document(
        "synthetic", PAGES, [1, 2, 3], lambda t: cli.call_claude(t, root / "cwd"),
        root, cli.claude_version(), say=lines.append)
    doc = root / prompt.prompt_hash()[:12] / "synthetic"
    print("status:", status, "|", "; ".join(lines))
    if status != "done":
        return 1
    accepted = json.loads((doc / "findings.json").read_text())
    rejected = [json.loads(x) for x in (doc / "rejected.jsonl").read_text().splitlines()]
    print("accepted %d, rejected %d" % (len(accepted), len(rejected)))
    for f in accepted:
        print("  accepted %s p%d: %s" % (f["code"], f["page"], f["quote"]))
    for f in rejected:
        print("  rejected %s p%d (%s): %s" % (f["code"], f["page"], f["reason"], f["quote"]))
    print("codes found:", sorted({f["code"] for f in accepted}),
          "| expected:", sorted(EXPECTED))
    print("page 3 findings:", sum(1 for f in accepted if f["page"] == 3))
    return 0


if __name__ == "__main__":
    sys.exit(main())
