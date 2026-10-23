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


def link(folder, name):
    return '<a href="/en/documents/%s/%s">View</a>' % (folder, name)


def test_suffix_dash_zero_is_found():
    page = link("assessment-report", "x-epar-public-assessment-report_en.pdf-0")
    assert report_link(page).endswith("x-epar-public-assessment-report_en.pdf-0")


def test_name_without_epar_is_found():
    page = link("assessment-report", "x-public-assessment-report_en.pdf")
    assert report_link(page).endswith("x-public-assessment-report_en.pdf")


def test_name_without_public_is_found():
    page = link("assessment-report", "x-epar-assessment-report_en.pdf")
    assert report_link(page).endswith("x-epar-assessment-report_en.pdf")


def test_epar_public_name_in_another_folder_is_found():
    page = link("variation-report", "x-epar-public-assessment-report_en.pdf")
    assert report_link(page) is not None


VARIATION_NAMES = (
    "x-vr-1-epar-assessment-report_en.pdf",
    "x-pam-1-epar-assessment-report_en.pdf",
    "x-h-c-004054-ii-0034-epar-assessment-report_en.pdf",
    "x-h-c-1-x-0033-g-epar-assessment-report-extension_en.pdf",
    "x-ii-13-epar-assessment-report_en.pdf",
)
# Tier 1 is the original rule and is kept as it was, so a variation-style name
# that contains epar-public-assessment-report still passes in the report folder.
ORIGINAL_RULE_ONLY = "x-vr-1-epar-public-assessment-report_en.pdf"


def test_fallback_tiers_skip_variation_style_names_in_other_folders():
    assert report_link(link("variation-report", ORIGINAL_RULE_ONLY)) is None


def test_variation_style_names_never_count_in_any_folder():
    for folder in ("variation-report", "assessment-report"):
        for name in VARIATION_NAMES:
            assert report_link(link(folder, name)) is None, (folder, name)


def test_original_rule_has_priority_over_the_new_tiers():
    page = (link("assessment-report", "x-assessment-report_en.pdf")
            + link("assessment-report", "x-epar-public-assessment-report_en.pdf"))
    assert report_link(page).endswith("x-epar-public-assessment-report_en.pdf")


def test_other_languages_do_not_count():
    assert report_link(link("assessment-report", "x-epar-public-assessment-report_de.pdf")) is None
