#!/usr/bin/env python3
"""
Mushoku Tensei ingestion script with multi‑stage extraction and rich logging.
"""

import asyncio
import logging
import time
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
        "Smaller chunks (max 1500 chars) for higher accuracy",
        border_style="green"
    ))

    client = LLMClient()
    console.print(f"🤖 LLM Gateway: [cyan]{client.config.provider}[/cyan] / [cyan]{client.config.model}[/cyan]")

    settings = MemorySettings(
        database_id=DATABASE_ID,
        search_result_limit=200,
        timeline_window=1000,
        bulk_ingestion_batch_size=2,  # reduced from 3 to avoid rate limits
    )
    engine = MemoryEngine(settings, entity_types=ENTITY_TYPES_EXTENDED)
    await engine.start(gateway=client)
    console.print(f"💾 Memory engine ready – database: [green]{settings.normalized_database_id}[/green]")
    archive_path = engine.database_manager.database_dir.parent / ARCHIVE_NAME

    try:
        full_text = await extract_all_text(PDF_DIR)
        console.print(f"📊 Total characters extracted: [bold]{len(full_text):,}[/bold]")

        # Segment with smaller chunk size
        segments = await segment_text(full_text, min_chunk_chars=300, max_chunk_chars=1500)
        console.print(f"✂️  Segmented into [bold]{len(segments)}[/bold] logical chunks")

        extracted_data: List[Dict[str, Any]] = []
        semaphore = asyncio.Semaphore(2)

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

        async def process_segment(seg: dict):
            async with semaphore:
                start_time = time.perf_counter()
                seg_index = seg["index"] + 1
                seg_len = len(seg["text"])
                progress.update(
                    progress_task,
                    description=f"[cyan]Segment {seg_index}/{len(segments)} (len {seg_len})",
                )

                extraction = await structured_extraction_v2(seg["text"], client)
                story_time = estimate_story_time(seg["index"], extraction.time_markers)

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
                return {
                    "index": seg["index"],
                    "text": seg["text"],
                    "volume": seg.get("volume"),
                    "chapter": seg.get("chapter"),
                    "entities": extraction.entities,
                    "edges": extraction.edges,
                    "time_markers": extraction.time_markers,
                    "story_time": story_time,
                }

        tasks = [process_segment(seg) for seg in segments]
        extracted_data = await asyncio.gather(*tasks)
        progress.stop()
        extracted_data.sort(key=lambda d: d["index"])

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

        console.print("💾 Ingesting episodes into memory engine (bulk)...")
        await engine.add_episodes_bulk(graph_payload, group_id=GROUP_ID)

        engine.database_manager.write_manifest(
            gateway=client,
            label="Mushoku Tensei V2 (multi‑stage)",
            source="mushoku_tensei",
            metadata={
                "group_id": GROUP_ID,
                "segments": len(graph_payload),
                "pdf_directory": str(PDF_DIR),
            },
        )
        console.print("📝 Manifest written to database")

        console.print("🔍 Verifying: searching for 'Rudeus' among Characters...")
        results = await engine.search("Rudeus", group_ids=[GROUP_ID], node_labels=["Character"])
        console.print(f"   ✅ Found [bold]{len(results)}[/bold] entries for 'Rudeus'")

    except Exception as e:
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
