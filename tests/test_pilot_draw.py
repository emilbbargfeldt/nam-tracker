import pytest

from studies.nam.pilot import draw


def item(au, year, n):
    return {"id": str(n), "authority": au, "year": year, "name": "d%d" % n}


def units(n_fda=60, n_ema=60):
    out = {}
    for i in range(n_fda):
        out["FDA|%d" % i] = item("FDA", 2015 + i % 12, i)
    for i in range(n_ema):
        out["EMA|%d" % i] = item("EMA", 2015 + i % 12, i)
    return out


def counts(items):
    return (sum(i["authority"] == "EMA" for i in items),
            sum(i["authority"] == "FDA" for i in items),
            sum(i["year"] >= 2023 for i in items))


def test_pick_keeps_quotas_reachable_known_answer():
    order = ([item("FDA", 2016, i) for i in range(6)]
             + [item("EMA", 2024, 10 + i) for i in range(4)]
             + [item("FDA", 2024, 20 + i) for i in range(4)])
    got = draw.pick(order, 5, {"EMA": 2, "FDA": 1}, 2)
    # three FDA 2016 fit; a fourth would leave one place for two EMA; the
    # remaining FDA 2016 are skipped, then the first two EMA 2024 are taken
    assert [(i["authority"], i["id"]) for i in got] == [
        ("FDA", "0"), ("FDA", "1"), ("FDA", "2"), ("EMA", "10"), ("EMA", "11")]


def test_pick_fails_when_quotas_cannot_be_met():
    with pytest.raises(ValueError):
        draw.pick([item("FDA", 2016, i) for i in range(10)], 5, {"EMA": 1})


def test_draw_meets_quotas_and_is_deterministic():
    u = units()
    a, _ = draw.draw(u)
    b, _ = draw.draw(dict(reversed(list(u.items()))))
    assert len(a) == 30 and a == b
    ema, fda, after = counts(a)
    assert ema >= 10 and fda >= 10 and after >= 10


def test_draw_other_seed_differs():
    u = units()
    assert draw.draw(u)[0] != draw.draw(u, seed=1)[0]


def test_draw_skips_fda_without_document_and_logs_it():
    u = units()
    bad = [("FDA|x%d" % i, "none") for i in range(200)]
    picked, skipped = draw.draw(u, bad)
    assert all(not i["id"].startswith("x") for i in picked)
    assert skipped and all(s["reason"] == "none" for s in skipped)


def test_pick_coder_quotas_and_determinism():
    pilot, _ = draw.draw(units())
    a = draw.pick_coder(pilot)
    assert len(a) == 15 and a == draw.pick_coder(list(reversed(pilot)))
    assert sum(k.startswith("EMA|") for k in a) >= 5
    assert sum(k.startswith("FDA|") for k in a) >= 5


def test_pick_coder_known_answer_with_forced_quota():
    # 10 FDA and 5 EMA in the pilot: all five EMA must be among 15 of 15
    pilot = [item("FDA", 2016, i) for i in range(10)] + [item("EMA", 2016, i) for i in range(5)]
    assert len(draw.pick_coder(pilot)) == 15
    pilot = [item("FDA", 2016, i) for i in range(20)] + [item("EMA", 2016, i) for i in range(5)]
    got = draw.pick_coder(pilot)
    assert sum(k.startswith("EMA|") for k in got) >= 5


def test_mutant_no_quota_check_is_caught(monkeypatch):
    u = units(n_fda=100, n_ema=12)
    ema, fda, after = counts(draw.draw(u)[0])
    assert ema >= 10 and after >= 10

    def no_quota(items, k, min_by_authority, min_after=0):
        return list(items)[:k]
    monkeypatch.setattr(draw, "pick", no_quota)
    ema, fda, after = counts(draw.draw(u)[0])
    assert ema < 10  # the test above would fail with this rule
