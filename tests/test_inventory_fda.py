from datetime import date

from studies.nam.inventory import fda
from studies.nam.inventory.fda_titles import (
    TocParseError, categories, has_strict_nonclinical, parse_flags)
import pytest

PAGE = """
<table><tr><th>No.</th><th>Drug Name</th><th>Active Ingredient</th>
<th>Approval Date</th><th>Use</th></tr>
<tr><td>2.</td><td><a href="https://x/label/2023/761269Orig1s000lbl.pdf">Alpha</a></td>
<td>alphamab</td><td>1/6/2023</td><td>use</td></tr>
<tr><td>1.</td><td><a href="http://x/index.cfm?event=overview.process&amp;varApplNo=209360">Beta</a></td>
<td>betaol</td><td>12/21/2023</td><td>use</td></tr>
<tr><td>3.</td><td>Gamma</td><td>gammaol</td><td>13/45/2023</td><td>use</td></tr>
</table>"""


def test_parse_novel_page_known_answer():
    rows = fda.parse_novel_page(PAGE)
    assert [r["name"] for r in rows] == ["Alpha", "Beta", "Gamma"]
    assert [r["appl_no"] for r in rows] == ["761269", "209360", None]
    assert rows[0]["approved"] == date(2023, 1, 6)
    assert rows[2]["approved"] is None


PRODUCTS = [
    {"ApplNo": "111111", "DrugName": "Gamma"},
    {"ApplNo": "222222", "DrugName": "Dup"},
    {"ApplNo": "333333", "DrugName": "Dup"},
]
APPS = [{"ApplNo": a, "ApplType": "NDA"} for a in ("111111", "222222", "333333")]
SUBS = [{"ApplNo": "111111", "SubmissionType": "ORIG   ",
         "SubmissionStatus": "AP", "SubmissionStatusDate": "2023-03-04 00:00:00"}]


def test_resolve_rows_repairs_and_flags():
    rows = fda.parse_novel_page(PAGE)
    out = fda.resolve_rows(rows, 2023, PRODUCTS, APPS, SUBS)
    gamma = out[2]
    assert gamma["appl_no"] == "111111"
    assert gamma["approved"] == date(2023, 3, 4)
    assert any("list date unusable" in n for n in gamma["notes"])
    assert out[0]["notes"] == []


def test_ambiguous_name_is_not_matched():
    assert fda.match_by_name(PRODUCTS, APPS, "Dup") is None
    assert fda.match_by_name(PRODUCTS, APPS, "Nope") is None


def test_wrong_year_date_is_not_trusted():
    rows = [{"name": "X", "appl_no": None, "approved": date(2028, 1, 1)}]
    out = fda.resolve_rows(rows, 2018, [], [], [])
    assert out[0]["approved"] is None


TOC = """<script>
var pdfFiles = {
    approv: 1,
    // comment
    integratedR: 0,
    multidisciplineR: 1,
    pharmR: 0
};
</script>"""


def test_parse_flags_known_answer():
    flags = parse_flags(TOC)
    assert flags["multidisciplineR"] == 1 and flags["pharmR"] == 0
    cats = categories(flags)
    assert cats == {"multidisc"}
    assert has_strict_nonclinical(cats)


def test_integrated_alone_is_not_strict():
    cats = categories(parse_flags("var pdfFiles = {\n integratedR: 1,\n multidisciplineR: 0,\n pharmR: 0\n};"))
    assert cats == {"integrated"}
    assert not has_strict_nonclinical(cats)


def test_toc_without_flags_is_an_error_not_a_zero():
    with pytest.raises(TocParseError):
        parse_flags("<html>no script</html>")


def test_flags_block_missing_a_flag_is_error():
    with pytest.raises(TocParseError):
        parse_flags("var pdfFiles = {\n multidisciplineR: 1,\n integratedR: 0\n};")


def test_name_match_requires_year_and_type_and_normalises():
    products = [{"ApplNo": "1", "DrugName": "Alpha"},
                {"ApplNo": "2", "DrugName": "Beta"},
                {"ApplNo": "3", "DrugName": "Gamma"}]
    apps = [{"ApplNo": "1", "ApplType": "NDA"}, {"ApplNo": "2", "ApplType": "ANDA"},
            {"ApplNo": "3", "ApplType": "BLA"}]
    subs = [{"ApplNo": a, "SubmissionType": "ORIG", "SubmissionStatus": "AP",
             "SubmissionStatusDate": d + "-01-01 00:00:00"}
            for a, d in (("1", "2010"), ("2", "2023"), ("3", "2023"))]
    assert fda.match_by_name(products, apps, "Alpha", 2023, subs) is None
    assert fda.match_by_name(products, apps, "Beta", 2023, subs) is None
    assert fda.match_by_name(products, apps, "Gamma*", 2023, subs) == "3"


