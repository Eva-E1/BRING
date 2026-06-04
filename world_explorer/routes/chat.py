"""
Chat route — the missing piece that connects the web UI to the RoleplayEngine.
Messages go here, searches go to /entities/search.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# ──────────────────────────────────────────────────────────────────
# Request / Response models
# ──────────────────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    """A single chat message from the user."""
    content: str = Field(..., min_length=1, description="The user's message text")
    character: Optional[str] = Field(None, description="Active character name")
    location: Optional[str] = Field(None, description="Current location")
    session_id: Optional[str] = Field(None, description="Session identifier for history")
    story_time: Optional[str] = Field(None, description="ISO-8601 story time override")


class ChatResponse(BaseModel):
    """Response from the roleplay engine."""
    narrative: str
    location: str = ""
    story_time: str = ""
    active_character: Optional[str] = None
    entities_mentioned: List[str] = []
    success: bool = True
    error: Optional[str] = None


class SessionSetup(BaseModel):
    """Setup a new or resume an existing roleplay session."""
    character: Optional[str] = None
    location: str = "unknown"
    story_time: Optional[str] = None
    role: str = "protagonist"
    session_id: Optional[str] = None


class SessionInfo(BaseModel):
    """Information about the current session."""
    active_character: Optional[str]
    current_location: str
    current_time: str
    session_id: Optional[str]


# ──────────────────────────────────────────────────────────────────
# Engine singleton (lazy-initialised on first use)
# ──────────────────────────────────────────────────────────────────

_engine: Optional[Any] = None       # RoleplayEngine
_ws_connections: List[WebSocket] = []


def get_engine():
    """Return the lazily-initialised RoleplayEngine."""
    global _engine
    if _engine is not None:
        return _engine
    raise HTTPException(
        status_code=503,
        detail="RoleplayEngine not initialised. Call POST /chat/setup first or check server logs.",
    )


def set_engine(engine: Any):
    """Called by api.py after construction."""
    global _engine
    _engine = engine


# ──────────────────────────────────────────────────────────────────
# REST endpoints
# ──────────────────────────────────────────────────────────────────


@router.post("/setup", response_model=SessionInfo)
async def setup_session(body: SessionSetup):
    """
    Initialise or update the active roleplay session.
    This MUST be called before sending messages.
    """
    engine = get_engine()

    story_time = (
        datetime.fromisoformat(body.story_time) if body.story_time
        else datetime.now()
    )
    session_id = body.session_id or f"session_{int(datetime.now().timestamp())}"

    engine.set_session(
        character=body.character,
        location=body.location,
        story_time=story_time,
        role=body.role,
        session_id=session_id,
    )

    return SessionInfo(
        active_character=engine.active_character,
        current_location=engine.current_location,
        current_time=engine.current_time.isoformat(),
        session_id=session_id,
    )


@router.post("/message", response_model=ChatResponse)
async def send_message(body: ChatMessage):
    """
    **The main message endpoint.**
    Sends a user message to the roleplay engine and returns narrative.
    This is NOT a search — it's a conversation action.
    """
    engine = get_engine()

    # Apply any session-state overrides from the client
    if body.character and body.character != engine.active_character:
        engine.active_character = body.character
    if body.location and body.location != engine.current_location:
        engine.current_location = body.location
    if body.story_time:
        try:
            engine.current_time = datetime.fromisoformat(body.story_time)
        except ValueError:
            pass

    try:
        narrative = await engine.process_input(body.content)
        return ChatResponse(
            narrative=narrative,
            location=engine.current_location,
            story_time=engine.current_time.isoformat(),
            active_character=engine.active_character,
            success=True,
        )
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        return ChatResponse(
            narrative="",
            location=engine.current_location,
            story_time=engine.current_time.isoformat(),
            active_character=engine.active_character,
            success=False,
            error=str(e),
        )


@router.get("/session", response_model=SessionInfo)
async def get_session_info():
    """Return current session state."""
    engine = get_engine()
    return SessionInfo(
        active_character=engine.active_character,
        current_location=engine.current_location,
        current_time=engine.current_time.isoformat(),
        session_id=engine.active_session_id,
    )


@router.get("/history")
async def get_history(limit: int = 20):
    """Return recent conversation history."""
    engine = get_engine()
    return engine.memory.get_recent(limit=limit)


# ──────────────────────────────────────────────────────────────────
# WebSocket endpoint for streaming / real-time chat
# ──────────────────────────────────────────────────────────────────


@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat.
    Messages arrive as JSON: {"type": "message", "content": "...", ...}
    """
    await websocket.accept()
    _ws_connections.append(websocket)

    engine = get_engine()

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "detail": "Invalid JSON. Send {\"type\": \"message\", \"content\": \"...\"}"
                })
                continue

            msg_type = data.get("type", "message")

            if msg_type == "message":
                content = data.get("content", "").strip()
                if not content:
                    await websocket.send_json({
                        "type": "error",
                        "detail": "Empty message",
                    })
                    continue

                # Apply optional overrides
                if data.get("character"):
                    engine.active_character = data["character"]
                if data.get("location"):
                    engine.current_location = data["location"]

                try:
                    narrative = await engine.process_input(content)
                    await websocket.send_json({
                        "type": "narrative",
                        "narrative": narrative,
                        "location": engine.current_location,
                        "story_time": engine.current_time.isoformat(),
                        "active_character": engine.active_character,
                    })
                except Exception as e:
                    logger.error(f"WS message error: {e}", exc_info=True)
                    await websocket.send_json({
                        "type": "error",
                        "detail": str(e),
                    })

            elif msg_type == "setup":
                story_time = (
                    datetime.fromisoformat(data["story_time"])
                    if data.get("story_time")
                    else datetime.now()
                )
                engine.set_session(
                    character=data.get("character"),
                    location=data.get("location", "unknown"),
                    story_time=story_time,
                    role=data.get("role", "protagonist"),
                    session_id=data.get("session_id"),
                )
                await websocket.send_json({
                    "type": "session",
                    "active_character": engine.active_character,
                    "current_location": engine.current_location,
                    "current_time": engine.current_time.isoformat(),
                })

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    finally:
        if websocket in _ws_connections:
            _ws_connections.remove(websocket)
