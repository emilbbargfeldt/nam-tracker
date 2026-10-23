import csv
import shutil
import subprocess

import pytest

from studies.nam.pilot import coder
from tests.test_inventory_measure import make_pdf

ITEMS = [
    {"name": "Zed", "authority": "FDA", "year": 2021, "coder": True},
    {"name": "Alpha", "authority": "EMA", "year": 2019, "coder": True},
    {"name": "Skip", "authority": "EMA", "year": 2019, "coder": False},
]


def test_coder_items_only_marked_and_sorted():
    assert [i["name"] for i in coder.coder_items(ITEMS)] == ["Alpha", "Zed"]


def test_template_columns_and_rows(tmp_path):
    p = tmp_path / "t.csv"
    coder.write_template(p, coder.coder_items(ITEMS))
    rows = list(csv.reader(p.open()))
    assert rows[0] == ["drug", "agency", "year", "A", "B", "C", "D", "A_pages",
                       "B_pages", "C_pages", "D_pages", "species",
                       "species_pages", "notes"]
    assert rows[1][:3] == ["Alpha", "EMA", "2019"] and set(rows[1][3:]) == {""}
    assert len(rows) == 3


def test_page_list_and_pdf_name():
    assert coder.page_list([[2, 3], [7, 7]]) == [2, 3, 7]
    assert coder.pdf_name({"name": "Mulpleo (previously X)", "authority": "EMA",
                           "year": 2019}) == "EMA_2019_Mulpleo_previously_X.pdf"


@pytest.mark.skipif(shutil.which("pdfseparate") is None, reason="poppler")
def test_extract_pages_known_answer(tmp_path):
    src = tmp_path / "s.pdf"
    make_pdf(src, ["Page one", "Page two", "Page three", "Page four", "Page five"])
    dst = tmp_path / "d.pdf"
    coder.extract_pages(src, dst, [2, 3, 5])
    info = subprocess.run(["pdfinfo", str(dst)], capture_output=True, text=True).stdout
    assert "Pages:           3" in info
    text = subprocess.run(["pdftotext", str(dst), "-"], capture_output=True,
                          text=True).stdout
    assert text.index("two") < text.index("three") < text.index("five")
    assert "one" not in text and "four" not in text


@pytest.mark.skipif(shutil.which("pdfseparate") is None, reason="poppler")
def test_extract_single_page(tmp_path):
    src = tmp_path / "s.pdf"
    make_pdf(src, ["Page one", "Page two"])
    dst = tmp_path / "d.pdf"
    coder.extract_pages(src, dst, [2])
    text = subprocess.run(["pdftotext", str(dst), "-"], capture_output=True,
                          text=True).stdout
    assert "two" in text and "one" not in text