def test_orig_date_ignores_supplements_and_nonapproved_and_takes_earliest():
    subs = [
        {"ApplNo": "9", "SubmissionType": "ORIG", "SubmissionStatus": "AP",
         "SubmissionStatusDate": "2020-05-01 00:00:00"},
        {"ApplNo": "9", "SubmissionType": "ORIG", "SubmissionStatus": "AP",
         "SubmissionStatusDate": "2019-05-01 00:00:00"},
        {"ApplNo": "9", "SubmissionType": "SUPPL", "SubmissionStatus": "AP",
         "SubmissionStatusDate": "2015-05-01 00:00:00"},
        {"ApplNo": "9", "SubmissionType": "ORIG", "SubmissionStatus": "TA",
         "SubmissionStatusDate": "2014-05-01 00:00:00"},
    ]
    assert fda.orig_approval_date(subs, "9") == date(2019, 5, 1)


def test_validate_page_flags_empty_gaps_and_duplicates():
    assert fda.validate_page([], 2020)
    ok = [{"no": 1, "appl_no": "1"}, {"no": 2, "appl_no": "2"}]
    assert fda.validate_page(ok, 2020) == []
    assert fda.validate_page([{"no": 1, "appl_no": "1"}, {"no": 3, "appl_no": "2"}], 2020)
    assert fda.validate_page([{"no": 1, "appl_no": "1"}, {"no": 2, "appl_no": "1"}], 2020)


def test_regex_priority_varapplno_first():
    links = ["https://x/label/2020/222222Orig1s000lbl.pdf", "x?varApplNo=111111"]
    assert fda.appl_no_from_links(links) == "111111"


def test_several_flags_per_line_and_comments():
    page = ("var pdfFiles = {\napprov: 1, lbl: 1, pharmR: 1,\n"
            "integratedR: 0, // pharmR: 0\nmultidisciplineR: 0\n};")
    flags = parse_flags(page)
    assert flags["pharmR"] == 1 and flags["integratedR"] == 0


def test_nested_table_in_ingredient_cell_keeps_row():
    page = ('<table><tr><td>1.</td><td><a href="x?varApplNo=111111">A</a></td>'
            '<td> <table><tbody><tr><td> <p>ing-x</p> </td> </tr></tbody></table></td>'
            '<td>12/21/2020</td><td>use</td></tr></table>')
    rows = fda.parse_novel_page(page)
    assert len(rows) == 1
    assert rows[0]["ingredient"] == "ing-x" and rows[0]["appl_no"] == "111111"
    assert rows[0]["approved"] == date(2020, 12, 21)


def test_row_number_with_comma_typo_is_kept():
    page = ('<table><tr><td>23,</td><td>A</td><td>x</td><td>6/11/2020</td>'
            '<td>u</td></tr></table>')
    assert [r["no"] for r in fda.parse_novel_page(page)] == [23]


def test_nested_table_with_link_and_text_keeps_link():
    page = ('<table><tr><td>1.</td><td>A</td><td>pre <table><tbody><tr><td>'
            '<a href="x?varApplNo=111111">l</a></td></tr></tbody></table> post</td>'
            '<td>1/2/2020</td><td>u</td></tr>'
            '<tr><td>2.</td><td>B</td><td>y</td><td>1/3/2020</td><td>u</td></tr></table>')
    rows = fda.parse_novel_page(page)
    assert [r["no"] for r in rows] == [1, 2]


def test_flag_regex_ignores_comments_urls_and_decimals():
    page = ("var pdfFiles = {\n"
            "pharmR: 1, /* integratedR: 1 */ integratedR: 0,\n"
            "multidisciplineR: 0, // note http://x pharmR: 0\n"
            "ratio: 1.5\n};")
    flags = parse_flags(page)
    assert flags["pharmR"] == 1 and flags["integratedR"] == 0
    assert "ratio" not in flags


def test_conflicting_duplicate_flag_is_error():
    with pytest.raises(TocParseError):
        parse_flags("var pdfFiles = {\npharmR: 1, pharmR: 0,\nintegratedR: 0,\nmultidisciplineR: 0\n};")
