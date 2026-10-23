from studies.nam.inventory.claim80 import ema_claim, fda_claim, meets


def test_fda_claim_known_answer_and_unread_counts_as_missing():
    s, n, d = fda_claim({2020: {"listed": 10, "nonclinical": 8},
                         2021: {"listed": 10, "nonclinical": 7}})
    assert (n, d) == (15, 20) and abs(s - 0.75) < 1e-9 and not meets(s)


def test_ema_claim_counts_missing_report():
    rows = [{"report": "u"}] * 4 + [{"report": None}]
    s, n, d = ema_claim(rows)
    assert (n, d) == (4, 5) and meets(s)


def test_threshold_boundary_is_inclusive():
    assert meets(0.8) and not meets(0.7999)


def test_empty_is_not_met():
    assert not meets(ema_claim([])[0])
