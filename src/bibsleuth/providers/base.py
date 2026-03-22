"""Base provider with async HTTP, caching, rate limiting, and retry.

Core pattern adapted from CiteSleuth (MIT license, https://github.com/uncrafted/CiteSleuth).
Extended with async support and semaphore-based rate limiting.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlencode

import httpx

from ..cache import Cache, NullCache
from ..types import Candidate


class ProviderError(RuntimeError):
    pass


class BaseProvider(ABC):
    provider_name: str = "base"
    base_url: str = ""
    min_delay_seconds: float = 0.0
    timeout_seconds: float = 10.0
    max_retries: int = 2
    backoff_seconds: float = 1.0

    def __init__(
        self,
        cache: Cache | NullCache | None = None,
        user_agent: str = "bibsleuth/0.1",
        offline: bool = False,
    ) -> None:
        self.cache = cache or NullCache()
        self.user_agent = user_agent
        self.offline = offline
        self._semaphore = asyncio.Semaphore(1)
        self._last_request = 0.0
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @abstractmethod
    async def search(
        self,
        title: str,
        authors: list[str] | None = None,
        year: int | None = None,
    ) -> list[Candidate]: ...

    @abstractmethod
    async def lookup_by_id(self, identifier: str, id_type: str) -> list[Candidate]: ...

    async def fetch_abstract(self, candidate: Candidate) -> str | None:
        """Fetch the abstract for a candidate. Override in subclasses."""
        return candidate.abstract

    def _make_request_key(self, url: str, params: dict[str, Any] | None) -> str:
        query = urlencode(sorted((params or {}).items()))
        raw = f"{url}?{query}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    async def _request_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_key = self._make_request_key(url, params)

        cached = self.cache.get(self.provider_name, request_key)
        if cached:
            return {
                "_cache": True,
                "status_code": cached.status_code,
                "data": cached.response_json,
            }

        if self.offline:
            raise ProviderError(f"{self.provider_name}: offline mode, no cache entry")

        request_headers = dict(headers or {})
        request_headers.setdefault("User-Agent", self.user_agent)

        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            async with self._semaphore:
                # Rate limit: wait if needed
                if self.min_delay_seconds > 0:
                    loop = asyncio.get_running_loop()
                    elapsed = loop.time() - self._last_request
                    if elapsed < self.min_delay_seconds:
                        await asyncio.sleep(self.min_delay_seconds - elapsed)

                try:
                    client = await self._get_client()
                    response = await client.get(
                        url, params=params, headers=request_headers
                    )
                except httpx.HTTPError as exc:
                    last_error = str(exc)
                    if self.min_delay_seconds > 0:
                        self._last_request = asyncio.get_running_loop().time()
                    if attempt < self.max_retries:
                        continue
                    raise ProviderError(last_error) from exc

                if self.min_delay_seconds > 0:
                    self._last_request = asyncio.get_running_loop().time()

            # Outside semaphore: handle response
            status_code = response.status_code

            if status_code == 429 and attempt < self.max_retries:
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else self.backoff_seconds * (2**attempt)
                )
                await asyncio.sleep(delay)
                continue

            if 500 <= status_code < 600 and attempt < self.max_retries:
                await asyncio.sleep(self.backoff_seconds * (2**attempt))
                continue

            try:
                data = response.json()
            except json.JSONDecodeError:
                data = {"raw": response.text}

            self.cache.set(self.provider_name, request_key, data, status_code)
            return {"_cache": False, "status_code": status_code, "data": data}

        raise ProviderError(last_error or "Request failed")
