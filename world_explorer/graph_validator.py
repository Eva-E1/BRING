"""Self‑healing graph validator."""
import networkx as nx
from typing import List, Dict, Set, Any
from .models import Entity
from .name_index import NameIndex
from .config import DEAD_REF_TYPE

class GraphValidator:
    def __init__(self, graph: nx.DiGraph, entities: List[Entity], name_index: NameIndex, auto_heal: bool = True):
        self.graph = graph
        self.entities = entities
        self.name_index = name_index
        self.auto_heal = auto_heal
        self.heal_log: List[str] = []

    def audit(self) -> Dict[str, Any]:
        report = {
            "missing_targets": self._find_missing_targets(),
            "orphans": self._find_orphans(),
            "duplicates": self._find_duplicates(),
            "implicit_edges": self._find_implicit_edges(),
        }
        if self.auto_heal:
            self._heal(report)
        return report

    def _find_missing_targets(self) -> List[str]:
        missing = []
        for u, v, data in self.graph.edges(data=True):
            if v not in self.graph.nodes:
                missing.append(f"{u} -> {v} (type={data.get('type','unknown')})")
        return missing

    def _find_orphans(self) -> List[str]:
        orphans = []
        for n in self.graph.nodes:
            if self.graph.degree(n) == 0:
                orphans.append(n)
        return orphans

    def _find_duplicates(self) -> List[Dict]:
        name_map: Dict[str, List[str]] = {}
        for n, attr in self.graph.nodes(data=True):
            label = attr.get("label", "")
            name_map.setdefault(label.lower(), []).append(n)
        dupes = []
        for label, uids in name_map.items():
            if len(uids) > 1:
                dupes.append({"label": label, "uids": uids})
        return dupes

    def _find_implicit_edges(self) -> List[Dict]:
        implicit = []
        for n in self.graph.nodes:
            if self.graph.nodes[n].get("type") != "Character":
                continue
            ent = next((e for e in self.entities if e.uid == n), None)
            if not ent:
                continue

            # Check affiliations
            for layer in ["l2", "l3"]:
                affs = ent.profile.get_layer(layer).get("affiliations", [])
                for aff in affs:
                    tgt = self.name_index.resolve(aff)
                    if tgt and not self.graph.has_edge(n, tgt):
                        implicit.append({
                            "source": n,
                            "target": tgt,
                            "type": "member_of",
                            "source_field": "affiliations"
                        })

            # Check current_location
            loc = ent.profile.l2.get("current_location") or ent.profile.l3.get("current_location")
            if loc:
                tgt = self.name_index.resolve(loc)
                if tgt and not self.graph.has_edge(n, tgt):
                    implicit.append({
                        "source": n,
                        "target": tgt,
                        "type": "located_at",
                        "source_field": "current_location"
                    })

        return implicit

    def _heal(self, report: Dict[str, Any]):
        # Heal missing targets – add placeholder nodes with DEAD_REF edges
        for item in report["missing_targets"]:
            # parse the string "source -> target (type=...)"
            parts = item.split(" -> ")
            if len(parts) != 2:
                continue
            u = parts[0]
            rest = parts[1]
            # extract target name before the first parenthesis
            v = rest.split(" (")[0]
            # Add placeholder node if not present
            if v not in self.graph.nodes:
                self.graph.add_node(v, label=v, type="Unknown", missing=True)
            # Add DEAD_REF edge
            self.graph.add_edge(u, v, type=DEAD_REF_TYPE)
            self.heal_log.append(f"Added placeholder node and DEAD_REF edge for missing target: {v}")

        # Heal orphans: connect all isolated nodes to a special LOST_ITEMS node
        if report["orphans"]:
            lost_uid = "__LOST_ITEMS__"
            if lost_uid not in self.graph.nodes:
                self.graph.add_node(lost_uid, label="Lost Items", type="Meta", group="system")
            for uid in report["orphans"]:
                if uid != lost_uid:
                    self.graph.add_edge(lost_uid, uid, type="collects", source="healer")
                    self.heal_log.append(f"Connected orphan {uid} to {lost_uid}")

        # Heal duplicates: merge all duplicates into the first occurrence
        for dup in report["duplicates"]:
            keep = dup["uids"][0]
            for uid in dup["uids"][1:]:
                for pred in list(self.graph.predecessors(uid)):
                    edge_data = self.graph.get_edge_data(pred, uid)
                    self.graph.add_edge(pred, keep, **edge_data)
                for succ in list(self.graph.successors(uid)):
                    edge_data = self.graph.get_edge_data(uid, succ)
                    self.graph.add_edge(keep, succ, **edge_data)
                self.graph.remove_node(uid)
                self.heal_log.append(f"Merged duplicate {uid} into {keep}")

        # Heal implicit edges: add missing member_of / located_at edges
        for edge in report["implicit_edges"]:
            src, tgt = edge["source"], edge["target"]
            if not self.graph.has_edge(src, tgt):
                self.graph.add_edge(src, tgt, type=edge["type"], source="healer")
                self.heal_log.append(f"Added implicit edge {src} → {tgt} ({edge['type']})")
