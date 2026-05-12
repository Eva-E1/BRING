"""FastAPI web API for the Lore Explorer."""
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, Query
from .store import GraphStore
from .navigator import Navigator
from .config import DEFAULT_DB_PATH

app = FastAPI(title="Lore Explorer API", version="1.0")
store = None
nav = None

@app.on_event("startup")
async def startup():
    global store, nav
    store = GraphStore(DEFAULT_DB_PATH)
    store.boot()
    nav = Navigator(store)

@app.get("/entity/{uid}")
async def get_entity(uid: str, layers: Optional[List[str]] = Query(None)):
    data = nav.get_entity(uid, layers)
    if not data:
        return {"error": "not found"}, 404
    return data

@app.get("/neighbors/{uid}")
async def get_neighbors(uid: str, depth: int = 1, direction: str = "out",
                        layers: Optional[List[str]] = Query(None)):
    return nav.get_neighbors(uid, depth, direction, layers)

@app.get("/path")
async def get_path(source: str, target: str, layers: Optional[List[str]] = Query(None)):
    return nav.find_path(source, target, layers)

@app.get("/search")
async def search(q: str, semantic: bool = False, top_k: int = 10,
                 entity_type: Optional[str] = None,
                 page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    if semantic:
        results = nav.semantic_search(q, top_k)
    else:
        results = nav.search_by_name(q, entity_type, limit=top_k)

    total = len(results)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": results[start:end]
    }

@app.get("/graph/summary")
async def graph_summary():
    G = store.get_active_graph()
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "node_types": {ntype: len([n for n, attr in G.nodes(data=True) if attr.get("type") == ntype])
                       for ntype in set(attr.get("type", "?") for _, attr in G.nodes(data=True))},
        "active_branch": store.branches.active
    }

@app.post("/branch/create")
async def branch_create(name: str, from_branch: str = "main"):
    store.branches.create(name, from_branch)
    return {"status": "created", "branch": name}

@app.post("/branch/switch")
async def branch_switch(name: str):
    store.branches.switch(name)
    return {"active_branch": name}

@app.post("/branch/merge")
async def branch_merge(name: str):
    store.branches.merge_into_main(name)
    return {"status": "merged"}
