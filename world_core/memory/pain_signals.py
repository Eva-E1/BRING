"""Pain signal tracking for recurring failures and warnings."""
import re
import logging
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from uuid import uuid4

from .world_memory import WorldMemory, WorldMemoryEntry, MemoryMetadata

logger = logging.getLogger(__name__)

class PainSignalManager:
    """Tracks recurring failures and provides warnings based on pain patterns."""

    def __init__(self, memory: WorldMemory):
        self.memory = memory
        self._pain_cache: Dict[str, List[str]] = {}  # keyword -> pain entry IDs

    async def record_pain(
        self,
        description: str,
        keywords: List[str],
        source_id: str,
        importance: float = 0.8
    ) -> str:
        """
        Record a pain signal memory.

        Args:
            description: Description of the pain/failure
            keywords: Keywords that trigger this pain signal
            source_id: Source identifier
            importance: Importance score (higher = more critical)

        Returns:
            ID of the created pain entry
        """
        entry = WorldMemoryEntry(
            id=str(uuid4()),
            content=description,
            timestamp=datetime.now(),
            source_type="pain",
            source_id=source_id,
            memory_type="procedural",
            pain_keywords=keywords,
            importance=importance,
            metadata=MemoryMetadata(
                immutable=False,
                importance=importance
            ),
            tags=["pain", "failure"]
        )

        await self.memory.add_memory(entry)

        # Update cache
        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower not in self._pain_cache:
                self._pain_cache[keyword_lower] = []
            self._pain_cache[keyword_lower].append(entry.id)

        logger.info(f"Recorded pain signal: {entry.id} ({keywords})")
        return entry.id

    async def get_warnings(
        self,
        context_text: str,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Find pain signals that match keywords in the given context.

        Args:
            context_text: Text to check for pain keyword matches
            top_k: Maximum number of warnings to return

        Returns:
            List of warning dictionaries with content and match score
        """
        # Extract keywords from context
        words = set(re.findall(r'\b\w+\b', context_text.lower()))

        if not words:
            return []

        # Search for pain memories with matching keywords
        results = []
        seen_ids = set()

        for eid, entry in self.memory.active_entries.items():
            if entry.source_type != "pain":
                continue

            # Calculate match score based on keyword overlap
            pain_keywords = set(k.lower() for k in entry.pain_keywords)
            if not pain_keywords:
                continue

            match_count = len(pain_keywords & words)
            if match_count == 0:
                continue

            match_score = match_count / max(1, len(pain_keywords))

            # Only include if we have a meaningful match
            if match_score > 0:
                # Avoid duplicates
                if eid not in seen_ids:
                    seen_ids.add(eid)
                    results.append({
                        "id": entry.id,
                        "content": entry.content,
                        "match_score": match_score,
                        "importance": entry.importance,
                        "keywords": entry.pain_keywords,
                        "timestamp": entry.timestamp.isoformat(),
                    })

        # Sort by match score and importance
        results.sort(
            key=lambda x: (x["match_score"], x["importance"]),
            reverse=True
        )

        return results[:top_k]

    async def check_context_for_warnings(
        self,
        user_input: str,
        assistant_response: str,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Check both user input and assistant response for pain warnings.

        Args:
            user_input: User's message
            assistant_response: Assistant's response
            top_k: Maximum warnings to return

        Returns:
            Combined list of warnings
        """
        combined_text = f"{user_input} {assistant_response}"
        return await self.get_warnings(combined_text, top_k)

    async def get_pain_summary(
        self,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get a summary of pain signals in the given time window.

        Args:
            hours: Number of hours to look back

        Returns:
            Summary dictionary with pain statistics
        """
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_pains = [
            e for e in self.memory.active_entries.values()
            if e.source_type == "pain" and e.timestamp >= cutoff
        ]

        if not recent_pains:
            return {
                "count": 0,
                "recent_pains": [],
                "top_keywords": [],
            }

        # Aggregate keywords
        keyword_counts: Dict[str, int] = {}
        for entry in recent_pains:
            for kw in entry.pain_keywords:
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

        # Sort keywords by frequency
        top_keywords = sorted(
            keyword_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        return {
            "count": len(recent_pains),
            "recent_pains": [
                {
                    "id": e.id,
                    "content": e.content[:100],
                    "keywords": e.pain_keywords,
                    "importance": e.importance,
                    "timestamp": e.timestamp.isoformat(),
                }
                for e in sorted(
                    recent_pains,
                    key=lambda x: x.importance,
                    reverse=True
                )[:5]
            ],
            "top_keywords": [{"keyword": k, "count": c} for k, c in top_keywords],
        }

    async def clear_old_pain_signals(
        self,
        days: int = 30
    ) -> int:
        """
        Remove old pain signals that are no longer relevant.

        Args:
            days: Age threshold in days

        Returns:
            Number of pain signals cleared
        """
        cutoff = datetime.now() - timedelta(days=days)
        to_remove = []

        for eid, entry in self.memory.active_entries.items():
            if entry.source_type == "pain":
                if entry.timestamp < cutoff and not entry.metadata.get("immutable", False):
                    to_remove.append(eid)

        for eid in to_remove:
            await self.memory._delete_entry(eid)

        # Clear cache entries
        for keyword in self._pain_cache:
            self._pain_cache[keyword] = [
                pid for pid in self._pain_cache[keyword]
                if pid not in to_remove
            ]

        if to_remove:
            logger.info(f"Cleared {len(to_remove)} old pain signals")

        return len(to_remove)

    def get_statistics(self) -> Dict[str, Any]:
        """Get pain signal statistics."""
        pain_entries = [
            e for e in self.memory.active_entries.values()
            if e.source_type == "pain"
        ]

        return {
            "total_pain_signals": len(pain_entries),
            "cached_keywords": len(self._pain_cache),
            "avg_importance": (
                sum(e.importance for e in pain_entries) / len(pain_entries)
                if pain_entries else 0
            ),
        }

    async def register_successful_recovery(
        self,
        pain_entry_id: str,
        recovery_description: str
    ):
        """
        Register a successful recovery from a pain signal.

        This creates a new memory linking back to the original pain,
        marking it as resolved.
        """
        pain_entry = self.memory.active_entries.get(pain_entry_id)
        if not pain_entry:
            logger.warning(f"Pain entry not found: {pain_entry_id}")
            return

        # Create resolution entry
        resolution_entry = WorldMemoryEntry(
            id=str(uuid4()),
            content=f"Resolved: {recovery_description}",
            timestamp=datetime.now(),
            source_type="pain_resolution",
            source_id=pain_entry.source_id,
            memory_type="procedural",
            importance=0.7,
            linked_entity_uids=[pain_entry_id],
            tags=["recovery", "resolved"],
            metadata=MemoryMetadata(immutable=True)
        )

        await self.memory.add_memory(resolution_entry)
        logger.info(f"Registered recovery for pain: {pain_entry_id}")

# Helper for timedelta
from datetime import timedelta
