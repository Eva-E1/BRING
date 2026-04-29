#!/usr/bin/env python3
"""
Small end-to-end Mushoku Tensei pipeline runner.

This mirrors the real ingestion flow on a tiny hand-picked sample so the user
can benchmark the complete stack with a real provider and a real memory
database:

sample text -> segmentation -> extraction -> graph build -> graph validation
-> memory ingestion -> search verification -> manifest/export
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from llm_gateway.client import LLMClient
from memory.config import MemorySettings
from memory.engine import MemoryEngine

from .graph_builder import build_layered_graph
from .ingest_v2 import reconcile_story_times, validate_gateway_configuration
from .ontology_extended import ENTITY_TYPES_EXTENDED
from .segmentation import segment_text
from .time_parser import estimate_story_time
from .extraction_v2 import structured_extraction_v2

console = Console()
GROUP_ID = "Mushoku-Tensei-Sample"
DATABASE_ID = "mushoku-tensei-sample-benchmark"
ARCHIVE_NAME = "mushoku-tensei-sample-benchmark.zip"
REPORT_NAME = "sample_pipeline_report.json"
SAMPLE_TEXT = """
Volume 1

Chapter 1

Rudeus was five years old when Roxy continued his tutoring. She taught him
water magic in the yard every morning, and he quietly practiced voiceless
incantation after memorizing the spell structure.

The next day, Paul watched from a distance while Zenith smiled at Rudeus's
progress. Roxy praised him warmly and told Paul that the boy had unusual talent.

