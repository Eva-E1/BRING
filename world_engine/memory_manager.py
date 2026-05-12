from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import deque
from datetime import datetime


class MemoryManager:
    def __init__(self, storage_path: Path, max_history: int = 20):
        self.storage_path = storage_path
        self.max_history = max_history
        self.conversation_history: deque = deque(maxlen=max_history)
        self._load()

    def _load(self):
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                self.conversation_history = deque(data.get("history", []), maxlen=self.max_history)
            except Exception:
                pass

    def _save(self):
        data = {"history": list(self.conversation_history)}
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.storage_path.parent, delete=False) as tf:
            json.dump(data, tf, indent=2)
            os.replace(tf.name, self.storage_path)

    def add_entry(self, user_input: str, assistant_output: str, metadata: Optional[Dict] = None):
        self.conversation_history.append({
            "user": user_input,
            "assistant": assistant_output,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat(),
        })
        self._save()

    def get_recent(self, limit: int = 10) -> List[Dict]:
        return list(self.conversation_history)[-limit:]

    def clear(self):
        self.conversation_history.clear()
        self._save()
