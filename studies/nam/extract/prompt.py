"""System prompt: fixed reading rules plus the codebook table of PREREG.md.

The codebook rows are read verbatim from PREREG.md when the prompt is built, so
the prompt cannot drift from the pre-registration. The prompt holds no drug
name, agency or year (extraction rule 1).
"""
import hashlib
import json
from pathlib import Path

PREREG = Path(__file__).resolve().parents[1] / "PREREG.md"
CODES = ("A", "B", "C", "D", "S")

RULES = """You are a reading tool. The user message is an extract of a regulatory assessment report, split into pages. Each page starts with a marker line of the form "=== Page N ===".

Task: list the passages of the text that match a category of the codebook below. You only read. You never judge a drug, a study, a method or the quality of anything, and you never infer what is not written.

Rules:
1. Report a passage only if its words state something that fits a category by the Included and Excluded columns.
2. Each finding has "code" (A, B, C, D or S), "page" (the number N of the marker above the passage) and "quote".
3. The quote must be copied verbatim from that page, in one piece, without changes, translation or ellipses, and as short as possible while still saying what it says. Keep numbers and negations exactly as written. Never combine text from two pages.
4. If the text has nothing that fits, return an empty list. No finding means nothing was found: do not explain and do not guess.
5. Answer only with JSON that matches the given schema."""

SCHEMA = {
    "type": "object",
    "properties": {"findings": {"type": "array", "items": {
        "type": "object",
        "properties": {"code": {"type": "string", "enum": list(CODES)},
                       "page": {"type": "integer"},
                       "quote": {"type": "string"}},
        "required": ["code", "page", "quote"],
        "additionalProperties": False}}},
    "required": ["findings"],
    "additionalProperties": False}


def codebook(text=None):
    """The codebook table (header, separator and rows) as written in PREREG.md."""
    lines = (PREREG.read_text() if text is None else text).splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("| Code |"))
    table = []
    for ln in lines[start:]:
        if not ln.startswith("|"):
            break
        table.append(ln)
    return "\n".join(table)


def system_prompt():
    return "%s\n\nCodebook (verbatim from the pre-registration):\n\n%s\n" % (
        RULES, codebook())


def prompt_hash(prompt=None):
    return hashlib.sha256((prompt or system_prompt()).encode()).hexdigest()


def schema_json():
    return json.dumps(SCHEMA, separators=(",", ":"))
