from studies.nam.inventory.ema_epar import report_link


def test_report_link_found():
    page = ('<a href="/en/documents/assessment-report/x-epar-public-assessment-report_en.pdf">'
            'View</a><a href="/de/documents/assessment-report/x-epar-public-assessment-report_de.pdf">')
    assert report_link(page).endswith("x-epar-public-assessment-report_en.pdf")


def test_report_link_absent_is_none_not_error():
    assert report_link('<a href="/en/documents/overview/x_en.pdf">View</a>') is None


def test_only_the_public_epar_counts_even_if_another_report_comes_first():
    page = ('<a href="/en/documents/assessment-report/x-epar-variation-assessment-report_en.pdf">v</a>'
            '<a href="/en/documents/assessment-report/x-epar-public-assessment-report_en.pdf">p</a>')
    assert report_link(page).endswith("x-epar-public-assessment-report_en.pdf")
    assert report_link('<a href="/en/documents/assessment-report/x-other_en.pdf">v</a>') is None
