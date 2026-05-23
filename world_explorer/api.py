
"""FastAPI web API for the Lore Explorer – extended with UI and /api prefix rewriting."""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Query, UploadFile, File, HTTPException, Request
from fastapi.responses import Response, HTMLResponse
from fastapi import WebSocket, WebSocketDisconnect
from starlette.middleware.base import BaseHTTPMiddleware

from .store import GraphStore
from .navigator import Navigator
from .config import DEFAULT_DB_PATH
from .templates import UI_HTML

from world_narrative.context import NarrativeContext
from world_explorer.config import DEFAULT_DB_PATH as NARRATIVE_DB_PATH


# ------------------------------------------------------------------
# Middleware to rewrite /api/* -> /*
# ------------------------------------------------------------------
class RewriteApiPrefixMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if path.startswith("/api"):
            # rewrite path by removing /api prefix
            new_path = path[4:] or "/"
            request.scope["path"] = new_path
        return await call_next(request)


# ------------------------------------------------------------------
# FastAPI App
# ------------------------------------------------------------------
app = FastAPI(title="Lore Explorer API + UI", version="1.0")
app.add_middleware(RewriteApiPrefixMiddleware)


# ------------------------------------------------------------------
# Global State
# ------------------------------------------------------------------
store = None
nav = None
history_mgr = None
_shared_context: Optional["NarrativeContext"] = None


# ------------------------------------------------------------------
# WebSocket Connection Manager
# ------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass  # Ignore send errors


memory_manager = ConnectionManager()


# ------------------------------------------------------------------
# WebSocket memory broadcasting callback
# ------------------------------------------------------------------
async def broadcast_memory_event(entry):
    """Callback for WorldMemory to broadcast new memories to all connected clients."""
    await memory_manager.broadcast({
        "type": "memory_added",
        "event": {
            "id": entry.id,
            "content": entry.content[:200] if entry.content else "",
            "importance": entry.importance,
            "source_type": getattr(entry, 'source_type', 'unknown'),
            "timestamp": entry.timestamp.isoformat() if hasattr(entry, 'timestamp') else ""
        }
    })


# ------------------------------------------------------------------
# Context Management
# ------------------------------------------------------------------
def get_maintenance_context() -> "NarrativeContext":
    """Get the shared narrative context.

    Context is created and started at server startup.
    """
    global _shared_context
    if _shared_context is None:
        raise RuntimeError("Shared context not initialized. Server may not have started properly.")
    return _shared_context


# ------------------------------------------------------------------
# Serve the UI at root
# ------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    return HTMLResponse(content=UI_HTML)


# ------------------------------------------------------------------
# Startup / Shutdown Events
# ------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    global store, nav, history_mgr, _shared_context
    from world_core.history_manager import HistoryManager

    store = GraphStore(DEFAULT_DB_PATH)
    store.boot()
    nav = Navigator(store)
    history_mgr = HistoryManager(DEFAULT_DB_PATH)

    # Initialize shared context and start background services once
    _shared_context = NarrativeContext(NARRATIVE_DB_PATH)
    await _shared_context.start_background_services()

    # Register the WebSocket broadcasting callback for memory events
    _shared_context.world_memory.set_broadcast_callback(broadcast_memory_event)


@app.on_event("shutdown")
async def shutdown():
    """Clean up shared context on shutdown."""
    global _shared_context
    if _shared_context is not None:
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_shared_context.stop_background_services())
            else:
                loop.run_until_complete(_shared_context.stop_background_services())
        except Exception:
            pass
        _shared_context = None


