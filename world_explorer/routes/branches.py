"""Branch management API endpoints."""
from fastapi import APIRouter

router = APIRouter(prefix="/branch", tags=["branches"])
_store = None

def init(store):
    global _store
    _store = store


@router.post("/create")
async def branch_create(name: str, from_branch: str = "main"):
    _store.branches.create(name, from_branch)
    return {"status": "created", "branch": name}


@router.post("/switch")
async def branch_switch(name: str):
    _store.branches.switch(name)
    return {"active_branch": name}


@router.post("/merge")
async def branch_merge(name: str):
    _store.branches.merge_into_main(name)
    return {"status": "merged"}

