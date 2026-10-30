"""Shared async HTTP client with timeouts, one retry, a small TTL cache and per-source health."""

import asyncio
import json
import time
from datetime import datetime, timezone

import httpx

from .config import USER_AGENT

_client: httpx.AsyncClient | None = None
_cache: dict[str, tuple[float, object]] = {}

# source name -> {"state": live|fallback|down, "note": str, "ms": int, "at": iso}
HEALTH: dict[str, dict] = {}


def mark(source: str, state: str, note: str = "", ms: int | None = None) -> None:
    HEALTH[source] = {"state": state, "note": note, "ms": ms, "at": datetime.now(timezone.utc).isoformat()}


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def get_json(
    url: str,
    *,
    params: dict | None = None,
    data: dict | None = None,
    ttl: float = 0,
    timeout: float = 10.0,
    retries: int = 1,
):
    """GET (or POST when `data` is given) and decode JSON. Raises on failure after retries."""
    key = url + "?" + json.dumps(params or {}, sort_keys=True) + json.dumps(data or {}, sort_keys=True)
    hit = _cache.get(key)
    if ttl and hit and hit[0] > time.monotonic():
        return hit[1]

    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            if data is None:
                r = await client().get(url, params=params, timeout=timeout)
            else:
                r = await client().post(url, params=params, data=data, timeout=timeout)
            if r.status_code >= 500 or r.status_code == 429:
                raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            r.raise_for_status()
            value = r.json()
            if ttl:
                _cache[key] = (time.monotonic() + ttl, value)
            return value
        except (httpx.HTTPError, ValueError) as e:
            last = e
            if attempt < retries:
                await asyncio.sleep(0.6 * (attempt + 1))
    assert last is not None
    raise last


class Timer:
    def __enter__(self):
        self.t = time.perf_counter()
        return self

    def __exit__(self, *_):
        self.ms = round((time.perf_counter() - self.t) * 1000)

    @property
    def elapsed(self) -> int:
        return round((time.perf_counter() - self.t) * 1000)
