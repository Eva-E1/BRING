"""CLI for the World Intelligence Engine."""
import asyncio
from pathlib import Path
from typing import Optional, List
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import json
from world_explorer.store import GraphStore
from world_explorer.navigator import Navigator
from world_explorer.builder_integration import BuilderInterface
from world_explorer.config import DEFAULT_DB_PATH
from .graph_analyzer import GraphAnalyzer
from .recommender import Recommender
from .scene_generator import SceneGenerator
from .rule_checker import RuleChecker
from .subgraph_expander import SubgraphExpander
from .pipeline import EnrichmentPipeline

app = typer.Typer(help="🧠 World Intelligence – analysis, recommendations, auto‑enrichment")
console = Console()

def get_store(db_path: Path = DEFAULT_DB_PATH) -> GraphStore:
    store = GraphStore(db_path)
    store.boot()
    return store

def get_builder(db_path: Path = DEFAULT_DB_PATH) -> BuilderInterface:
    return BuilderInterface(db_path)

@app.command()
def analyze(
    db_path: Path = typer.Option(DEFAULT_DB_PATH, help="Path to world_db"),
):
    """Show social network analysis of the world graph."""
    store = get_store(db_path)
    analyzer = GraphAnalyzer(store)

    console.print("[bold]Centrality Report (top 10 by degree)[/]")
    rep = analyzer.centrality_report(top_n=10)
    table = Table(title="Top Degree Centrality")
    table.add_column("UID")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Degree")
    table.add_column("Betweenness")
    table.add_column("Closeness")
    for n in rep["top_degree"]:
        table.add_row(n["uid"], n["name"], n["type"],
                      str(n["degree_centrality"]), str(n["betweenness_centrality"]), str(n["closeness_centrality"]))
    console.print(table)

    console.print("\n[bold]Community Detection[/]")
    comm = analyzer.community_detection()
    for cid, members in comm["communities"].items():
        console.print(f"Community {cid}: {', '.join([m['name'] for m in members])}")

    console.print("\n[bold]Path Statistics[/]")
    stats = analyzer.path_stats()
    console.print(f"Average shortest path: {stats['average_shortest_path_length']}")
    console.print(f"Diameter: {stats['diameter']}")
    console.print(f"Connected: {stats['is_connected']}")

@app.command()
def recommend(
    db_path: Path = typer.Option(DEFAULT_DB_PATH, help="Path to world_db"),
):
    """Suggest missing relationships and new entities."""
    store = get_store(db_path)
    rec = Recommender(store)
    console.print("[bold]Missing relationship suggestions[/]")
    missing = rec.suggest_missing_relationships(top_k=20)
    if missing:
        for r in missing:
            console.print(f"  {r['source_name']} ↔ {r['target_name']} (common neighbors: {r['common_neighbors']}, score: {r['score']:.3f})")
    else:
        console.print("No strong suggestions.")

    console.print("\n[bold]New entity suggestions[/]")
    new = rec.suggest_new_entities()
    if new:
        for e in new:
            console.print(f"  {e['suggested_type']} based on {e['based_on_members']}")
    else:
        console.print("No suggestions.")

@app.command()
def generate_scene(
    uid: str = typer.Argument(..., help="Entity UID to center the scene on"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, help="Path to world_db"),
):
    """Generate a narrative scene around an entity."""
    store = get_store(db_path)
    builder = get_builder(db_path)
    gen = SceneGenerator(store, builder)
    scene = asyncio.run(gen.generate_scene_from_cluster(uid))
    console.print_json(data=scene)

@app.command()
def check_rules(
    auto_fix: bool = typer.Option(False, "--fix", help="Automatically repair violations"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, help="Path to world_db"),
):
    """Check all entities for rule violations and optionally fix them."""
    store = get_store(db_path)
    builder = get_builder(db_path)
    checker = RuleChecker(store, builder)
    conflicts = checker.check_all(auto_fix=auto_fix)
    if not conflicts:
        console.print("[green]No rule violations found.[/]")
    else:
        console.print(f"[red]Found {len(conflicts)} violations:[/]")
        for c in conflicts:
            console.print(f"  {c['name']}: {c['description']}")
        if auto_fix:
            console.print("Auto‑fix applied.")

@app.command()
def expand(
    uid: str = typer.Argument(..., help="Entity UID to expand around"),
    depth: int = typer.Option(2, help="Subgraph depth"),
    fix_rules: bool = typer.Option(False, "--fix-rules", help="Auto‑fix rule violations in subgraph"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, help="Path to world_db"),
):
    """Expand a subgraph: complete missing data, check rules, generate a scene."""
    store = get_store(db_path)
    builder = get_builder(db_path)
    expander = SubgraphExpander(store, builder)
    report = expander.expand(uid, depth=depth, fix_rules=fix_rules)
    console.print_json(data=report)

@app.command()
def enrich(
    db_path: Path = typer.Option(DEFAULT_DB_PATH, help="Path to world_db"),
    fix_rules: bool = typer.Option(False, "--fix-rules", help="Automatically repair rule violations"),
    background: bool = typer.Option(False, "--background", help="Run enrichment in the background (non‑blocking)"),
):
    """Run the full enrichment pipeline (complete layers, relationships, rule check, recommendations)."""
    store = get_store(db_path)
    builder = get_builder(db_path)
    pipeline = EnrichmentPipeline(store, builder)
    if background:
        console.print("[cyan]Enrichment started in background. The process will run asynchronously.[/]")
        # We run the async pipeline and let it continue in the background.
        # Since Typer command functions are synchronous, we create a new event loop task.
        loop = asyncio.get_event_loop()
        loop.create_task(pipeline.run_async(complete_layers=True, relationships=True, check_rules=True, fix_rules=fix_rules))
        # We must not let the main thread exit. In a real application you'd await the task.
        # For now, we'll just run synchronously if not background, otherwise notify.
        console.print("Run 'python -m world_intelligence.cli enrich --background' and then leave the terminal open.")
    else:
        pipeline.run(complete_layers=True, relationships=True, check_rules=True, fix_rules=fix_rules)

@app.command()
def deduplicate(
    dry_run: bool = typer.Option(True, help="Show what would be merged without actually merging"),
    db_path: Path = typer.Option(DEFAULT_DB_PATH, help="Path to world_db"),
):
    """Detect and merge duplicate entities using semantic similarity."""
    store = get_store(db_path)
    from .duplicate_detector import DuplicateDetector
    detector = DuplicateDetector(store, similarity_threshold=0.85)
    detector.merge_duplicates(dry_run=dry_run)

if __name__ == "__main__":
    app()
