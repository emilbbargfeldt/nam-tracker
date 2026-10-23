from datetime import date

import pytest

from studies.nam.inventory import ema

HEAD = ["Category", "Name of medicine", "Medicine status", "Active substance",
        "Generic", "Biosimilar", "Marketing authorisation date",
        "European Commission decision date", "Medicine URL",
        "Opinion adopted date"]


def table(*rows):
    meta = [["Content type:", "Medicine"], [], list(HEAD)]
    return ema.load_table(meta + [list(r) for r in rows])


def r(name, status, sub, gen="No", bio="No", ma="", ec="", cat="Human", op=""):
    return [cat, name, status, sub, gen, bio, ma, ec, "u/" + name, op]


def test_known_answer_definition_b():
    t = table(
        r("First", "Authorised", "alphamab", ma="01/02/2016"),
        r("GenericOfFirst", "Authorised", "alphamab", gen="Yes", ma="01/02/2019"),
        r("Second", "Withdrawn", "betaol hydrochloride", ma="05/05/2017"),
        r("BetaSalt", "Authorised", "betaol sodium", ma="05/05/2020"),
        r("Combo", "Authorised", "alphamab;gammaol", ma="01/01/2021"),
        r("Vet", "Authorised", "deltaol", ma="01/01/2018", cat="Veterinary"),
        r("Refused", "Refused", "epsilonol", ec="01/01/2018"),
        r("Bio", "Authorised", "zetamab", bio="Yes", ma="01/01/2018"),
    )
    nas, log = ema.new_active_substances(t)
    assert sorted(x["name"] for x in nas) == ["Combo", "First", "Second"]
    assert ema.per_year(nas)[2016] == 1 and ema.per_year(nas)[2021] == 1
    combo = [x for x in nas if x["name"] == "Combo"][0]
    assert combo["new_subs"] == ["gammaol"]


def test_generic_first_in_table_blocks_later_originator():
    t = table(r("Gen", "Authorised", "xol", gen="Yes", ma="01/01/2016"),
              r("Orig", "Authorised", "xol", ma="01/01/2018"))
    assert ema.new_active_substances(t)[0] == []


def test_ec_date_fallback_only_for_authorised_status():
    t = table(r("A", "Authorised", "aol", ec="02/03/2022"),
              r("B", "Refused", "bol", ec="02/03/2022"),
              r("C", "Application withdrawn", "col", ec="02/03/2022"))
    nas, log = ema.new_active_substances(t)
    assert [x["name"] for x in nas] == ["A"] and log["date_from_ec"] == 1


def test_missing_column_stops():
    rows = [["Category", "Name of medicine"], ["Human", "x"]]
    with pytest.raises(ema.EmaTableError):
        ema.load_table(rows)


def test_ma_ec_difference_is_counted():
    t = table(r("A", "Authorised", "aol", ma="01/01/2016", ec="05/05/2024"),
              r("B", "Authorised", "bol", ma="01/01/2016", ec="01/01/2016"))
    assert ema.new_active_substances(t)[1]["ma_ec_differ"] == 1


def test_norm_substances_strips_salts_case_and_accents():
    assert ema.norm_substances("Betaol Hydrochloride;Caf\u00e9ine") == {"betaol", "cafeine"}
    assert ema.norm_substances("") == set()


def test_crosscheck_reports_deviation_by_opinion_and_approval_year():
    t = table(r("A", "Authorised", "aol", ma="10/01/2017", op="15/11/2016"))
    nas, _ = ema.new_active_substances(t)
    cc = ema.crosscheck(nas)
    assert cc[2016]["b_by_opinion_year"] == 1 and cc[2016]["dev_opinion"] == 1 - 27
    assert cc[2017]["b_by_approval_year"] == 1


def test_salt_only_part_is_kept_not_dropped():
    assert ema.norm_substances("sodium chloride") == {"sodium chloride"}
    assert ema.norm_substances("betaol sodium;calcium chloride") == {"betaol", "calcium chloride"}
    assert ema.has_salt_only_part("sodium chloride")
    assert not ema.has_salt_only_part("betaol sodium")


def test_ma_date_is_used_for_any_status_but_ec_fallback_is_gated():
    t = table(r("A", "SomeNewStatus", "aol", ma="01/01/2019"),
              r("B", "SomeNewStatus", "bol", ec="01/01/2019"))
    nas, log = ema.new_active_substances(t)
    assert [x["name"] for x in nas] == ["A"]
    assert log["unknown_status"] == ["SomeNewStatus"]


def test_unparsable_dates_are_logged():
    t = table(r("A", "Authorised", "aol", ma="31/02/2019", ec="01/01/2019"))
    nas, log = ema.new_active_substances(t)
    assert log["unparsable_dates"] == 1
    assert nas[0]["date_src"] == "ec"


def test_same_day_sibling_log_does_not_depend_on_row_order():
    a = r("A", "Authorised", "xol", ma="01/01/2019")
    b = r("B", "Authorised", "xol", ma="01/01/2019")
    c = r("C", "Authorised", "xol", ma="01/01/2020")
    n1 = ema.new_active_substances(table(a, b, c))[1]["same_day_siblings"]
    n2 = ema.new_active_substances(table(c, b, a))[1]["same_day_siblings"]
    assert n1 == n2 == 1


def test_ec_fallback_rows_are_listed_in_the_log():
    t = table(r("A", "Authorised", "aol", ec="02/03/2022"))
    log = ema.new_active_substances(t)[1]
    assert log["ec_fallback_rows"] == [("A", "2022-03-02", "Authorised")]
