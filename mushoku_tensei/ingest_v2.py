#!/usr/bin/env python3
"""
Mushoku Tensei ingestion script with multi‑stage extraction and rich logging.
Enhanced with live calibration, per‑segment stage progress, and rolling summary.
"""

import asyncio
import hashlib
import json
import logging
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

import pdfplumber
from rich.box import SIMPLE_HEAD
from rich.columns import Columns
from rich.console import Console, Group
from rich.live import Live
from rich.logging import RichHandler
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskID,
)
from rich.table import Column, Table
from rich.panel import Panel
from rich.text import Text

from llm_gateway.client import LLMClient
from memory.config import MemorySettings
from memory.engine import MemoryEngine

from .ontology_extended import ENTITY_TYPES_EXTENDED
from .segmentation import _is_japanese_heavy_text, segment_text
from .time_parser import TimelineBuilder, detect_large_timeline_jump, estimate_story_time
from .extraction_v2 import _build_extraction_units, _unit_likely_contains_time_cues, structured_extraction_v2
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
PRECHECK_STATE_NAME = "preflight_tests.json"
PARTIAL_ARCHIVE_NAME = "mushoku-tensei-v2.partial.zip"
SNAPSHOT_INTERVAL = 25
MAX_PROVIDER_PARALLELISM = 6
EXTRACTION_TIMEOUT_SECONDS = 120
MAX_SEGMENT_RETRIES = 2
LOW_CONFIDENCE_SEGMENT_CHARS = 650
LOW_CONFIDENCE_MIN_ENTITIES = 1


def render_banner() -> None:
    console.rule(f"[bold {PALETTE['lavender']}]Mushoku Tensei V2 Knowledge Graph Ingester[/bold {PALETTE['lavender']}]")


# ------------------- Rich UI -------------------
def _build_step_progress() -> Progress:
    return Progress(
        SpinnerColumn(style=PALETTE["lavender"]),
        TextColumn("{task.description}", table_column=Column(ratio=3, min_width=18)),
        BarColumn(
            bar_width=14,
            style=PALETTE["blush"],
            complete_style=PALETTE["mint"],
            finished_style=PALETTE["mint"],
            pulse_style=PALETTE["sky"],
        ),
        TextColumn(f"[{PALETTE['sky']}]{{task.completed:>3.0f}}/{{task.total:.0f}}[/]"),
        console=console,
        expand=True,
    )


def _build_position_progress() -> Progress:
    return Progress(
        TextColumn(f"[{PALETTE['ink']}]{{task.description}}[/]", table_column=Column(ratio=3, min_width=18)),
        BarColumn(
            bar_width=26,
            style=PALETTE["blush"],
            complete_style=PALETTE["sky"],
            finished_style=PALETTE["mint"],
            pulse_style=PALETTE["lavender"],
        ),
        TextColumn(f"[{PALETTE['peach']}]{{task.completed:>3.0f}}/{{task.total:.0f}}[/]"),
        console=console,
        expand=True,
    )


def _build_worker_progress() -> Progress:
    return Progress(
        TextColumn(f"[{PALETTE['ink']}]{{task.description}}[/]", table_column=Column(ratio=4, min_width=24)),
        BarColumn(
            bar_width=8,
            style=PALETTE["blush"],
            complete_style=PALETTE["lavender"],
            finished_style=PALETTE["mint"],
            pulse_style=PALETTE["sky"],
        ),
        TextColumn(f"[{PALETTE['peach']}]{{task.completed:>1.0f}}/{{task.total:.0f}}[/]"),
        console=console,
        expand=True,
    )


