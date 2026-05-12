"""Rich Typer CLI with global store."""
import asyncio
from pathlib import Path
from typing import Optional, List
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import json
from .store import GraphStore
from .navigator import Navigator
from .config import DEFAULT_DB_PATH
from .builder_integration import BuilderInterface

app = typer.Typer(help="🌐 Lore Explorer – Graph‑powered world navigation")
console = Console()

_store = None

def get_store(db_path: Path) -> GraphStore:
    global _store
    if _store is None or _store.db_path != db_path:
        _store = GraphStore(db_path)
        _store.boot()
    return _store

@app.callback()
def main(ctx: typer.Context, db_path: Path = typer.Option(DEFAULT_DB_PATH, help="Path to world_db directory")):
    ctx.obj = {"db_path": db_path}

# ── Entity display (now with --complete and multiple -l) ──
@app.command()
def show(
    uid: str = typer.Argument(...),
    layers: Optional[List[str]] = typer.Option(None, "-l", "--layer", help="Layers to show (use multiple times, e.g., -l l1 -l l2)"),
    complete: bool = typer.Option(False, "--complete", help="Auto‑complete missing L2/L3 before showing"),
    relationships: bool = typer.Option(False, "--relationships", help="Auto‑complete missing relationships across all entities."),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True),
):
    """Display an entity, optionally completing missing layers."""
    store = get_store(db_path)
    nav = Navigator(store)

    if complete:
        # Reuse the store's entity store so we don't reload
        from world_builder.graph_manager import GraphManager as BuilderGM
        from world_builder.config import get_entity_store_path
        gm = BuilderGM(entity_store_path=get_entity_store_path(db_path))
        bi = BuilderInterface(db_path, gm=gm)
        node = nav._find_entity(uid)
        if node:
            if not node.profile.l2:
                console.print("[cyan]Completing L2...[/]")
                bi.complete_entity(uid, "l2")
            if layers and "l3" in layers and not node.profile.l3:
                console.print("[cyan]Completing L3...[/]")
                bi.complete_entity(uid, "l3")
            if relationships:
                console.print("[cyan]Completing relationships...[/]")
                bi.complete_relationships()
        # Reload the shared store to pick up changes
        store.boot()
        nav = Navigator(store)

    data = nav.get_entity(uid, layers)
    if not data:
        console.print(f"[red]Entity {uid} not found[/]")
        raise typer.Exit(1)
    console.print_json(data=data)

# ── Neighbourhood ──
@app.command()
def neighbors(
    uid: str = typer.Argument(...),
    depth: int = 1,
    direction: str = "out",
    layers: Optional[List[str]] = typer.Option(None, "-l", "--layer", help="Layers to include (e.g., -l l1 -l l2)"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True),
):
    store = get_store(db_path)
    nav = Navigator(store)
    hood = nav.get_neighbors(uid, depth, direction, layers)
    if not hood:
        console.print("[yellow]No neighbours[/]")
        return
    table = Table(title=f"Neighbours of {uid} (depth {depth}, {direction})")
    table.add_column("UID", no_wrap=True)
    table.add_column("Type")
    table.add_column("Name")
    table.add_column("Dist", justify="right")
    for n in hood:
        table.add_row(n["uid"], n.get("type","?"), n.get("name","?"), str(n.get("distance","")))
    console.print(table)

    if layers:
        for n in hood:
            layer_data = {k: v for k, v in n.items() if k in layers}
            if layer_data:
                console.print(Panel(json.dumps(layer_data, indent=2), title=n["name"]))

# ── Pathfinding ──
@app.command()
def path(
    source: str = typer.Argument(...),
    target: str = typer.Argument(...),
    layers: Optional[List[str]] = typer.Option(None, "-l", "--layer", help="Layers to include"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True),
):
    store = get_store(db_path)
    nav = Navigator(store)
    way = nav.find_path(source, target, layers)
    if not way:
        console.print("[red]No path found[/]")
        return
    for i, step in enumerate(way):
        console.print(f"{i}: [bold]{step['name']}[/] ({step['entity_type']})")

# ── Search ──
@app.command()
def search(
    query: str = typer.Argument(...),
    semantic: bool = typer.Option(False, "--semantic"),
    top_k: int = 10,
    entity_type: Optional[str] = typer.Option(None, "--type"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True),
):
    store = get_store(db_path)
    nav = Navigator(store)
    if semantic:
        hits = nav.semantic_search(query, top_k)
        table = Table(title=f"Semantic search: '{query}'")
        table.add_column("Name", style="cyan")
        table.add_column("Type")
        table.add_column("Score")
        for h in hits:
            table.add_row(h["name"], h["type"], str(h["score"]))
        console.print(table)
    else:
        results = nav.search_by_name(query, entity_type, limit=top_k)
        if not results:
            console.print("[yellow]No matches[/]")
            return
        table = Table(title=f"Text search: '{query}'")
        table.add_column("UID")
        table.add_column("Type")
        table.add_column("Name")
        for e in results:
            table.add_row(e["uid"], e["type"], e["name"])
        console.print(table)

# ── Branch management ──
branch_app = typer.Typer(help="Manage narrative branches")
app.add_typer(branch_app, name="branch")

@branch_app.command("create")
def branch_create(name: str, from_branch: str = "main", db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True)):
    store = get_store(db_path)
    store.branches.create(name, from_branch)
    console.print(f"[green]Branch '{name}' created from '{from_branch}'[/]")

