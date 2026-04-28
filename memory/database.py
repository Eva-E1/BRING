"""Portable multi-database helpers for isolated BRING memory stores."""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from llm_gateway.client import LLMClient

from .config import MemorySettings

SCHEMA_VERSION = 1


class DatabaseManifest(BaseModel):
    schema_version: int = SCHEMA_VERSION
    database_id: str
    label: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    source: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dimensions: Optional[int] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryDatabaseManager:
    """Creates isolated database layouts and portable archives."""

    def __init__(self, settings: MemorySettings):
        self._settings = settings

    @property
    def database_dir(self) -> Path:
        return self._settings.database_path.parent

    @property
    def kuzu_path(self) -> Path:
        return self._settings.database_path

    @property
    def manifest_path(self) -> Path:
        return self._settings.manifest_path

    def ensure_layout(self) -> None:
        self.kuzu_path.mkdir(parents=True, exist_ok=True)
        self._settings.attachments_path.mkdir(parents=True, exist_ok=True)

    def write_manifest(
        self,
        *,
        gateway: Optional[LLMClient] = None,
        label: Optional[str] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DatabaseManifest:
        self.ensure_layout()
        manifest = self._build_manifest(
            gateway=gateway,
            label=label,
            source=source,
            metadata=metadata or {},
        )
        self.manifest_path.write_text(
            json.dumps(manifest.model_dump(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return manifest

    def load_manifest(self) -> Optional[DatabaseManifest]:
        if not self.manifest_path.exists():
            return None
        return DatabaseManifest.model_validate_json(self.manifest_path.read_text(encoding="utf-8"))

    def export_archive(self, destination: Optional[str | Path] = None) -> Path:
        self.ensure_layout()
        archive_path = Path(destination) if destination is not None else self.database_dir.with_suffix(".zip")
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(self.database_dir.rglob("*")):
                if path.is_dir():
                    continue
                archive.write(path, arcname=path.relative_to(self.database_dir))
        return archive_path

    @classmethod
    def import_archive(
        cls,
        archive_path: str | Path,
        settings: MemorySettings,
        *,
        database_id: Optional[str] = None,
    ) -> "MemoryDatabaseManager":
        manager = cls(
            settings.model_copy(
                update={"database_id": database_id or settings.database_id, "kuzu_db_path": None}
            )
        )
        manager.ensure_layout()
        with zipfile.ZipFile(Path(archive_path), mode="r") as archive:
            archive.extractall(manager.database_dir)
        if database_id is not None:
            manifest = manager.load_manifest()
            if manifest is not None:
                manifest.database_id = manager._settings.normalized_database_id
                manager.manifest_path.write_text(
                    json.dumps(manifest.model_dump(), indent=2, sort_keys=True),
                    encoding="utf-8",
                )
        return manager

    def clone_database(self, database_id: str) -> "MemoryDatabaseManager":
        target_settings = self._settings.model_copy(update={"database_id": database_id, "kuzu_db_path": None})
        target_manager = MemoryDatabaseManager(target_settings)
        if target_manager.database_dir.exists():
            raise FileExistsError(f"Target database already exists: {target_manager.database_dir}")
        shutil.copytree(self.database_dir, target_manager.database_dir)
        manifest = target_manager.load_manifest()
        if manifest is not None:
            manifest.database_id = target_manager._settings.normalized_database_id
            target_manager.manifest_path.write_text(
                json.dumps(manifest.model_dump(), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return target_manager

    def _build_manifest(
        self,
        *,
        gateway: Optional[LLMClient],
        label: Optional[str],
        source: Optional[str],
        metadata: Dict[str, Any],
    ) -> DatabaseManifest:
        llm_provider = llm_model = embedding_provider = embedding_model = None
        embedding_dimensions = None
        if gateway is not None:
            provider_settings = gateway.config.provider_settings
            llm_provider = gateway.config.provider
            llm_model = gateway.config.model
            embedding_provider = provider_settings.embedding.provider
            embedding_model = provider_settings.embedding.model
            embedding_dimensions = provider_settings.embedding.dimensions
        return DatabaseManifest(
            database_id=self._settings.normalized_database_id,
            label=label or self._settings.normalized_database_id,
            source=source,
            llm_provider=llm_provider,
            llm_model=llm_model,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
            metadata=metadata,
        )
