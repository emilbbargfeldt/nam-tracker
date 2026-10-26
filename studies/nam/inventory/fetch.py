"""Polite, cached, read-only HTTP GET.

At most one request per second, every URL fetched once (cache keyed by the
URL hash), and a hard stop when the data directory passes the size cap or the
free space on its filesystem falls below the floor.

Usage: NAM_DATA=... python -I -m studies.nam.inventory.fetch --from-missing <jsonl>
fetches, serially, the documents listed with reason "no pdf in cache".
"""
import gzip
import hashlib
import os
import json
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "nam-tracker-phase0/1.0 (academic inventory; read-only)"
MIN_INTERVAL_S = 1.0
MAX_DATA_BYTES = 15 * 1024 ** 3
MIN_FREE_BYTES = 10 * 1024 ** 3
TIMEOUT_S = 60
MAX_BODY_BYTES = 512 * 1024 ** 2
CHUNK = 1024 * 1024


class DataCapExceeded(RuntimeError):
    pass


def data_dir():
    value = os.environ.get("NAM_DATA")
    if not value:
        raise RuntimeError("NAM_DATA is not set")
    return Path(value).expanduser()


def dir_size(path):
    total = 0
    for p in Path(path).rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


class Fetcher:
    def __init__(self, root=None, min_interval=MIN_INTERVAL_S,
                 cap=MAX_DATA_BYTES, opener=None, clock=time.monotonic,
                 sleep=time.sleep, min_free=MIN_FREE_BYTES,
                 free_space=None):
        self.root = Path(root) if root is not None else data_dir()
        self.cache = self.root / "cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self.cap = cap
        self.min_free = min_free
        self._free_space = free_space or (lambda p: shutil.disk_usage(p).free)
        self._opener = opener or self._urlopen
        self._clock = clock
        self._sleep = sleep
        self._last = None
        self.requests = 0

    @staticmethod
    def _urlopen(url):
        safe = urllib.parse.quote(url, safe=":/%?=&#;,+@~")
        req = urllib.request.Request(safe, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            parts, size = [], 0
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    return b"".join(parts)
                size += len(chunk)
                if size > MAX_BODY_BYTES:
                    raise DataCapExceeded("response body too large")
                parts.append(chunk)

    def path_for(self, url):
        return self.cache / hashlib.sha256(url.encode()).hexdigest()

    def get(self, url):
        """Return the cached body path for url, fetching it at most once."""
        path = self.path_for(url)
        if path.exists():
            return path
        if dir_size(self.root) >= self.cap:
            raise DataCapExceeded("data directory reached the size cap")
        if self._free_space(self.root) < self.min_free:
            raise DataCapExceeded("free disk space below the floor")
        if self._last is not None:
            wait = self.min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()
        self.requests += 1
        body = self._opener(url)
        tmp = path.with_suffix(".part")
        try:
            tmp.write_bytes(body)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        tmp.replace(path)
        return path

    def get_bytes(self, url):
        body = self.get(url).read_bytes()
        if body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        return body


def missing_items(jsonl, units, doc_id_of):
    """Units whose doc id is listed with reason "no pdf in cache", sorted by id."""
    ids = set()
    with open(jsonl) as fh:
        for line in fh:
            row = json.loads(line)
            if row.get("reason") == "no pdf in cache":
                ids.add(row["doc"])
    return sorted((u for u in units if doc_id_of(u) in ids), key=doc_id_of)


def fetch_items(fetcher, items, doc_id_of, get=None, every=100, out=print):
    """Fetch items one at a time. Returns (fetched, failed, bytes).

    Prints a short status every `every` items and stops at once when a limit
    (DataCapExceeded) is hit.
    """
    if get is None:
        from studies.nam.inventory.fetch_tocs import get_with_retry
        get = get_with_retry
    ok = failed = size = 0
    for n, item in enumerate(items, 1):
        try:
            size += get(fetcher, item["url"]).stat().st_size
            ok += 1
        except Exception as exc:
            failed += 1
            out("fail %s: %s" % (doc_id_of(item), type(exc).__name__))
            if isinstance(exc, DataCapExceeded):
                out("stopped on limit")
                break
        if n % every == 0:
            out("%d/%d fetched %d failed %d MB %.0f"
                % (n, len(items), ok, failed, size / 1e6))
    return ok, failed, size


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] != "--from-missing":
        print("usage: fetch --from-missing <jsonl> (nothing run)")
        return 2
    from studies.nam.extract.candidates import doc_id_of
    from studies.nam.pilot import draw
    f = Fetcher()
    units, _ = draw.universe(f)
    items = missing_items(argv[1], units.values(), doc_id_of)
    start = time.monotonic()
    ok, failed, size = fetch_items(f, items, doc_id_of)
    print("DONE fetched %d failed %d MB %.0f time %.0f min"
          % (ok, failed, size / 1e6, (time.monotonic() - start) / 60))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