def _format_eta(completed: int, total: int, started_at: float | None) -> str:
    if started_at is None or completed <= 0 or total <= completed:
        return "n/a"
    elapsed = max(0.0, time.perf_counter() - started_at)
    rate = elapsed / completed if completed else 0.0
    remaining = max(0, total - completed)
    eta_seconds = int(rate * remaining)
    minutes, seconds = divmod(eta_seconds, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {seconds:02d}s"


def _is_nonstandard_openai_model(model: str) -> bool:
    normalized = (model or "").strip().lower()
    if not normalized:
        return False
    standard_prefixes = ("gpt-", "o1", "o3", "o4", "text-embedding-", "omni-")
    return not normalized.startswith(standard_prefixes)


def _resolve_extraction_parallelism(client: LLMClient, calibrated_parallelism: int) -> tuple[int, str]:
    model = client.config.model
    base_url = (client.config.provider_settings.base_url or "").strip().lower()
    is_custom_endpoint = bool(base_url) and "api.openai.com" not in base_url
    if client.config.runtime_provider == "openai" and (_is_nonstandard_openai_model(model) or is_custom_endpoint):
        return max(2, min(4, calibrated_parallelism)), "compat-safe"
    return calibrated_parallelism, "native"


def estimate_extraction_work_units(segments: List[dict], *, max_unit_chars: int = 700) -> int:
    total = 0
    for segment in segments:
        total += estimate_segment_work_units(segment, max_unit_chars=max_unit_chars)
    return max(1, total)


def estimate_segment_work_units(segment: dict, *, max_unit_chars: int = 700) -> int:
    total = 0
    units = _build_extraction_units(str(segment.get("text") or ""), max_unit_chars=max_unit_chars)
    for _unit in units:
        total += 3  # entities + relationships + time/skip decision
    return max(1, total)


@contextmanager
def quiet_live_logging():
    targets = [
        logging.getLogger("mushoku_tensei.segmentation"),
        logging.getLogger("llm_gateway.client"),
        logging.getLogger("memory.engine"),
    ]
    previous = [(target, target.level) for target in targets]
    try:
        for target, _ in previous:
            target.setLevel(logging.WARNING)
        yield
    finally:
        for target, level in previous:
            target.setLevel(level)


class IngestUX:
    def __init__(self, *, total_segments: int):
        self.total_segments = total_segments
        self.phase = "Starting"
        self.status = "Preparing pipeline"
        self.gateway_summary = "uninitialized"
        self.gateway_mode = "detecting"
        self.memory_summary = "uninitialized"
        self.active_workers: dict[int, dict[str, Any]] = {}
        self.completed_rows: list[dict[str, str]] = []
        self.calibration_rows: dict[int, dict[str, str]] = {}
        self.graph_summary: dict[str, str] = {}
        self.extraction_started_at: float | None = None
        self.ingestion_started_at: float | None = None
        self.step_progress = _build_step_progress()
        self.position_progress = _build_position_progress()

        self.task_boot_validate = self.step_progress.add_task("Validate config", total=1)
        self.task_boot_preflight = self.step_progress.add_task("Run self-tests", total=1)
        self.task_boot_memory = self.step_progress.add_task("Start memory", total=1)
        self.task_pdf_scan = self.step_progress.add_task("Scan PDFs", total=1)
        self.task_pdf_extract = self.step_progress.add_task("Extract pages", total=1)
        self.task_segment_split = self.step_progress.add_task("Split sections", total=1)
        self.task_segment_resume = self.step_progress.add_task("Load checkpoints", total=1)
        self.task_calibrate_probe = self.step_progress.add_task("Probe provider", total=1)
        self.task_calibrate_apply = self.step_progress.add_task("Apply parallelism", total=1)
        self.task_extract = self.step_progress.add_task("Extract segments", total=max(1, total_segments))
        self.task_graph = self.step_progress.add_task("Build graph", total=1)
        self.task_ingest_plan = self.step_progress.add_task("Plan batches", total=1)
        self.task_ingest = self.step_progress.add_task("Ingest to memory", total=max(1, total_segments))
        self.task_verify_search = self.step_progress.add_task("Verify search", total=1)
        self.task_verify_manifest = self.step_progress.add_task("Write manifest", total=1)
        self.task_archive = self.step_progress.add_task("Export archive", total=1)
        self.task_position = self.position_progress.add_task("Waiting", total=max(1, total_segments * 3 + 10))
        self.live = Live(
            self.render(),
            refresh_per_second=8,
            auto_refresh=True,
            console=console,
            transient=False,
        )

    async def __aenter__(self) -> "IngestUX":
        self.live.__enter__()
        self.refresh(force=True)
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.live.__exit__(*exc)

    def refresh(self, *, force: bool = False) -> None:
        self.live.update(self.render(), refresh=force)

    def render(self) -> Group:
        return Group(
            Panel(self._render_header(), border_style=PALETTE["blush"], padding=(0, 1)),
            Panel(self.position_progress, title="Now", title_align="left", border_style=PALETTE["sky"], padding=(0, 1)),
            Columns(
                [
                    Panel(self.step_progress, title="Pipeline", title_align="left", border_style=PALETTE["lavender"], padding=(0, 1)),
                    Panel(self._render_workers(), title="Active Scenes", title_align="left", border_style=PALETTE["mint"], padding=(0, 1)),
                ],
                equal=True,
                expand=True,
            ),
            Columns(
                [
                    Panel(self._render_story_signals(), title="Story Signals", title_align="left", border_style=PALETTE["peach"], padding=(0, 1)),
                    Panel(self._render_system_snapshot(), title="Graph & Runtime", title_align="left", border_style=PALETTE["butter"], padding=(0, 1)),
                ],
                equal=True,
                expand=True,
            ),
        )

    def _render_header(self) -> Text:
        text = Text()
        text.append("Phase ", style=f"bold {PALETTE['ink']}")
        text.append(self.phase, style=f"bold {PALETTE['lavender']}")
        text.append("  •  ", style=PALETTE["ink"])
        text.append(self.status, style=PALETTE["ink"])
        text.append("\n")
        text.append("Gateway ", style=PALETTE["sky"])
        text.append(self.gateway_summary, style=PALETTE["ink"])
        text.append("  •  ", style=PALETTE["ink"])
        text.append("Mode ", style=PALETTE["butter"])
        text.append(self.gateway_mode, style=PALETTE["ink"])
        text.append("  •  ", style=PALETTE["ink"])
        text.append("Memory ", style=PALETTE["mint"])
        text.append(self.memory_summary, style=PALETTE["ink"])
        text.append("\n")
        text.append("ETA ", style=PALETTE["peach"])
        text.append(
            f"extract {self.extract_eta()}  •  ingest {self.ingest_eta()}",
            style=PALETTE["ink"],
        )
        text.append("\n")
        return text

    def _render_workers(self) -> Table:
        table = Table(box=SIMPLE_HEAD, expand=True, show_header=False, padding=(0, 1))
        table.add_column("Seg", justify="right", style=PALETTE["lavender"], width=6)
        table.add_column("Stage", style=PALETTE["ink"])
        table.add_column("Bar", justify="left", width=12)
        table.add_column("Done", justify="right", style=PALETTE["peach"], width=4)

        worker_items = sorted(
            self.active_workers.values(),
            key=lambda item: (item["priority"], item["segment"]),
        )[:4]
        if not worker_items:
            table.add_row("—", "waiting", "", "—")
            return table

        for item in worker_items:
            filled = min(3, max(0, int(item["completed"])))
            bar = "━" * filled + "─" * (3 - filled)
            table.add_row(
                f"{item['segment']:03d}",
                f"v{item.get('volume', '?')} · c{item.get('chapter', '?')} · {item['stage']}",
                bar,
                f"{filled}/3",
            )
        return table

    def _render_story_signals(self) -> Table:
        recent = Table(box=SIMPLE_HEAD, expand=True, show_header=False, padding=(0, 1))
        recent.add_column("Seg", justify="right", style=PALETTE["lavender"], width=6)
        recent.add_column("Scene", style=PALETTE["ink"], ratio=2)
        recent.add_column("Signals", style=PALETTE["peach"], ratio=2)
        if self.completed_rows:
            for row in self.completed_rows:
                recent.add_row(
                    row["segment"],
                    row["scene"],
                    row["signals"],
                )
        else:
            recent.add_row("—", "waiting", "No extracted story signals yet")
        return recent

    def _render_system_snapshot(self) -> Table:
        table = Table(box=SIMPLE_HEAD, expand=True, show_header=False, padding=(0, 1))
        table.add_column("Label", style=PALETTE["ink"], width=14)
        table.add_column("Value", style=PALETTE["ink"])

        if self.calibration_rows:
            best_level = max(self.calibration_rows)
            row = self.calibration_rows[best_level]
            calibration_value = f"level {best_level} • {row['successes']}/{row['samples']} • {row['elapsed']}s"
        else:
            calibration_value = "waiting"
        table.add_row("Calibration", calibration_value)
        table.add_row("Extraction ETA", self.extract_eta())
        table.add_row("Ingestion ETA", self.ingest_eta())
        if self.graph_summary:
            for key in ("layers", "types", "episodes"):
                value = self.graph_summary.get(key)
                if value:
                    table.add_row(key.capitalize(), value)
        else:
            table.add_row("Graph", "Graph summary appears after graph build")
        return table

    def set_phase(self, phase: str, status: str) -> None:
        self.phase = phase
        self.status = status
        self.refresh(force=True)

    def set_gateway_summary(self, provider: str, model: str, *, parallelism: Optional[int] = None, latency: str = "n/a") -> None:
        summary = f"{provider} · {model}"
        if parallelism is not None:
            summary += f" · x{parallelism} · {latency}"
        self.gateway_summary = summary
        self.refresh()

    def set_gateway_mode(self, mode: str) -> None:
        self.gateway_mode = mode
        self.refresh()

    def set_memory_summary(self, database_id: str, *, batch_size: Optional[int] = None) -> None:
        summary = database_id
        if batch_size is not None:
            summary += f" · batch={batch_size}"
        self.memory_summary = summary
        self.refresh()

    def finish_task(self, task_id: TaskID, *, status: Optional[str] = None) -> None:
        self.step_progress.update(task_id, completed=self.step_progress.tasks[task_id].total)
        if status is not None:
            self.status = status
        self.advance_position("Step complete")
        self.refresh(force=True)

    def advance_extract(self, amount: int = 1) -> None:
        self.step_progress.advance(self.task_extract, amount)
        self.refresh()

    def advance_ingest(self, amount: int = 1) -> None:
        self.step_progress.advance(self.task_ingest, amount)
        self.refresh()

    def start_extraction_clock(self) -> None:
        if self.extraction_started_at is None:
            self.extraction_started_at = time.perf_counter()
            self.refresh()

    def start_ingestion_clock(self) -> None:
        if self.ingestion_started_at is None:
            self.ingestion_started_at = time.perf_counter()
            self.refresh()

    def extract_eta(self) -> str:
        task = self.step_progress.tasks[self.task_extract]
        return _format_eta(int(task.completed), int(task.total), self.extraction_started_at)

    def ingest_eta(self) -> str:
        task = self.step_progress.tasks[self.task_ingest]
        return _format_eta(int(task.completed), int(task.total), self.ingestion_started_at)

    def set_position(self, description: str) -> None:
        self.position_progress.update(self.task_position, description=description)
        self.refresh()

    def advance_position(self, description: str, amount: int = 1) -> None:
        self.position_progress.advance(self.task_position, amount)
        self.position_progress.update(self.task_position, description=description)
        self.refresh()

    def update_calibration(self, data: dict[str, Any]) -> None:
        if data["event"] == "calibration_start":
            self.calibration_rows[data["level"]] = {
                "samples": "0",
                "successes": "0",
                "elapsed": "0.00",
                "status": "…",
            }
        elif data["event"] == "calibration_result":
            self.calibration_rows[data["level"]] = {
                "samples": str(data["samples"]),
                "successes": str(data["successes"]),
                "elapsed": f"{data['elapsed']:.2f}",
                "status": "ok" if data["successes"] == data["samples"] else "limit",
            }
        elif data["event"] == "calibration_complete":
            self.status = f"Provider calibrated at x{data['parallelism']}"
        self.set_position(f"Calibration level {data.get('level', data.get('parallelism', 'done'))}")

    def bind_segment(self, seg: dict) -> TaskID:
        segment_number = seg["index"] + 1
        self.active_workers[seg["index"]] = {
            "segment": segment_number,
            "stage": "queued",
            "completed": 0,
            "volume": seg.get("volume") or "—",
            "chapter": seg.get("chapter") or "—",
            "priority": segment_number,
        }
        self.refresh()
        return seg["index"]

    def release_segment(self, seg_index: int) -> None:
        self.active_workers.pop(seg_index, None)
        self.refresh()

    def update_segment_stage(self, seg: dict, data: dict[str, Any]) -> None:
        worker = self.active_workers.get(seg["index"])
        if worker is None:
            return
        if data["event"] == "stage_start":
            stage = data["stage"]
            stage_map = {"entities": (0, "entities"), "relationships": (1, "relations"), "time": (2, "time")}
            if stage in stage_map:
                completed, label = stage_map[stage]
                worker["completed"] = completed
                worker["stage"] = label
                worker["priority"] = completed
                self.set_position(f"Segment {seg['index'] + 1:03d} · {label}")
        elif data["event"] == "stage_end":
            stage_map = {"entities": 1, "relationships": 2, "time": 3}
            stage = data["stage"]
            if stage in stage_map:
                worker["completed"] = stage_map[stage]
                worker["priority"] = stage_map[stage]
                self.advance_position(f"Segment {seg['index'] + 1:03d} · {stage}")
        elif data["event"] == "stage_skip":
            stage = data.get("stage", "stage")
            if stage == "relationships":
                worker["completed"] = max(int(worker["completed"]), 2)
            elif stage == "time":
                worker["completed"] = 3
            worker["stage"] = f"skip {stage}"
            worker["priority"] = int(worker["completed"])
            self.advance_position(f"Segment {seg['index'] + 1:03d} · skip {stage}")
        elif data["event"] == "segment_complete":
            worker["completed"] = 3
            worker["stage"] = "done"
            worker["priority"] = 99
        self.refresh()

    def record_segment_completion(self, stat: dict) -> None:
        state = "restored" if stat["restored"] else "new"
        scene = f"v{stat.get('volume', '—')} · c{stat.get('chapter', '—')} · {state}"
        signals = f"{stat['entities']}E/{stat['edges']}R/{stat['time_markers']}T"
        key_entities = stat.get("key_entities") or "No key entities"
        time_hint = stat.get("time_hint") or stat["story_time"].strftime("%Y-%m-%d")
        self.completed_rows.insert(
            0,
            {
                "segment": f"{stat['index']:03d}",
                "scene": scene,
                "signals": f"{signals} • {key_entities} • {time_hint}",
            },
        )
        self.completed_rows = self.completed_rows[:5]
        self.refresh()

    def record_graph_summary(self, graph_payload: List[dict]) -> None:
        layer_counts = {"fact": 0, "rule": 0, "story": 0, "concept": 0}
        type_counts: dict[str, int] = {}
        for episode in graph_payload:
            for entity in episode.get("metadata", {}).get("entities", []):
                layer = str(entity.get("attributes", {}).get("layer", "fact"))
                layer_counts[layer] = layer_counts.get(layer, 0) + 1
                entity_type = str(entity.get("entity_type", "Unknown"))
                type_counts[entity_type] = type_counts.get(entity_type, 0) + 1

        top_types = sorted(type_counts.items(), key=lambda item: (-item[1], item[0]))[:3]
        self.graph_summary = {
            "episodes": str(len(graph_payload)),
            "layers": " · ".join(f"{name[0].upper()}={count}" for name, count in layer_counts.items() if count),
            "types": " · ".join(f"{name}:{count}" for name, count in top_types) or "n/a",
        }
        self.refresh(force=True)


class SegmentStageProgress:
    def __init__(self, ui: IngestUX, seg: dict):
        self.ui = ui
        self.seg = seg

    async def on_stage_event(self, data: dict) -> None:
        self.ui.update_segment_stage(self.seg, data)
        if data["event"] in {"stage_end", "stage_skip"}:
            self.ui.advance_extract()


async def calibrate_with_live_display(
    client: LLMClient,
    ui: IngestUX,
    max_parallelism: int = 6,
) -> int:
    def callback(data: dict[str, Any]) -> None:
        ui.update_calibration(data)

    return await client.calibrate_parallelism(
        max_parallelism=max_parallelism,
        samples_per_level=1,
        progress_callback=callback,
    )


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
    # This function is kept for compatibility but not used in the new live summary.
    pass


def _top_entity_names(entities: List[dict], limit: int = 2) -> str:
    names = [str(entity.get("name", "")).strip() for entity in entities if str(entity.get("name", "")).strip()]
    deduped: list[str] = []
    seen: set[str] = set()
    for name in names:
        normalized = name.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(name)
        if len(deduped) >= limit:
            break
    return ", ".join(deduped)


async def process_segment(
    seg: dict,
    *,
    client: LLMClient,
    settings: MemorySettings,
    state: dict,
    completed_extraction: set[int],
    stage_progress: Optional[SegmentStageProgress] = None,
) -> tuple[dict, dict]:
    segment_fingerprint = compute_segment_fingerprint(seg["text"])
    checkpoint = load_segment_checkpoint(
        settings,
        seg["index"],
        expected_fingerprint=segment_fingerprint,
    )
    if checkpoint is not None and seg["index"] in completed_extraction:
        return checkpoint, {
            "index": seg["index"] + 1,
            "time": 0.0,
            "entities": len(checkpoint.get("entities", [])),
            "edges": len(checkpoint.get("edges", [])),
            "time_markers": len(checkpoint.get("time_markers", [])),
            "segment_length": len(checkpoint.get("text", "")),
            "story_time": checkpoint.get("story_time"),
            "volume": checkpoint.get("volume"),
            "chapter": checkpoint.get("chapter"),
            "key_entities": _top_entity_names(checkpoint.get("entities", [])),
            "time_hint": next(iter(checkpoint.get("time_markers", [])), ""),
            "restored": True,
            "work_units": estimate_segment_work_units(seg),
        }

    start_time = time.perf_counter()
    extraction, extraction_metadata = await _extract_segment_with_retries(
        seg,
        client=client,
        stage_progress=stage_progress,
    )
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
        "previous_excerpt": seg.get("previous_excerpt"),
        "next_excerpt": seg.get("next_excerpt"),
        "entities": extraction.entities,
        "edges": extraction.edges,
        "time_markers": extraction.time_markers,
        "story_time": story_time,
        "segment_fingerprint": segment_fingerprint,
        "extraction_metadata": extraction_metadata,
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
        "volume": seg.get("volume"),
        "chapter": seg.get("chapter"),
        "key_entities": _top_entity_names(extraction.entities),
        "time_hint": next(iter(extraction.time_markers), ""),
        "restored": False,
        "work_units": estimate_segment_work_units(seg),
    }


