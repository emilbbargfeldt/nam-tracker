import os
import shutil
import subprocess

import pytest

from studies.nam.extract import ocr, run
from tests.test_inventory_measure import make_pdf


class Fake:
    """Stands in for pdftoppm and tesseract."""

    def __init__(self, texts=None, version=True, fail=None):
        self.calls = []
        self.texts = texts or {}
        self.version = version
        self.fail = fail

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[0] == "tesseract" and cmd[1] == "--version":
            if not self.version:
                raise FileNotFoundError("tesseract")
            return subprocess.CompletedProcess(cmd, 0, "tesseract 5.5.0\n more", "")
        if cmd[0] == "pdftoppm":
            page = int(cmd[cmd.index("-f") + 1])
            if self.fail == "render":
                return subprocess.CompletedProcess(cmd, 1, "", "")
            open("%s-%03d.png" % (cmd[-1], page), "wb").write(b"png")
            self.page = page
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if self.fail == "read":
            return subprocess.CompletedProcess(cmd, 1, "", "")
        return subprocess.CompletedProcess(cmd, 0, self.texts.get(self.page, ""), "")

    def ocr_calls(self):
        return [c for c in self.calls if c[0] == "tesseract" and c[1] != "--version"]


def test_ocr_page_commands_and_text(tmp_path):
    fake = Fake({3: "read by ocr"})
    assert ocr.ocr_page("a.pdf", 3, fake) == "read by ocr"
    render, read = fake.calls
    assert render[:9] == ["pdftoppm", "-r", "300", "-f", "3", "-l", "3", "-gray", "-png"]
    assert read[0] == "tesseract" and read[2:] == ["stdout", "-l", "eng"]


def test_ocr_pages_cached_second_time(tmp_path):
    fake = Fake({2: "two", 5: "five"})
    pdf = tmp_path / "doc"
    first = ocr.ocr_pages(pdf, [2, 5], tmp_path / "c", fake)
    n = len(fake.calls)
    assert first == {2: "two", 5: "five"}
    assert ocr.ocr_pages(pdf, [2, 5], tmp_path / "c", fake) == first
    assert len(fake.calls) == n


def test_apply_ocr_replaces_only_low_pages_known_answer(tmp_path):
    pages = ["good page " * 20, "", "another good page " * 20, "ab"]
    fake = Fake({2: "ocr text of page two", 4: "ocr text of page four"})
    new, info = ocr.apply_ocr(tmp_path / "d", pages, [2, 4], tmp_path / "c", fake)
    assert new[0] == pages[0] and new[2] == pages[2]
    assert new[1] == "ocr text of page two" and new[3] == "ocr text of page four"
    assert info["low_pages"] == [2, 4] and info["replaced"] == [2, 4]
    assert info["tesseract"] == "tesseract 5.5.0" and info["dpi"] == 300


def test_apply_ocr_keeps_text_layer_when_ocr_is_shorter(tmp_path):
    pages = ["a fairly long text layer of a page"]
    new, info = ocr.apply_ocr(tmp_path / "d", pages, [1], tmp_path / "c", Fake({1: "x"}))
    assert new == pages and info["replaced"] == []


def test_apply_ocr_blank_page_is_valid(tmp_path):
    new, info = ocr.apply_ocr(tmp_path / "d", [""], [1], tmp_path / "c", Fake({1: ""}))
    assert new == [""] and info["low_pages"] == [1]


def test_no_low_pages_needs_no_tesseract(tmp_path):
    fake = Fake(version=False)
    new, info = ocr.apply_ocr(tmp_path / "d", ["p"], [], tmp_path / "c", fake)
    assert new == ["p"] and info is None and fake.calls == []


def test_missing_tesseract_with_low_pages_is_an_error(tmp_path):
    with pytest.raises(ocr.OcrError):
        ocr.apply_ocr(tmp_path / "d", [""], [1], tmp_path / "c", Fake(version=False))


@pytest.mark.parametrize("fail", ["render", "read"])
def test_failed_command_is_an_error_not_an_empty_page(tmp_path, fail):
    with pytest.raises(ocr.OcrError):
        ocr.apply_ocr(tmp_path / "d", [""], [1], tmp_path / "c", Fake(fail=fail))
    assert not list((tmp_path / "c").rglob("page_*.txt"))


def test_mutant_ocr_not_applied_is_caught(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "apply_ocr",
                        lambda pdf, pages, low, cache, run=None: (list(pages), None))
    pages = ["good page " * 20, ""]
    new, _ = ocr.apply_ocr(tmp_path / "d", pages, [2], tmp_path / "c")
    assert new[1] == ""  # the known-answer test above expects the OCR text


# --- prepare_document: a made-up PDF whose first page has no text layer
@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="poppler")
def test_prepare_document_ocrs_the_empty_page(tmp_path):
    pdf = tmp_path / "s.pdf"
    make_pdf(pdf, ["", "Text page two " * 12, "Text page three " * 12])
    pages, numbers, info = run.prepare_document(pdf, "separate", tmp_path / "c",
                                                Fake({1: "ocr of page one"}))
    assert numbers == [1, 2, 3] and pages[0] == "ocr of page one"
    assert info["low_pages"] == [1]


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="poppler")
def test_prepare_document_refuses_without_ocr(tmp_path):
    pdf = tmp_path / "s.pdf"
    make_pdf(pdf, ["", "Text page two " * 12])
    with pytest.raises(ocr.OcrError):
        run.prepare_document(pdf, "separate", tmp_path / "c", Fake(version=False))


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="poppler")
def test_prepare_document_without_low_pages_does_not_need_ocr(tmp_path):
    pdf = tmp_path / "s.pdf"
    make_pdf(pdf, ["Text page one " * 12, "Text page two " * 12])
    pages, numbers, info = run.prepare_document(pdf, "separate", tmp_path / "c",
                                                Fake(version=False))
    assert info is None and numbers == [1, 2]


# --- the real tools (skipped until tesseract is installed)
@pytest.mark.skipif(shutil.which("tesseract") is None or shutil.which("pdftoppm") is None,
                    reason="tesseract not installed")
def test_real_tesseract_reads_a_rendered_page(tmp_path):
    pdf = tmp_path / "r.pdf"
    make_pdf(pdf, ["Hepatocyte spheroids were cultured for fourteen days"])
    text = ocr.ocr_page(pdf, 1).lower()
    assert "spheroids" in text and "fourteen" in text
