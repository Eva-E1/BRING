from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)

# Maximum log file size before rotation (10 MB)
MAX_LOG_SIZE = 10 * 1024 * 1024


class Chronicler:
    def __init__(self, log_path: Path, max_log_size: int = MAX_LOG_SIZE):
        self.log_path = log_path
        self.max_log_size = max_log_size
        self._ensure_file()

    def _ensure_file(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.touch()

    def _check_and_rotate(self) -> None:
        """Rotate log file if it exceeds max size."""
        if not self.log_path.exists():
            return

        try:
            file_size = self.log_path.stat().st_size
            if file_size > self.max_log_size:
                # Create backup with timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = self.log_path.with_suffix(f".jsonl.old_{timestamp}")

                # Rename current log to backup
                self.log_path.rename(backup_path)
                logger.info(f"Rotated log file to {backup_path}")

                # Create new empty log file
                self._ensure_file()
        except OSError as e:
            logger.warning(f"Log rotation failed: {e}")

    async def log_event(self, description: str, story_time: datetime, group: str = "narrative") -> str:
        # Check and rotate before writing
        self._check_and_rotate()

        event_id = str(uuid4())
        entry = {
            "id": event_id,
            "timestamp": story_time.isoformat(),
            "group": group,
            "description": description,
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError as e:
            logger.error(f"Failed to write event to log: {e}")
            raise
        return event_id

    async def get_timeline(self, since: Optional[datetime] = None, limit: int = 50) -> List[dict]:
        entries = []
        if not self.log_path.exists():
            return entries

        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        ts = datetime.fromisoformat(entry["timestamp"])
                        if since is None or ts >= since:
                            entries.append(entry)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Skipping malformed log entry: {e}")
                        continue
        except OSError as e:
            logger.error(f"Failed to read timeline: {e}")
            return entries

        entries.sort(key=lambda e: e["timestamp"])
        return entries[-limit:]

    async def get_events_by_group(self, group: str, limit: int = 50) -> List[dict]:
        """Get events filtered by group."""
        all_events = await self.get_timeline(limit=limit * 2)  # Get more to filter
        return [e for e in all_events if e.get("group") == group][-limit:]
