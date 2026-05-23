"""Time-based partition manager for memory storage."""
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class MemoryPartitionManager:
    """Manages memory partitions by month for efficient storage and retrieval."""

    def __init__(
        self,
        base_path: Path,
        retention_months: int,
        active_count: int
    ):
        self.base_path = base_path
        self.retention_months = retention_months
        self.active_count = active_count
        self._cache: Dict[str, List[dict]] = {}  # partition_key -> entries

        # Ensure base directory exists
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _partition_key(self, dt: datetime) -> str:
        """Generate partition key from datetime (YYYY-MM format)."""
        return dt.strftime("%Y-%m")

    async def load_partition(self, dt: datetime) -> List[dict]:
        """Load entries from a specific partition."""
        key = self._partition_key(dt)

        # Return cached data if available
        if key in self._cache:
            return self._cache[key]

        # Load from disk
        path = self.base_path / f"memories_{key}.json"
        if path.exists():
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                self._cache[key] = data
                logger.debug(f"Loaded partition {key} with {len(data)} entries")
                return data
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load partition {key}: {e}")
                self._cache[key] = []
                return []

        # Empty partition
        self._cache[key] = []
        return []

    async def save_entry(self, entry_dict: dict):
        """Save an entry to the appropriate partition."""
        ts = datetime.fromisoformat(entry_dict["timestamp"])
        key = self._partition_key(ts)

        # Ensure partition is loaded
        await self.load_partition(ts)

        # Check if entry already exists (by id)
        existing_ids = {e.get("id") for e in self._cache[key]}
        if entry_dict.get("id") not in existing_ids:
            self._cache[key].append(entry_dict)
            await self._persist_partition(key)

    async def _persist_partition(self, key: str):
        """Write partition data to disk using atomic file operations."""
        if key not in self._cache:
            return

        path = self.base_path / f"memories_{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        # Use atomic write with temp file
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                dir=path.parent,
                delete=False,
                suffix=".tmp"
            ) as tf:
                json.dump(self._cache[key], tf, indent=2)
                temp_path = tf.name

            os.replace(temp_path, path)
            logger.debug(f"Persisted partition {key}")
        except Exception as e:
            logger.error(f"Failed to persist partition {key}: {e}")
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.unlink(temp_path)

    async def delete_partition(self, key: str):
        """Delete a partition completely."""
        if key in self._cache:
            del self._cache[key]

        path = self.base_path / f"memories_{key}.json"
        if path.exists():
            try:
                path.unlink()
                logger.info(f"Deleted partition {key}")
            except OSError as e:
                logger.error(f"Failed to delete partition {key}: {e}")

    async def archive_old_partitions(self) -> int:
        """Archive partitions older than retention period."""
        cutoff = datetime.now() - timedelta(days=30 * self.retention_months)
        cutoff_key = self._partition_key(cutoff)

        keys_to_remove = [
            k for k in self._cache.keys()
            if k < cutoff_key
        ]

        count = 0
        for key in keys_to_remove:
            await self.delete_partition(key)
            count += 1

        if count > 0:
            logger.info(f"Archived {count} old partitions")

        return count

    async def get_active_entries(self) -> List[dict]:
        """Return entries from the most recent N partitions."""
        now = datetime.now()
        keys = set()

        # Collect keys for active partitions
        for i in range(self.active_count):
            dt = now - timedelta(days=30 * i)
            keys.add(self._partition_key(dt))

        # Load and combine all active partitions
        result = []
        for key in keys:
            data = await self.load_partition(
                datetime.strptime(key + "-01", "%Y-%m-%d")
            )
            result.extend(data)

        logger.debug(f"Loaded {len(result)} active entries from {len(keys)} partitions")
        return result

    async def get_partition_info(self) -> Dict[str, dict]:
        """Get information about all partitions."""
        info = {}

        # Scan for partition files on disk
        for path in self.base_path.glob("memories_*.json"):
            key = path.stem.replace("memories_", "")
            try:
                stat = path.stat()
                info[key] = {
                    "path": str(path),
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "cached": key in self._cache,
                    "entry_count": len(self._cache.get(key, [])),
                }
            except OSError as e:
                logger.warning(f"Failed to stat partition {key}: {e}")

        return info

    async def compact_partition(self, key: str) -> int:
        """Remove duplicate and superseded entries from a partition."""
        if key not in self._cache:
            return 0

        entries = self._cache[key]
        seen_ids = set()
        unique_entries = []
        removed = 0

        for entry in entries:
            eid = entry.get("id")
            if eid and eid not in seen_ids:
                seen_ids.add(eid)
                unique_entries.append(entry)
            else:
                removed += 1

        if removed > 0:
            self._cache[key] = unique_entries
            await self._persist_partition(key)
            logger.info(f"Compacted partition {key}, removed {removed} duplicates")

        return removed

    def clear_cache(self):
        """Clear the in-memory cache (forces reload from disk)."""
        self._cache.clear()
        logger.debug("Partition cache cleared")
