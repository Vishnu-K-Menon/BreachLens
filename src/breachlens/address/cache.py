"""On-disk JSON cache for external API responses (one file per request).

Keys are the sha256 of the request (method, URL, sorted params), so a repeated request
never hits the network. Each entry keeps the time it was first fetched; reading from the
cache therefore reproduces the same `verified_on` dates on every run.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CacheEntry:
    fetched_at: str
    response: dict[str, Any]


class JsonCache:
    """A directory of `<sha256>.json` files, written atomically."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    @staticmethod
    def key(method: str, url: str, params: dict[str, str]) -> str:
        payload = json.dumps([method.upper(), url, sorted(params.items())], ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> CacheEntry | None:
        path = self._path(key)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return CacheEntry(fetched_at=data["fetched_at"], response=data["response"])

    def put(
        self, key: str, response: dict[str, Any], fetched_at: datetime | None = None
    ) -> CacheEntry:
        entry = CacheEntry(
            fetched_at=(fetched_at or datetime.now(UTC)).isoformat(timespec="seconds"),
            response=response,
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(
                {"fetched_at": entry.fetched_at, "response": response}, sort_keys=True, indent=1
            ),
            encoding="utf-8",
        )
        os.replace(tmp, path)
        return entry
