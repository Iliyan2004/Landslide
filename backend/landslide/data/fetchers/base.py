"""Fetcher contract. Credentials come from ENV (server-side only, §7.2). Blocked fetch => SourceUnavailable (never fake)."""
from __future__ import annotations
import hashlib, os, urllib.error, urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from ...errors import SourceUnavailable


@dataclass
class FetchResult:
    source_id: str
    version: str
    files: list
    sha256: dict
    acquired_utc: str
    notes: list = field(default_factory=list)


def http_download(url, dest: Path, headers=None, timeout=120):
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "landslide-platform/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
            h = hashlib.sha256()
            for chunk in iter(lambda: r.read(1 << 20), b""):
                f.write(chunk); h.update(chunk)
    except urllib.error.HTTPError as e:
        raise SourceUnavailable(f"{url}: HTTP {e.code} ({e.headers.get('x-deny-reason', 'no deny reason')})") from e
    except Exception as e:
        raise SourceUnavailable(f"{url}: {e}. If this is a network policy block, update network settings.") from e
    return h.hexdigest()


def require_env(*names):
    miss = [n for n in names if not os.environ.get(n)]
    if miss:
        raise SourceUnavailable(f"credentials missing in environment: {', '.join(miss)} (register for the free account)")
    return {n: os.environ[n] for n in names}


class Fetcher:
    source_id = ""
    registry_ids = ()
    needs_credentials = False

    def fetch(self, bbox, dest, **kw) -> FetchResult:   # bbox=(lon_min,lat_min,lon_max,lat_max)
        raise NotImplementedError

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