# ------------------------------------------------------------------
# Entity API Endpoints
# ------------------------------------------------------------------
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
    paged = results[start:start + page_size]

    return {
        "results": paged,
        "total": total,
        "page": page,
        "page_size": page_size
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


# ------------------------------------------------------------------
# Branch Management
# ------------------------------------------------------------------
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


# ------------------------------------------------------------------
# Maintenance API Endpoints
# ------------------------------------------------------------------
@app.post("/maintenance/run")
async def run_maintenance(full: bool = True):
    """Trigger a maintenance cycle (full or quick)."""
    ctx = get_maintenance_context()
    try:
        if full:
            report = await ctx.world_memory.optimizer.run_full_maintenance()
            return {"status": "complete", "full": True, "report": report}
        else:
            # Quick: only consolidation and cleanup
            await ctx.world_memory.trigger_consolidation()
            removed = await ctx.world_memory.clear_old_entries()
            return {
                "status": "complete",
                "full": False,
                "consolidation_triggered": True,
                "old_entries_removed": removed
            }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/maintenance/status")
async def maintenance_status():
    """Get current memory and maintenance statistics."""
    ctx = get_maintenance_context()
    stats = await ctx.world_memory.get_stats()
    optimizer_stats = ctx.world_memory.optimizer.get_stats()
    return {
        "memory": stats,
        "maintenance": optimizer_stats
    }


@app.post("/maintenance/rebuild-index")
async def rebuild_index():
    """Force rebuild of FAISS index."""
    ctx = get_maintenance_context()
    await ctx.world_memory.rebuild_faiss_index()
    return {"status": "rebuilt", "index_size": ctx.world_memory.get_stats().get("faiss_index_size", 0)}


@app.post("/maintenance/clean-orphans")
async def clean_orphans():
    """Clean orphaned embedding files."""
    ctx = get_maintenance_context()
    removed = await ctx.world_memory.clean_orphaned_embeddings()
    return {"status": "cleaned", "orphans_removed": removed}


# ------------------------------------------------------------------
# WebSocket Endpoint for Real-time Memory Events
# ------------------------------------------------------------------
@app.websocket("/ws/memory")
async def websocket_memory(websocket: WebSocket):
    """WebSocket endpoint for real-time memory updates."""
    await memory_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive - wait for any message
            await websocket.receive_text()
    except WebSocketDisconnect:
        memory_manager.disconnect(websocket)


# ------------------------------------------------------------------
# Roleplay WebSocket Session Management
# ------------------------------------------------------------------
roleplay_sessions = {}


class RoleplaySession:
    """Manages one client's roleplay engine and WebSocket connection."""

    def __init__(self, session_id: str, websocket: WebSocket, character: str = None, location: str = None):
        self.session_id = session_id
        self.websocket = websocket
        self.character = character or "Unknown"
        self.location = location or "The Crossroads"
        self.engine = None
        self._running = True

    async def start(self):
        """Initialize narrative context and roleplay engine using shared context."""
        global history_mgr, _shared_context
        # Use the shared context (already started at server startup)
        self.engine = _shared_context.create_roleplay_engine()
        # Set session parameters with character and location from WebSocket query
        self.engine.set_session(
            character=self.character,
            location=self.location,
            story_time=datetime.now(),
            role="protagonist",
            session_id=self.session_id
        )
        # Load existing session if any
        if hasattr(self.engine, 'load_session'):
            self.engine.load_session(self.session_id)
        # Send initial status
        await self.send_status()

    async def send_status(self):
        """Send current character status and location."""
        status = {
            "type": "status",
            "character": getattr(self.engine, 'active_character', None),
            "location": getattr(self.engine, 'current_location', None),
            "time": getattr(self.engine, 'current_time', None),
            "health": None,
            "mood": None,
        }
        if self.engine and hasattr(self.engine, 'active_character') and self.engine.active_character:
            npc = _shared_context.npc_mgr.get(self.engine.active_character)
            if npc and hasattr(npc, 'health'):
                status["health"] = npc.health
                status["mood"] = getattr(npc, 'mood', None)
        await self.websocket.send_json(status)

    async def process_message(self, data: dict):
        """Process a single message from the client."""
        msg_type = data.get("type", "text")
        if msg_type == "text":
            user_input = data.get("content", "")
            if not user_input:
                return
            # Process input asynchronously and stream response
            response = await self.engine.process_input(user_input)
            # Send the full response
            await self.websocket.send_json({
                "type": "narrative",
                "content": response
            })
            # Update status after action
            await self.send_status()
        elif msg_type == "command":
            cmd = data.get("command", "")
            if cmd.startswith("/"):
                response = await self.engine.process_input(cmd)
                await self.websocket.send_json({
                    "type": "narrative",
                    "content": response
                })
            else:
                await self.websocket.send_json({
                    "type": "error",
                    "content": f"Unknown command: {cmd}"
                })
        elif msg_type == "ping":
            await self.websocket.send_json({"type": "pong"})

    async def run(self):
        """Main loop for this session."""
        try:
            while self._running:
                data = await self.websocket.receive_text()
                try:
                    msg = json.loads(data)
                    await self.process_message(msg)
                except json.JSONDecodeError:
                    # Treat as plain text input
                    await self.process_message({"type": "text", "content": data})
        except WebSocketDisconnect:
            pass
        finally:
            # Save session state
            if hasattr(self.engine, 'save_session'):
                self.engine.save_session(self.session_id)
            roleplay_sessions.pop(self.session_id, None)

    async def stop(self):
        self._running = False


@app.websocket("/ws/roleplay/{session_id}")
async def websocket_roleplay(websocket: WebSocket, session_id: str):
    """WebSocket for real-time narrative roleplay."""
    character = websocket.query_params.get("character", "Unknown")
    location = websocket.query_params.get("location", "The Crossroads")
    await websocket.accept()
    session = RoleplaySession(session_id, websocket, character, location)
    roleplay_sessions[session_id] = session
    await session.start()
    await session.run()


# ------------------------------------------------------------------
# Memory Management API Endpoints
# ------------------------------------------------------------------
@app.post("/memory/forget")
async def api_memory_forget(older_than: int = 30, min_importance: float = 0.2):
    """Forget old, low-importance memories."""
    ctx = get_maintenance_context()
    removed = await ctx.world_memory.forget_old_entries(older_than, min_importance)
    return {"removed": removed}


@app.post("/memory/summarise")
async def api_memory_summarise(tag: Optional[str] = None, node_uid: Optional[str] = None):
    """Summarise memories with a given tag or node UID."""
    if not tag and not node_uid:
        raise HTTPException(400, "Provide tag or node_uid")
    ctx = get_maintenance_context()
    if tag:
        count = await ctx.world_memory.consolidate_cluster(tag=tag)
    else:
        count = await ctx.world_memory.consolidate_cluster(node_uid=node_uid)
    return {"consolidated": count}


@app.get("/memory/export")
async def api_memory_export(fmt: str = "json"):
    """Export all memories to a file."""
    ctx = get_maintenance_context()
    data = await ctx.world_memory.export_memories(fmt)
    media_type = "application/json" if fmt == "json" else "application/parquet"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=memories.{fmt}"}
    )


