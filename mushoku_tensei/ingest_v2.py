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
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Column, Table
from rich.panel import Panel

from llm_gateway.client import LLMClient
from memory.config import MemorySettings
from memory.engine import MemoryEngine

from .ontology_extended import ENTITY_TYPES_EXTENDED
from .segmentation import segment_text
from .time_parser import estimate_story_time
from .extraction_v2 import structured_extraction_v2
from .graph_builder import build_layered_graph

PALETTE = {
    "ink": "#7b6f86",
    "lavender": "#b8a1d9",
    "blush": "#f2c6de",
    "peach": "#f6d1b0",
    "mint": "#b9e3d2",
    "sky": "#b8d8f8",
    "butter": "#f7e5a1",
    "rose": "#e8b4b8",
}

console = Console(soft_wrap=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        RichHandler(
            console=console,
            rich_tracebacks=True,
            markup=True,
            show_path=False,
            omit_repeated_times=False,
        )
    ],
)
logger = logging.getLogger("mushoku_tensei.ingest_v2")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("posthog").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

PDF_DIR = Path(__file__).parent / "pdfs"
GROUP_ID = "Mushoku-Tensei"
DATABASE_ID = "mushoku-tensei-v2"
ARCHIVE_NAME = "mushoku-tensei-v2.zip"
CHECKPOINT_DIRNAME = "ingestion_checkpoints"
CHECKPOINT_STATE_NAME = "state.json"
PARTIAL_ARCHIVE_NAME = "mushoku-tensei-v2.partial.zip"
SNAPSHOT_INTERVAL = 25
MAX_PROVIDER_PARALLELISM = 6


def render_banner() -> None:
    console.rule(f"[bold {PALETTE['lavender']}]Mushoku Tensei V2 Knowledge Graph Ingester[/bold {PALETTE['lavender']}]")
    console.print(
        Panel.fit(
            "[bold #7b6f86]Multi-stage extraction[/bold #7b6f86]\n"
            f"[{PALETTE['ink']}]entities -> relationships -> time markers[/]\n"
            f"[{PALETTE['sky']}]semantic chunks up to 900 chars for cleaner recall[/]",
            border_style=PALETTE["blush"],
            padding=(1, 2),
        )
    )


def build_progress(total_segments: int) -> tuple[Progress, int]:
    progress = Progress(
        SpinnerColumn(style=PALETTE["lavender"]),
        TextColumn(f"[{PALETTE['ink']}]{{task.description}}[/]", table_column=Column(ratio=2, min_width=18)),
        BarColumn(
            bar_width=24,
            style=PALETTE["blush"],
            complete_style=PALETTE["mint"],
            finished_style=PALETTE["mint"],
            pulse_style=PALETTE["sky"],
        ),
        TextColumn(f"[{PALETTE['sky']}]{{task.completed:>3.0f}}/{{task.total:.0f}}[/]"),
        TextColumn(f"[{PALETTE['peach']}]{{task.percentage:>5.1f}}%[/]"),
        TimeElapsedColumn(),
        TextColumn(f"[{PALETTE['ink']}]•[/]"),
        TimeRemainingColumn(),
        console=console,
        expand=True,
    )
    task_id = progress.add_task(f"[{PALETTE['ink']}]warmup[/]", total=total_segments)
    return progress, task_id


def print_segment_result(
    seg_index: int,
    total_segments: int,
    seg_len: int,
    elapsed: float,
    *,
    entity_count: int,
    edge_count: int,
    time_marker_count: int,
    story_time: datetime,
) -> None:
    details = Table.grid(expand=True)
    details.add_column(justify="left", ratio=3)
    details.add_column(justify="right", ratio=2)
    details.add_row(
        f"[bold {PALETTE['lavender']}]Segment {seg_index:03d}/{total_segments}[/]  "
        f"[{PALETTE['ink']}]len {seg_len}[/]",
        f"[{PALETTE['mint']}] {elapsed:>5.1f}s [/]",
    )
    details.add_row(
        f"[{PALETTE['sky']}]entities[/] {entity_count:>2}   "
        f"[{PALETTE['blush']}]edges[/] {edge_count:>2}   "
        f"[{PALETTE['butter']}]time[/] {time_marker_count:>2}",
        f"[{PALETTE['peach']}]{story_time.strftime('%Y-%m-%d %H:%M')}[/]",
    )
    console.print(
        Panel(
            details,
            border_style=PALETTE["blush"],
            padding=(0, 1),
            expand=True,
        )
    )


