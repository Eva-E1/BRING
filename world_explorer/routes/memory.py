"""Memory management API endpoints."""
from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Optional

router = APIRouter(prefix="/memory", tags=["memory"])
_ctx = None

def init(ctx):
    global _ctx
    _ctx = ctx


@router.post("/forget")
async def memory_forget(older_than: int = 30, min_importance: float = 0.2):
    removed = await _ctx.world_memory.forget_old_entries(older_than, min_importance)
    return {"removed": removed}


@router.post("/summarise")
async def memory_summarise(tag: Optional[str] = None, node_uid: Optional[str] = None):
    if not tag and not node_uid:
        raise HTTPException(400, "Provide tag or node_uid")
    if tag:
        count = await _ctx.world_memory.consolidate_cluster(tag=tag)
    else:
        count = await _ctx.world_memory.consolidate_cluster(node_uid=node_uid)
    return {"consolidated": count}

