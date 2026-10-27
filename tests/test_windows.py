import hashlib
import json
from pathlib import Path

import pytest

from core.quotecheck import verify_quote
from studies.nam.extract import candidates, cli, keywords, prompt, run, windows

A_LINE = "Human iPSC-derived cardiomyocytes were exposed to the compound for 24 hours."
FAR_LINE = "Beagle dogs received the vehicle control by oral gavage for four weeks."


def page(tag, a_at=None, far_at=None, n=50):
    lines = ["Filler %02d-%02d on the study design without special words." % (tag, i)
             for i in range(n)]
    if a_at is not None:
        lines[a_at] = A_LINE
    if far_at is not None:
        lines[far_at] = FAR_LINE
    return "\n".join(lines)


def doc(a_at=5, far_at=40):
    """Two pages; the A hit is on page 1 line a_at, the far line on page 1."""
    return [page(1, a_at, far_at), page(2)], [1, 2]


def result(findings):
    return {"findings": findings, "model": "m", "usage": {}, "duration_ms": 1}


def finding(quote, page_no=1, code="A"):
    return {"code": code, "page": page_no, "quote": quote}


class Caller:
    def __init__(self, answer=None, quota_at=None, error_at=None):
        self.texts, self.answer = [], answer or (lambda text: [])
        self.quota_at, self.error_at = quota_at, error_at

    def __call__(self, text):
        self.texts.append(text)
        n = len(self.texts)
        if n == self.quota_at:
            raise cli.QuotaExhausted("limit")
        if n == self.error_at:
            raise cli.CallError("boom")
        return result(self.answer(text))


def read(tmp_path, pages_numbers, caller, **kw):
    pages, numbers = pages_numbers
    root = tmp_path / "extract"
    windows.write_manifest(root, "h" * 40, "v1")
    return windows.read_document("DOC", pages, numbers, caller, root, "v1", **kw), root


def doc_dir(root):
    return windows.design_dir(root) / "DOC"


