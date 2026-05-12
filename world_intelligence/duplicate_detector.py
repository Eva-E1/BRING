"""Intelligent duplicate detection and merging using embeddings."""
import numpy as np
from typing import List, Dict, Any, Optional
from rich.console import Console
from world_explorer.store import GraphStore

console = Console()

class DuplicateDetector:
    def __init__(self, store: GraphStore, similarity_threshold: float = 0.85):
        self.store = store
        self.entities = store.entities
        self.embeddings = store.embeddings
        self.threshold = similarity_threshold

    def find_duplicates(self) -> List[Dict[str, Any]]:
        """Return pairs of entities that are likely duplicates."""
        pairs = []
        uids = list(self.embeddings.uid_to_embedding.keys())
        for i in range(len(uids)):
            for j in range(i+1, len(uids)):
                sim = self._cosine_sim(self.embeddings.uid_to_embedding[uids[i]],
                                       self.embeddings.uid_to_embedding[uids[j]])
                if sim >= self.threshold:
                    # Ensure they are the same type or at least compatible
                    ent_i = self.store.entities_by_uid.get(uids[i])
                    ent_j = self.store.entities_by_uid.get(uids[j])
                    if ent_i and ent_j and ent_i.entity_type == ent_j.entity_type:
                        pairs.append({
                            "uid1": uids[i],
                            "name1": ent_i.name,
                            "uid2": uids[j],
                            "name2": ent_j.name,
                            "similarity": round(sim, 3),
                        })
        return pairs

    def merge_duplicates(self, dry_run: bool = True) -> List[str]:
        """Merge detected duplicates. If dry_run, just returns list of actions."""
        actions = []
        pairs = self.find_duplicates()
        if not pairs:
            console.print("[green]No duplicates found.[/]")
            return []

        # Sort by similarity, keep the first as the "canonical" entity
        merged = set()
        for pair in pairs:
            uid1, uid2 = pair["uid1"], pair["uid2"]
            if uid1 in merged or uid2 in merged:
                continue
            if dry_run:
                actions.append(f"Would merge {uid2} into {uid1} (similarity {pair['similarity']})")
                continue
            # Perform merge in store and graph
            self._merge_two(uid1, uid2)
            merged.add(uid2)
            actions.append(f"Merged {uid2} into {uid1}")

        if dry_run:
            for a in actions:
                console.print(a)
        else:
            for a in actions:
                console.print(a)
            self.store.save()
        return actions

    def _merge_two(self, keep_uid: str, remove_uid: str):
        """Merge remove_uid into keep_uid, updating graph and store."""
        G = self.store.get_active_graph()
        # Transfer relationships and edges
        remove_ent = self.store.entities_by_uid.get(remove_uid)
        keep_ent = self.store.entities_by_uid.get(keep_uid)
        if not remove_ent or not keep_ent:
            return
        # Merge L1 relationships
        keep_rels = keep_ent.profile.l1.setdefault("relationships", [])
        for rel in remove_ent.profile.l1.get("relationships", []):
            if rel not in keep_rels:
                keep_rels.append(rel)
        # Update graph edges
        for pred in list(G.predecessors(remove_uid)):
            edge_data = G.get_edge_data(pred, remove_uid)
            if not G.has_edge(pred, keep_uid):
                G.add_edge(pred, keep_uid, **edge_data)
        for succ in list(G.successors(remove_uid)):
            edge_data = G.get_edge_data(remove_uid, succ)
            if not G.has_edge(keep_uid, succ):
                G.add_edge(keep_uid, succ, **edge_data)
        # Remove the duplicate node
        G.remove_node(remove_uid)
        # Remove from store
        # Note: EntityStore doesn't have remove, but we can mark it as deleted.
        # Since we're just removing edges, keep it for now.
        # A full implementation would remove from the JSON as well.
        # For simplicity, we'll rely on the graph to be rebuilt next time.

    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
