"""
BRING v2 — Graph store using UnifiedEntityStore for O(1) lookups and batch operations.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Dict, List, Optional

import networkx as nx
from rich.console import Console

from world_core.models import EntityNode
from world_core.store import UnifiedEntityStore, NameIndex

from .config import (
    DEFAULT_DB_PATH,
    AUTO_HEAL,
    DEFAULT_EMBED_LAYERS,
    embedding_is_configured,
)
from .embeddings import EmbeddingManager
from .graph_builder import build_graph
from .graph_validator import GraphValidator
from .branch_manager import BranchManager

console = Console()


class GraphStore:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.entities: List[EntityNode] = []
        self.entities_by_uid: Dict[str, EntityNode] = {}
        self.name_index: Optional[NameIndex] = None
        self.graph: Optional[nx.DiGraph] = None
        self.branches: Optional[BranchManager] = None
        self.embeddings = EmbeddingManager()
        self.embed_cache_file = db_path / "embeddings.pkl"
        self._unified_store: Optional[UnifiedEntityStore] = None
        self.booted = False

    async def boot(self):
        if self.booted:
            return

        t0 = time.time()

        # Load via unified store for O(1) lookups
        entities_path = self.db_path / "entities.json"
        self._unified_store = UnifiedEntityStore(entities_path, auto_save=False)

        # Populate legacy lists from unified store
        self.entities = self._unified_store.all_nodes()
        self.entities_by_uid = {e.uid: e for e in self.entities}
        self.name_index = self._unified_store.name_index
        console.print(f"[green]✓[/] {len(self.entities)} entities loaded")

        # Build graph – offload to thread to avoid blocking event loop
        console.print("[cyan]Building graph...[/]")
        self.graph = await asyncio.to_thread(build_graph, self.entities, self.name_index)
        console.print(
            f"[green]✓[/] Graph: {self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges"
        )

        # Self-healing – offload to thread
        if AUTO_HEAL:
            console.print("[cyan]Running self‑healing validator...[/]")
            validator = GraphValidator(self.graph, self.entities, self.name_index, auto_heal=True)
            report = await asyncio.to_thread(validator.audit)
            console.print(f"[green]✓[/] Healed {len(validator.heal_log)} issues")

        # Branches
        self.branches = BranchManager(self.graph, self.db_path)

        # Embeddings – offload to thread
        console.print("[cyan]Preparing embeddings...[/]")
        if not embedding_is_configured():
            console.print("[yellow]⚠ Embedding API not configured.[/]")
        else:
            with console.status("Embedding entities..."):
                await asyncio.to_thread(
                    self.embeddings.build_embeddings,
                    self.entities, DEFAULT_EMBED_LAYERS,
                    cache_file=self.embed_cache_file,
                )
            console.print("[green]✓[/] Embeddings ready")

        elapsed = time.time() - t0
        console.print(f"[bold green]Store booted in {elapsed:.2f}s[/]")
        self.booted = True

    def boot_sync(self):
        """Synchronous wrapper around boot() for backward compatibility with CLI commands.

        Must NOT be called if an event loop is already running (e.g. inside API startup).
        In async contexts, use 'await graph_store.boot()' instead.
        """
        if self.booted:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, safe to use asyncio.run()
            asyncio.run(self.boot())
        else:
            # There's a running loop, use it to run boot()
            loop.run_until_complete(self.boot())

    def get_active_graph(self) -> nx.DiGraph:
        return self.branches.get_active_graph() if self.branches else self.graph

    def save_graph(self):
        """Persist graph edge changes back to entity L1 relationships."""
        if not self._unified_store:
            return

        G = self.get_active_graph()
        updates = []

        for source, target, data in G.edges(data=True):
            source_entity = self.entities_by_uid.get(source)
            if not source_entity:
                continue
            rel_type = data.get("type", "knows")
            strength = data.get("strength")
            rels = source_entity.profile.l1.setdefault("relationships", [])
            existing = next((r for r in rels if r.get("target") == target), None)
            if existing:
                existing["type"] = rel_type
                if strength is not None:
                    existing["strength"] = strength
            else:
                new_rel = {"target": target, "type": rel_type}
                if strength is not None:
                    new_rel["strength"] = strength
                rels.append(new_rel)
            updates.append((source, "l1", source_entity.profile.l1))

        if updates:
            self._unified_store.batch_update(updates)
            console.print(f"[cyan]Graph changes persisted to {len(updates)} entities[/]")
        else:
            console.print("[cyan]No graph changes to persist[/]")

    async def reload(self):
        """Force reload from disk."""
        self.booted = False
        await self.boot()
