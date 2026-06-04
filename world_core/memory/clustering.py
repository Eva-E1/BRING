"""Clustering engine for memory consolidation and summarization."""
import logging
from typing import List, TYPE_CHECKING, Optional, Dict, Any
import numpy as np

if TYPE_CHECKING:
    from .world_memory import WorldMemoryEntry

logger = logging.getLogger(__name__)

class ClusterEngine:
    """Engine for finding and merging related memory clusters."""

    def __init__(
        self,
        similarity_threshold: float = 0.85,
        min_cluster_size: int = 3,
        merge_threshold: int = 5,
        enable_llm_merge: bool = True
    ):
        self.similarity_threshold = similarity_threshold
        self.min_cluster_size = min_cluster_size
        self.merge_threshold = merge_threshold
        self.enable_llm_merge = enable_llm_merge

    async def find_clusters(
        self,
        entries: List["WorldMemoryEntry"]
    ) -> List[List["WorldMemoryEntry"]]:
        """
        Find clusters of related memories using DBSCAN with cosine similarity.

        Args:
            entries: List of memory entries to cluster

        Returns:
            List of clusters, each containing related entries
        """
        if len(entries) < self.min_cluster_size:
            return []

        # Filter entries with valid embeddings
        valid = [e for e in entries if e.embedding is not None]
        if len(valid) < self.min_cluster_size:
            return []

        try:
            from sklearn.cluster import DBSCAN
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            logger.warning("sklearn not available, using simple clustering")
            return await self._simple_clustering(valid)

        # Filter embeddings to ensure consistent dimensions
        if not valid:
            return []

        # Get expected dimension from first valid embedding
        first_emb = valid[0].embedding
        if first_emb is None:
            return []
        expected_dim = len(first_emb)

        # Filter entries to only those with matching dimension
        valid_filtered = [e for e in valid if e.embedding is not None and len(e.embedding) == expected_dim]
        if len(valid_filtered) < self.min_cluster_size:
            return []

        # Convert embeddings to numpy array
        embeddings = np.array([e.embedding for e in valid_filtered])

        # Use DBSCAN with cosine distance
        # eps = 1 - similarity_threshold gives us the right distance threshold
        eps = 1 - self.similarity_threshold
        clustering = DBSCAN(
            eps=eps,
            min_samples=self.min_cluster_size,
            metric='cosine'
        )
        labels = clustering.fit_predict(embeddings)

        # Group entries by cluster label
        clusters: Dict[int, List["WorldMemoryEntry"]] = {}
        for i, label in enumerate(labels):
            if label == -1:  # -1 means noise (not in any cluster)
                continue
            clusters.setdefault(label, []).append(valid[i])

        return list(clusters.values())

    async def _simple_clustering(
        self,
        entries: List["WorldMemoryEntry"]
    ) -> List[List["WorldMemoryEntry"]]:
        """Simple clustering using pairwise similarity when sklearn unavailable."""
        if len(entries) < 2:
            return []

        clusters = []
        assigned = set()

        for i, entry in enumerate(entries):
            if entry.id in assigned:
                continue

            # Start a new cluster
            cluster = [entry]
            assigned.add(entry.id)

            # Find similar entries
            for j, other in enumerate(entries):
                if other.id in assigned or i == j:
                    continue

                # Calculate cosine similarity manually
                sim = self._cosine_similarity(
                    entry.embedding,
                    other.embedding
                )
                if sim >= self.similarity_threshold:
                    cluster.append(other)
                    assigned.add(other.id)

            if len(cluster) >= self.min_cluster_size:
                clusters.append(cluster)

        return clusters

    def _cosine_similarity(
        self,
        vec1: List[float],
        vec2: List[float]
    ) -> float:
        """Calculate cosine similarity between two vectors."""
        v1 = np.array(vec1)
        v2 = np.array(vec2)

        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(v1, v2) / (norm1 * norm2))

    async def merge_cluster(
        self,
        cluster: List["WorldMemoryEntry"],
        llm: Any
    ) -> Optional["WorldMemoryEntry"]:
        """
        Merge a cluster of memories into a single summary.

        Args:
            cluster: List of related memory entries
            llm: LLM client for generating summaries

        Returns:
            A new memory entry containing the summary, or None if merge fails
        """
        if len(cluster) < 2:
            return None

        from datetime import datetime
        from uuid import uuid4
        from .world_memory import WorldMemoryEntry, MemoryMetadata

        if not self.enable_llm_merge:
            # When LLM merge is disabled, keep the highest importance entry
            return max(cluster, key=lambda e: e.importance)

        # Generate summary using LLM
        texts = [e.content for e in cluster]
        combined = "\n".join(f"- {t}" for t in texts)

        prompt = f"""Summarise the following related memories into a single, concise statement (max 100 words). Preserve key facts but remove redundancy.

Memories:
{combined}

Summary:"""

        try:
            summary = await llm.generate_text(
                prompt,
                temperature=0.3,
                max_tokens=150
            )
        except Exception as e:
            logger.warning(f"LLM summary generation failed: {e}")
            # Fallback: create a simple concatenation
            summary = f"Related memories: {', '.join(texts[:3])}"

        # Create summary entry
        new_entry = WorldMemoryEntry(
            id=str(uuid4()),
            content=summary.strip(),
            timestamp=datetime.now(),
            source_type="summary",
            source_id="cluster_summary",
            importance=max(e.importance for e in cluster),
            tags=["summary"],
            metadata=MemoryMetadata(
                immutable=True,
                cluster_representative=True
            )
        )

        logger.info(
            f"Merged {len(cluster)} memories into summary: {new_entry.id}"
        )

        return new_entry

    async def get_cluster_summary(
        self,
        cluster: List["WorldMemoryEntry"]
    ) -> Dict[str, Any]:
        """Get a summary of a cluster without creating a new entry."""
        if not cluster:
            return {
                "count": 0,
                "avg_importance": 0.0,
                "time_range": None,
                "sources": [],
            }

        timestamps = [e.timestamp for e in cluster]
        return {
            "count": len(cluster),
            "avg_importance": sum(e.importance for e in cluster) / len(cluster),
            "time_range": {
                "oldest": min(timestamps).isoformat(),
                "newest": max(timestamps).isoformat(),
            },
            "sources": list(set(e.source_type for e in cluster)),
            "total_accesses": sum(
                e.metadata.get("access_count", 0) for e in cluster
            ),
        }
