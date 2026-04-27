"""Memory-specific runtime settings, with provider and embedding settings owned by llm_gateway."""

import os
from pathlib import Path

from pydantic import BaseModel, Field


class MemorySettings(BaseModel):
    """Settings for the BRING memory subsystem."""

    kuzu_db_path: Path = Field(
        default=Path(os.getenv("MEMORY_KUZU_DB_PATH", "./bring_kuzu_db")),
        description="Directory for the embedded Kuzu graph database",
    )
    graphiti_max_coroutines: int = Field(
        default=int(os.getenv("MEMORY_GRAPHITI_MAX_COROUTINES", "10"))
    )
    graphiti_store_raw_episodes: bool = Field(
        default=os.getenv("MEMORY_GRAPHITI_STORE_RAW_EPISODES", "true").lower() == "true"
    )
    use_structured_extraction: bool = Field(
        default=os.getenv("MEMORY_STRUCTURED_EXTRACTION", "true").lower() == "true",
        description="Use the gateway's structured extraction flow for ontology-safe ingestion",
    )
    bulk_ingestion_batch_size: int = Field(
        default=int(os.getenv("MEMORY_BULK_BATCH", "5")),
        description="Max concurrent episode ingestion calls",
    )
    search_result_limit: int = Field(
        default=int(os.getenv("MEMORY_SEARCH_RESULT_LIMIT", "50")),
        description="Hard cap for normalized graph search results",
    )
    timeline_window: int = Field(
        default=int(os.getenv("MEMORY_TIMELINE_WINDOW", "30")),
        description="Maximum number of timeline items returned to downstream agents",
    )
    search_cache_ttl_seconds: int = Field(
        default=int(os.getenv("MEMORY_SEARCH_CACHE_TTL_SECONDS", "120")),
        description="TTL for normalized graph search results",
    )
    search_cache_maxsize: int = Field(
        default=int(os.getenv("MEMORY_SEARCH_CACHE_MAXSIZE", "256")),
        description="Maximum number of cached graph search entries",
    )

    class Config:
        env_prefix = "MEMORY_"
        extra = "allow"


def get_settings() -> MemorySettings:
    """Return a settings object backed by current environment variables."""
    return MemorySettings()
