"""Configuration for the revolutionary memory system."""
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class MemoryConfig:
    """Configuration for the revolutionary memory system."""

    # Partitioning & retention
    retention_months: int = 6
    active_partitions_count: int = 3  # number of recent months kept in active memory

    # Embedding queue
    batch_embed_size: int = 50
    flush_interval_seconds: float = 5.0

    # Write buffer
    write_buffer_max_size: int = 100

    # Optimizer (runs every N hours)
    optimizer_interval_hours: int = 1

    # Scoring
    scoring_weights: Dict[str, float] = field(default_factory=lambda: {
        "importance": 0.35,
        "recency": 0.25,
        "access": 0.15,
        "emotion": 0.10,
        "relevance": 0.15,
    })
    half_life_days: float = 7.0
    min_keep_score: float = 0.15
    min_keep_days: int = 30

    # Clustering
    cluster_similarity_threshold: float = 0.85
    cluster_min_size: int = 3
    merge_cluster_min_size: int = 5  # summarise when cluster has this many entries
    enable_llm_merge: bool = True  # use LLM to summarise larger clusters

    # Indexing
    embedding_dim: int = 384
    faiss_rebuild_fragmentation_threshold: float = 0.2  # soft delete fraction that triggers rebuild

# Default configuration instance
DEFAULT_CONFIG = MemoryConfig()
