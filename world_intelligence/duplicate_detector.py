"""
BRING v2 — Duplicate detection using FAISS for sub-linear similarity search.
Replaces O(n²) pairwise comparison with FAISS approximate nearest neighbors.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


class DuplicateDetector:
    """
    FAISS-accelerated duplicate detection.
    Uses index search instead of O(n²) pairwise comparison.
    """

    def __init__(self, store: Any, similarity_threshold: float = 0.85):
        self.store = store
        self.entities = store.entities
        self.embeddings = store.embeddings
        self.threshold = similarity_threshold

    def find_duplicates(self) -> List[Dict[str, Any]]:
        """Find duplicate pairs using FAISS-accelerated search."""
        pairs = []
        uid_list = list(self.embeddings.uid_to_embedding.keys())

        if not uid_list:
            return []

        # Build embedding matrix
        embeddings_matrix = np.array([
            self.embeddings.uid_to_embedding[uid] for uid in uid_list
        ], dtype=np.float32)

        # Normalize for cosine similarity
        norms = np.linalg.norm(embeddings_matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        normalized = embeddings_matrix / norms

        # Try FAISS for fast search
        try:
            import faiss
            index = faiss.IndexFlatIP(normalized.shape[1])
            index.add(normalized)

            # Search for top-2 nearest neighbors (self + closest)
            similarities, indices = index.search(normalized, 2)

            for i in range(len(uid_list)):
                if indices[i][1] == -1:
                    continue
                sim = float(similarities[i][1])
                if sim >= self.threshold:
                    j = int(indices[i][1])
                    ent_i = self.store.entities_by_uid.get(uid_list[i])
                    ent_j = self.store.entities_by_uid.get(uid_list[j])
                    if ent_i and ent_j and ent_i.entity_type == ent_j.entity_type:
                        pairs.append({
                            "uid1": uid_list[i],
                            "name1": ent_i.name,
                            "uid2": uid_list[j],
                            "name2": ent_j.name,
                            "similarity": round(sim, 3),
                        })
        except ImportError:
            logger.warning("FAISS not available, using numpy fallback")
            pairs = self._find_duplicates_numpy(normalized, uid_list)

        return pairs

    def _find_duplicates_numpy(
        self, normalized: np.ndarray, uid_list: List[str]
    ) -> List[Dict[str, Any]]:
        """Numpy fallback when FAISS is not available. O(n²) but vectorized."""
        pairs = []
        n = len(uid_list)
        # Compute similarity matrix (vectorized)
        sim_matrix = normalized @ normalized.T

        for i in range(n):
            for j in range(i + 1, n):
                sim = float(sim_matrix[i, j])
                if sim >= self.threshold:
                    ent_i = self.store.entities_by_uid.get(uid_list[i])
                    ent_j = self.store.entities_by_uid.get(uid_list[j])
                    if ent_i and ent_j and ent_i.entity_type == ent_j.entity_type:
                        pairs.append({
                            "uid1": uid_list[i],
                            "name1": ent_i.name,
                            "uid2": uid_list[j],
                            "name2": ent_j.name,
                            "similarity": round(sim, 3),
                        })
        return pairs

    def merge_duplicates(self, dry_run: bool = True) -> List[str]:
        actions = []
        pairs = self.find_duplicates()
        if not pairs:
            console.print("[green]No duplicates found.[/]")
            return []

        merged = set()
        for pair in pairs:
            uid1, uid2 = pair["uid1"], pair["uid2"]
            if uid1 in merged or uid2 in merged:
                continue
            if dry_run:
                actions.append(f"Would merge {uid2} into {uid1} (sim={pair['similarity']})")
                continue

            self._merge_two(uid1, uid2)
            merged.add(uid2)
            actions.append(f"Merged {uid2} into {uid1}")

        for a in actions:
            console.print(a)
        if not dry_run:
            self.store.save()
        return actions

    def _merge_two(self, keep_uid: str, remove_uid: str):
        G = self.store.get_active_graph()
        remove_ent = self.store.entities_by_uid.get(remove_uid)
        keep_ent = self.store.entities_by_uid.get(keep_uid)
        if not remove_ent or not keep_ent:
            return

        keep_rels = keep_ent.profile.l1.setdefault("relationships", [])
        for rel in remove_ent.profile.l1.get("relationships", []):
            if rel not in keep_rels:
                keep_rels.append(rel)

        for pred in list(G.predecessors(remove_uid)):
            edge_data = G.get_edge_data(pred, remove_uid)
            if not G.has_edge(pred, keep_uid):
                G.add_edge(pred, keep_uid, **edge_data)
        for succ in list(G.successors(remove_uid)):
            edge_data = G.get_edge_data(remove_uid, succ)
            if not G.has_edge(keep_uid, succ):
                G.add_edge(keep_uid, succ, **edge_data)

        G.remove_node(remove_uid)

