#!/usr/bin/env python3
"""Smart CLI for BRING setup and portable database management."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from bring_cli_support import (
    default_database_id,
    infer_provider,
    merge_env_file,
    suggest_embedding_dimensions,
)
from llm_gateway.settings import GatewaySettings
from memory.config import MemorySettings
from memory.database import MemoryDatabaseManager

app = typer.Typer(
    help="Guided setup and database management for BRING.",
    add_completion=False,
    rich_markup_mode="rich",
)
db_app = typer.Typer(help="Create, inspect, share, and clone memory databases.")
app.add_typer(db_app, name="db")

console = Console()
logger = logging.getLogger("bring.cli")


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True)],
    )


def _progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=None),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    )


def _settings_for_db(database_id: str, database_root: Optional[str]) -> MemorySettings:
    updates = {"database_id": database_id}
    if database_root:
        updates["database_root"] = Path(database_root)
    return MemorySettings().model_copy(update=updates)


def _list_database_dirs(settings: MemorySettings) -> list[Path]:
    root = settings.database_root
    if not root.exists():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logging."),
) -> None:
    _configure_logging(verbose)


@app.command()
def setup(
    config_path: Path = typer.Option(Path(".bring.env"), help="Where to write the shared project config."),
    project_name: str = typer.Option("default", help="Used to auto-generate the default memory database id."),
) -> None:
    """Run a guided setup flow and write a clean `.bring.env` file."""
    console.print(Panel.fit("[bold cyan]BRING setup[/bold cyan]\nGuided LLM, embedding, and memory configuration"))

    llm_base_url = Prompt.ask("LLM base URL", default="https://api.openai.com/v1")
    llm_api_key = Prompt.ask("LLM API key", password=True)
    llm_model = Prompt.ask("LLM model", default="gpt-4o-mini")
    embed_base_url = Prompt.ask("Embedding base URL", default=llm_base_url)
    embed_api_key = Prompt.ask(
        "Embedding API key",
        password=True,
        default=llm_api_key,
        show_default=False,
    )
    embed_model = Prompt.ask("Embedding model", default="text-embedding-3-small")
    db_root = Prompt.ask("Database root", default="./memory_databases")
    db_id = Prompt.ask("Default database id", default=default_database_id(project_name))

    llm_provider, llm_provider_type = infer_provider(llm_base_url, llm_model)
    embed_provider, embed_provider_type = infer_provider(embed_base_url, embed_model)
    embed_dim = suggest_embedding_dimensions(embed_model)

    updates = {
        "LLM_PROVIDER": llm_provider,
        "LLM_PROVIDER_TYPE": llm_provider_type,
        "LLM_MODEL": llm_model,
        "LLM_API_KEY": llm_api_key,
        "LLM_BASE_URL": llm_base_url,
        "LLM_TEMPERATURE": "0.7",
        "LLM_MAX_TOKENS": "1024",
        "LLM_EMBEDDING_PROVIDER": embed_provider,
        "LLM_EMBEDDING_PROVIDER_TYPE": embed_provider_type,
        "LLM_EMBEDDING_MODEL": embed_model,
        "LLM_EMBEDDING_API_KEY": embed_api_key,
        "LLM_EMBEDDING_BASE_URL": embed_base_url,
        "LLM_EMBEDDING_DIM": str(embed_dim),
        "MEMORY_DATABASE_ROOT": db_root,
        "MEMORY_DATABASE_ID": db_id,
        "MEMORY_GRAPHITI_MAX_COROUTINES": "10",
        "MEMORY_GRAPHITI_STORE_RAW_EPISODES": "true",
        "MEMORY_STRUCTURED_EXTRACTION": "true",
        "MEMORY_BULK_BATCH": "5",
        "MEMORY_SEARCH_RESULT_LIMIT": "50",
        "MEMORY_TIMELINE_WINDOW": "30",
        "MEMORY_SEARCH_CACHE_TTL_SECONDS": "120",
        "MEMORY_SEARCH_CACHE_MAXSIZE": "256",
    }

    with _progress() as progress:
        task = progress.add_task("Preparing smart defaults", total=3)
        time.sleep(0.1)
        progress.advance(task)
        logger.info("LLM provider inferred as %s", llm_provider)
        time.sleep(0.1)
        progress.advance(task)
        logger.info("Embedding provider inferred as %s with dimension %s", embed_provider, embed_dim)
        merge_env_file(updates, config_path)
        progress.advance(task)

    table = Table(title="Saved configuration")
    table.add_column("Setting")
    table.add_column("Value")
    table.add_row("Config path", str(config_path))
    table.add_row("LLM provider", llm_provider)
    table.add_row("Embedding provider", embed_provider)
    table.add_row("Default database", db_id)
    table.add_row("Database root", db_root)
    console.print(table)


@app.command("show-config")
def show_config(
    config_path: Path = typer.Option(Path(".bring.env"), help="Shared project config file."),
) -> None:
    """Show the current resolved gateway and memory settings."""
    gateway = GatewaySettings.from_file(config_path)
    memory = MemorySettings.from_file(config_path)
    table = Table(title="Resolved BRING settings")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("LLM provider", gateway.provider)
    table.add_row("LLM model", gateway.model)
    table.add_row("Embedding provider", gateway.provider_settings.embedding.provider)
    table.add_row("Embedding model", gateway.provider_settings.embedding.model)
    table.add_row("Embedding dim", str(gateway.provider_settings.embedding.dimensions))
    table.add_row("Database root", str(memory.database_root))
    table.add_row("Database id", memory.normalized_database_id)
    table.add_row("Database path", str(memory.database_path))
    console.print(table)


@db_app.command("list")
def list_databases(
    database_root: Optional[str] = typer.Option(None, help="Override database root."),
) -> None:
    """List all locally available isolated memory databases."""
    settings = _settings_for_db("default", database_root)
    entries = _list_database_dirs(settings)
    table = Table(title="Memory databases")
    table.add_column("Database")
    table.add_column("Manifest")
    table.add_column("Kuzu path")
    if not entries:
        console.print("[yellow]No databases found.[/yellow]")
        return
    for entry in entries:
        db_settings = settings.model_copy(update={"database_id": entry.name})
        manager = MemoryDatabaseManager(db_settings)
        table.add_row(entry.name, "yes" if manager.manifest_path.exists() else "no", str(manager.kuzu_path))
    console.print(table)


@db_app.command("create")
def create_database(
    database_id: str = typer.Argument(..., help="Logical id for the database."),
    database_root: Optional[str] = typer.Option(None, help="Override database root."),
    label: Optional[str] = typer.Option(None, help="Human-friendly label stored in the manifest."),
) -> None:
    """Create a clean isolated database layout and manifest."""
    settings = _settings_for_db(database_id, database_root)
    manager = MemoryDatabaseManager(settings)
    with _progress() as progress:
        task = progress.add_task("Creating database", total=2)
        manager.ensure_layout()
        progress.advance(task)
        manager.write_manifest(label=label)
        progress.advance(task)
    console.print(f"[green]Created database:[/green] {manager.database_dir}")


@db_app.command("inspect")
def inspect_database(
    database_id: str = typer.Argument(..., help="Logical id for the database."),
    database_root: Optional[str] = typer.Option(None, help="Override database root."),
) -> None:
    """Inspect one database manifest and layout."""
    settings = _settings_for_db(database_id, database_root)
    manager = MemoryDatabaseManager(settings)
    manifest = manager.load_manifest()
    table = Table(title=f"Database: {settings.normalized_database_id}")
    table.add_column("Key")
    table.add_column("Value")
    table.add_row("Directory", str(manager.database_dir))
    table.add_row("Kuzu path", str(manager.kuzu_path))
    table.add_row("Manifest path", str(manager.manifest_path))
    if manifest is not None:
        for key, value in manifest.model_dump().items():
            table.add_row(str(key), str(value))
    console.print(table)


@db_app.command("export")
def export_database(
    database_id: str = typer.Argument(..., help="Logical id for the database."),
    destination: Optional[Path] = typer.Option(None, help="Target .zip path."),
    database_root: Optional[str] = typer.Option(None, help="Override database root."),
) -> None:
    """Package one database into a portable archive."""
    settings = _settings_for_db(database_id, database_root)
    manager = MemoryDatabaseManager(settings)
    with _progress() as progress:
        task = progress.add_task("Exporting database", total=1)
        archive_path = manager.export_archive(destination)
        progress.advance(task)
    console.print(f"[green]Archive created:[/green] {archive_path}")


@db_app.command("import")
def import_database(
    archive_path: Path = typer.Argument(..., exists=True, help="Archive created with `db export`."),
    database_id: str = typer.Argument(..., help="Target local database id."),
    database_root: Optional[str] = typer.Option(None, help="Override database root."),
) -> None:
    """Import a shared archive into a fresh isolated local database."""
    settings = _settings_for_db(database_id, database_root)
    with _progress() as progress:
        task = progress.add_task("Importing database", total=1)
        manager = MemoryDatabaseManager.import_archive(archive_path, settings, database_id=database_id)
        progress.advance(task)
    console.print(f"[green]Imported database:[/green] {manager.database_dir}")


@db_app.command("clone")
def clone_database(
    source_database_id: str = typer.Argument(..., help="Existing database id."),
    target_database_id: str = typer.Argument(..., help="New database id."),
    database_root: Optional[str] = typer.Option(None, help="Override database root."),
) -> None:
    """Clone a database before editing so the original remains untouched."""
    settings = _settings_for_db(source_database_id, database_root)
    manager = MemoryDatabaseManager(settings)
    with _progress() as progress:
        task = progress.add_task("Cloning database", total=1)
        clone = manager.clone_database(target_database_id)
        progress.advance(task)
    console.print(f"[green]Cloned to:[/green] {clone.database_dir}")


@db_app.command("remove")
def remove_database(
    database_id: str = typer.Argument(..., help="Database id to remove."),
    database_root: Optional[str] = typer.Option(None, help="Override database root."),
) -> None:
    """Remove a database directory after confirmation."""
    import shutil

    settings = _settings_for_db(database_id, database_root)
    manager = MemoryDatabaseManager(settings)
    if not manager.database_dir.exists():
        raise typer.BadParameter(f"Database does not exist: {settings.normalized_database_id}")
    if not Confirm.ask(f"Delete database '{settings.normalized_database_id}'?"):
        raise typer.Exit()
    shutil.rmtree(manager.database_dir)
    console.print(f"[green]Removed:[/green] {manager.database_dir}")


if __name__ == "__main__":
    app()
