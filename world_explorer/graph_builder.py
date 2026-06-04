"""Build a NetworkX directed graph from entities and a NameIndex."""
import networkx as nx
from typing import List, Dict, Set
from .models import Entity
from .name_index import NameIndex

def build_graph(entities: List[Entity], name_index: NameIndex) -> nx.DiGraph:
    G = nx.DiGraph()

    # 1. Add nodes
    valid_uids: Set[str] = set()
    for e in entities:
        G.add_node(e.uid, label=e.name, type=e.entity_type, group=e.group_id, missing=False)
        valid_uids.add(e.uid)

    # 2. Closure to resolve using NameIndex (valid_uids managed internally)
    def resolve(name: str) -> str or None:
        return name_index.resolve(name)

    # 3. Explicit L1 relationships
    for e in entities:
        for rel in e.profile.l1.get("relationships", []):
            target = rel.get("target")
            if target and (tgt := resolve(target)):
                G.add_edge(e.uid, tgt, type=rel.get("type", "related"), source="l1", explicit=True)

    # 4. Inferred edges from L2/L3
    for e in entities:
        uid = e.uid
        for layer in ["l2", "l3"]:
            data = e.profile.get_layer(layer)
            if not data:
                continue

            # affiliations (Character → Faction/Group)
            for aff in data.get("affiliations", []):
                if tgt := resolve(aff):
                    G.add_edge(uid, tgt, type="member_of", source=layer, explicit=False)

            # notable_members (Faction → Character, reversed)
            for member in data.get("notable_members", []):
                if tgt := resolve(member):
                    G.add_edge(tgt, uid, type="member_of", source=layer, explicit=False)

            # current_location
            loc = data.get("current_location")
            if isinstance(loc, str) and (tgt := resolve(loc)):
                G.add_edge(uid, tgt, type="located_at", source=layer, explicit=False)

            # location in Events
            ev_loc = data.get("location")
            if isinstance(ev_loc, str) and (tgt := resolve(ev_loc)):
                G.add_edge(uid, tgt, type="located_at", source=layer, explicit=False)

            # ruling_faction (Location ← Faction) → edge from faction to location
            ruling = data.get("ruling_faction")
            if isinstance(ruling, str) and (tgt := resolve(ruling)):
                G.add_edge(tgt, uid, type="controls", source=layer, explicit=False)

            # tags
            for tag in data.get("tags", []):
                if isinstance(tag, str) and (tgt := resolve(tag)):
                    G.add_edge(uid, tgt, type="tagged_as", source=layer, explicit=False)

    return G