@app.post("/memory/import")
async def api_memory_import(file: UploadFile = File(...), merge: bool = True):
    """Import memories from a file."""
    content = await file.read()
    fmt = "parquet" if file.filename.endswith(".parquet") else "json"
    ctx = get_maintenance_context()
    await ctx.world_memory.import_memories(content, fmt, merge)
    return {"status": "imported"}


@app.post("/memory/update/{entry_id}")
async def api_memory_update(entry_id: str, new_content: str):
    """Update a memory entry, creating a new version."""
    ctx = get_maintenance_context()
    new_id = await ctx.world_memory.update_memory(entry_id, new_content)
    if not new_id:
        raise HTTPException(404, "Entry not found")
    return {"status": "updated", "new_entry_id": new_id}


# ------------------------------------------------------------------
# Probability API Endpoints
# ------------------------------------------------------------------
@app.get("/probability/{character}/{profile}")
async def get_probability(character: str, profile: str, target: str = None):
    """Get success probability for a character action."""
    from world_core.probability.profiles import get_profile
    ctx = get_maintenance_context()
    profile_obj = get_profile(profile)
    if not profile_obj:
        raise HTTPException(404, f"Profile {profile} not found")
    context = await ctx.prob_resolver.build_context(actor=character, target=target, action_type=profile)
    prob = ctx.prob_engine.get_success_chance(profile_obj, context, character)
    return {"character": character, "profile": profile, "probability": prob}


