from studies.nam.inventory.fda_count import count_year


def toc(p, m, i):
    return ("var pdfFiles = {\n pharmR: %d,\n multidisciplineR: %d,\n"
            " integratedR: %d\n};" % (p, m, i))


def doc(appl, t, url, sub="ORIG"):
    return {"ApplNo": appl, "SubmissionType": sub, "ApplicationDocsTypeID": t,
            "ApplicationDocsURL": url}


ROWS = [{"name": n, "appl_no": a, "notes": []} for n, a in
        (("A", "1"), ("B", "2"), ("C", "3"), ("D", "4"), ("E", None), ("F", "9"))]
DOCS = {
    "1": [doc("1", "3", "u1/TOC.html")],
    "2": [doc("2", "3", "u2/TOC.html")],
    "3": [doc("3", "3", "u3/TOC.html")],
    "4": [doc("4", "2", "u4/lbl.pdf")],
    "9": [doc("9", "3", "u9/TOC.html", sub="SUPPL")],
}
PAGES = {"u1/TOC.html": toc(1, 0, 0), "u2/TOC.html": toc(0, 0, 1),
         "u3/TOC.html": toc(0, 0, 0)}


def test_known_answer():
    c, _ = count_year(ROWS, DOCS, {"1", "2", "3", "4"}, PAGES)
    assert c["listed"] == 6
    assert c["no_appl_no"] == 1
    assert c["not_in_drugsatfda"] == 1
    assert c["in_drugsatfda"] == 4
    assert c["with_review_docs"] == 3
    assert c["strict_nonclinical"] == 1
    assert c["integrated"] == 1
    assert c["strict_or_integrated"] == 2
    assert c["no_toc"] == 1


def test_unfetched_and_unparsed_tocs_are_not_zeros():
    pages = {"u1/TOC.html": None, "u2/TOC.html": "<html>x</html>",
             "u3/TOC.html": toc(0, 0, 0)}
    c, _ = count_year(ROWS, DOCS, {"1", "2", "3", "4"}, pages)
    assert c["toc_not_fetched"] == 1
    assert c["toc_unparsed"] == 1
    assert c["toc_ok"] == 1
    assert c.get("strict_nonclinical", 0) == 0


def test_union_over_all_orig_tocs_and_invariant():
    docs = {"1": [doc("1", "3", "a/TOC.html"), doc("1", "3", "b/TOC.html"),
                  doc("1", "3", "c/TOC.html", sub="SUPPL")]}
    pages = {"a/TOC.html": toc(1, 0, 0), "b/TOC.html": toc(0, 0, 1),
             "c/TOC.html": toc(0, 1, 0)}
    rows = [{"name": "A", "appl_no": "1", "notes": []}]
    c, d = count_year(rows, docs, {"1"}, pages)
    assert d[0]["cats"] == ["integrated", "pharmtox"]
    assert c["multiple_tocs"] == 1 and c["strict_nonclinical"] == 1
    assert c["multidisc"] if "multidisc" in c else True


def test_status_counts_add_up():
    c, _ = count_year(ROWS, DOCS, {"1", "2", "3", "4"}, PAGES)
    parts = (c.get("toc_ok", 0) + c.get("toc_unparsed", 0)
             + c.get("toc_not_fetched", 0) + c.get("no_toc", 0))
    assert parts == c["in_drugsatfda"]


def test_duplicate_appl_no_is_flagged():
    rows = [{"name": "A", "appl_no": "1", "notes": []},
            {"name": "A2", "appl_no": "1", "notes": []}]
    c, _ = count_year(rows, DOCS, {"1"}, PAGES)
    assert c["duplicate_appl_no"] == 1


def test_missing_appl_no_is_not_a_duplicate():
    rows = [{"name": "A", "appl_no": None, "notes": []},
            {"name": "B", "appl_no": None, "notes": []}]
    c, _ = count_year(rows, {}, set(), {})
    assert c.get("duplicate_appl_no", 0) == 0 and c["no_appl_no"] == 2
