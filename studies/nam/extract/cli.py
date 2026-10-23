"""One Claude Code call: headless, model set explicitly, no tools.

The call reads the chunk from stdin and returns the structured findings. An
interrupted or incomplete answer is an error (CallError), never an empty list;
a usage or rate limit is QuotaExhausted. The working directory is an empty
folder so that no CLAUDE.md or project settings are found.
"""
import json
import re
import subprocess

from . import prompt

MODEL = "claude-sonnet-5-5"
TIMEOUT_S = 900
_QUOTA = re.compile(r"usage limit|rate limit|quota|limit reached|too many requests|\b429\b",
                    re.I)


class CallError(RuntimeError):
    """The answer is missing, cut off or malformed; the chunk must be rerun."""


class QuotaExhausted(RuntimeError):
    """A usage or rate limit was hit; stop and resume later."""


def build_argv(model=MODEL):
    return ["claude", "-p", "--model", model, "--tools", "",
            "--strict-mcp-config", "--disable-slash-commands",
            "--setting-sources", "", "--no-session-persistence",
            "--output-format", "json", "--json-schema", prompt.schema_json(),
            "--system-prompt", prompt.system_prompt()]


def claude_version():
    proc = subprocess.run(["claude", "--version"], capture_output=True, text=True,
                          timeout=60)
    return proc.stdout.strip()


def _valid_finding(f):
    return (isinstance(f, dict) and isinstance(f.get("code"), str)
            and isinstance(f.get("page"), int) and not isinstance(f.get("page"), bool)
            and isinstance(f.get("quote"), str))


def parse_response(stdout, stderr="", returncode=0):
    """Return {"findings", "model", "usage", "duration_ms"} or raise."""
    try:
        data = json.loads(stdout)
    except ValueError:
        data = None
    failed = returncode != 0 or not isinstance(data, dict) or bool(data.get("is_error"))
    if failed and _QUOTA.search("%s %s %s" % (
            stdout, stderr, data.get("api_error_status") if isinstance(data, dict) else "")):
        raise QuotaExhausted("usage or rate limit")
    if not isinstance(data, dict):
        raise CallError("answer is not JSON")
    if failed:
        raise CallError("call failed")
    if (data.get("type") != "result" or data.get("subtype") != "success"
            or data.get("terminal_reason") != "completed"
            or data.get("stop_reason") == "max_tokens"):
        raise CallError("answer incomplete")
    out = data.get("structured_output")
    if not isinstance(out, dict) or not isinstance(out.get("findings"), list):
        raise CallError("findings missing")
    if not all(_valid_finding(f) for f in out["findings"]):
        raise CallError("finding malformed")
    models = list(data.get("modelUsage") or {})
    return {"findings": out["findings"], "model": models[0] if models else None,
            "usage": data.get("usage") or {}, "duration_ms": data.get("duration_ms")}


def call_claude(text, cwd, model=MODEL, run=subprocess.run):
    """Send one chunk to Claude Code and return the parsed answer."""
    try:
        proc = run(build_argv(model), input=text, capture_output=True, text=True,
                   cwd=str(cwd), timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        raise CallError("timeout") from None
    return parse_response(proc.stdout, proc.stderr, proc.returncode)

