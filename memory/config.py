"""Memory runtime settings loaded from the shared BRING project config."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping, Optional

from pydantic import BaseModel, Field

from bring_settings import DEFAULT_SETTINGS_FILE, load_settings, read_bool, read_int, read_str


class MemorySettings(BaseModel):
    """Settings for the BRING memory subsystem."""

    database_root: Path = Field(
        default=Path("./memory_databases"),
        description="Root folder that contains isolated portable memory databases",
    )
    database_id: str = Field(
        default="default",
        description="Logical database namespace used to isolate one graph from another",
    )
    kuzu_db_path: Optional[Path] = Field(
        default=None,
        description="Optional override for the embedded Kuzu graph database directory",
    )
    graphiti_max_coroutines: int = Field(default=10)
    graphiti_store_raw_episodes: bool = Field(default=True)
    use_structured_extraction: bool = Field(
        default=True,
        description="Use the gateway's structured extraction flow for ontology-safe ingestion",
    )
    bulk_ingestion_batch_size: int = Field(
        default=5,
        description="Max concurrent episode ingestion calls",
    )
    search_result_limit: int = Field(
        default=50,
        description="Hard cap for normalized graph search results",
    )
    timeline_window: int = Field(
        default=30,
        description="Maximum number of timeline items returned to downstream agents",
    )
    search_cache_ttl_seconds: int = Field(
        default=120,
        description="TTL for normalized graph search results",
    )
    search_cache_maxsize: int = Field(
        default=256,
        description="Maximum number of cached graph search entries",
    )

    @property
    def normalized_database_id(self) -> str:
        sanitized = "".join(
            ch.lower() if ch.isalnum() else "-"
            for ch in self.database_id.strip()
        )
        sanitized = re.sub(r"-{2,}", "-", sanitized).strip("-")
        return sanitized or "default"

    @property
    def database_path(self) -> Path:
        if self.kuzu_db_path is not None:
            return Path(self.kuzu_db_path)
        return self.database_root / self.normalized_database_id / "kuzu"

    @property
    def manifest_path(self) -> Path:
        return self.database_path.parent / "manifest.json"

    @property
    def attachments_path(self) -> Path:
        return self.database_path.parent / "attachments"

    @classmethod
    def from_file(
        cls,
        path: Optional[str | Path] = None,
        *,
        env: Optional[Mapping[str, str]] = None,
    ) -> "MemorySettings":
        merged = load_settings(
            path,
            env=env,
            env_var_names=("BRING_SETTINGS_FILE", "MEMORY_SETTINGS_FILE"),
            default_files=(DEFAULT_SETTINGS_FILE,),
        )
        return cls(
            database_root=Path(
                read_str(
                    merged,
                    "MEMORY_DATABASE_ROOT",
                    default=str(cls.model_fields["database_root"].default),
                )
            ),
            database_id=read_str(
                merged,
                "MEMORY_DATABASE_ID",
                default=cls.model_fields["database_id"].default,
            ),
            kuzu_db_path=(
                Path(kuzu_db_path)
                if (
                    kuzu_db_path := read_str(
                        merged,
                        "MEMORY_KUZU_DB_PATH",
                    )
                )
                else None
            ),
            graphiti_max_coroutines=read_int(
                merged,
                "MEMORY_GRAPHITI_MAX_COROUTINES",
                default=cls.model_fields["graphiti_max_coroutines"].default,
            ),
            graphiti_store_raw_episodes=read_bool(
                merged,
                "MEMORY_GRAPHITI_STORE_RAW_EPISODES",
                default=cls.model_fields["graphiti_store_raw_episodes"].default,
            ),
            use_structured_extraction=read_bool(
                merged,
                "MEMORY_STRUCTURED_EXTRACTION",
                default=cls.model_fields["use_structured_extraction"].default,
            ),
            bulk_ingestion_batch_size=read_int(
                merged,
                "MEMORY_BULK_BATCH",
                default=cls.model_fields["bulk_ingestion_batch_size"].default,
            ),
            search_result_limit=read_int(
                merged,
                "MEMORY_SEARCH_RESULT_LIMIT",
                default=cls.model_fields["search_result_limit"].default,
            ),
            timeline_window=read_int(
                merged,
                "MEMORY_TIMELINE_WINDOW",
                default=cls.model_fields["timeline_window"].default,
            ),
            search_cache_ttl_seconds=read_int(
                merged,
                "MEMORY_SEARCH_CACHE_TTL_SECONDS",
                default=cls.model_fields["search_cache_ttl_seconds"].default,
            ),
            search_cache_maxsize=read_int(
                merged,
                "MEMORY_SEARCH_CACHE_MAXSIZE",
                default=cls.model_fields["search_cache_maxsize"].default,
            ),
        )


def get_settings(
    path: Optional[str | Path] = None,
    *,
    env: Optional[Mapping[str, str]] = None,
) -> MemorySettings:
    """Return a settings object backed by the shared project configuration."""
    return MemorySettings.from_file(path, env=env)