@app.post("/probability/modifier")
async def apply_probability_modifier(
    entity: str,
    parameter: str,
    value: float,
    duration_seconds: int = None
):
    """Apply a probability modifier to an entity."""
    from world_core.probability.models import ProbabilityModifier, ModifierType
    ctx = get_maintenance_context()
    uid = f"Character:{entity}" if ":" not in entity else entity
    mod = ProbabilityModifier(
        parameter_name=parameter,
        value=value,
        modifier_type=ModifierType.ADD,
        duration_seconds=duration_seconds,
        source="api"
    )
    ctx.prob_engine.apply_modifier(uid, mod)
    return {"status": "applied", "modifier": mod.to_dict()}


@app.get("/probability/modifiers/{entity}")
async def get_probability_modifiers(entity: str):
    """Get active probability modifiers for an entity."""
    ctx = get_maintenance_context()
    uid = f"Character:{entity}" if ":" not in entity else entity
    modifiers = ctx.prob_engine.get_modifiers(uid)
    return {"entity": uid, "modifiers": [m.to_dict() for m in modifiers]}


# ------------------------------------------------------------------
# Romance API Endpoints
# ------------------------------------------------------------------
@app.get("/romance/{character1}/{character2}")
async def get_romance(character1: str, character2: str):
    """Get romance relationship status between two characters."""
    ctx = get_maintenance_context()
    rel = await ctx.romance_engine.get_relationship(character1, character2)
    if not rel:
        return {"status": "no_relationship"}
    return {
        "status": rel.status.value,
        "affection": rel.affection,
        "compatibility": rel.compatibility,
        "stage": rel.progression_stage.value,
        "last_interaction": rel.last_interaction.isoformat() if rel.last_interaction else None
    }


@app.post("/romance/attempt/{action}")
async def attempt_romance_action(
    action: str,
    character: str,
    target: str,
    location: str = "unknown",
    message: str = ""
):
    """Attempt a romance action (attraction, confession, date, kiss, proposal, breakup)."""
    ctx = get_maintenance_context()
    if action == "attraction":
        success, narrative, aff = await ctx.romance_engine.attempt_attraction(
            character, target, location
        )
    elif action == "confess":
        success, narrative, aff = await ctx.romance_engine.attempt_confession(
            character, target, location, message
        )
    elif action == "date":
        success, narrative, aff = await ctx.romance_engine.attempt_date(
            character, target, location
        )
    elif action == "kiss":
        success, narrative, aff = await ctx.romance_engine.attempt_kiss(
            character, target, location
        )
    elif action == "propose":
        success, narrative, aff = await ctx.romance_engine.attempt_proposal(
            character, target, location
        )
    elif action == "breakup":
        success, narrative, aff = await ctx.romance_engine.attempt_breakup(
            character, target, message
        )
    else:
        raise HTTPException(400, f"Unknown romance action: {action}")

    return {
        "success": success,
        "narrative": narrative,
        "affection_change": aff
    }


@app.get("/romance/characters/{character}")
async def get_character_romances(character: str):
    """Get all romance relationships for a character."""
    ctx = get_maintenance_context()
    relationships = await ctx.romance_engine.get_all_relationships(character)
    return {
        "character": character,
        "relationships": [
            {
                "partner": rel.partner,
                "status": rel.status.value,
                "affection": rel.affection,
                "stage": rel.progression_stage.value
            }
            for rel in relationships
        ]
    }


# ------------------------------------------------------------------
# Quests API Endpoints
# ------------------------------------------------------------------
@app.get("/quests")
async def get_quests():
    """Get all active quests."""
    ctx = get_maintenance_context()
    quests = ctx.quest_mgr.get_all_quests()
    return {
        "quests": [
            {
                "id": q.id,
                "title": q.title,
                "description": q.description,
                "progress": getattr(q, "progress", 0),
                "status": q.status,
                "npc": getattr(q, "giver", ""),
                "location": getattr(q, "location", ""),
                "objectives": q.objectives
            }
            for q in quests
        ]
    }


