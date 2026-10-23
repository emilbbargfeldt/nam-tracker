from studies.nam.pilot import ocr_fill


def test_still_low_counts_only_requested_pages():
    pages = ["a" * 150, "b" * 10, "c" * 99, "d" * 100]
    assert ocr_fill.still_low(pages, [2, 3, 4]) == [2, 3]
    assert ocr_fill.still_low(pages, [1, 4]) == []
