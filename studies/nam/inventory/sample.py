"""Stratified, seeded sample: k documents per year per authority."""
import random

SEED = 20261023  # not the pilot seed (20261101)


def draw(candidates, k, authority, year, eligible=lambda c: True, seed=SEED):
    """Draw k eligible candidates for one stratum.

    candidates is sorted first so the draw depends only on the seed and the
    set. Ineligible candidates met on the way are recorded as skipped and a
    new one is drawn from the same stratum. Returns (picked, skipped).
    """
    order = sorted(set(candidates))
    random.Random("%s|%s|%s" % (seed, authority, year)).shuffle(order)
    picked, skipped = [], []
    for c in order:
        if len(picked) == k:
            break
        (picked if eligible(c) else skipped).append(c)
    return picked, skipped
