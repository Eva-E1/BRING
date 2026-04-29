#!/usr/bin/env python3
"""
Mushoku Tensei ingestion script with multi‑stage extraction and rich logging.
"""

import asyncio
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Dict, Any

import pdfplumber
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.panel import Panel

from llm_gateway.client import LLMClient
from memory.config import MemorySettings
from memory.engine import MemoryEngine

from .ontology_extended import ENTITY_TYPES_EXTENDED
from .segmentation import segment_text
from .time_parser import estimate_story_time
from .extraction_v2 import structured_extraction_v2
from .graph_builder import build_layered_graph

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True)]
)
logger = logging.getLogger("mushoku_tensei.ingest_v2")

PDF_DIR = Path(__file__).parent / "pdfs"
GROUP_ID = "Mushoku-Tensei"
DATABASE_ID = "mushoku-tensei-v2"
ARCHIVE_NAME = "mushoku-tensei-v2.zip"
CHECKPOINT_DIRNAME = "ingestion_checkpoints"
CHECKPOINT_STATE_NAME = "state.json"
PARTIAL_ARCHIVE_NAME = "mushoku-tensei-v2.partial.zip"
SNAPSHOT_INTERVAL = 25


def validate_gateway_configuration(client: LLMClient) -> None:
    provider_settings = client.config.provider_settings
    embedding_settings = provider_settings.embedding

    if not provider_settings.api_key:
        raise RuntimeError(
            "LLM provider API key is missing. Set `LLM_API_KEY` in your BRING settings or environment before running ingestion."
        )
    if not embedding_settings.api_key:
        raise RuntimeError(
            "Embedding provider API key is missing. Set `LLM_EMBEDDING_API_KEY` or `LLM_API_KEY` before running ingestion."
        )


def checkpoint_dir_for(settings: MemorySettings) -> Path:
    return settings.database_path.parent / CHECKPOINT_DIRNAME


def checkpoint_state_path_for(settings: MemorySettings) -> Path:
    return checkpoint_dir_for(settings) / CHECKPOINT_STATE_NAME


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def compute_text_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_checkpoint_state(settings: MemorySettings) -> dict:
    path = checkpoint_state_path_for(settings)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        broken_path = path.with_suffix(".broken.json")
        path.replace(broken_path)
        return {}


def save_checkpoint_state(settings: MemorySettings, state: dict) -> None:
    path = checkpoint_state_path_for(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now_iso()
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True, default=str), encoding="utf-8")
    tmp_path.replace(path)


def segment_checkpoint_path(settings: MemorySettings, segment_index: int) -> Path:
    return checkpoint_dir_for(settings) / "segments" / f"{segment_index:04d}.json"


def save_segment_checkpoint(settings: MemorySettings, segment_index: int, payload: dict) -> None:
    path = segment_checkpoint_path(settings, segment_index)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    tmp_path.replace(path)


def load_segment_checkpoint(settings: MemorySettings, segment_index: int) -> dict | None:
    path = segment_checkpoint_path(settings, segment_index)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        broken_path = path.with_suffix(".broken.json")
        path.replace(broken_path)
        return None
    story_time = payload.get("story_time")
    if isinstance(story_time, str):
        payload["story_time"] = datetime.fromisoformat(story_time)
    return payload


def build_initial_state(full_text: str, segments: List[dict]) -> dict:
    return {
        "status": "extracting",
        "source_fingerprint": compute_text_fingerprint(full_text),
        "total_segments": len(segments),
        "completed_extraction_indices": [],
        "completed_ingestion_indices": [],
        "last_partial_archive": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def resume_or_initialize_state(settings: MemorySettings, full_text: str, segments: List[dict]) -> dict:
    state = load_checkpoint_state(settings)
    fingerprint = compute_text_fingerprint(full_text)
    if not state or state.get("source_fingerprint") != fingerprint or state.get("total_segments") != len(segments):
        state = build_initial_state(full_text, segments)
        save_checkpoint_state(settings, state)
    return state


def mark_segment_extracted(settings: MemorySettings, state: dict, segment_index: int) -> None:
    completed = set(state.get("completed_extraction_indices", []))
    completed.add(segment_index)
    state["completed_extraction_indices"] = sorted(completed)
    save_checkpoint_state(settings, state)


def mark_segment_ingested(settings: MemorySettings, state: dict, segment_index: int) -> None:
    completed = set(state.get("completed_ingestion_indices", []))
    completed.add(segment_index)
    state["completed_ingestion_indices"] = sorted(completed)
    state["status"] = "ingesting"
    save_checkpoint_state(settings, state)


def all_segments_completed(state: dict) -> bool:
    total = int(state.get("total_segments", 0))
    return len(state.get("completed_ingestion_indices", [])) == total and total > 0


def export_partial_archive(engine: MemoryEngine, archive_path: Path, state: dict, force: bool = False) -> None:
    completed = len(state.get("completed_ingestion_indices", []))
    if completed == 0:
        return
    if not force and completed % SNAPSHOT_INTERVAL != 0:
        return
    archive = engine.database_manager.export_archive(archive_path)
    state["last_partial_archive"] = str(archive)


def checkpoint_metadata(state: dict) -> dict:
    return {
        "ingestion_status": state.get("status"),
        "total_segments": state.get("total_segments", 0),
        "completed_extraction_segments": len(state.get("completed_extraction_indices", [])),
        "completed_ingestion_segments": len(state.get("completed_ingestion_indices", [])),
        "last_partial_archive": state.get("last_partial_archive"),
        "updated_at": state.get("updated_at"),
    }


async def extract_all_text(pdf_dir: Path) -> str:
    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"No PDF files found in {pdf_dir}")
    console.print(f"\n📄 [bold cyan]Found {len(pdf_files)} PDF file(s)[/bold cyan]")
    full_text = []
    for pdf_path in pdf_files:
        console.print(f"   📖 Reading [yellow]{pdf_path.name}[/yellow] ...")
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text.append(text)
    return "\n\n".join(full_text)


