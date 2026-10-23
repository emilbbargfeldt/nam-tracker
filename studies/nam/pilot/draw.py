"""Pilot selection (PREREG, accuracy): 30 drugs drawn with seed 20261101.

Quotas: at least 10 EMA (unit "yes" only, PREREG v4), at least 10 FDA, at least
10 approved after 2022 (year >= 2023). The candidates are shuffled with the
seed after sorting, then taken in that order while every quota stays reachable.
Reads the local cache only. Emil's 15 blind codings are chosen from the 30 with
a derived seed string and the quotas of at least 5 EMA and 5 FDA.

Usage: NAM_DATA=... python -I -m studies.nam.pilot.draw
"""
import json
import random
import sys
from pathlib import Path

from studies.nam.inventory import run_sample
from studies.nam.inventory.fetch import Fetcher

SEED = 20261101
N_PILOT, MIN_EMA, MIN_FDA, MIN_AFTER, AFTER_FROM = 30, 10, 10, 10, 2023
N_CODER, CODER_MIN = 15, 5
OUT = Path(__file__).with_name("pilot.json")
RULE = ("sorted candidates shuffled with random.Random(seed); take in order while "
        "the quotas stay reachable; FDA candidates without a document are skipped")


def order(keys, seed):
    items = sorted(set(keys))
    random.Random(seed).shuffle(items)
    return items


def pick(items, k, min_by_authority, min_after=0):
    """First k items (dicts with authority and year) of an ordered list that
    keep every quota reachable: with r places left, r must cover the missing
    items of all authorities together and the missing items after 2022."""
    picked = []
    for it in items:
        if len(picked) == k:
            break
        trial = picked + [it]
        left = k - len(trial)
        need = sum(max(0, m - sum(1 for x in trial if x["authority"] == au))
                   for au, m in min_by_authority.items())
        need_after = max(0, min_after - sum(1 for x in trial if x["year"] >= AFTER_FROM))
        if left >= need and left >= need_after:
            picked = trial
    if len(picked) < k:
        raise ValueError("quotas cannot be met from the candidates")
    return picked


def draw(units, statuses=(), seed=SEED):
    """units: {key: item dict}; statuses: [(key, reason)] FDA candidates that
    have no document. Returns (picked items, skipped keys met on the way)."""
    ordered = order(list(units) + [k for k, _ in statuses], seed)
    reasons = dict(statuses)
    skipped, usable = [], []
    for key in ordered:
        if key in reasons:
            skipped.append({"id": key, "reason": reasons[key]})
        else:
            usable.append(units[key])
    picked = pick(usable, N_PILOT, {"EMA": MIN_EMA, "FDA": MIN_FDA}, MIN_AFTER)
    # only report skipped candidates met before the last pick
    last = ordered.index(key_of(picked[-1]))
    return picked, [s for s in skipped if ordered.index(s["id"]) < last]


def key_of(item):
    return "%s|%s" % (item["authority"], item["id"])


def pick_coder(pilot, k=N_CODER, seed=SEED):
    """Keys of the k drugs Emil codes blind: derived seed string, at least 5
    EMA and 5 FDA."""
    by_key = {key_of(i): i for i in pilot}
    ordered = [by_key[x] for x in order(list(by_key), "%s|coder" % seed)]
    return [key_of(i) for i in pick(ordered, k, {"EMA": CODER_MIN, "FDA": CODER_MIN})]


def universe(f):
    """({key: item}, [(key, reason)]) from the local cache."""
    units, bad = {}, []
    fda_c, _ = run_sample.fda_candidates(f)
    for year, cands in fda_c.items():
        for appl, (status, payload) in cands.items():
            key = "FDA|%s" % appl
            if status == "ok":
                name, url, fmt = payload
                units[key] = {"id": appl, "authority": "FDA", "name": name,
                              "year": year, "url": url, "format": fmt}
            else:
                bad.append((key, status))
    for r in json.loads((f.root / "derived" / "ema_nas_epar.json").read_text()):
        if r["verdict"] == "yes" and r["report"]:
            units["EMA|%s" % r["url"]] = {
                "id": r["url"], "authority": "EMA", "name": r["name"],
                "year": r["year"], "url": r["report"], "format": "epar"}
    return units, bad


def main():
    f = Fetcher()
    units, bad = universe(f)
    picked, skipped = draw(units, bad)
    coders = set(pick_coder(picked))
    for it in picked:
        it["coder"] = key_of(it) in coders
    picked.sort(key=lambda i: (i["authority"], i["year"], i["name"]))
    OUT.write_text(json.dumps({
        "seed": SEED, "rule": RULE,
        "quotas": {"EMA": MIN_EMA, "FDA": MIN_FDA, "after_2022": MIN_AFTER},
        "coder_rule": "derived seed '%s|coder', at least %d EMA and %d FDA"
                      % (SEED, CODER_MIN, CODER_MIN),
        "candidates": len(units), "skipped": skipped, "items": picked},
        indent=1) + "\n")
    print("pilot", len(picked), "coder", len(coders))


if __name__ == "__main__":
    sys.exit(main())
