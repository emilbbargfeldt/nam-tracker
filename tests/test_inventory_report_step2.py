from studies.nam.inventory import report_step2 as r2


def rec(year, verdict, opinion=None):
    return {"year": year, "verdict": verdict, "opinion_year": opinion or year,
            "matches": [], "name": "x", "report": "u"}


def test_rows_count_verdicts_and_unknown_share():
    recs = ([rec(2020, "yes")] * 6 + [rec(2020, "no")] * 3 + [rec(2020, "unknown")])
    rows = r2.ema_unit_rows(recs, {2020: 5}, {2020: 8})
    row = [x for x in rows if x["year"] == 2020][0]
    assert (row["n"], row["yes"], row["no"], row["unknown"]) == (10, 6, 3, 1)
    assert row["unknown_share"] == 0.1
    assert row["yes_by_opinion"] == 6 and row["highlights"] == 5


def test_yes_plus_unknown_by_opinion_year():
    recs = [rec(2020, "yes"), rec(2020, "unknown"), rec(2020, "no"),
            rec(2021, "unknown", opinion=2020)]
    row = {x["year"]: x for x in r2.ema_unit_rows(recs, {}, {})}[2020]
    assert row["yes_by_opinion"] == 1
    assert row["yes_unknown_by_opinion"] == 3


def test_unknown_reason_and_spot_text_hold_no_text():
    base = {"error": None, "unmatched": [], "matches": [], "known": []}
    assert r2.unknown_reason(dict(base, error="no report link")) == "no report or error"
    assert r2.unknown_reason(dict(base, unmatched=[{"page": 1, "sentence": 2}])).startswith("phrase present")
    assert r2.unknown_reason(base) == "phrase absent from the report"
    m = [{"page": 3, "sentence": 4, "polarity": "positive"}]
    assert r2.spot_text(dict(base, matches=m)) == "decisive p3 s4 (positive)"
    assert r2.spot_text(dict(base, known=[{"page": 5, "sentence": 6}])) == "known-signal p5 s6"


def test_opinion_year_can_differ_from_approval_year():
    recs = [rec(2021, "yes", opinion=2020)]
    rows = {x["year"]: x for x in r2.ema_unit_rows(recs, {}, {})}
    assert rows[2021]["yes"] == 1 and rows[2021]["yes_by_opinion"] == 0
    assert rows[2020]["yes_by_opinion"] == 1


def test_stop_rule_is_strictly_above_ten_percent():
    at = r2.ema_unit_rows([rec(2020, "unknown")] + [rec(2020, "yes")] * 9, {}, {})
    over = r2.ema_unit_rows([rec(2021, "unknown")] * 2 + [rec(2021, "yes")] * 9, {}, {})
    assert r2.stop_years(at) == []
    assert r2.stop_years(over) == [2021]
