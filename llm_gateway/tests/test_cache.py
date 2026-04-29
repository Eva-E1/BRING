import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from llm_gateway.cache import AsyncTTLCache


class PersistentCacheTests(unittest.TestCase):
    def test_cache_persists_entries_across_instances(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir) / "cache"

            first = AsyncTTLCache(maxsize=16, ttl=3600, persist_dir=cache_dir)
            asyncio.run(first.set("prompt:1", {"text": "hello"}))

            second = AsyncTTLCache(maxsize=16, ttl=3600, persist_dir=cache_dir)
            value = asyncio.run(second.get("prompt:1"))

            self.assertEqual(value, {"text": "hello"})

    def test_cache_purges_expired_persisted_entries(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir) / "cache"

            cache = AsyncTTLCache(maxsize=16, ttl=0, persist_dir=cache_dir)
            asyncio.run(cache.set("prompt:expired", "bye"))

            reloaded = AsyncTTLCache(maxsize=16, ttl=0, persist_dir=cache_dir)
            self.assertIsNone(asyncio.run(reloaded.get("prompt:expired")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
