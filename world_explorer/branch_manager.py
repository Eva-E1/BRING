"""Branch overlay management: alternate storylines without touching base graph."""
import json
from pathlib import Path
from typing import Dict, Any
import networkx as nx

class Branch:
    def __init__(self, parent: str = "main"):
        self.parent = parent
        self.additions: Dict[str, Any] = {"nodes": [], "edges": []}
        self.deletions: list = []  # list of (source, target) edges to remove

class BranchManager:
    def __init__(self, base_graph: nx.DiGraph, db_path: Path):
        self.base_graph = base_graph
        self.db_path = db_path
        self.branches: Dict[str, Branch] = {}
        self.active = "main"
        self._load_branches()

    def _branches_file(self) -> Path:
        return self.db_path / "branches.json"

    def _load_branches(self):
        f = self._branches_file()
        if f.exists():
            with open(f) as fp:
                data = json.load(fp)
                for name, bdata in data.items():
                    branch = Branch(parent=bdata.get("parent", "main"))
                    branch.additions = bdata.get("additions", {"nodes": [], "edges": []})
                    branch.deletions = bdata.get("deletions", [])
                    self.branches[name] = branch
        else:
            # Ensure 'main' branch exists (empty)
            self.branches["main"] = Branch()

    def _save_branches(self):
        ser = {}
        for name, branch in self.branches.items():
            ser[name] = {
                "parent": branch.parent,
                "additions": branch.additions,
                "deletions": branch.deletions,
            }
        self._branches_file().write_text(json.dumps(ser, indent=2))

    def create(self, name: str, from_branch: str = "main"):
        if name in self.branches:
            raise ValueError(f"Branch '{name}' already exists")
        self.branches[name] = Branch(parent=from_branch)
        self._save_branches()

    def switch(self, name: str):
        if name not in self.branches:
            raise ValueError(f"Branch '{name}' not found")
        self.active = name

    def get_active_graph(self) -> nx.DiGraph:
        if self.active == "main":
            return self.base_graph
        branch = self.branches[self.active]
        # Start from parent
        if branch.parent == "main":
            G = self.base_graph.copy()
        else:
            # Recursively apply parent branch (simplified: assume parent is already resolved)
            parent_branch = self.branches[branch.parent]
            G = self._apply_branch(self.base_graph, parent_branch)
        # Apply current branch modifications
        G = self._apply_branch_modifications(G, branch)
        return G

    def _apply_branch(self, graph: nx.DiGraph, branch: Branch) -> nx.DiGraph:
        G = graph.copy()
        return self._apply_branch_modifications(G, branch)

    def _apply_branch_modifications(self, G: nx.DiGraph, branch: Branch) -> nx.DiGraph:
        # Remove edges
        for src, tgt in branch.deletions:
            if G.has_edge(src, tgt):
                G.remove_edge(src, tgt)
        # Add nodes
        for n in branch.additions.get("nodes", []):
            G.add_node(n["uid"], **n.get("attr", {}))
        # Add edges
        for e in branch.additions.get("edges", []):
            G.add_edge(e["source"], e["target"], **e.get("attr", {}))
        return G

    def add_node(self, uid: str, attr: dict = None):
        branch = self.branches[self.active]
        branch.additions["nodes"].append({"uid": uid, "attr": attr or {}})
        self._save_branches()

    def delete_edge(self, source: str, target: str):
        branch = self.branches[self.active]
        branch.deletions.append((source, target))
        self._save_branches()

    def merge_into_main(self, branch_name: str):
        """Permanently apply a branch to the base graph."""
        if branch_name not in self.branches:
            raise ValueError("Branch not found")
        branch = self.branches[branch_name]
        G = self._apply_branch_modifications(self.base_graph, branch)
        self.base_graph = G
        # Remove the branch and reset active to main
        del self.branches[branch_name]
        self.active = "main"
        self._save_branches()
