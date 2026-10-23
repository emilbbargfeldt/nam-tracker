from studies.nam.inventory import section


def test_low_pages_inside_ranges_only_known_answer():
    pages = ["a" * 150, "b" * 10, "", "c" * 99, "d" * 100, "e" * 5]
    loc = {"ranges": [[2, 4], [6, 6]]}
    # 100 characters count as text; page 1 and 5 are outside the ranges
    assert section.low_pages(loc, pages) == [2, 3, 4, 6]


def test_whitespace_does_not_count():
    pages = ["  \n " * 200, "x" * 100]
    assert section.low_pages({"ranges": [[1, 2]]}, pages) == [1]


def test_none_below_threshold():
    assert section.low_pages({"ranges": [[1, 1]]}, ["z" * 500]) == []
