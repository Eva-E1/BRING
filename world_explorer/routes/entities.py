"""Entity-related API endpoints."""
from fastapi import APIRouter, Query
from typing import List, Optional

router = APIRouter(prefix="", tags=["entities"])

# These will be injected at startup
_nav = None
_store = None

def init(nav, store):
    global _nav, _store
    _nav = nav
    _store = store


@router.get("/entity/{uid}")
async def get_entity(uid: str, layers: Optional[List[str]] = Query(None)):
    data = _nav.get_entity(uid, layers)
    if not data:
        return {"error": "not found"}, 404
    return data


@router.get("/neighbors/{uid}")
async def get_neighbors(
    uid: str,
    depth: int = 1,
    direction: str = "out",
    layers: Optional[List[str]] = Query(None),
):
    return _nav.get_neighbors(uid, depth, direction, layers)


@router.get("/path")
async def get_path(
    source: str, target: str, layers: Optional[List[str]] = Query(None)
):
    return _nav.find_path(source, target, layers)


@router.get("/search")
async def search(
    q: str,
    semantic: bool = False,
    top_k: int = 10,
    entity_type: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    if semantic:
        results = _nav.semantic_search(q, top_k)
    else:
        results = _nav.search_by_name(q, entity_type, limit=top_k)
    total = len(results)
    start = (page - 1) * page_size
    paged = results[start:start + page_size]
    return {"results": paged, "total": total, "page": page, "page_size": page_size}


@router.get("/graph/summary")
async def graph_summary():
    G = _store.get_active_graph()
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "node_types": {
            ntype: len([n for n, attr in G.nodes(data=True) if attr.get("type") == ntype])
            for ntype in set(attr.get("type", "?") for _, attr in G.nodes(data=True))
        },
        "active_branch": _store.branches.active if _store.branches else "main",
    }

