"""Beautiful, feature‑rich CLI for world building with pastel colours, animations, and real‑time logs."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich import box
from rich.logging import RichHandler
from rich.theme import Theme
from rich.traceback import install

from .config import DATABASE_PATH, get_world_frame_path, get_entity_store_path
from .llm import LLMClient
from .graph_manager import GraphManager
from .builder import WorldBuilder

PASTEL_THEME = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "danger": "bold red",
    "success": "bold green",
    "heading": "bold #d7afff",
    "subheading": "#b5e8e0",
    "accent": "#f7cac9",
    "border": "#c4a4e3",
    "progress": "#a3c9f1",
    "table.header": "bold #f5c2e7",
    "table.row": "#e0f0ea",
    "log.time": "dim #a9b7c6",
    "log.message": "white",
})

install(show_locals=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, console=Console(theme=PASTEL_THEME))]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

log = logging.getLogger("world_builder")

app = typer.Typer(help="✨ World Builder – forge consistent fantasy worlds with AI")
console = Console(theme=PASTEL_THEME)

def run_async(coro):
    asyncio.run(coro)


@app.command()
def build(
    episodes: int = typer.Option(10, help="Number of narrative scenes to generate."),
    force: bool = typer.Option(False, "--force", help="Force rebuild of L1 (world frame) even if it already exists."),
    relationships: bool = typer.Option(False, "--relationships", help="Generate complex relationships between entities."),
    db_path: Optional[Path] = typer.Option(None, help="Path to database directory."),
):
    """Create a complete world, layer by layer. Resumes from existing data unless --force is used."""
    db = db_path or DATABASE_PATH
    llm = LLMClient()
    gm = GraphManager(entity_store_path=get_entity_store_path(db))
    frame_path = get_world_frame_path(db)
    builder = WorldBuilder(llm, gm, num_episodes=episodes, world_frame_path=frame_path)

    async def run():
        start_time = time.time()
        console.rule("[heading]🌍 World Building Process[/]")

        # Determine if a world already exists
        existing_world = frame_path.exists()
        if existing_world and not force:
            console.print("[yellow]Existing world found. Resuming from saved state.[/]")
            console.print("[dim](Use --force to rebuild the world frame and L1)[/]")
            # Phase 1: Load existing world (skips L1 generation)
            with console.status("[accent]Loading existing world...[/]", spinner="dots"):
                await builder.load_existing_world()
                log.info("World loaded from disk.")
        else:
            if existing_world and force:
                console.print("[red]Overwriting existing world![/]")
            # Phase 1: Generate new world frame & L1
            with console.status("[accent]Generating world frame and L1 profiles...[/]", spinner="dots"):
                try:
                    await builder.create_world()
                    log.info("World frame and L1 stored.")
                except Exception as e:
                    log.error(f"World creation failed: {e}")
                    console.print(f"[danger]❌ Failed: {e}[/]")
                    raise typer.Exit(1)

        # Phase 2: L2 details
        with console.status("[accent]Building L2 (details) for all entities...[/]", spinner="dots"):
            await builder.build_L2()

        # Phase 3: L3 secrets
        with console.status("[accent]Building L3 (secrets) for all entities...[/]", spinner="dots"):
            await builder.build_L3()

        # Phase 4: Relationships
        if relationships:
            with console.status("[accent]Building relationships...[/]", spinner="dots"):
                await builder.build_relationships()

        # Narrative episodes (optional)
        if episodes > 0:
            console.rule("[heading]📖 Writing Narrative Episodes[/]")
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None, style="progress"),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("[accent]Generating scenes...", total=episodes)
                await builder.add_narrative_episodes(progress_callback=lambda: progress.update(task, advance=1))

        elapsed = time.time() - start_time
        console.rule("[heading]✨ Build Complete[/]")
        console.print(
            f"[success]World built in {elapsed:.1f} seconds.[/] "
            f"Run [accent]'view summary'[/] to explore."
        )

    run_async(run())


# ── The rest of the CLI (view, add, search, validate) remains unchanged ────
# (included for completeness)

@app.command()
def export(
    archive: Path = typer.Argument(..., help="Output zip file path."),
    db_path: Optional[Path] = typer.Option(None),
):
    import shutil
    db = db_path or DATABASE_PATH
    shutil.make_archive(str(archive.with_suffix('')), 'zip', db)
    console.print(f"[success]✅ Exported to {archive}[/]")

add_app = typer.Typer(help="Add new entities to the world")
app.add_typer(add_app, name="add")

@add_app.command("npc")
def add_npc(
    faction_or_race: str = typer.Argument(..., help="Faction or race the NPC belongs to."),
    db_path: Optional[Path] = typer.Option(None),
):
    db = db_path or DATABASE_PATH
    gm = GraphManager(entity_store_path=get_entity_store_path(db))
    frame_path = get_world_frame_path(db)
    builder = WorldBuilder(LLMClient(), gm, num_episodes=0, world_frame_path=frame_path)
    async def run():
        with console.status(f"[accent]🎭 Generating NPC: {faction_or_race}...[/]", spinner="bouncingBall"):
            node = await builder.add_npc(faction_or_race)
        console.print(f"[success]✅ Created NPC: {node.name}[/]")
    run_async(run())

@add_app.command("item")
def add_item(
    item_type: str = typer.Argument("weapon", help="weapon, artifact, potion, armor, tool"),
    rarity: str = typer.Option("uncommon", help="Rarity level."),
    db_path: Optional[Path] = typer.Option(None),
):
    db = db_path or DATABASE_PATH
    gm = GraphManager(entity_store_path=get_entity_store_path(db))
    frame_path = get_world_frame_path(db)
    builder = WorldBuilder(LLMClient(), gm, num_episodes=0, world_frame_path=frame_path)
    async def run():
        with console.status(f"[accent]⚔️ Crafting {rarity} {item_type}...[/]", spinner="dots"):
            node = await builder.add_item(item_type, rarity)
        console.print(f"[success]✅ Created item: {node.name}[/]")
    run_async(run())

@add_app.command("faction")
def add_faction(db_path: Optional[Path] = typer.Option(None)):
    db = db_path or DATABASE_PATH
    gm = GraphManager(entity_store_path=get_entity_store_path(db))
    frame_path = get_world_frame_path(db)
    builder = WorldBuilder(LLMClient(), gm, num_episodes=0, world_frame_path=frame_path)
    async def run():
        with console.status("[accent]🏛️  Forming faction...[/]", spinner="bouncingBar"):
            node = await builder.add_faction()
        console.print(f"[success]✅ Faction created: {node.name}[/]")
    run_async(run())

@add_app.command("location")
def add_location(db_path: Optional[Path] = typer.Option(None)):
    db = db_path or DATABASE_PATH
    gm = GraphManager(entity_store_path=get_entity_store_path(db))
    frame_path = get_world_frame_path(db)
    builder = WorldBuilder(LLMClient(), gm, num_episodes=0, world_frame_path=frame_path)
    async def run():
        with console.status("[accent]🗺️  Mapping location...[/]", spinner="dots"):
            node = await builder.add_location()
        console.print(f"[success]✅ Location discovered: {node.name}[/]")
    run_async(run())

@add_app.command("event")
def add_event(db_path: Optional[Path] = typer.Option(None)):
    db = db_path or DATABASE_PATH
    gm = GraphManager(entity_store_path=get_entity_store_path(db))
    frame_path = get_world_frame_path(db)
    builder = WorldBuilder(LLMClient(), gm, num_episodes=0, world_frame_path=frame_path)
    async def run():
        with console.status("[accent]📜 Chronicling event...[/]", spinner="dots"):
            node = await builder.add_event()
        console.print(f"[success]✅ Event recorded: {node.name}[/]")
    run_async(run())

@add_app.command("rule")
def add_rule(db_path: Optional[Path] = typer.Option(None)):
    db = db_path or DATABASE_PATH
    gm = GraphManager(entity_store_path=get_entity_store_path(db))
    frame_path = get_world_frame_path(db)
    builder = WorldBuilder(LLMClient(), gm, num_episodes=0, world_frame_path=frame_path)
    async def run():
        with console.status("[accent]📏 Proclaiming rule...[/]", spinner="dots"):
            node = await builder.add_rule()
        console.print(f"[success]✅ Rule established: {node.name}[/]")
    run_async(run())

view_app = typer.Typer(help="Explore the world")
app.add_typer(view_app, name="view")

def _load_world_frame(db_path: Optional[Path] = None) -> dict:
    path = get_world_frame_path(db_path or DATABASE_PATH)
    if not path.exists():
        console.print("[danger]No world found. Run 'build' first.[/]")
        raise typer.Exit()
    with open(path) as f:
        return json.load(f)

def _get_gm(db_path: Optional[Path]) -> GraphManager:
    db = db_path or DATABASE_PATH
    return GraphManager(entity_store_path=get_entity_store_path(db))

@view_app.command("summary")
def view_summary(db_path: Optional[Path] = typer.Option(None)):
    world = _load_world_frame(db_path)
    summary = (
        f"[heading]World: {world['world_name']}[/heading]\n"
        f"[subheading]Calendar era:[/] {world['calendar_era']['name']}\n"
        f"[subheading]Magic:[/] {world['magic_system']['name']}\n"
        f"[subheading]Races:[/] {', '.join(r['name'] for r in world['races'])}\n"
        f"[subheading]Factions:[/] {', '.join(f['name'] for f in world['factions'])}\n"
        f"[subheading]Characters:[/] {', '.join(c['name'] for c in world['characters'])}\n"
        f"[subheading]Locations:[/] {', '.join(l['name'] for l in world['locations'])}\n"
        f"[subheading]Items:[/] {', '.join(i['name'] for i in world['items'])}\n"
        f"[subheading]Events:[/] {', '.join(e['name'] for e in world['historical_events'])}\n"
        f"[subheading]Rules:[/] {', '.join(r['name'] for r in world['world_rules'])}"
    )
    console.print(Panel(summary, title="World Summary", border_style="border", padding=(1,2)))

@view_app.command("characters")
def view_characters(db_path: Optional[Path] = typer.Option(None)):
    gm = _get_gm(db_path)
    nodes = gm.store.list_by_type("Character")
    table = Table(title="👥 Characters", box=box.ROUNDED, header_style="table.header",
                  style="table.row", border_style="border")
    table.add_column("Name", style="accent")
    table.add_column("Group")
    table.add_column("Summary")
    for node in nodes:
        l1 = node.profile.l1
        table.add_row(node.name, node.group_id, l1.get("summary", ""))
    console.print(table)

@view_app.command("factions")
def view_factions(db_path: Optional[Path] = typer.Option(None)):
    gm = _get_gm(db_path)
    nodes = gm.store.list_by_type("Faction")
    table = Table(title="🏛️  Factions", box=box.ROUNDED, header_style="table.header",
                  style="table.row", border_style="border")
    table.add_column("Name", style="accent")
    table.add_column("Group")
    table.add_column("Summary")
    for node in nodes:
        l1 = node.profile.l1
        table.add_row(node.name, node.group_id, l1.get("summary", ""))
    console.print(table)

@view_app.command("locations")
def view_locations(db_path: Optional[Path] = typer.Option(None)):
    gm = _get_gm(db_path)
    nodes = gm.store.list_by_type("Location")
    table = Table(title="🗺️  Locations", box=box.ROUNDED, header_style="table.header",
                  style="table.row", border_style="border")
    table.add_column("Name", style="accent")
    table.add_column("Type")
    table.add_column("Summary")
    for node in nodes:
        l1 = node.profile.l1
        table.add_row(node.name, node.profile.l2.get("type", ""), l1.get("summary", ""))
    console.print(table)

@view_app.command("items")
def view_items(db_path: Optional[Path] = typer.Option(None)):
    gm = _get_gm(db_path)
    nodes = gm.store.list_by_type("Item")
    table = Table(title="⚔️ Items", box=box.ROUNDED, header_style="table.header",
                  style="table.row", border_style="border")
    table.add_column("Name", style="accent")
    table.add_column("Type")
    table.add_column("Summary")
    for node in nodes:
        l1 = node.profile.l1
        table.add_row(node.name, node.profile.l2.get("type", ""), l1.get("summary", ""))
    console.print(table)

@view_app.command("events")
def view_events(db_path: Optional[Path] = typer.Option(None)):
    gm = _get_gm(db_path)
    nodes = gm.store.list_by_type("Event")
    table = Table(title="📜 Historical Events", box=box.ROUNDED, header_style="table.header",
                  style="table.row", border_style="border")
    table.add_column("Name", style="accent")
    table.add_column("Summary")
    for node in nodes:
        l1 = node.profile.l1
        table.add_row(node.name, l1.get("summary", ""))
    console.print(table)

@view_app.command("rules")
def view_rules(db_path: Optional[Path] = typer.Option(None)):
    gm = _get_gm(db_path)
    nodes = gm.store.list_by_type("WorldRule")
    table = Table(title="📏 World Rules", box=box.ROUNDED, header_style="table.header",
                  style="table.row", border_style="border")
    table.add_column("Name", style="accent")
    table.add_column("Category")
    table.add_column("Description")
    for node in nodes:
        l1 = node.profile.l1
        l2 = node.profile.l2
        table.add_row(node.name, l1.get("category", ""), l2.get("description", ""))
    console.print(table)

@view_app.command("entity")
def view_entity(
    name: str = typer.Argument(..., help="Name of the entity to inspect."),
    level: Optional[int] = typer.Option(None, help="Show only L1, L2, or L3. Omit for all."),
    db_path: Optional[Path] = typer.Option(None),
):
    gm = _get_gm(db_path)
    uid = gm._resolve_entity_uid(name)
    if not uid:
        console.print(f"[danger]Entity '{name}' not found.[/]")
        return
    node = gm.store.get(uid)
    if level:
        if level == 1:
            data = node.profile.l1
        elif level == 2:
            data = node.profile.l2
        elif level == 3:
            data = node.profile.l3
        else:
            data = node.profile.to_dict()
        console.print(Panel(json.dumps(data, indent=2, ensure_ascii=False),
                            title=f"{node.entity_type}: {node.name} (L{level})",
                            border_style="border"))
    else:
        console.print(Panel(json.dumps(node.profile.to_dict(), indent=2, ensure_ascii=False),
                            title=f"{node.entity_type}: {node.name} (Full Profile)",
                            border_style="border"))

@app.command()
def search(query: str, db_path: Optional[Path] = typer.Option(None)):
    gm = _get_gm(db_path)
    async def run():
        with console.status("[accent]🔍 Searching...[/]", spinner="dots"):
            results = await gm.search(query, limit=10)
        if not results:
            console.print("[warning]No matches found.[/]")
        else:
            table = Table(title=f"🔍 Results for '{query}'", box=box.ROUNDED,
                          header_style="table.header", style="table.row", border_style="border")
            table.add_column("Name")
            table.add_column("Type")
            table.add_column("Summary")
            for r in results:
                table.add_row(r["name"], r["type"], r["summary"])
            console.print(table)
    run_async(run())

@app.command()
def validate(db_path: Optional[Path] = typer.Option(None)):
    gm = _get_gm(db_path)
    missing = []
    for node in gm.store.all_nodes():
        for rel in node.profile.l1.get("relationships", []):
            target_uid = gm._resolve_entity_uid(rel["target"])
            if not target_uid:
                missing.append(f"{node.name} -> {rel['target']}")
    if missing:
        console.print("[warning]Some relationships reference unknown entities:[/]")
        for m in missing:
            console.print(f" - {m}")
    else:
        console.print("[success]✅ All references valid.[/]")

@app.command()
def repair(
    intelligent: bool = typer.Option(True, "--intelligent/--simple", help="Use intelligent fuzzy matching"),
    merge: bool = typer.Option(True, "--merge/--no-merge", help="Merge highly similar entities"),
    create: bool = typer.Option(True, "--create/--no-create", help="Create missing entities automatically"),
    db_path: Optional[Path] = typer.Option(None),
):
    """Repair invalid relationships using progressive fuzzy matching."""
    db = db_path or DATABASE_PATH
    llm = LLMClient()
    gm = GraphManager(entity_store_path=get_entity_store_path(db))
    frame_path = get_world_frame_path(db)
    builder = WorldBuilder(llm, gm, num_episodes=0, world_frame_path=frame_path)
    # Attach builder to gm for repairer
    gm.builder = builder

    def run():
        async def do_repair():
            if intelligent:
                console.print("[cyan]Intelligent repair with fuzzy matching...[/]")
                # Configure repairer with auto_merge/auto_create
                from world_intelligence.relationship_repairer import RelationshipRepairer
                repairer = RelationshipRepairer(
                    gm, builder, auto_merge=merge, auto_create=create
                )
                stats = await repairer.repair_all_relationships()
            else:
                console.print("[cyan]Simple repair (placeholders only)...[/]")
                stats = await gm.repair_all_relationships(intelligent=False)

            console.print(f"[green]✓ Repair complete[/]")
            console.print(f"  Resolved: {stats.get('resolved', 0)}")
            console.print(f"  Merged: {stats.get('merged', 0)}")
            console.print(f"  Created: {stats.get('created', 0)}")
            console.print(f"  Failed: {stats.get('failed', 0)}")
            console.print(f"  Skipped: {stats.get('skipped', 0)}")

        asyncio.run(do_repair())

    run()


if __name__ == "__main__":
    app()
