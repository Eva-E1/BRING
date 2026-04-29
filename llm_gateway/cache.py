from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional


def default_cache_dir() -> Path:
    return Path(".bring_cache") / "llm_gateway"


class AsyncTTLCache:
    """
    Async TTL cache with optional on-disk persistence.

    When a persistence directory is configured, each cache key is stored in its
    own JSON file so long-running ingestion jobs can resume after crashes.
    """

    def __init__(
        self,
        maxsize: int = 256,
        ttl: int = 3600,
        persist_dir: Optional[str | Path] = None,
    ):
        self._cache: OrderedDict[str, tuple[object, float, float]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl
        self._lock = asyncio.Lock()
        self._persist_dir = Path(persist_dir) if persist_dir is not None else None
        if self._persist_dir is not None:
            self._persist_dir.mkdir(parents=True, exist_ok=True)

    async def get(self, key: str) -> object | None:
        async with self._lock:
            entry = self._cache.get(key)
            now = time.time()
            if entry is not None:
                value, expiry_epoch, created_epoch = entry
                if now > expiry_epoch:
                    del self._cache[key]
                    self._delete_persisted_key(key)
                    return None
                self._cache.move_to_end(key)
                return value

            persisted = self._load_persisted_key(key, now)
            if persisted is None:
                return None
            value, expiry_epoch, created_epoch = persisted
            self._cache[key] = (value, expiry_epoch, created_epoch)
            self._cache.move_to_end(key)
            self._evict_if_needed(now)
            return value

    async def set(self, key: str, value: object) -> None:
        async with self._lock:
            now = time.time()
            expiry_epoch = now + self._ttl
            self._cache[key] = (value, expiry_epoch, now)
            self._cache.move_to_end(key)
            self._evict_if_needed(now)
            self._persist_key(key, value, expiry_epoch, now)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._cache.pop(key, None)
            self._delete_persisted_key(key)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()
            if self._persist_dir is not None and self._persist_dir.exists():
                for path in self._persist_dir.glob("*.json"):
                    path.unlink(missing_ok=True)

    async def purge_expired(self) -> None:
        async with self._lock:
            now = time.time()
            expired_keys = [key for key, (_, expiry, _) in self._cache.items() if now > expiry]
            for key in expired_keys:
                del self._cache[key]
                self._delete_persisted_key(key)
            if self._persist_dir is not None:
                for path in self._persist_dir.glob("*.json"):
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        path.unlink(missing_ok=True)
                        continue
                    if now > float(payload.get("expiry_epoch", 0)):
                        path.unlink(missing_ok=True)

    def _evict_if_needed(self, now: float) -> None:
        expired_keys = [key for key, (_, expiry, _) in self._cache.items() if now > expiry]
        for key in expired_keys:
            del self._cache[key]
            self._delete_persisted_key(key)

        while len(self._cache) > self._maxsize:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            # Preserve persisted entries so crash recovery remains effective.

    def _persist_key(self, key: str, value: object, expiry_epoch: float, created_epoch: float) -> None:
        if self._persist_dir is None:
            return
        path = self._path_for_key(key)
        payload = {
            "key": key,
            "value": value,
            "expiry_epoch": expiry_epoch,
            "created_epoch": created_epoch,
        }
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, sort_keys=True, default=str), encoding="utf-8")
        tmp_path.replace(path)

    def _load_persisted_key(self, key: str, now: float) -> tuple[object, float, float] | None:
        if self._persist_dir is None:
            return None
        path = self._path_for_key(key)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
            return None
        expiry_epoch = float(payload.get("expiry_epoch", 0))
        if now > expiry_epoch:
            path.unlink(missing_ok=True)
            return None
        created_epoch = float(payload.get("created_epoch", now))
        return payload.get("value"), expiry_epoch, created_epoch

    def _delete_persisted_key(self, key: str) -> None:
        if self._persist_dir is None:
            return
        self._path_for_key(key).unlink(missing_ok=True)

    def _path_for_key(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._persist_dir / f"{digest}.json"
