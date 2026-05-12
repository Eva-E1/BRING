"""Global store: entities, graph, embeddings, branch manager."""
from pathlib import Path
from typing import List, Optional, Dict, Any
import time
from rich.console import Console
from .config import (
    DEFAULT_DB_PATH,
    AUTO_HEAL,
    DEFAULT_EMBED_LAYERS,
    embedding_is_configured,
)
from .loader import load_entities
from .models import Entity
from .name_index import NameIndex
from .graph_builder import build_graph
from .graph_validator import GraphValidator
from .branch_manager import BranchManager
from .embeddings import EmbeddingManager

console = Console()

class GraphStore:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.entities: List[Entity] = []
        self.name_index: NameIndex = None
        self.graph = None
        self.branches: BranchManager = None
        # Instantiate with defaults (reads from config automatically)
        self.embeddings = EmbeddingManager()
        self.embed_cache_file = db_path / "embeddings.pkl"
        self.booted = False

    def boot(self):
        """Heavy initialization; call once at startup."""
        if self.booted:
            return
        t0 = time.time()
        console.print("[cyan]Loading entities...[/]")
        self.entities = load_entities(self.db_path)
        console.print(f"[green]✓[/] {len(self.entities)} entities loaded "
                      f"from {self.db_path / 'entities.json'}")

        console.print("[cyan]Building name index...[/]")
        self.name_index = NameIndex(self.entities)

        console.print("[cyan]Building graph...[/]")
        self.graph = build_graph(self.entities, self.name_index)
        console.print(f"[green]✓[/] Graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")

        # Validator (self‑healing)
        if AUTO_HEAL:
            console.print("[cyan]Running self‑healing validator...[/]")
            validator = GraphValidator(self.graph, self.entities, self.name_index, auto_heal=True)
            report = validator.audit()
            console.print(f"[green]✓[/] Healed {len(validator.heal_log)} issues")

        # Branch manager
        self.branches = BranchManager(self.graph, self.db_path)

        # Embeddings (load or compute) – skip if not configured
        console.print("[cyan]Preparing embeddings...[/]")
        if not embedding_is_configured():
            console.print("[yellow]⚠ Embedding API not configured – semantic search disabled.[/]")
        else:
            with console.status("Embedding entities (first run may take a while)..."):
                self.embeddings.build_embeddings(self.entities, DEFAULT_EMBED_LAYERS,
                                                 cache_file=self.embed_cache_file,
                                                 progress_callback=None)
            console.print(f"[green]✓[/] Embeddings ready")
        elapsed = time.time() - t0
        console.print(f"[bold green]Store booted in {elapsed:.2f}s[/]")
        self.booted = True

    def get_active_graph(self):
        return self.branches.get_active_graph()

    def save_graph(self):
        """Persist graph edge changes back to entity L1 relationships.

        This method iterates through all edges in the active graph and updates
        the corresponding entities' L1 relationships. Call this after making
        changes like relationship_strength updates.
        """
        G = self.get_active_graph()

        # For each edge, check if it has attributes to persist
        for source, target, data in G.edges(data=True):
            # Find source entity
            source_entity = self.name_index.get(source)
            target_entity = self.name_index.get(target)

            if source_entity and target_entity:
                # Get current L1 relationships
                l1 = source_entity.profile.l1 if hasattr(source_entity.profile, 'l1') else {}
                if not l1:
                    l1 = {}

                # Update relationship if strength changed
                if "strength" in data:
                    rel_type = data.get("type", "knows")
                    if "relationships" not in l1:
                        l1["relationships"] = {}

                    key = f"{rel_type}:{target}"
                    l1["relationships"][key] = data["strength"]

        console.print("[cyan]Graph changes persisted to entities[/]")
