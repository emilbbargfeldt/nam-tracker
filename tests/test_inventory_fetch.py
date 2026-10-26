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
                sleep=clock.sleep, cap=cap, min_free=0)
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

    f = Fetcher(root=tmp_path, opener=opener, clock=clock.time,
                sleep=clock.sleep, min_free=0)
    with pytest.raises(OSError):
        f.get("u1")
    t0 = clock.now
    f.get("u2")
    assert clock.now - t0 >= 1.0 - 1e-9


def test_cap_constant_is_fifteen_gib():
    from studies.nam.inventory import fetch
    assert fetch.MAX_DATA_BYTES == 15 * 1024 ** 3


def test_free_space_floor_constant_is_ten_gib():
    from studies.nam.inventory import fetch
    assert fetch.MIN_FREE_BYTES == 10 * 1024 ** 3


def test_low_free_space_stops_fetching(tmp_path):
    calls = []

    def opener(url):
        calls.append(url)
        return b"x"

    f = Fetcher(root=tmp_path, opener=opener, min_free=100,
                free_space=lambda p: 99)
    with pytest.raises(DataCapExceeded):
        f.get("u1")
    assert calls == []


def test_enough_free_space_fetches_and_cached_url_is_served(tmp_path):
    free = {"n": 100}
    f = Fetcher(root=tmp_path, opener=lambda u: b"x", min_free=100,
                free_space=lambda p: free["n"])
    f.get("u1")
    free["n"] = 0
    assert f.get("u1").read_bytes() == b"x"


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


def _id(u):
    return u["name"]


def test_missing_items_selects_only_no_pdf_rows(tmp_path):
    jsonl = tmp_path / "m.jsonl"
    jsonl.write_text('{"doc": "b", "reason": "no pdf in cache"}\n'
                     '{"doc": "a", "reason": "ocr missing", "pages": [1]}\n'
                     '{"doc": "c", "reason": "no pdf in cache"}\n')
    units = [{"name": n, "url": n} for n in ("c", "a", "b", "d")]
    from studies.nam.inventory.fetch import missing_items
    assert [u["name"] for u in missing_items(jsonl, units, _id)] == ["b", "c"]


def test_fetch_items_counts_status_and_stops_on_limit(tmp_path):
    from studies.nam.inventory.fetch import fetch_items
    f, _, _ = make(tmp_path, {"u%d" % i: b"x" * 10 for i in range(5)})
    items = [{"name": "n%d" % i, "url": "u%d" % i} for i in range(5)]
    lines = []
    ok, failed, size = fetch_items(f, items, _id, get=lambda fe, u: fe.get(u),
                                   every=2, out=lines.append)
    assert (ok, failed, size) == (5, 0, 50)
    assert lines == ["2/5 fetched 2 failed 0 MB 0", "4/5 fetched 4 failed 0 MB 0"]
    low = Fetcher(root=tmp_path / "low", opener=lambda u: b"x", min_free=100,
                  free_space=lambda p: 0)
    lines = []
    ok, failed, size = fetch_items(low, items, _id, get=lambda fe, u: fe.get(u),
                                   out=lines.append)
    assert (ok, failed) == (0, 1)
    assert lines == ["fail n0: DataCapExceeded", "stopped on limit"]


def test_main_rejects_other_arguments(capsys):
    from studies.nam.inventory.fetch import main
    assert main(["--other"]) == 2
    assert "nothing run" in capsys.readouterr().out


def test_failed_check_changes_no_state(tmp_path):
    calls = []
    f = Fetcher(root=tmp_path, opener=lambda u: calls.append(u) or b"x",
                min_free=100, free_space=lambda p: 0)
    with pytest.raises(DataCapExceeded):
        f.get("u1")
    assert (calls, f.requests, f._last) == ([], 0, None)


def test_cached_url_served_when_cap_exceeded_and_space_low(tmp_path):
    f, _, _ = make(tmp_path, {"u1": b"x" * 100})
    f.get("u1")
    g = Fetcher(root=tmp_path, opener=lambda u: b"y", cap=0, min_free=100,
                free_space=lambda p: 0)
    assert g.get("u1").read_bytes() == b"x" * 100


def test_retry_wrapper_does_not_retry_a_limit(tmp_path):
    from studies.nam.inventory.fetch_tocs import get_with_retry
    calls = []
    f = Fetcher(root=tmp_path, opener=lambda u: calls.append(u) or b"x",
                min_free=100, free_space=lambda p: 0)
    with pytest.raises(DataCapExceeded):
        get_with_retry(f, "u1")
    assert calls == []


def test_default_free_space_function_is_used(tmp_path):
    f = Fetcher(root=tmp_path, opener=lambda u: b"x", min_free=1 << 62)
    with pytest.raises(DataCapExceeded):
        f.get("u1")


def test_failed_write_leaves_no_part_file(tmp_path, monkeypatch):
    f, _, _ = make(tmp_path, {"u1": b"x"})
    real = type(f.path_for("u1")).write_bytes

    def boom(self, data):
        real(self, data[:0])
        raise OSError("disk full")

    monkeypatch.setattr(type(f.path_for("u1")), "write_bytes", boom)
    with pytest.raises(OSError):
        f.get("u1")
    assert list(f.cache.glob("*")) == []
