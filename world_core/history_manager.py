"""Session history manager – persistent storage of conversation turns."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import uuid4


def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically using a temp file and rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create temp file in same directory for atomic rename
    fd, temp_path = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, path)
    except Exception:
        # Clean up temp file on failure
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


class ConversationTurn:
    """A single turn in the conversation."""
    def __init__(
        self,
        role: str,
        content: str,
        timestamp: datetime = None,
        metadata: Dict = None
    ):
        self.role = role  # "user", "assistant", or "system"
        self.content = content
        self.timestamp = timestamp or datetime.now()
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConversationTurn":
        return cls(
            role=d["role"],
            content=d["content"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            metadata=d.get("metadata", {}),
        )


class SessionHistory:
    """Manages the history for a single session."""
    def __init__(self, session_id: str, storage_dir: Path):
        self.session_id = session_id
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._path = storage_dir / f"{session_id}.json"
        self.turns: List[ConversationTurn] = []
        self._load()

    def _load(self):
        """Load session history from disk."""
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self.turns = [ConversationTurn.from_dict(t) for t in data.get("turns", [])]
            except Exception as e:
                print(f"Error loading session {self.session_id}: {e}")
                self.turns = []

    def save(self):
        """Save session history to disk atomically."""
        data = {
            "session_id": self.session_id,
            "updated_at": datetime.now().isoformat(),
            "turn_count": len(self.turns),
            "turns": [t.to_dict() for t in self.turns],
        }
        atomic_write_json(self._path, data)

    def add_turn(self, role: str, content: str, metadata: Dict = None) -> ConversationTurn:
        """Add a turn to the session history."""
        turn = ConversationTurn(role, content, metadata=metadata)
        self.turns.append(turn)
        self.save()
        return turn

    def get_turns(self, limit: int = None, offset: int = 0) -> List[Dict]:
        """Return turns as dicts, optionally paginated."""
        turns = self.turns[offset:]
        if limit:
            turns = turns[:limit]
        return [t.to_dict() for t in turns]

    def get_last_n(self, n: int) -> List[Dict]:
        """Return the last N turns."""
        return self.get_turns(limit=n)

    def get_all(self) -> List[Dict]:
        """Return all turns."""
        return self.get_turns()

    def get_conversation_pairs(self) -> List[Dict]:
        """Return turns as user-assistant pairs."""
        pairs = []
        for i in range(0, len(self.turns) - 1, 2):
            if self.turns[i].role == "user" and self.turns[i + 1].role == "assistant":
                pairs.append({
                    "user": self.turns[i].to_dict(),
                    "assistant": self.turns[i + 1].to_dict()
                })
        return pairs

    def clear(self):
        """Clear all turns."""
        self.turns = []
        self.save()

    def delete(self):
        """Delete the session file."""
        if self._path.exists():
            self._path.unlink()
        self.turns = []

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def last_updated(self) -> Optional[datetime]:
        if not self.turns:
            return None
        return self.turns[-1].timestamp

    @property
    def is_empty(self) -> bool:
        return len(self.turns) == 0


class HistoryManager:
    """Top-level manager for all session histories."""
    def __init__(self, db_path: Path):
        self.storage_dir = db_path / "session_history"
        self._sessions: Dict[str, SessionHistory] = {}

    def _get_session(self, session_id: str) -> SessionHistory:
        """Get or create a session history."""
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionHistory(session_id, self.storage_dir)
        return self._sessions[session_id]

    def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Dict = None
    ) -> ConversationTurn:
        """Add a turn to the session history."""
        sess = self._get_session(session_id)
        return sess.add_turn(role, content, metadata)

    def get_history(
        self,
        session_id: str,
        limit: int = None,
        offset: int = 0
    ) -> List[Dict]:
        """Get session history with optional pagination."""
        sess = self._get_session(session_id)
        return sess.get_turns(limit, offset)

    def get_last_n(self, session_id: str, n: int) -> List[Dict]:
        """Get the last N turns."""
        return self.get_history(session_id, limit=n)

    def get_conversation_pairs(self, session_id: str) -> List[Dict]:
        """Get conversation as user-assistant pairs."""
        sess = self._get_session(session_id)
        return sess.get_conversation_pairs()

    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        path = self.storage_dir / f"{session_id}.json"
        return path.exists()

    def delete_session(self, session_id: str) -> bool:
        """Delete a session history."""
        if session_id in self._sessions:
            self._sessions[session_id].delete()
            del self._sessions[session_id]
            return True
        path = self.storage_dir / f"{session_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Return metadata for all sessions."""
        sessions = []
        if not self.storage_dir.exists():
            return sessions

        for path in self.storage_dir.glob("*.json"):
            session_id = path.stem
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sessions.append({
                    "session_id": session_id,
                    "turn_count": len(data.get("turns", [])),
                    "last_updated": data.get("updated_at"),
                })
            except Exception:
                sessions.append({
                    "session_id": session_id,
                    "turn_count": 0,
                    "last_updated": None,
                })

        # Sort by last_updated descending
        sessions.sort(key=lambda x: x.get("last_updated") or "", reverse=True)
        return sessions

    def get_or_create_session(self, session_id: str) -> SessionHistory:
        """Get or create a session."""
        return self._get_session(session_id)

    def clear_cache(self):
        """Clear in-memory cache (forces reload on next access)."""
        self._sessions.clear()