async def extract_segments_adaptive(
    *,
    segments: List[dict],
    client: LLMClient,
    settings: MemorySettings,
    state: dict,
    ui: IngestUX,
) -> tuple[List[dict], List[dict]]:
    extracted_data = []
    segment_stats = []
    completed_extraction = set(state.get("completed_extraction_indices", []))
    active_tasks: dict[asyncio.Task, dict] = {}
    next_index = 0
    worker_limit = max(1, client.recommended_parallelism)

    while next_index < len(segments) or active_tasks:
        while next_index < len(segments) and len(active_tasks) < worker_limit:
            seg = segments[next_index]
            ui.set_phase(
                "Extraction",
                f"Running {len(active_tasks) + 1}/{worker_limit} segment workers",
            )
            ui.bind_segment(seg)
            stage_progress = SegmentStageProgress(ui, seg)
            task = asyncio.create_task(
                process_segment(
                    seg,
                    client=client,
                    settings=settings,
                    state=state,
                    completed_extraction=completed_extraction,
                    stage_progress=stage_progress,
                )
            )
            active_tasks[task] = {"seg": seg}
            next_index += 1

        done, _ = await asyncio.wait(active_tasks.keys(), return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            info = active_tasks.pop(task)
            seg = info["seg"]
            try:
                result, stat = task.result()
            except Exception:
                ui.release_segment(seg["index"])
                for pending in active_tasks:
                    pending.cancel()
                await asyncio.gather(*active_tasks.keys(), return_exceptions=True)
                raise

            extracted_data.append(result)
            segment_stats.append(stat)
            if stat.get("restored"):
                ui.advance_extract(int(stat.get("work_units", 1)))
            ui.record_segment_completion(stat)
            ui.release_segment(seg["index"])

    extracted_data.sort(key=lambda d: d["index"])
    segment_stats.sort(key=lambda d: d["index"])
    return extracted_data, segment_stats


# ------------------- Remainder of script (unchanged except calibration call) -------------------
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


def preflight_state_path_for(settings: MemorySettings) -> Path:
    return checkpoint_dir_for(settings) / PRECHECK_STATE_NAME


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def compute_text_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_segment_fingerprint(segment_text: str) -> str:
    return hashlib.sha256(segment_text.encode("utf-8")).hexdigest()


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


def load_preflight_state(settings: MemorySettings) -> dict:
    path = preflight_state_path_for(settings)
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


def save_preflight_state(settings: MemorySettings, state: dict) -> None:
    path = preflight_state_path_for(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
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


def load_segment_checkpoint(
    settings: MemorySettings,
    segment_index: int,
    *,
    expected_fingerprint: Optional[str] = None,
) -> dict | None:
    path = segment_checkpoint_path(settings, segment_index)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        broken_path = path.with_suffix(".broken.json")
        path.replace(broken_path)
        return None
    if expected_fingerprint and payload.get("segment_fingerprint") != expected_fingerprint:
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


def iter_ingestion_batches(
    graph_payload: List[dict],
    extracted_data: List[dict],
    completed_ingestion: set[int],
    *,
    batch_size: int,
) -> List[tuple[List[dict], List[int]]]:
    pending: List[tuple[dict, int]] = []
    for episode, segment in zip(graph_payload, extracted_data, strict=False):
        segment_index = int(segment["index"])
        if segment_index in completed_ingestion:
            continue
        pending.append((episode, segment_index))

    batches: List[tuple[List[dict], List[int]]] = []
    for offset in range(0, len(pending), max(1, batch_size)):
        chunk = pending[offset : offset + max(1, batch_size)]
        batches.append(([item[0] for item in chunk], [item[1] for item in chunk]))
    return batches


def checkpoint_metadata(state: dict) -> dict:
    return {
        "ingestion_status": state.get("status"),
        "total_segments": state.get("total_segments", 0),
        "completed_extraction_segments": len(state.get("completed_extraction_indices", [])),
        "completed_ingestion_segments": len(state.get("completed_ingestion_indices", [])),
        "last_partial_archive": state.get("last_partial_archive"),
        "updated_at": state.get("updated_at"),
    }


def reconcile_story_times(extracted_data: List[dict]) -> None:
    builder = TimelineBuilder()
    previous_time: datetime | None = None
    for segment in sorted(extracted_data, key=lambda item: int(item.get("index", 0))):
        computed_time = builder.apply_segment(
            segment_index=int(segment.get("index", 0)),
            markers=list(segment.get("time_markers", [])),
        )
        current_time = segment.get("story_time") if isinstance(segment.get("story_time"), datetime) else computed_time
        explicit_markers = bool(segment.get("time_markers"))
        if explicit_markers:
            current_time = computed_time
        if previous_time is not None and current_time <= previous_time:
            current_time = previous_time + timedelta(days=1)
        if previous_time is not None and detect_large_timeline_jump(previous_time, current_time) and not explicit_markers:
            logger.warning(
                "Large implicit story-time jump detected between segments %s and %s; preserving monotonic fallback.",
                int(segment.get("index", 0)),
                int(segment.get("index", 0)) + 1,
            )
        segment["story_time"] = current_time
        previous_time = current_time


async def extract_all_text(pdf_dir: Path) -> str:
    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        raise FileNotFoundError(f"No PDF files found in {pdf_dir}")
    full_text = []
    for pdf_path in pdf_files:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_number, page in enumerate(pdf.pages, start=1):
                    try:
                        text = page.extract_text()
                    except Exception as exc:
                        logger.warning("Skipping %s page %d after extract failure (%s)", pdf_path.name, page_number, exc)
                        continue
                    if text and not _is_japanese_heavy_text(text):
                        full_text.append(text)
        except Exception as exc:
            logger.warning("Skipping unreadable PDF %s (%s)", pdf_path.name, exc)
    combined_text = "\n\n".join(full_text).strip()
    if not combined_text:
        raise RuntimeError(f"No readable text could be extracted from PDFs in {pdf_dir}")
    return combined_text


def should_run_preflight_tests(settings: MemorySettings) -> bool:
    state = load_preflight_state(settings)
    return not bool(state.get("passed"))


async def run_preflight_tests_if_needed(settings: MemorySettings) -> None:
    if not should_run_preflight_tests(settings):
        return

    console.rule(f"[bold {PALETTE['butter']}]First-run self-test[/bold {PALETTE['butter']}]")
    console.print("Running Mushoku Tensei automated checks before building the main database...")

    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "mushoku_tensei/tests",
            ],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            check=False,
        )

    result = await asyncio.to_thread(_run)
    if result.returncode != 0:
        if result.stdout.strip():
            console.print(result.stdout.rstrip())
        if result.stderr.strip():
            console.print(result.stderr.rstrip(), style="bold red")
        raise RuntimeError(
            "Preflight self-tests failed. Fix the Mushoku Tensei pipeline before running ingestion."
        )

    save_preflight_state(
        settings,
        {
            "passed": True,
            "command": f"{sys.executable} -m unittest discover -s mushoku_tensei/tests",
            "passed_at": now_iso(),
        },
    )
    console.print("[green]Self-tests passed.[/green] Continuing to database creation.")


