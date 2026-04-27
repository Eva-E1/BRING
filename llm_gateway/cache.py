import asyncio
import time

class AsyncTTLCache:
    """Asyncio‑native TTL cache, no threads or locks besides asyncio.Lock."""

    def __init__(self, maxsize: int = 256, ttl: int = 3600):
        self._cache: dict[str, tuple[object, float]] = {}
        self._maxsize = maxsize
        self._ttl = ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> object | None:
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            value, expiry = entry
            if time.monotonic() > expiry:
                del self._cache[key]
                return None
            return value

    async def set(self, key: str, value: object) -> None:
        async with self._lock:
            # evict oldest if at capacity
            if len(self._cache) >= self._maxsize:
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[key] = (value, time.monotonic() + self._ttl)
