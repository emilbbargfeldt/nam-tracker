"""Polite, cached, read-only HTTP GET.

At most one request per second, every URL fetched once (cache keyed by the
URL hash), and a hard stop when the data directory passes the size cap.
"""
import gzip
import hashlib
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "nam-tracker-phase0/1.0 (academic inventory; read-only)"
MIN_INTERVAL_S = 1.0
MAX_DATA_BYTES = 5 * 1024 ** 3
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
                 sleep=time.sleep):
        self.root = Path(root) if root is not None else data_dir()
        self.cache = self.root / "cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self.cap = cap
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
        if self._last is not None:
            wait = self.min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        self._last = self._clock()
        self.requests += 1
        body = self._opener(url)
        tmp = path.with_suffix(".part")
        tmp.write_bytes(body)
        tmp.replace(path)
        return path

    def get_bytes(self, url):
        body = self.get(url).read_bytes()
        if body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
        return body
