import datetime
import fcntl
import json
import subprocess

from studies.nam.extract import ocr
from studies.nam.pilot import ocr_run
from tests.test_extract_ocr import Fake
from tests.test_inventory_measure import make_pdf

START = datetime.datetime(2026, 11, 1, 23, 0)


class Clock:
    def __init__(self, t=START):
        self.t = t

    def __call__(self):
        return self.t


class Mono:
    """Every call is one second later than the previous."""
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 1.0
        return self.t


def setup(tmp_path, a1_texts=None):
    root = tmp_path / "data"
    (root / "cache").mkdir(parents=True)
    (root / "pilot").mkdir()
    make_pdf(root / "cache" / "a1d1.pdf", ["x" * 300, "", "ab", ""])
    make_pdf(root / "cache" / "a2d1.pdf", ["", "y" * 500])
    manifest = {"min_chars": 100, "parts": {
        "a1": [{"doc": "A1", "pdf": "a1d1.pdf", "layer1": 4, "low": [2, 3, 4],
                "todo": [2, 3, 4]}],
        "a2": [{"doc": "A2", "pdf": "a2d1.pdf", "layer1": 2, "low": [1],
                "todo": [1]},
               {"doc": "A3", "pdf": None, "layer1": 0, "low": [], "todo": [],
                "missing": True}]}}
    (root / "pilot" / "ocr_manifest_r0.json").write_text(json.dumps(manifest))
    return root


TEXTS = {2: "o" * 200, 3: "q" * 50, 4: "", 1: "z" * 150}


def go(root, argv=("r0",), fake=None, clock=None, **kw):
    fake = fake or Fake(texts=TEXTS)
    code = ocr_run.main(list(argv), run=fake, now=clock or Clock(), mono=Mono(),
                        root=root, nice=lambda n: None, **kw)
    return code, fake


def test_happy_path_numbers_only(tmp_path, capsys):
    root = setup(tmp_path)
    code, fake = go(root)
    out = capsys.readouterr().out
    assert code == 0
    assert "tesseract 5.5.0, 300 dpi, eng" in out
    assert "a1 | below 100 chars before: 3 | replaced by OCR: 2 | still below after: 2" in out
    assert "a2 | below 100 chars before: 1 | replaced by OCR: 1 | still below after: 0" in out
    assert out.index("a1 |") < out.index("a2 |")
    assert "ooo" not in out and "zzz" not in out
    assert len(fake.ocr_calls()) == 4


def test_resume_and_no_overwrite(tmp_path, capsys):
    root = setup(tmp_path)
    pdf = root / "cache" / "a1d1.pdf"
    folder = ocr._folder(pdf, root / "ocr")
    folder.mkdir(parents=True)
    (folder / "page_0002.txt").write_text("kept")
    code, fake = go(root)
    assert code == 0
    assert (folder / "page_0002.txt").read_text() == "kept"
    assert len(fake.ocr_calls()) == 3
    capsys.readouterr()
    code, fake2 = go(root)
    assert code == 0 and fake2.ocr_calls() == []
    assert "a2 |" in capsys.readouterr().out


def test_ocr_failure_stops_with_doc_and_page(tmp_path, capsys):
    for mode in ("render", "read"):
        root = setup(tmp_path / mode)
        code, fake = go(root, fake=Fake(texts=TEXTS, fail=mode))
        out = capsys.readouterr().out
        assert code == 1
        assert "a1 doc A1 page 2" in out
        assert "a2 |" not in out and "a1 |" not in out
        assert len([c for c in fake.calls if c[0] == "pdftoppm"]) == 1


def test_timeout_stops_with_doc_and_page(tmp_path, capsys):
    root = setup(tmp_path)

    def run(cmd, **kw):
        if cmd[0] == "pdftoppm":
            raise subprocess.TimeoutExpired(cmd, 300)
        return Fake()(cmd, **kw)
    code = ocr_run.main(["r0"], run=run, now=Clock(), mono=Mono(), root=root,
                        nice=lambda n: None)
    out = capsys.readouterr().out
    assert code == 1
    assert "doc A1 page 2" in out and "TimeoutExpired" in out
    assert "pdftoppm" not in out and "cache" not in out and "a1d1" not in out


