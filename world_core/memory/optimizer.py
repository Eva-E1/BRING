"""Memory optimizer for pruning, clustering, and lifecycle management."""
import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Any

if TYPE_CHECKING:
    from .world_memory import WorldMemory, WorldMemoryEntry

logger = logging.getLogger(__name__)

class MemoryOptimizer:
    """Background optimizer that manages memory lifecycle."""

    def __init__(
        self,
        world_memory: "WorldMemory",
        interval_hours: int,
        scoring_engine: Any,
        cluster_engine: Any,
        min_keep_score: float,
        min_keep_days: int
    ):
        self.world_memory = world_memory
        self.interval_hours = interval_hours
        self.scoring = scoring_engine
        self.cluster = cluster_engine
        self.min_keep_score = min_keep_score
        self.min_keep_days = min_keep_days
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._stats = {
            "pruned_count": 0,
            "merged_count": 0,
            "archived_count": 0,
            "last_run": None,
        }

    async def start(self):
        """Start the background optimization task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("MemoryOptimizer started")

    async def stop(self):
        """Stop the background optimization task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MemoryOptimizer stopped")

    async def _loop(self):
        """Background loop that runs optimization periodically with exponential backoff."""
        backoff = 60  # Start with 60 seconds
        max_backoff = 300  # Max 5 minutes

        while self._running:
            try:
                await self._run()
                backoff = 60  # Reset backoff on successful run
            except Exception as e:
                logger.error(f"Optimizer error: {e}", exc_info=True)
                logger.info(f"Retrying in {backoff} seconds (exponential backoff)")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
            await asyncio.sleep(self.interval_hours * 3600)

    async def _run(self):
        """Execute one optimization cycle."""
        logger.info("Running memory optimization...")
        now = datetime.now()

        # 1. Prune low-score old entries
        pruned = await self._prune_low_score_entries(now)
        self._stats["pruned_count"] += pruned
        logger.info(f"Pruned {pruned} low-score entries")

        # 2. Cluster and merge related memories
        merged = await self._cluster_and_merge()
        self._stats["merged_count"] += merged
        logger.info(f"Merged {merged} entries into summaries")

        # 3. Archive old partitions
        archived = await self.world_memory.partition_mgr.archive_old_partitions()
        self._stats["archived_count"] += archived
        if archived:
            logger.info(f"Archived {archived} old partitions")

        # 4. Check if FAISS index needs rebuilding
        await self._check_index_rebuild()

        self._stats["last_run"] = now.isoformat()
        logger.info(f"Optimization complete. Stats: {self._stats}")

    async def _prune_low_score_entries(self, now: datetime) -> int:
        """Remove entries with low retention scores that are old enough."""
        to_prune = []

        for eid, entry in self.world_memory.active_entries.items():
            # Skip immutable entries
            if entry.metadata.get("immutable", False):
                continue

            # Only consider entries older than minimum retention period
            age_days = (now - entry.timestamp).days
            if age_days < self.min_keep_days:
                continue

            # Compute retention score
            score = self.scoring.compute_score(entry, now)
            if score < self.min_keep_score:
                to_prune.append(eid)

        # Delete pruned entries
        for eid in to_prune:
            await self.world_memory._delete_entry(eid)

        return len(to_prune)

    async def _cluster_and_merge(self) -> int:
        """Find clusters of related memories (only dirty entries) and merge them."""
        entries_to_cluster = [e for e in self.world_memory.active_entries.values() if e.needs_clustering]
        if not entries_to_cluster:
            return 0

        clusters = await self.cluster.find_clusters(entries_to_cluster)
        if not clusters:
            return 0

        merged_count = 0

        for cluster in clusters:
            # Only merge clusters above threshold
            if len(cluster) < self.cluster.merge_threshold:
                continue

            # Skip if any entry is immutable
            if any(e.metadata.get("immutable", False) for e in cluster):
                continue

            # Merge cluster
            summary_entry = await self.cluster.merge_cluster(
                cluster,
                self.world_memory.llm
            )

            if summary_entry:
                # Add summary entry
                await self.world_memory.add_memory(summary_entry)

                # Remove original entries
                for e in cluster:
                    await self.world_memory._delete_entry(e.id)

                merged_count += len(cluster)

        # Mark all clustered entries as clean
        for entry in entries_to_cluster:
            entry.needs_clustering = False

        return merged_count

    async def _check_index_rebuild(self):
        """Rebuild FAISS index if fragmentation is too high."""
        if not self.world_memory.faiss_index:
            return

        fragmentation = self.world_memory.faiss_index.fragmentation_ratio()
        threshold = self.world_memory.config.faiss_rebuild_fragmentation_threshold

        if fragmentation > threshold:
            logger.info(
                f"Rebuilding FAISS index (fragmentation: {fragmentation:.2%})"
            )
            self.world_memory.faiss_index.rebuild()

    def get_stats(self) -> dict:
        """Return optimization statistics."""
        return {
            **self._stats,
            "running": self._running,
        }

    async def run_manual(self):
        """Manually trigger an optimization run."""
        logger.info("Manually triggered optimization")
        await self._run()

    async def run_full_maintenance(self) -> dict:
        """Run all maintenance stages and return a detailed report."""
        logger.info("=== Starting full maintenance cycle (manual) ===")
        report = {}
        # Stage 1: Prune
        now = datetime.now()
        pruned = await self._prune_low_score_entries(now)
        report["pruned"] = pruned
        # Stage 2: Cluster and merge
        merged = await self._cluster_and_merge()
        report["merged"] = merged
        # Stage 3: Archive
        archived = await self.world_memory.partition_mgr.archive_old_partitions()
        report["archived"] = archived
        # Stage 4: Check FAISS rebuild
        await self._check_index_rebuild()
        report["faiss_rebuilt"] = True
        self._stats["last_run"] = now.isoformat()
        logger.info("=== Full maintenance cycle complete ===")
        return report
