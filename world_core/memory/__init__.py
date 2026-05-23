"""Revolutionary graph-based self-optimizing memory system.

This module provides a complete memory system with:
- Incremental FAISS indexing for fast vector similarity search
- Batch embedding generation for efficient processing
- Write-behind persistence for improved performance
- Time-based partitioning for scalable storage
- Deterministic scoring for memory retention decisions
- Automated memory lifecycle management
- Entity extraction and resolution
- Contradiction detection and belief propagation
- Pain signal tracking for failure warnings
- Multi-pass retrieval with delta-aware context
- Salience decay and access boost
- Attention-optimized ordering (U-curve)
- Speculative caching for predicted queries
"""

from .config import MemoryConfig, DEFAULT_CONFIG
from .scoring import MemoryScoringEngine
from .embedding_queue import EmbeddingQueue
from .faiss_index import IncrementalFAISSIndex
from .write_buffer import WriteBehindBuffer
from .partition import MemoryPartitionManager
from .clustering import ClusterEngine
from .optimizer import MemoryOptimizer
from .world_memory import (
    WorldMemory,
    WorldMemoryEntry,
    MemoryMetadata,
    SessionDeltaTracker,
    SpeculativeCache,
)
from .entity_extractor import EntityExtractor
from .contradiction import ContradictionDetector
from .pain_signals import PainSignalManager
from .cognitive_pipeline import CognitivePipeline

__all__ = [
    # Configuration
    "MemoryConfig",
    "DEFAULT_CONFIG",
    # Core components
    "MemoryScoringEngine",
    "EmbeddingQueue",
    "IncrementalFAISSIndex",
    "WriteBehindBuffer",
    "MemoryPartitionManager",
    "ClusterEngine",
    "MemoryOptimizer",
    # Main classes
    "WorldMemory",
    "WorldMemoryEntry",
    "MemoryMetadata",
    "SessionDeltaTracker",
    "SpeculativeCache",
    # Cognitive features
    "EntityExtractor",
    "ContradictionDetector",
    "PainSignalManager",
    "CognitivePipeline",
]

__version__ = "2.0.0"