async def process_segment(
    seg: dict,
    *,
    client: LLMClient,
    settings: MemorySettings,
    state: dict,
    completed_extraction: set[int],
) -> tuple[dict, dict]:
    checkpoint = load_segment_checkpoint(settings, seg["index"])
    if checkpoint is not None and seg["index"] in completed_extraction:
        return checkpoint, {
            "index": seg["index"] + 1,
            "time": 0.0,
            "entities": len(checkpoint.get("entities", [])),
            "edges": len(checkpoint.get("edges", [])),
            "time_markers": len(checkpoint.get("time_markers", [])),
            "segment_length": len(checkpoint.get("text", "")),
            "story_time": checkpoint.get("story_time"),
            "restored": True,
        }

    start_time = time.perf_counter()
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
    completed_extraction.add(seg["index"])

    elapsed = time.perf_counter() - start_time
    return result, {
        "index": seg["index"] + 1,
        "time": elapsed,
        "entities": len(extraction.entities),
        "edges": len(extraction.edges),
        "time_markers": len(extraction.time_markers),
        "segment_length": len(seg["text"]),
        "story_time": story_time,
        "restored": False,
    }


async def extract_segments_adaptive(
    *,
    segments: List[dict],
    client: LLMClient,
    settings: MemorySettings,
    state: dict,
    progress: Progress,
    progress_task: int,
) -> tuple[List[dict], List[dict]]:
    extracted_data: List[dict] = []
    segment_stats: List[dict] = []
    completed_extraction = set(state.get("completed_extraction_indices", []))
    active_tasks: dict[asyncio.Task, dict] = {}
    next_index = 0

    while next_index < len(segments) or active_tasks:
        while next_index < len(segments) and len(active_tasks) < client.recommended_parallelism:
            seg = segments[next_index]
            progress.update(
                progress_task,
                description=f"s{seg['index'] + 1:03d} · {len(seg['text'])}ch · x{client.recommended_parallelism}",
            )
            task = asyncio.create_task(
                process_segment(
                    seg,
                    client=client,
                    settings=settings,
                    state=state,
                    completed_extraction=completed_extraction,
                )
            )
            active_tasks[task] = seg
            next_index += 1

        done, _ = await asyncio.wait(active_tasks.keys(), return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            seg = active_tasks.pop(task)
            try:
                result, stat = task.result()
            except Exception:
                for pending in active_tasks:
                    pending.cancel()
                await asyncio.gather(*active_tasks.keys(), return_exceptions=True)
                raise

            extracted_data.append(result)
            segment_stats.append(stat)
            progress.advance(progress_task)

            if not stat["restored"]:
                print_segment_result(
                    stat["index"],
                    len(segments),
                    stat["segment_length"],
                    stat["time"],
                    entity_count=stat["entities"],
                    edge_count=stat["edges"],
                    time_marker_count=stat["time_markers"],
                    story_time=stat["story_time"],
                )

    extracted_data.sort(key=lambda d: d["index"])
    segment_stats.sort(key=lambda d: d["index"])
    return extracted_data, segment_stats


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
    render_banner()

    client = LLMClient()
    validate_gateway_configuration(client)
    console.print(
        f"[{PALETTE['sky']}]Gateway[/]  "
        f"[bold {PALETTE['ink']}]{client.config.provider}[/]  "
        f"[{PALETTE['ink']}]·[/]  "
        f"[{PALETTE['lavender']}]{client.config.model}[/]"
    )

    settings = MemorySettings(
        database_id=DATABASE_ID,
        search_result_limit=200,
        timeline_window=1000,
        bulk_ingestion_batch_size=1,
    )
    engine = MemoryEngine(settings, entity_types=ENTITY_TYPES_EXTENDED)
    await engine.start(gateway=client)
    console.print(
        f"[{PALETTE['mint']}]Memory[/]  "
        f"[{PALETTE['ink']}]database[/] "
        f"[bold {PALETTE['ink']}]{settings.normalized_database_id}[/]"
    )
    archive_path = engine.database_manager.database_dir.parent / ARCHIVE_NAME
    partial_archive_path = engine.database_manager.database_dir.parent / PARTIAL_ARCHIVE_NAME

    try:
        full_text = await extract_all_text(PDF_DIR)
        console.print(f"[{PALETTE['peach']}]Text[/]  [bold]{len(full_text):,}[/bold] chars extracted")

        # Segment with smaller chunk size
        segments = await segment_text(full_text, min_chunk_chars=350, max_chunk_chars=900)
        console.print(f"[{PALETTE['lavender']}]Chunks[/]  [bold]{len(segments)}[/bold] semantic segments ready")
        state = resume_or_initialize_state(settings, full_text, segments)
        calibrated_parallelism = await client.calibrate_parallelism(max_parallelism=MAX_PROVIDER_PARALLELISM)
        metrics = client.runtime_metrics()
        latency_hint = f"{metrics.ewma_latency:.2f}s" if metrics.ewma_latency is not None else "n/a"
        console.print(
            f"[{PALETTE['sky']}]Provider[/]  adaptive parallelism "
            f"[bold]{calibrated_parallelism}[/bold]  "
            f"[{PALETTE['ink']}]· latency[/] {latency_hint}"
        )

        progress, progress_task = build_progress(len(segments))
        progress.start()
        extracted_data, segment_stats = await extract_segments_adaptive(
            segments=segments,
            client=client,
            settings=settings,
            state=state,
            progress=progress,
            progress_task=progress_task,
        )
        progress.stop()
        state["status"] = "extracted"
        save_checkpoint_state(settings, state)

        # Summary table
        summary_table = Table(
            title="Segment Processing Summary",
            title_style=f"bold {PALETTE['lavender']}",
            border_style=PALETTE["blush"],
        )
        summary_table.add_column("Segment", style=PALETTE["ink"])
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

        console.print(f"\n[{PALETTE['sky']}]Graph[/]  building layered payload...")
        graph_payload = build_layered_graph(extracted_data, group_id=GROUP_ID)
        console.print(f"[{PALETTE['ink']}]Episodes[/]  [bold]{len(graph_payload)}[/bold]")

        console.print(f"[{PALETTE['mint']}]Ingest[/]  writing episodes to memory engine...")
        completed_ingestion = set(state.get("completed_ingestion_indices", []))
        for episode, segment in zip(graph_payload, extracted_data, strict=False):
            segment_index = segment["index"]
            if segment_index in completed_ingestion:
                continue
            await engine.add_episodes_bulk([episode], group_id=GROUP_ID)
            mark_segment_ingested(settings, state, segment_index)
            export_partial_archive(engine, partial_archive_path, state)
            save_checkpoint_state(settings, state)

        console.print(f"[{PALETTE['butter']}]Verify[/]  searching for 'Rudeus' in Character nodes...")
        results = await engine.search("Rudeus", group_ids=[GROUP_ID], node_labels=["Character"])
        console.print(f"[{PALETTE['mint']}]Found[/]  [bold]{len(results)}[/bold] matching entries")
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
        console.print(f"[{PALETTE['sky']}]Manifest[/]  written to database")

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
        console.print(f"[bold {PALETTE['rose']}]Ingestion error:[/] {e}")
        raise
    finally:
        await engine.stop()
        console.print(f"[{PALETTE['rose']}]Memory[/]  engine stopped")

    if settings.database_path.exists():
        console.print(f"\n[{PALETTE['peach']}]Archive[/]  compressing into [bold]{archive_path.name}[/bold]...")
        archive = engine.database_manager.export_archive(archive_path)
        console.print(f"[{PALETTE['mint']}]Exported[/]  {archive}")
    else:
        console.print(f"[{PALETTE['peach']}]Archive[/]  skipped because the database directory was not found")

    console.rule(f"[bold {PALETTE['mint']}]Ingestion finished successfully[/bold {PALETTE['mint']}]")


if __name__ == "__main__":
    asyncio.run(main())
