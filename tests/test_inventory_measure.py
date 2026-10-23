import shutil
import subprocess

import pytest

from studies.nam.inventory import measure
from studies.nam.inventory.sample import draw

pytestmark = pytest.mark.skipif(shutil.which("pdftotext") is None,
                                reason="poppler not installed")


def make_pdf(path, page_texts):
    """Minimal valid PDF; one page per entry, empty string = no text."""
    objs = []
    n = len(page_texts)
    kids = " ".join("%d 0 R" % (3 + i * 2) for i in range(n))
    objs.append("<< /Type /Catalog /Pages 2 0 R >>")
    objs.append("<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, n))
    for i, t in enumerate(page_texts):
        content_id = 4 + i * 2
        objs.append("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    "/Contents %d 0 R /Resources << /Font << /F1 << /Type /Font "
                    "/Subtype /Type1 /BaseFont /Helvetica >> >> >> >>" % content_id)
        lines = [t[j:j + 60] for j in range(0, len(t), 60)]
        stream = "BT /F1 8 Tf 20 770 Td 9 TL " + " ".join(
            "(%s) Tj T*" % ln for ln in lines) + " ET" if t else ""
        objs.append("<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += ("%d 0 obj\n%s\nendobj\n" % (i, o)).encode()
    xref = len(out)
    out += ("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode()
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, xref)).encode()
    path.write_bytes(out)


def test_known_pdf_two_text_pages_one_empty(tmp_path):
    p = tmp_path / "a.pdf"
    make_pdf(p, ["x" * 150, "", "y" * 400])
    m = measure.measure(p)
    assert m["pages"] == 3
    assert m["chars_per_page"] == [150, 0, 400]
    assert m["text_pages"] == 2
    assert abs(m["text_share"] - 2 / 3) < 1e-9
    assert m["size_bytes"] == p.stat().st_size


def test_page_just_below_threshold_is_not_text(tmp_path):
    p = tmp_path / "b.pdf"
    make_pdf(p, ["x" * (measure.TEXT_LAYER_MIN_CHARS - 1),
                 "x" * measure.TEXT_LAYER_MIN_CHARS])
    assert measure.measure(p)["text_pages"] == 1


def test_scanned_pdf_without_text_layer_is_zero_share(tmp_path):
    p = tmp_path / "c.pdf"
    make_pdf(p, ["", ""])
    assert measure.measure(p)["text_share"] == 0.0


def test_corrupt_file_raises(tmp_path):
    p = tmp_path / "d.pdf"
    p.write_bytes(b"not a pdf")
    with pytest.raises(measure.MeasureError):
        measure.measure(p)


def test_threshold_is_the_pre_registered_value():
    assert measure.TEXT_LAYER_MIN_CHARS == 100


def test_draw_is_deterministic_and_size_k():
    c = ["d%02d" % i for i in range(30)]
    a, _ = draw(c, 2, "FDA", 2020)
    b, _ = draw(list(reversed(c)), 2, "FDA", 2020)
    assert a == b and len(a) == 2


def test_draw_redraws_when_ineligible():
    c = ["a", "b", "c", "d"]
    picked, skipped = draw(c, 2, "FDA", 2019, eligible=lambda x: x in ("c", "d"))
    assert sorted(picked) == ["c", "d"]
    assert set(skipped) <= {"a", "b"}


def test_draw_with_too_few_eligible_returns_fewer():
    picked, _ = draw(["a", "b"], 2, "EMA", 2018, eligible=lambda x: x == "a")
    assert picked == ["a"]


def test_other_seed_gives_other_draw_somewhere():
    c = ["d%02d" % i for i in range(40)]
    assert any(draw(c, 2, "FDA", y)[0] != draw(c, 2, "FDA", y, seed=20261101)[0]
               for y in range(2015, 2027))


def test_draw_depends_on_authority_and_year():
    c = ["d%02d" % i for i in range(60)]
    assert draw(c, 2, "FDA", 2020)[0] != draw(c, 2, "EMA", 2020)[0]
    assert draw(c, 2, "FDA", 2020)[0] != draw(c, 2, "FDA", 2021)[0]


def test_draw_never_picks_duplicates():
    picked, _ = draw(["a", "a", "b"], 2, "FDA", 2020)
    assert sorted(picked) == ["a", "b"]


def test_measure_result_has_only_numbers(tmp_path):
    p = tmp_path / "e.pdf"
    make_pdf(p, ["secret words here " * 10])
    m = measure.measure(p)
    assert all(isinstance(v, (int, float, list)) for v in m.values())
    assert all(isinstance(c, int) for c in m["chars_per_page"])