def _segment_needs_retry(seg: dict, extraction: Any) -> bool:
    segment_text = str(seg.get("text") or "")
    if len(segment_text) < LOW_CONFIDENCE_SEGMENT_CHARS:
        return False
    if len(extraction.entities) >= LOW_CONFIDENCE_MIN_ENTITIES:
        return False
    # Flag long scenes that produced almost no structure for later inspection.
    return len(extraction.edges) == 0


async def _extract_segment_with_retries(
    seg: dict,
    *,
    client: LLMClient,
    stage_progress: Optional[SegmentStageProgress],
) -> tuple[Any, dict[str, Any]]:
    max_unit_chars = 700
    last_error: Exception | None = None
    for attempt in range(1, MAX_SEGMENT_RETRIES + 1):
        started_at = time.perf_counter()
        try:
            extraction = await asyncio.wait_for(
                structured_extraction_v2(
                    seg["text"],
                    client,
                    max_unit_chars=max_unit_chars,
                    segment_context={
                        "heading": seg.get("heading"),
                        "volume": seg.get("volume"),
                        "chapter": seg.get("chapter"),
                        "scene_index": seg.get("scene_index"),
                        "previous_excerpt": seg.get("previous_excerpt"),
                        "next_excerpt": seg.get("next_excerpt"),
                    },
                    progress_callback=stage_progress.on_stage_event if stage_progress else None,
                ),
                timeout=EXTRACTION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            last_error = RuntimeError(
                f"Segment {int(seg.get('index', 0)) + 1} extraction timed out after {EXTRACTION_TIMEOUT_SECONDS}s"
            )
            logger.warning("%s (attempt %d/%d)", last_error, attempt, MAX_SEGMENT_RETRIES)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Segment %d extraction failed on attempt %d/%d (%s)",
                int(seg.get("index", 0)) + 1,
                attempt,
                MAX_SEGMENT_RETRIES,
                exc,
            )
        else:
            elapsed = time.perf_counter() - started_at
            metadata = {
                "attempts": attempt,
                "max_unit_chars": max_unit_chars,
                "elapsed_seconds": round(elapsed, 3),
                "model": client.config.model,
                "provider": client.config.provider,
            }
            if _segment_needs_retry(seg, extraction):
                metadata["low_confidence"] = True
                logger.warning(
                    "Low-confidence extraction detected for segment %d (%d entities, %d edges).",
                    int(seg.get("index", 0)) + 1,
                    len(extraction.entities),
                    len(extraction.edges),
                )
            return extraction, metadata

        if attempt < MAX_SEGMENT_RETRIES:
            max_unit_chars = max(450, max_unit_chars - 150)
            await asyncio.sleep(0.25 * attempt)

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Segment {int(seg.get('index', 0)) + 1} extraction failed without a captured error")


