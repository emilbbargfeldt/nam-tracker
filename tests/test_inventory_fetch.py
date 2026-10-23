import gzip

import pytest

from studies.nam.inventory.fetch import DataCapExceeded, Fetcher


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def make(tmp_path, bodies, cap=10 ** 9):
    clock = FakeClock()
    calls = []

    def opener(url):
        calls.append(url)
        return bodies[url]

    f = Fetcher(root=tmp_path, opener=opener, clock=clock.time,
                sleep=clock.sleep, cap=cap)
    return f, calls, clock


def test_cache_fetches_each_url_once(tmp_path):
    f, calls, _ = make(tmp_path, {"u1": b"a"})
    f.get("u1")
    f.get("u1")
    assert calls == ["u1"]
    assert f.requests == 1


def test_at_most_one_request_per_second(tmp_path):
    f, calls, clock = make(tmp_path, {"u1": b"a", "u2": b"b", "u3": b"c"})
    stamps = []
    for u in ("u1", "u2", "u3"):
        f.get(u)
        stamps.append(clock.now)
    assert all(b - a >= 1.0 - 1e-9 for a, b in zip(stamps, stamps[1:]))


def test_size_cap_stops_fetching(tmp_path):
    f, calls, _ = make(tmp_path, {"u1": b"x" * 100, "u2": b"y"}, cap=50)
    f.get("u1")
    with pytest.raises(DataCapExceeded):
        f.get("u2")
    assert calls == ["u1"]


def test_cached_url_still_served_when_cap_reached(tmp_path):
    f, _, _ = make(tmp_path, {"u1": b"x" * 100}, cap=50)
    f.get("u1")
    assert f.get("u1").read_bytes() == b"x" * 100


def test_gzip_body_is_decoded_on_read(tmp_path):
    f, _, _ = make(tmp_path, {"u1": gzip.compress(b"hello")})
    assert f.get_bytes("u1") == b"hello"


def test_failed_request_still_counts_for_rate_limit(tmp_path):
    clock = FakeClock()
    state = {"n": 0}

    def opener(url):
        state["n"] += 1
        if state["n"] == 1:
            raise OSError("boom")
        return b"ok"

    f = Fetcher(root=tmp_path, opener=opener, clock=clock.time, sleep=clock.sleep)
    with pytest.raises(OSError):
        f.get("u1")
    t0 = clock.now
    f.get("u2")
    assert clock.now - t0 >= 1.0 - 1e-9


def test_cap_constant_is_five_gib():
    from studies.nam.inventory import fetch
    assert fetch.MAX_DATA_BYTES == 5 * 1024 ** 3


def test_url_with_space_is_quoted_not_rejected(monkeypatch):
    seen = {}

    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return b"" if seen.get("done") else seen.setdefault("done", True) and b"x"

    def fake(req, timeout=0):
        seen["url"] = req.full_url
        return R()

    monkeypatch.setattr("urllib.request.urlopen", fake)
    from studies.nam.inventory import fetch
    fetch.Fetcher._urlopen("http://h/a b,c.html")
    assert " " not in seen["url"]