def tree_md5(path):
    h = hashlib.md5()
    for p in sorted(Path(path).rglob("*")):
        h.update(str(p).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def test_the_model_gets_only_the_window_text(tmp_path):
    caller = Caller()
    status, _ = read(tmp_path, doc(), caller)
    assert status == "done" and len(caller.texts) == 1
    text = caller.texts[0]
    assert A_LINE in text and "=== Page 1 ===" in text
    assert FAR_LINE not in text and "Filler 02-" not in text


def test_finding_in_the_window_is_accepted_and_collected(tmp_path):
    caller = Caller(lambda t: [finding("Human iPSC-derived cardiomyocytes were exposed")])
    status, root = read(tmp_path, doc(), caller)
    assert status == "done"
    found = json.loads((doc_dir(root) / "findings.json").read_text())
    assert found == [finding("Human iPSC-derived cardiomyocytes were exposed")]
    assert (doc_dir(root) / "rejected.jsonl").read_text() == ""
    assert verify_quote(doc()[0][0], found[0]["quote"], run.MIN_RATIO)


@pytest.mark.parametrize("bad, reason", [
    (finding(FAR_LINE), "quote outside window"),
    (finding("Mice were dosed intravenously every day for a year."), "quote not verified"),
    (finding(A_LINE, code="C"), "code outside v6 scope"),
    (finding(A_LINE, page_no=2), "page outside the chunk"),
    (finding("   "), "empty quote"),
])
def test_bad_findings_are_rejected_with_a_reason(tmp_path, bad, reason):
    caller = Caller(lambda t: [bad, finding(A_LINE)])
    status, root = read(tmp_path, doc(), caller)
    assert status == "done"
    accepted = json.loads((doc_dir(root) / "findings.json").read_text())
    assert accepted == [finding(A_LINE)]
    rejected = [json.loads(x) for x in (doc_dir(root) / "rejected.jsonl").open()]
    assert [r["reason"] for r in rejected] == [reason]


def test_quota_stop_resumes_without_repeating_finished_windows(tmp_path):
    pages = [page(1, 5), page(2, 5), page(3, 5)]
    pn = (pages, [1, 2, 3])
    n_windows = len(windows.window_chunks(*pn))
    assert n_windows >= 2
    stopper = Caller(quota_at=2)
    status, root = read(tmp_path, pn, stopper)
    assert status == "quota" and len(stopper.texts) == 2
    assert not (doc_dir(root) / "findings.json").exists()
    assert len(list(doc_dir(root).glob("chunk_*.json"))) == 1
    lines = []
    again = Caller(lambda t: [])
    status2 = windows.read_document("DOC", pages, [1, 2, 3], again, tmp_path / "extract",
                                    "v1", say=lines.append)
    assert status2 == "done" and len(again.texts) == n_windows - 1
    assert any("skipped" in ln for ln in lines)
    assert (doc_dir(tmp_path / "extract") / "findings.json").exists()
    log = [json.loads(x) for x in (windows.design_dir(tmp_path / "extract")
                                   / "calls.jsonl").open()]
    assert [r["status"] for r in log][:2] == ["ok", "quota"]


def test_call_error_is_logged_and_the_window_is_read_on_the_next_run(tmp_path):
    pn = ([page(1, 5), page(2, 5)], [1, 2])
    first = Caller(error_at=1)
    status, root = read(tmp_path, pn, first)
    assert status == "error"
    again = Caller()
    assert windows.read_document("DOC", pn[0], pn[1], again, root, "v1") == "done"
    assert len(again.texts) == 1


def test_oversized_window_is_split_between_pages(tmp_path):
    pn = ([page(1, 45), page(2, 4)], [1, 2])
    whole = windows.window_chunks(*pn)
    assert len(whole) == 1 and whole[0]["pages"] == [1, 2]
    split = windows.window_chunks(*pn, max_chars=len(whole[0]["text"]) - 1)
    assert len(split) == 2 and [c["pages"] for c in split] == [[1], [2]]
    assert [c["index"] for c in split] == [1, 2]


def test_manifest_has_the_design_and_refuses_a_changed_design(tmp_path):
    root = tmp_path / "extract"
    m = windows.write_manifest(root, "a" * 40, "v1")
    assert m["design"] == "v6-windows" and m["first_git_head"] == "a" * 40
    assert m["prompt_hash"] == prompt.prompt_hash()
    assert m["keywords_md5"] == candidates.md5_of(keywords.__file__)
    assert m["prereg_version"] == candidates.prereg_version() >= 8
    assert m["radius"] == candidates.WINDOW_LINES
    assert windows.design_dir(root).name == "v6-windows-%s-%s" % (
        prompt.prompt_hash()[:12], m["keywords_md5"][:8])
    again = windows.write_manifest(root, "b" * 40, "v2")
    assert again["first_git_head"] == "a" * 40 and len(again["runs"]) == 2
    assert again["runs"][1]["git_head"] == "b" * 40
    changed = dict(windows.design_fields(), radius=3)
    with pytest.raises(windows.WindowError):
        windows.write_manifest(root, "c" * 40, "v3", changed)


def test_archive_and_cache_are_never_written(tmp_path):
    archive = tmp_path / "extract_v5_fulllayer1"
    archive.mkdir()
    (archive / "x.json").write_text("old")
    before = tree_md5(archive)
    with pytest.raises(windows.WindowError):
        windows.check_root(archive, tmp_path / "cache")
    with pytest.raises(windows.WindowError):
        windows.check_root(archive / "sub", tmp_path / "cache")
    with pytest.raises(windows.WindowError):
        windows.check_root(tmp_path / "cache" / "x", tmp_path / "cache")
    with pytest.raises(windows.WindowError):
        windows.run_documents({"D": 1}, lambda d: None, Caller(), archive,
                              tmp_path / "cache", "h", "v", say=lambda s: None)
    out = tmp_path / "extract"
    windows.run_documents({"D": 1}, lambda d: doc(), Caller(), out,
                          tmp_path / "cache", "h", "v", say=lambda s: None)
    assert tree_md5(archive) == before
    assert not (tmp_path / "cache").exists()


def test_run_documents_orders_skips_and_stops_on_quota(tmp_path):
    seen = []

    def load(d):
        seen.append(d)
        return None if d == "B" else doc()

    lines = []
    caller = Caller(quota_at=2)
    status = windows.run_documents({"C": 1, "A": 1, "B": 1}, load, caller,
                                   tmp_path / "e", tmp_path / "cache", "h", "v",
                                   say=lines.append)
    assert status == "quota" and seen == ["A", "B", "C"]
    assert lines[0].startswith("A window 1 done")
    assert any(ln.startswith("B skipped") for ln in lines)
    assert lines[-1].startswith("C window 1 quota")


def test_works_on_spike_in_test_copies(tmp_path):
    from studies.nam.extract import spikein
    docs = {"DOC%d" % i: doc(far_at=None) for i in range(4)}
    out = tmp_path / "spiked"
    manifest = spikein.prepare(out, tmp_path / "cache", docs,
                               {"1": "Study 1: organoids and iPSC cardiomyocytes were studied."},
                               docs.get, "h" * 40, 3)
    row = manifest[0]
    pages, numbers = spikein.load_copy(out, row["doc"])
    caller = Caller(lambda t: [finding("organoids and iPSC cardiomyocytes were studied",
                                       row["page"])])
    status = windows.read_document(row["doc"], pages, numbers, caller,
                                   out / "extract", "v1")
    assert status == "done"
    found = json.loads((windows.design_dir(out / "extract") / row["doc"]
                        / "findings.json").read_text())
    assert any(f["page"] == row["page"] for f in found)


def test_main_rejects_other_arguments(capsys):
    for args in ([], ["pilot"], ["x"], ["spiked", "y"]):
        assert windows.main(args) == 2
    assert "nothing run" in capsys.readouterr().out


# Mutants: each one must change the outcome of a test above.

def test_mutant_without_the_window_check_is_caught(tmp_path, monkeypatch):
    caller = Caller(lambda t: [finding(FAR_LINE)])
    _, root = read(tmp_path / "clean", doc(), caller)
    assert json.loads((doc_dir(root) / "findings.json").read_text()) == []

    def page_only(finding_, chunk, pages):
        return run.check_finding(finding_, chunk, pages)

    monkeypatch.setattr(windows, "check_window_finding", page_only)
    _, root = read(tmp_path / "mutant", doc(), Caller(lambda t: [finding(FAR_LINE)]))
    assert len(json.loads((doc_dir(root) / "findings.json").read_text())) == 1


def test_mutant_wider_windows_are_caught(tmp_path, monkeypatch):
    clean = Caller()
    read(tmp_path / "a", doc(), clean)
    assert FAR_LINE not in clean.texts[0]
    orig = candidates.a_windows
    monkeypatch.setattr(candidates, "a_windows",
                        lambda pages, numbers, radius=10: orig(pages, numbers, 40))
    mutant = Caller()
    read(tmp_path / "b", doc(), mutant)
    assert FAR_LINE in mutant.texts[0]


def test_mutant_without_resume_is_caught(tmp_path, monkeypatch):
    pn = ([page(1, 5), page(2, 5)], [1, 2])
    _, root = read(tmp_path, pn, Caller())
    clean = Caller()
    windows.read_document("DOC", pn[0], pn[1], clean, root, "v1")
    assert clean.texts == []
    monkeypatch.setattr(windows, "chunk_done", lambda path, chunk: False)
    mutant = Caller()
    windows.read_document("DOC", pn[0], pn[1], mutant, root, "v1")
    assert len(mutant.texts) >= 1


def test_mutant_check_root_that_allows_the_archive_is_caught(tmp_path, monkeypatch):
    archive = tmp_path / "extract_v5_fulllayer1"
    with pytest.raises(windows.WindowError):
        windows.check_root(archive, None)
    monkeypatch.setattr(windows, "check_root", lambda root, cache=None: None)
    windows.run_documents({"D": 1}, lambda d: doc(), Caller(), archive, None, "h", "v",
                          say=lambda s: None)
    assert archive.exists()


def test_check_root_sees_symlinks_and_relative_paths(tmp_path, monkeypatch):
    archive = tmp_path / "extract_v5_fulllayer1"
    archive.mkdir()
    link = tmp_path / "innocent"
    link.symlink_to(archive)
    with pytest.raises(windows.WindowError):
        windows.check_root(link, tmp_path / "cache")
    with pytest.raises(windows.WindowError):
        windows.check_root(link / "deeper", tmp_path / "cache")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(windows.WindowError):
        windows.check_root("extract_v5_fulllayer1/x", None)
    with pytest.raises(windows.WindowError):
        windows.check_root("sub/../extract_v5_fulllayer1", None)
    windows.check_root(tmp_path / "extract", tmp_path / "cache")


def test_stale_window_files_do_not_reach_the_findings(tmp_path):
    root = tmp_path / "extract"
    windows.write_manifest(root, "h", "v")
    long = ([page(1, 5), page(2, 5), page(3, 5)], [1, 2, 3])
    n = len(windows.window_chunks(*long))
    assert n >= 3
    windows.read_document("DOC", *long, Caller(lambda t: [finding(A_LINE, 1)]), root)
    short = ([page(1, 5), page(2), page(3)], [1, 2, 3])
    assert len(windows.window_chunks(*short)) == 1
    windows.read_document("DOC", *short, Caller(lambda t: [finding(A_LINE, 1)]), root)
    found = json.loads((doc_dir(root) / "findings.json").read_text())
    assert [f["page"] for f in found] == [1]
    assert len(list(doc_dir(root).glob("chunk_*.json"))) == n      # stale files remain


def test_changed_keywords_give_a_new_design_directory(tmp_path):
    a = tmp_path / "k1.py"
    b = tmp_path / "k2.py"
    a.write_text("x = 1\n")
    b.write_text("x = 2\n")
    root = tmp_path / "extract"
    assert windows.design_dir(root, a) != windows.design_dir(root, b)
    assert windows.design_dir(root, a) == windows.design_dir(root, a)


def test_results_without_a_manifest_and_corrupt_manifest_are_refused(tmp_path):
    root = tmp_path / "extract"
    d = windows.design_dir(root)
    (d / "DOC").mkdir(parents=True)
    (d / "DOC" / "chunk_001.json").write_text("{}")
    with pytest.raises(windows.WindowError):
        windows.write_manifest(root, "h", "v")
    root2 = tmp_path / "extract2"
    windows.write_manifest(root2, "h", "v")
    (windows.design_dir(root2) / "manifest.json").write_text("not json")
    with pytest.raises(windows.WindowError):
        windows.write_manifest(root2, "h", "v")
    (windows.design_dir(root2) / "manifest.json").write_text('{"design": "v6-windows"}')
    with pytest.raises(windows.WindowError):
        windows.write_manifest(root2, "h", "v")


def test_unreadable_document_is_skipped_and_reported_as_error(tmp_path):
    lines = []

    def load(d):
        if d == "A":
            raise IndexError("pages shorter than numbers")
        return doc()

    status = windows.run_documents({"A": 1, "B": 1}, load, Caller(), tmp_path / "e",
                                   tmp_path / "cache", "h", "v", say=lines.append)
    assert status == "error"
    assert lines[0] == "A skipped: unreadable" and lines[1].startswith("B window 1 done")


def test_document_ids_with_other_characters_are_refused(tmp_path):
    root = tmp_path / "extract"
    windows.write_manifest(root, "h", "v")
    for bad in ("../x", "a/b", "", "a b"):
        with pytest.raises(windows.WindowError):
            windows.read_document(bad, *doc(), Caller(), root)


def test_prereg_version_reads_the_log_lines_only(tmp_path):
    f = tmp_path / "P.md"
    f.write_text("Version 12 of nothing.\nSee version 99 of the tool.\n"
                 "- 2026-10-23 version 3 (x)\n- 2026-10-26 version 8 (y)\n")
    assert candidates.prereg_version(f) == 8
    assert candidates.prereg_version() >= 8


def test_pilot_run_prints_no_counts_or_findings(tmp_path):
    lines = []
    caller = Caller(lambda t: [finding(A_LINE)])
    windows.run_documents({"D": 1}, lambda d: doc(), caller, tmp_path / "e",
                          tmp_path / "cache", "h", "v", say=lines.append)
    assert lines == ["D window 1 done"]
    assert all("Human" not in ln and "finding" not in ln.lower() for ln in lines)
