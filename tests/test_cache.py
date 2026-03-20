"""Tests for the SQLite cache."""

import tempfile
from pathlib import Path

from bibsleuth.cache import Cache, NullCache


class TestCache:
    def _make_cache(self, **kwargs):
        tmpdir = tempfile.mkdtemp()
        return Cache(path=str(Path(tmpdir) / "test.db"), **kwargs)

    def test_set_and_get(self):
        cache = self._make_cache()
        cache.set("test_provider", "key1", {"title": "hello"}, 200)
        entry = cache.get("test_provider", "key1")
        assert entry is not None
        assert entry.response_json == {"title": "hello"}
        assert entry.status_code == 200

    def test_miss(self):
        cache = self._make_cache()
        assert cache.get("test_provider", "nonexistent") is None

    def test_positive_ttl_fresh(self):
        cache = self._make_cache(positive_ttl_days=7)
        cache.set("prov", "key1", {"data": 1}, 200)
        # Fresh entry should be returned
        assert cache.get("prov", "key1") is not None

    def test_negative_ttl_fresh(self):
        cache = self._make_cache(negative_ttl_days=1)
        cache.set("prov", "key1", {"error": "not found"}, 404)
        # Fresh error entry should be returned within TTL
        assert cache.get("prov", "key1") is not None

    def test_overwrite(self):
        cache = self._make_cache()
        cache.set("prov", "key1", {"v": 1}, 200)
        cache.set("prov", "key1", {"v": 2}, 200)
        entry = cache.get("prov", "key1")
        assert entry.response_json == {"v": 2}


class TestNullCache:
    def test_always_miss(self):
        cache = NullCache()
        assert cache.get("any", "key") is None

    def test_set_noop(self):
        cache = NullCache()
        cache.set("any", "key", {"data": 1}, 200)
        assert cache.get("any", "key") is None