Two years later, Rudeus left home to work as a tutor. He still remembered
Roxy's lessons and regretted how hard it was to leave Sylphie behind.
""".strip()


@dataclass(slots=True)
class StageTiming:
    name: str
    seconds: float


def _stage(started_at: float, name: str) -> StageTiming:
    return StageTiming(name=name, seconds=round(time.perf_counter() - started_at, 3))


def validate_graph_payload(payload: list[dict]) -> list[str]:
    issues: list[str] = []
    seen_episode_names: set[str] = set()

    for episode_index, episode in enumerate(payload, start=1):
        name = str(episode.get("name", "")).strip()
        if not name:
            issues.append(f"Episode {episode_index} is missing a name.")
        elif name in seen_episode_names:
            issues.append(f"Duplicate episode name: {name}")
        else:
            seen_episode_names.add(name)

        if not isinstance(episode.get("reference_time"), datetime):
            issues.append(f"Episode {name or episode_index} has an invalid reference_time.")

        metadata = episode.get("metadata", {}) or {}
        entities = metadata.get("entities", []) or []
        entity_names = {str(entity.get("name", "")).strip().lower() for entity in entities}
        if not entity_names:
            issues.append(f"Episode {name or episode_index} has no extracted entities.")

        for edge in metadata.get("edges", []) or []:
            source = str(edge.get("source_name", "")).strip().lower()
            target = str(edge.get("target_name", "")).strip().lower()
            if source not in entity_names:
                issues.append(f"Episode {name or episode_index} edge source is missing: {edge}")
            if target not in entity_names:
                issues.append(f"Episode {name or episode_index} edge target is missing: {edge}")

    return issues


async def run_sample_pipeline() -> dict[str, Any]:
    timings: list[StageTiming] = []
    client = LLMClient()
    validate_gateway_configuration(client)

    settings = MemorySettings(
        database_id=DATABASE_ID,
        search_result_limit=50,
        timeline_window=50,
        bulk_ingestion_batch_size=1,
    )
    engine = MemoryEngine(settings, entity_types=ENTITY_TYPES_EXTENDED)
    archive_path = engine.database_manager.database_dir.parent / ARCHIVE_NAME
    report_path = engine.database_manager.database_dir.parent / REPORT_NAME

    extraction_results: list[dict[str, Any]] = []
    graph_payload: list[dict[str, Any]] = []
    search_results: list[dict[str, Any]] = []
    graph_issues: list[str] = []

    await engine.start(gateway=client)
    try:
        started_at = time.perf_counter()
        segments = await segment_text(SAMPLE_TEXT, min_chunk_chars=180, max_chunk_chars=450)
        timings.append(_stage(started_at, "segment"))

        started_at = time.perf_counter()
        for segment in segments:
            extraction = await structured_extraction_v2(
                segment["text"],
                client,
                segment_context={
                    "heading": segment.get("heading"),
                    "volume": segment.get("volume"),
                    "chapter": segment.get("chapter"),
                    "scene_index": segment.get("scene_index"),
                    "previous_excerpt": segment.get("previous_excerpt"),
                    "next_excerpt": segment.get("next_excerpt"),
                },
            )
            extraction_results.append(
                {
                    "index": segment["index"],
                    "text": segment["text"],
                    "clean_text": segment.get("clean_text"),
                    "volume": segment.get("volume"),
                    "chapter": segment.get("chapter"),
                    "heading": segment.get("heading"),
                    "scene_index": segment.get("scene_index"),
                    "segment_kind": segment.get("segment_kind"),
                    "previous_excerpt": segment.get("previous_excerpt"),
                    "next_excerpt": segment.get("next_excerpt"),
                    "entities": extraction.entities,
                    "edges": extraction.edges,
                    "time_markers": extraction.time_markers,
                    "story_time": estimate_story_time(segment["index"], extraction.time_markers),
                    "extraction_metadata": {
                        "provider": client.config.provider,
                        "model": client.config.model,
                    },
                }
            )
        reconcile_story_times(extraction_results)
        timings.append(_stage(started_at, "extract"))

        started_at = time.perf_counter()
        graph_payload = build_layered_graph(extraction_results, group_id=GROUP_ID)
        timings.append(_stage(started_at, "graph_build"))

        started_at = time.perf_counter()
        graph_issues = validate_graph_payload(graph_payload)
        timings.append(_stage(started_at, "graph_validate"))
        if graph_issues:
            raise RuntimeError("Graph validation failed:\n- " + "\n- ".join(graph_issues))

        started_at = time.perf_counter()
        await engine.add_episodes_bulk(graph_payload, group_id=GROUP_ID)
        timings.append(_stage(started_at, "ingest"))

        started_at = time.perf_counter()
        search_results = await engine.search("Rudeus", group_ids=[GROUP_ID], node_labels=["Character"])
        timings.append(_stage(started_at, "verify_search"))

        engine.database_manager.write_manifest(
            gateway=client,
            label="Mushoku Tensei Sample Benchmark",
            source="mushoku_tensei.sample_pipeline",
            metadata={
                "group_id": GROUP_ID,
                "segments": len(extraction_results),
                "episodes": len(graph_payload),
                "search_term": "Rudeus",
                "character_results": len(search_results),
                "timings": [asdict(item) for item in timings],
                "graph_validation": {"issues": graph_issues, "passed": not graph_issues},
            },
        )
        archive = engine.database_manager.export_archive(archive_path)

        report = {
            "database_id": settings.normalized_database_id,
            "database_path": str(settings.database_path),
            "archive_path": str(archive),
            "segments": len(extraction_results),
            "episodes": len(graph_payload),
            "entity_count": sum(len(item.get("entities", [])) for item in extraction_results),
            "edge_count": sum(len(item.get("edges", [])) for item in extraction_results),
            "time_marker_count": sum(len(item.get("time_markers", [])) for item in extraction_results),
            "search_results": len(search_results),
            "timings": [asdict(item) for item in timings],
            "graph_validation": {"passed": not graph_issues, "issues": graph_issues},
            "extraction_results": extraction_results,
        }
        report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        return report
    finally:
        await engine.stop()


def print_report(report: dict[str, Any]) -> None:
    console.rule("[bold cyan]Mushoku Sample Pipeline Benchmark[/bold cyan]")
    summary = Table(show_header=False)
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", style="white")
    summary.add_row("Database", report["database_id"])
    summary.add_row("Segments", str(report["segments"]))
    summary.add_row("Episodes", str(report["episodes"]))
    summary.add_row("Entities", str(report["entity_count"]))
    summary.add_row("Edges", str(report["edge_count"]))
    summary.add_row("Time markers", str(report["time_marker_count"]))
    summary.add_row("Search results", str(report["search_results"]))
    summary.add_row("Graph valid", str(report["graph_validation"]["passed"]))
    summary.add_row("Database path", report["database_path"])
    summary.add_row("Archive path", report["archive_path"])
    console.print(summary)

    timings = Table(title="Stage Timings")
    timings.add_column("Stage", style="cyan")
    timings.add_column("Seconds", justify="right")
    for item in report["timings"]:
        timings.add_row(item["name"], f"{item['seconds']:.3f}")
    console.print(timings)


async def main() -> None:
    report = await run_sample_pipeline()
    print_report(report)


if __name__ == "__main__":
    asyncio.run(main())
