"""SQLite-backed cache with TTL for provider responses.

Adapted from CiteSleuth (MIT license, https://github.com/uncrafted/CiteSleuth).
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    response_json: Any
    status_code: int
    created_at: int


class Cache:
    def __init__(
        self,
        path: str = "~/.cache/bibsleuth/cache.db",
        positive_ttl_days: int = 7,
        negative_ttl_days: int = 1,
    ) -> None:
        self.path = os.path.expanduser(path)
        self.positive_ttl = positive_ttl_days * 86400
        self.negative_ttl = negative_ttl_days * 86400
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    provider TEXT NOT NULL,
                    request_key TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY (provider, request_key)
                )
                """
            )
            conn.commit()

    def get(self, provider: str, request_key: str) -> CacheEntry | None:
        now = int(time.time())
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute(
                "SELECT response_json, status_code, created_at FROM cache "
                "WHERE provider=? AND request_key=?",
                (provider, request_key),
            ).fetchone()
        if not row:
            return None
        response_json, status_code, created_at = row
        ttl = self.negative_ttl if status_code >= 400 else self.positive_ttl
        if now - created_at > ttl:
            return None
        return CacheEntry(json.loads(response_json), int(status_code), int(created_at))

    def set(
        self,
        provider: str,
        request_key: str,
        response_json: Any,
        status_code: int,
    ) -> None:
        payload = json.dumps(response_json)
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache "
                "(provider, request_key, response_json, status_code, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (provider, request_key, payload, int(status_code), int(time.time())),
            )
            conn.commit()


class NullCache:
    """No-op cache for when caching is disabled."""

    def get(self, provider: str, request_key: str) -> CacheEntry | None:
        return None

    def set(
        self,
        provider: str,
        request_key: str,
        response_json: Any,
        status_code: int,
    ) -> None:
        pass
