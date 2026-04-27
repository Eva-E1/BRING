"""Maintenance helpers for memory ingestion, normalization, and cache invalidation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping, Optional

from llm_gateway.cache import AsyncTTLCache

from .config import MemorySettings


@dataclass(frozen=True)
class EpisodeRecord:
    name: str
    body: str
    reference_time: datetime
    group_id: str = "default"
    uuid: Optional[str] = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object], default_group_id: str) -> "EpisodeRecord":
        return cls(
            name=str(payload["name"]),
            body=str(payload["body"]),
            reference_time=payload["reference_time"],
            group_id=str(payload.get("group_id", default_group_id)),
            uuid=str(payload["uuid"]) if payload.get("uuid") else None,
        )

    @property
    def fingerprint(self) -> str:
        raw = "|".join(
            [
                self.group_id.strip(),
                self.name.strip(),
                self.body.strip(),
                self.reference_time.isoformat(),
            ]
        )
        return hashlib.md5(raw.encode("utf-8")).hexdigest()


class MemoryMaintenance:
    def __init__(self, settings: MemorySettings):
        self._settings = settings
        self._search_cache = AsyncTTLCache(
            maxsize=settings.search_cache_maxsize,
            ttl=settings.search_cache_ttl_seconds,
        )
        self._cache_generation = 0

    def prepare_episode_batch(
        self,
        episodes: Iterable[Mapping[str, object]],
        default_group_id: str,
    ) -> list[EpisodeRecord]:
        deduped: list[EpisodeRecord] = []
        seen: set[str] = set()
        for payload in episodes:
            episode = EpisodeRecord.from_mapping(payload, default_group_id)
            if episode.fingerprint in seen:
                continue
            seen.add(episode.fingerprint)
            deduped.append(episode)
        deduped.sort(key=lambda item: item.reference_time)
        return deduped

    async def get_cached_search(self, cache_key: str) -> Optional[list[dict]]:
        cached = await self._search_cache.get(self._scoped_cache_key(cache_key))
        if cached is None:
            return None
        return [dict(item) for item in cached]

    async def cache_search(self, cache_key: str, results: list[dict]) -> None:
        await self._search_cache.set(
            self._scoped_cache_key(cache_key),
            [dict(item) for item in results],
        )

    def invalidate_search_cache(self) -> None:
        self._cache_generation += 1

    def build_search_cache_key(
        self,
        *,
        query: str,
        group_ids: Optional[list[str]],
        node_labels: Optional[list[str]],
        center_node_uuid: Optional[str],
    ) -> str:
        payload = {
            "query": query.strip(),
            "group_ids": sorted(group_ids or ["default"]),
            "node_labels": sorted(node_labels or []),
            "center_node_uuid": center_node_uuid or "",
            "limit": self._settings.search_result_limit,
        }
        return json.dumps(payload, sort_keys=True)

    def normalize_search_results(self, edges: Iterable[object]) -> list[dict]:
        normalized: list[dict] = []
        seen: set[str] = set()
        for edge in edges:
            edge_uuid = getattr(edge, "uuid", None) or hashlib.md5(str(edge).encode("utf-8")).hexdigest()
            if edge_uuid in seen:
                continue
            seen.add(edge_uuid)
            normalized.append(
                {
                    "uuid": edge_uuid,
                    "source_uuid": getattr(edge, "source_node_uuid", None),
                    "target_uuid": getattr(edge, "target_node_uuid", None),
                    "name": getattr(edge, "name", None),
                    "fact": getattr(edge, "fact", None),
                    "valid_at": self._isoformat(getattr(edge, "valid_at", None)),
                    "invalid_at": self._isoformat(getattr(edge, "invalid_at", None)),
                    "score": float(getattr(edge, "score", 0.0) or 0.0),
                }
            )
        normalized.sort(
            key=lambda item: (
                -item["score"],
                item["valid_at"] or "",
                item["uuid"],
            )
        )
        return normalized[: self._settings.search_result_limit]

    @staticmethod
    def _isoformat(value: object) -> Optional[str]:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    def _scoped_cache_key(self, cache_key: str) -> str:
        return f"{self._cache_generation}:{cache_key}"