def test_deadline_stops_between_pages_and_resumes(tmp_path, capsys):
    root = setup(tmp_path)
    clock = Clock()
    fake = Fake(texts=TEXTS)

    def run(cmd, **kw):
        res = fake(cmd, **kw)
        if len(fake.ocr_calls()) == 2:
            clock.t = datetime.datetime(2026, 11, 2, 2, 20)
        return res
    code = ocr_run.main(["r0"], run=run, now=clock, mono=Mono(), root=root,
                        nice=lambda n: None)
    out = capsys.readouterr().out
    assert code == 3
    assert "stopped at 02:20 in a1, doc A1 page 4" in out
    assert "a1 |" not in out
    assert len(fake.ocr_calls()) == 2
    code, fake2 = go(root)
    assert code == 0 and len(fake2.ocr_calls()) == 2
    assert "a2 |" in capsys.readouterr().out


def test_before_deadline_runs_through(tmp_path, capsys):
    root = setup(tmp_path)
    code, _ = go(root, argv=("r0", "--stop-at", "23:30"),
                 clock=Clock(START))
    assert code == 0


def test_usage_and_missing_manifest(tmp_path, capsys):
    root = setup(tmp_path)
    assert go(root, argv=("r9",))[0] == 2
    assert go(root, argv=())[0] == 2
    assert go(root, argv=("r0", "--stop-at", "xx"))[0] == 2
    assert go(root, argv=("r0", "--max-pages", "0"))[0] == 2
    assert go(root, argv=("bad/tag",))[0] == 2


def test_max_pages_timing(tmp_path, capsys):
    root = setup(tmp_path)
    pdf = root / "cache" / "a1d1.pdf"
    folder = ocr._folder(pdf, root / "ocr")
    folder.mkdir(parents=True)
    (folder / "page_0002.txt").write_text("cached")
    code, fake = go(root, argv=("r0", "--max-pages", "2"))
    out = capsys.readouterr().out
    assert code == 0
    assert len(fake.ocr_calls()) == 2
    assert "timing: 2 pages OCR'd, 2.0 s total, 1.0 s/page; 1 pages left, about 0:00" in out
    assert "a1 |" in out and "a2 |" not in out  # a1 was finished, a2 not started


def test_stop_time_rolls_to_next_day():
    assert ocr_run.stop_time("02:15", START) == datetime.datetime(2026, 11, 2, 2, 15)
    early = datetime.datetime(2026, 11, 2, 1, 0)
    assert ocr_run.stop_time("02:15", early) == datetime.datetime(2026, 11, 2, 2, 15)


def test_bad_pdf_name_rejected():
    import pytest
    with pytest.raises(ValueError):
        ocr_run.pdf_path("/x", "../evil")


def test_unexpected_error_in_report_stops_cleanly(tmp_path, capsys):
    root = setup(tmp_path)
    assert go(root)[0] == 0
    capsys.readouterr()
    (root / "cache" / "a1d1.pdf").write_bytes(b"not a pdf")
    code, fake = go(root)
    out = capsys.readouterr().out
    assert code == 1
    assert "stopped by error" in out and "part a1 doc A1" in out
    assert "a1d1" not in out and "cache" not in out and "Traceback" not in out


def test_broken_manifest_stops_cleanly(tmp_path, capsys):
    root = setup(tmp_path)
    (root / "pilot" / "ocr_manifest_r0.json").write_text("{broken")
    code, _ = go(root)
    out = capsys.readouterr().out
    assert code == 1
    assert "JSONDecodeError" in out and "broken" not in out


def test_second_run_is_refused_while_locked(tmp_path, capsys):
    root = setup(tmp_path)
    (root / "ocr").mkdir()
    with open(root / "ocr" / ".ocr_run.lock", "w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        code, fake = go(root)
    assert code == 2
    assert fake.calls == []
    assert "lock" in capsys.readouterr().out
    assert go(root)[0] == 0  # lock is released after the first holder is gone


def test_max_pages_estimate_counts_shared_pages_once(tmp_path, capsys):
    root = setup(tmp_path)
    path = root / "pilot" / "ocr_manifest_r0.json"
    data = json.loads(path.read_text())
    data["parts"]["a2"].append({"doc": "A4", "pdf": "a1d1.pdf", "layer1": 4,
                                "low": [3, 4], "todo": [3, 4]})
    path.write_text(json.dumps(data))
    code, _ = go(root, argv=("r0", "--max-pages", "1"))
    assert code == 0
    assert "3 pages left" in capsys.readouterr().out  # 5 without the dedupe