@app.get("/quest/{quest_id}")
async def get_quest(quest_id: str):
    """Get a specific quest by ID."""
    ctx = get_maintenance_context()
    quest = ctx.quest_mgr.get_quest(quest_id)
    if not quest:
        raise HTTPException(404, "Quest not found")
    return {
        "id": quest.id,
        "title": quest.title,
        "description": quest.description,
        "progress": quest.progress,
        "status": quest.status,
        "objectives": quest.objectives
    }


# ------------------------------------------------------------------
# Session History API Endpoints
# ------------------------------------------------------------------
@app.get("/sessions")
async def list_sessions():
    """List all session histories."""
    ctx = get_maintenance_context()
    sessions = ctx.history_mgr.list_sessions()
    return sessions


@app.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str):
    """Get conversation history for a session."""
    ctx = get_maintenance_context()
    turns = ctx.history_mgr.get_conversation_pairs(session_id)
    return {"session_id": session_id, "turns": turns}


@app.get("/sessions/{session_id}/summarize")
async def summarize_session(session_id: str):
    """Summarize a session's conversation history."""
    ctx = get_maintenance_context()
    turns = ctx.history_mgr.get_last_n(session_id, 30)
    if not turns:
        return {"session_id": session_id, "summary": "No conversation history found."}

    # Build conversation text (last 30 turns)
    conv_text = "\n".join(
        f"{t['role']}: {t['content']}" for t in turns[-30:]
    )
    prompt = (
        f"Summarize the following conversation in 2-3 sentences, "
        f"focusing on key events and decisions:\n\n{conv_text}"
    )

    ctx = get_maintenance_context()
    summary = await ctx.llm.generate_text(prompt, temperature=0.5)
    return {"session_id": session_id, "summary": summary}


# ------------------------------------------------------------------
# Launch / New Game Endpoints
# ------------------------------------------------------------------
@app.get("/sessions/list")
async def list_all_sessions():
    """List all available game sessions (snapshots and session files)."""
    from world_narrative.launcher import list_sessions
    sessions = list_sessions()
    return {"sessions": sessions, "count": len(sessions)}


@app.post("/launch")
async def api_launch(
    hints: str = "",
    isekai: bool = False,
    starting_age: int = 5,
    port: int = 8000,
    open_browser: bool = True,
):

    """
    Launch a new game - creates world (if needed), generates character,
    runs post-birth tasks, and returns session info.
    """
    from world_narrative.launcher import launch_new_game
    from world_explorer.config import DEFAULT_DB_PATH

    try:
        session_id, character_name, opening = await launch_new_game(
            hints=hints,
            isekai=isekai,
            starting_age=starting_age,
            db_path=DEFAULT_DB_PATH,
            open_browser=open_browser,
            port=port
        )
        return {
            "status": "success",
            "session_id": session_id,
            "character_name": character_name,
            "opening_narrative": opening,
            "url": f"http://localhost:{port}/?session={session_id}&character={character_name}"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/continue")
async def api_continue(request: Request):

    """Continue an existing game session."""
    from world_narrative.launcher import continue_game
    from world_explorer.config import DEFAULT_DB_PATH

    # Extract JSON body
    try:
        body = await request.json()
    except Exception:
        body = {}

    session_id = body.get("session_id", "")
    port = body.get("port", 8000)
    open_browser = body.get("open_browser", True)

    if not session_id:
        return {"status": "error", "error": "session_id is required"}

    try:
        ctx = await continue_game(
            session_id=session_id,
            db_path=DEFAULT_DB_PATH,
            open_browser=open_browser,
            port=port
        )

        # Get character name
        try:
            engine = ctx.create_roleplay_engine()
            character_name = getattr(engine, 'active_character', 'Unknown')
        except Exception:
            character_name = 'Unknown'

        return {
            "status": "success",
            "session_id": session_id,
            "character_name": character_name,
            "url": f"http://localhost:{port}/?session={session_id}&character={character_name}"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/system-check")
async def api_system_check():
    """Run system checks and return status."""
    from world_narrative.launcher import system_check
    ok, msg = system_check()
    return {"ok": ok, "message": msg}