async def main():
    client = LLMClient()
    settings = MemorySettings(
        database_id=DATABASE_ID,
        search_result_limit=200,
        timeline_window=1000,
        bulk_ingestion_batch_size=max(2, min(8, client.recommended_parallelism)),
    )
    await run_preflight_tests_if_needed(settings)

    render_banner()
    succeeded = False

    engine = MemoryEngine(settings, entity_types=ENTITY_TYPES_EXTENDED)
    archive_path = engine.database_manager.database_dir.parent / ARCHIVE_NAME
    partial_archive_path = engine.database_manager.database_dir.parent / PARTIAL_ARCHIVE_NAME

    with quiet_live_logging():
        async with IngestUX(total_segments=1) as ui:
            ui.set_gateway_summary(client.config.provider, client.config.model)
            ui.set_memory_summary(settings.normalized_database_id, batch_size=settings.bulk_ingestion_batch_size)
            ui.set_phase("Boot", "Validating configuration")

            try:
                validate_gateway_configuration(client)
                ui.finish_task(ui.task_boot_validate, status="Configuration validated")
                ui.finish_task(ui.task_boot_preflight, status="Self-tests already passed")
                ui.set_position("Starting memory engine")
                await engine.start(gateway=client)
                ui.finish_task(ui.task_boot_memory, status="Gateway and memory engine ready")
                ui.set_memory_summary(settings.normalized_database_id, batch_size=settings.bulk_ingestion_batch_size)

                ui.set_phase("Load", "Reading source PDFs")
                ui.set_position("Scanning PDF files")
                ui.finish_task(ui.task_pdf_scan, status="PDF sources discovered")
                ui.set_position("Extracting PDF text")
                full_text = await extract_all_text(PDF_DIR)
                ui.finish_task(ui.task_pdf_extract, status=f"Loaded {len(full_text):,} characters")

                ui.set_phase("Segment", "Splitting novel into semantic scenes")
                ui.set_position("Splitting text into sections")
                segments = await segment_text(full_text, min_chunk_chars=350, max_chunk_chars=900)
                ui.finish_task(ui.task_segment_split, status=f"Built {len(segments)} scene chunks")
                ui.set_position("Loading checkpoint state")
                state = resume_or_initialize_state(settings, full_text, segments)
                estimated_extract_work = estimate_extraction_work_units(segments)
                ui.total_segments = len(segments)
                ui.step_progress.update(ui.task_extract, total=estimated_extract_work)
                ui.step_progress.update(ui.task_ingest, total=max(1, len(segments)))
                ui.position_progress.update(ui.task_position, total=max(1, estimated_extract_work + len(segments) + 12))
                ui.finish_task(ui.task_segment_resume, status=f"Prepared {len(segments)} segments")

                ui.set_phase("Calibrate", "Probing provider parallelism")
                ui.set_position("Running provider probes")
                calibrated_parallelism = await calibrate_with_live_display(client, ui, MAX_PROVIDER_PARALLELISM)
                ui.finish_task(ui.task_calibrate_probe, status=f"Probe finished at x{calibrated_parallelism}")
                metrics = client.runtime_metrics()
                latency_hint = f"{metrics.ewma_latency:.2f}s" if metrics.ewma_latency is not None else "n/a"
                extraction_parallelism, gateway_mode = _resolve_extraction_parallelism(client, calibrated_parallelism)
                client.configure_parallelism(initial=extraction_parallelism, maximum=calibrated_parallelism)
                settings.bulk_ingestion_batch_size = max(2, min(8, extraction_parallelism))
                ui.set_gateway_summary(
                    client.config.provider,
                    client.config.model,
                    parallelism=extraction_parallelism,
                    latency=latency_hint,
                )
                ui.set_gateway_mode(gateway_mode)
                ui.set_memory_summary(settings.normalized_database_id, batch_size=settings.bulk_ingestion_batch_size)
                ui.finish_task(
                    ui.task_calibrate_apply,
                    status=f"Extract parallelism x{extraction_parallelism} (probe x{calibrated_parallelism})",
                )

                ui.set_phase("Extraction", "Processing scene units")
                ui.start_extraction_clock()
                ui.set_position("Queueing segment extraction")
                extracted_data, segment_stats = await extract_segments_adaptive(
                    segments=segments,
                    client=client,
                    settings=settings,
                    state=state,
                    ui=ui,
                )
                reconcile_story_times(extracted_data)
                for result, stat in zip(extracted_data, segment_stats, strict=False):
                    stat["story_time"] = result["story_time"]
                state["status"] = "extracted"
                save_checkpoint_state(settings, state)
                ui.finish_task(ui.task_extract, status=f"Extracted {len(extracted_data)} segments")

                ui.set_phase("Graph", "Building layered episodes")
                ui.set_position("Constructing layered graph payload")
                graph_payload = build_layered_graph(extracted_data, group_id=GROUP_ID)
                ui.record_graph_summary(graph_payload)
                ui.finish_task(ui.task_graph, status=f"Built {len(graph_payload)} episodes")

                ui.set_phase("Memory", "Writing episodes to graph memory")
                ui.start_ingestion_clock()
                completed_ingestion = set(state.get("completed_ingestion_indices", []))
                ui.set_position("Planning ingestion batches")
                ingestion_batches = iter_ingestion_batches(
                    graph_payload,
                    extracted_data,
                    completed_ingestion,
                    batch_size=settings.bulk_ingestion_batch_size,
                )
                ui.finish_task(ui.task_ingest_plan, status=f"Prepared {len(ingestion_batches)} ingestion batches")
                for batch_number, (batch_episodes, batch_indices) in enumerate(ingestion_batches, start=1):
                    ui.set_phase(
                        "Memory",
                        f"Ingesting batch {batch_number}/{max(1, len(ingestion_batches))} ({len(batch_indices)} segments)",
                    )
                    ui.set_position(f"Memory batch {batch_number}/{max(1, len(ingestion_batches))}")
                    await engine.add_episodes_bulk(batch_episodes, group_id=GROUP_ID)
                    for segment_index in batch_indices:
                        mark_segment_ingested(settings, state, segment_index)
                    ui.advance_ingest(len(batch_indices))
                    ui.advance_position(f"Stored batch {batch_number}", amount=len(batch_indices))
                    export_partial_archive(engine, partial_archive_path, state)
                    save_checkpoint_state(settings, state)
                ui.finish_task(ui.task_ingest, status="Memory ingestion complete")

                ui.set_phase("Verify", "Running character search health check")
                ui.set_position("Searching for Rudeus")
                results = await engine.search("Rudeus", group_ids=[GROUP_ID], node_labels=["Character"])
                ui.finish_task(ui.task_verify_search, status=f"Verification returned {len(results)} matches")
                state["status"] = "complete"
                export_partial_archive(engine, partial_archive_path, state, force=True)
                save_checkpoint_state(settings, state)
                ui.set_position("Writing manifest")
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
                ui.finish_task(ui.task_verify_manifest, status="Manifest written")

                ui.set_phase("Archive", "Exporting database archive")
                if settings.database_path.exists():
                    ui.set_position("Compressing archive")
                    archive = engine.database_manager.export_archive(archive_path)
                    ui.finish_task(ui.task_archive, status=f"Archive exported to {archive.name}")
                else:
                    ui.finish_task(ui.task_archive, status="Archive skipped; database path missing")

                ui.set_phase("Complete", "Ingestion finished successfully")
                succeeded = True

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
                ui.set_phase("Failed", str(e))
                raise
            finally:
                await engine.stop()

    if succeeded:
        console.rule(f"[bold {PALETTE['mint']}]Ingestion finished successfully[/bold {PALETTE['mint']}]")


if __name__ == "__main__":
    asyncio.run(main())