async def main():
    console.rule("[bold green]Mushoku Tensei V2 Knowledge Graph Ingester (Multi‑stage)[/bold green]")
    console.print(Panel.fit(
        "Multi‑stage extraction: entities → relationships → time markers\n"
        "Smaller semantic chunks (max 900 chars) for higher accuracy",
        border_style="green"
    ))

    client = LLMClient()
    validate_gateway_configuration(client)
    console.print(f"🤖 LLM Gateway: [cyan]{client.config.provider}[/cyan] / [cyan]{client.config.model}[/cyan]")

    settings = MemorySettings(
        database_id=DATABASE_ID,
        search_result_limit=200,
        timeline_window=1000,
        bulk_ingestion_batch_size=1,
    )
    engine = MemoryEngine(settings, entity_types=ENTITY_TYPES_EXTENDED)
    await engine.start(gateway=client)
    console.print(f"💾 Memory engine ready – database: [green]{settings.normalized_database_id}[/green]")
    archive_path = engine.database_manager.database_dir.parent / ARCHIVE_NAME
    partial_archive_path = engine.database_manager.database_dir.parent / PARTIAL_ARCHIVE_NAME

    try:
        full_text = await extract_all_text(PDF_DIR)
        console.print(f"📊 Total characters extracted: [bold]{len(full_text):,}[/bold]")

        # Segment with smaller chunk size
        segments = await segment_text(full_text, min_chunk_chars=350, max_chunk_chars=900)
        console.print(f"✂️  Segmented into [bold]{len(segments)}[/bold] logical chunks")
        state = resume_or_initialize_state(settings, full_text, segments)

        extracted_data: List[Dict[str, Any]] = []

        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        )
        progress_task = progress.add_task("[cyan]Processing segments...", total=len(segments))
        progress.start()

        segment_stats = []
        completed_extraction = set(state.get("completed_extraction_indices", []))
        for seg in segments:
            checkpoint = load_segment_checkpoint(settings, seg["index"])
            if checkpoint is not None and seg["index"] in completed_extraction:
                extracted_data.append(checkpoint)
                segment_stats.append({
                    "index": seg["index"] + 1,
                    "time": 0.0,
                    "entities": len(checkpoint.get("entities", [])),
                    "edges": len(checkpoint.get("edges", [])),
                    "time_markers": len(checkpoint.get("time_markers", [])),
                })
                progress.advance(progress_task)
                continue

            start_time = time.perf_counter()
            seg_index = seg["index"] + 1
            seg_len = len(seg["text"])
            progress.update(
                progress_task,
                description=f"[cyan]Segment {seg_index}/{len(segments)} (len {seg_len})",
            )

            extraction = await structured_extraction_v2(seg["text"], client)
            story_time = estimate_story_time(seg["index"], extraction.time_markers)
            result = {
                "index": seg["index"],
                "text": seg["text"],
                "clean_text": seg.get("clean_text"),
                "volume": seg.get("volume"),
                "chapter": seg.get("chapter"),
                "heading": seg.get("heading"),
                "scene_index": seg.get("scene_index"),
                "segment_kind": seg.get("segment_kind"),
                "entities": extraction.entities,
                "edges": extraction.edges,
                "time_markers": extraction.time_markers,
                "story_time": story_time,
            }
            save_segment_checkpoint(settings, seg["index"], result)
            mark_segment_extracted(settings, state, seg["index"])

            elapsed = time.perf_counter() - start_time
            console.log(
                f"✅ [green]Segment {seg_index:2d}/{len(segments)}[/green] | "
                f"⏱️ {elapsed:.1f}s | "
                f"🧩 {len(extraction.entities):2d} entities | "
                f"🔗 {len(extraction.edges):2d} edges | "
                f"🕒 {len(extraction.time_markers):2d} time markers | "
                f"📅 {story_time.strftime('%Y-%m-%d %H:%M')}"
            )
            segment_stats.append({
                "index": seg_index,
                "time": elapsed,
                "entities": len(extraction.entities),
                "edges": len(extraction.edges),
                "time_markers": len(extraction.time_markers),
            })
            progress.advance(progress_task)
            extracted_data.append(result)
        progress.stop()
        extracted_data.sort(key=lambda d: d["index"])
        state["status"] = "extracted"
        save_checkpoint_state(settings, state)

        # Summary table
        summary_table = Table(title="📊 Segment processing summary", title_style="bold cyan")
        summary_table.add_column("Segment", style="cyan")
        summary_table.add_column("Time (s)", justify="right")
        summary_table.add_column("Entities", justify="right")
        summary_table.add_column("Edges", justify="right")
        summary_table.add_column("Time markers", justify="right")
        for stat in segment_stats:
            summary_table.add_row(
                str(stat["index"]),
                f"{stat['time']:.1f}",
                str(stat["entities"]),
                str(stat["edges"]),
                str(stat["time_markers"]),
            )
        console.print(summary_table)

        console.print("\n🏗️ Building layered graph payload...")
        graph_payload = build_layered_graph(extracted_data, group_id=GROUP_ID)
        console.print(f"   📦 Graph contains {len(graph_payload)} episodes")

        console.print("💾 Ingesting episodes into memory engine (resumable)...")
        completed_ingestion = set(state.get("completed_ingestion_indices", []))
        for episode, segment in zip(graph_payload, extracted_data, strict=False):
            segment_index = segment["index"]
            if segment_index in completed_ingestion:
                continue
            await engine.add_episodes_bulk([episode], group_id=GROUP_ID)
            mark_segment_ingested(settings, state, segment_index)
            export_partial_archive(engine, partial_archive_path, state)
            save_checkpoint_state(settings, state)

        console.print("🔍 Verifying: searching for 'Rudeus' among Characters...")
        results = await engine.search("Rudeus", group_ids=[GROUP_ID], node_labels=["Character"])
        console.print(f"   ✅ Found [bold]{len(results)}[/bold] entries for 'Rudeus'")
        state["status"] = "complete"
        export_partial_archive(engine, partial_archive_path, state, force=True)
        save_checkpoint_state(settings, state)
        engine.database_manager.write_manifest(
            gateway=client,
            label="Mushoku Tensei V2 (multi‑stage)",
            source="mushoku_tensei",
            metadata={
                "group_id": GROUP_ID,
                "segments": len(graph_payload),
                "pdf_directory": str(PDF_DIR),
                "health": "verified" if all_segments_completed(state) else "partial",
                "checkpoint": checkpoint_metadata(state),
                "verification": {
                    "search_term": "Rudeus",
                    "character_results": len(results),
                },
            },
        )
        console.print("📝 Manifest written to database")

    except Exception as e:
        state = load_checkpoint_state(settings) if checkpoint_state_path_for(settings).exists() else {}
        if state:
            state["status"] = "failed"
            state["last_error"] = str(e)
            save_checkpoint_state(settings, state)
            engine.database_manager.write_manifest(
                gateway=client,
                label="Mushoku Tensei V2 (multi‑stage)",
                source="mushoku_tensei",
                metadata={
                    "group_id": GROUP_ID,
                    "pdf_directory": str(PDF_DIR),
                    "health": "partial",
                    "checkpoint": checkpoint_metadata(state),
                    "last_error": str(e),
                },
            )
        console.print(f"[bold red]❌ ERROR during ingestion: {e}[/bold red]")
        raise
    finally:
        await engine.stop()
        console.print("🛑 Memory engine stopped.")

    if settings.database_path.exists():
        console.print(f"\n🗜️ Compressing database into [yellow]{archive_path.name}[/yellow] ...")
        archive = engine.database_manager.export_archive(archive_path)
        console.print(f"[green]✅ Database exported successfully:[/green] {archive}")
    else:
        console.print("[yellow]⚠️ Database directory not found; skipping export.[/yellow]")

    console.rule("[bold green]Ingestion finished successfully[/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