@branch_app.command("switch")
def branch_switch(name: str, db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True)):
    store = get_store(db_path)
    store.branches.switch(name)
    console.print(f"[green]Switched to branch '{name}'[/]")

@branch_app.command("list")
def branch_list(db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True)):
    store = get_store(db_path)
    active = store.branches.active
    for bname in store.branches.branches:
        mark = "[bold green]* " if bname == active else "  "
        console.print(f"{mark}{bname}")

@branch_app.command("merge")
def branch_merge(name: str, db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True)):
    store = get_store(db_path)
    store.branches.merge_into_main(name)
    console.print(f"[green]Branch '{name}' merged into main[/]")

@app.command()
def branch_from_narrative(
    branch_name: str = typer.Argument(...),
    session_id: str = typer.Option("default", help="Session ID to branch from"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True),
):
    """Create a new story branch based on the current narrative session state."""
    from world_narrative.context import NarrativeContext
    ctx = NarrativeContext(db_path)
    ctx.ensure_booted()
    session = asyncio.run(ctx.user_agent.load_session(session_id))
    # Create a new branch in the explorer
    store = get_store(db_path)
    store.branches.create(branch_name, from_branch=store.branches.active)
    # (Optional) Also store session snapshot in branch metadata
    console.print(f"[green]Branch '{branch_name}' created from narrative session '{session_id}'.[/]")

# ── Build (layer generation) ───────────────────────────
@app.command()
def build(
    layer: str = typer.Option("all", help="Which layer to build: l1, l2, l3, or all"),
    episodes: int = typer.Option(0, help="Number of narrative scenes (only for 'all')"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True),
):
    """Use the world_builder to generate world layers."""
    bi = BuilderInterface(db_path)
    if layer in ("l1", "all"):
        console.print("[cyan]Generating world frame & L1...[/]")
        bi.build_L1()
    if layer in ("l2", "all"):
        console.print("[cyan]Building L2 details...[/]")
        bi.build_L2()
    if layer in ("l3", "all"):
        console.print("[cyan]Building L3 secrets...[/]")
        bi.build_L3()
    console.print("[green]✓ Layers built.[/]")

# ── Generate new entities ──────────────────────────────
gen_app = typer.Typer(help="Generate new world content")
app.add_typer(gen_app, name="generate")

@gen_app.command("npc")
def gen_npc(faction_or_race: str = typer.Argument(...), db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True)):
    bi = BuilderInterface(db_path)
    node = bi.add_npc(faction_or_race)
    console.print(f"[green]Created NPC: {node.name}[/]")

@gen_app.command("item")
def gen_item(item_type: str = typer.Argument("weapon"), rarity: str = typer.Option("uncommon"),
             db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True)):
    bi = BuilderInterface(db_path)
    node = bi.add_item(item_type, rarity)
    console.print(f"[green]Created item: {node.name}[/]")

@gen_app.command("faction")
def gen_faction(db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True)):
    bi = BuilderInterface(db_path)
    node = bi.add_faction()
    console.print(f"[green]Created faction: {node.name}[/]")

@gen_app.command("location")
def gen_location(db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True)):
    bi = BuilderInterface(db_path)
    node = bi.add_location()
    console.print(f"[green]Created location: {node.name}[/]")

@gen_app.command("event")
def gen_event(db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True)):
    bi = BuilderInterface(db_path)
    node = bi.add_event()
    console.print(f"[green]Created event: {node.name}[/]")

@gen_app.command("rule")
def gen_rule(db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True)):
    bi = BuilderInterface(db_path)
    node = bi.add_rule()
    console.print(f"[green]Created rule: {node.name}[/]")

# ── Visualize ──────────────────────────────────────────
@app.command()
def visualize(
    output: Path = typer.Option("world_graph.html", help="Output HTML file path."),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, hidden=True),
):
    """Export an interactive HTML visualization of the world graph."""
    try:
        from pyvis.network import Network
    except ImportError:
        console.print("[red]pyvis is not installed. Run: pip install pyvis[/]")
        raise typer.Exit(1)

    store = get_store(db_path)
    G = store.get_active_graph()

    # Create a NetworkX-compatible Pyvis network with inline resources (works offline)
    net = Network(height="800px", width="100%", directed=True, notebook=False, cdn_resources="in_line")

    # Colour map per entity type
    type_colors = {
        "Character": "#FF6B6B",
        "Faction": "#4ECDC4",
        "Location": "#FFE66D",
        "Item": "#A37CBA",
        "Event": "#FFB347",
        "WorldRule": "#87CEEB",
        "Race": "#98FB98",
    }

    for node, attr in G.nodes(data=True):
        etype = attr.get("type", "Unknown")
        label = attr.get("label", node)
        title = f"<b>{label}</b><br>Type: {etype}"
        color = type_colors.get(etype, "#CCCCCC")
        net.add_node(node, label=label, title=title, color=color, shape="dot")

    for u, v, data in G.edges(data=True):
        edge_type = data.get("type", "related")
        source_label = data.get("source", "")
        title = f"{edge_type} (from {source_label})"
        net.add_edge(u, v, title=title, label=edge_type, arrows="to")

    # Enable physics for better layout
    net.toggle_physics(True)

    # Save the HTML file (don't open browser automatically)
    out_path = str(output)
    net.write_html(out_path, open_browser=False)
    console.print(f"[green]Visualization saved to {out_path}[/]")

if __name__ == "__main__":
    app()
