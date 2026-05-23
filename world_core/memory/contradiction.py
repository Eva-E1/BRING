"""Contradiction detection and belief propagation for cognitive memory system."""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4

from world_builder.llm import LLMClient
from .world_memory import WorldMemory, WorldMemoryEntry, MemoryMetadata

logger = logging.getLogger(__name__)

class ContradictionDetector:
    """Detects contradictions between new and existing memories."""

    def __init__(
        self,
        memory: WorldMemory,
        llm: LLMClient,
        similarity_threshold: float = 0.85
    ):
        self.memory = memory
        self.llm = llm
        self.sim_threshold = similarity_threshold
        self._contradiction_log: List[Dict] = []

    async def check_and_handle(
        self,
        new_entry: WorldMemoryEntry
    ) -> List[WorldMemoryEntry]:
        """
        Find contradictions with existing memories and handle them.

        Returns list of updated entries that need to be saved.
        """
        # Skip contradiction check for certain memory types
        if new_entry.source_type in ("entity", "summary", "pain"):
            return []

        # Find similar entries to check for contradictions
        similar = await self.memory.retrieve(
            query=new_entry.content,
            top_k=20,
            min_importance=0.0,
            source_type_filter={"episodic", "semantic", "event", "entity_change"}
        )

        if not similar:
            return []

        # Build candidate list
        candidates = []
        for s in similar:
            # Skip if same ID
            if s.get("id") == new_entry.id:
                continue
            cand_entry = self.memory.active_entries.get(s.get("id"))
            if cand_entry and cand_entry.id != new_entry.id:
                candidates.append(cand_entry)

        if not candidates:
            return []

        # Use LLM to judge contradictions
        updates = await self._judge_contradictions(new_entry, candidates[:10])

        # Log contradictions
        for update in updates:
            self._contradiction_log.append({
                "timestamp": datetime.now().isoformat(),
                "new_entry_id": new_entry.id,
                "contradicted_entry_id": update.id,
                "type": "supersedes"
            })

        return updates

    async def _judge_contradictions(
        self,
        new_entry: WorldMemoryEntry,
        candidates: List[WorldMemoryEntry]
    ) -> List[WorldMemoryEntry]:
        """Use LLM to judge if new entry contradicts any candidates."""
        prompt = f"""You are a memory contradiction detector. Compare the new memory with each existing memory.
For each pair, decide if the new memory invalidates/contradicts the old one (Supersedes),
or if the old one contradicts the new (ContradictedBy), or if they are Compatible.
Output a JSON array of objects with keys: "existing_id", "verdict" (one of "supersedes", "contradicted_by", "compatible"), "reason".

New memory (id: {new_entry.id}): {new_entry.content}

Existing memories:
{chr(10).join(f"- id: {e.id} content: {e.content[:200]}" for e in candidates)}

JSON:"""

        try:
            result = await self.llm.generate_json(prompt, temperature=0.2)
            if not isinstance(result, list):
                return []

            updates = []
            for item in result:
                verdict = item.get("verdict", "compatible")
                existing_id = item.get("existing_id")

                if not existing_id:
                    continue

                existing = self.memory.active_entries.get(existing_id)
                if not existing:
                    continue

                if verdict == "supersedes":
                    # New memory supersedes old one
                    existing.metadata.immutable = False  # Allow invalidation
                    if new_entry.id not in existing.superseded_by:
                        existing.superseded_by.append(new_entry.id)
                    if existing.id not in new_entry.supersedes:
                        new_entry.supersedes.append(existing.id)
                    updates.append(existing)

                elif verdict == "contradicted_by":
                    # Old memory contradicts new - mark new as superseded
                    if existing.id not in new_entry.superseded_by:
                        new_entry.superseded_by.append(existing.id)

            return updates

        except Exception as e:
            logger.warning(f"Contradiction check failed: {e}")
            return []

    async def find_belief_conflicts(
        self,
        entity_uid: str
    ) -> List[Dict[str, Any]]:
        """Find all conflicting beliefs about a specific entity."""
        memories = await self.memory.retrieve(
            query=entity_uid,
            top_k=50,
            entity_filter={entity_uid},
        )

        conflicts = []
        checked_pairs = set()

        for i, mem1 in enumerate(memories):
            for mem2 in memories[i + 1:]:
                pair_key = tuple(sorted([mem1.get("id"), mem2.get("id")]))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)

                # Check if these are contradictory
                entry1 = self.memory.active_entries.get(mem1.get("id"))
                entry2 = self.memory.active_entries.get(mem2.get("id"))

                if entry1 and entry2:
                    # Check supersedes relationship
                    if (entry2.id in entry1.supersedes or
                        entry1.id in entry2.supersedes):
                        conflicts.append({
                            "entry1_id": entry1.id,
                            "entry1_content": entry1.content,
                            "entry2_id": entry2.id,
                            "entry2_content": entry2.content,
                            "relationship": "supersedes"
                        })

        return conflicts

    def get_contradiction_log(self) -> List[Dict]:
        """Get the log of detected contradictions."""
        return self._contradiction_log

    async def resolve_conflict(
        self,
        winner_id: str,
        loser_id: str
    ):
        """Manually resolve a conflict by marking one entry as superseded."""
        winner = self.memory.active_entries.get(winner_id)
        loser = self.memory.active_entries.get(loser_id)

        if not winner or not loser:
            logger.warning(f"Cannot resolve conflict - entry not found")
            return

        # Mark loser as superseded by winner
        loser.metadata.immutable = False
        if winner.id not in loser.superseded_by:
            loser.superseded_by.append(winner.id)
        if loser.id not in winner.supersedes:
            winner.supersedes.append(loser.id)

        # Save updated entries
        await self.memory.partition_mgr.save_entry(loser.to_dict())
        await self.memory.partition_mgr.save_entry(winner.to_dict())

        logger.info(f"Resolved conflict: {winner_id} supersedes {loser_id}")

    async def propagate_belief_change(
        self,
        entry_id: str
    ):
        """
        Propagate belief changes when an entry is invalidated.
        All entries that reference the invalidated entry should be reviewed.
        """
        entry = self.memory.active_entries.get(entry_id)
        if not entry:
            return

        # Find all entries that supersede this one
        superseding = [
            e for e in self.memory.active_entries.values()
            if entry_id in e.supersedes
        ]

        # For each superseding entry, find entries that reference it
        for superseding_entry in superseding:
            # Look for related memories that might also be affected
            related = await self.memory.retrieve(
                query=superseding_entry.content,
                top_k=10,
                source_type_filter={"episodic", "semantic"}
            )

            for rel in related:
                rel_entry = self.memory.active_entries.get(rel.get("id"))
                if rel_entry and rel_entry.id != superseding_entry.id:
                    # Check if this entry references the original invalidated one
                    if entry_id in rel_entry.superseded_by:
                        # This might need review - log for human attention
                        logger.info(
                            f"Potential cascade: {superseding_entry.id} -> {rel_entry.id} "
                            f"(original: {entry_id})"
                        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get contradiction detection statistics."""
        total_contradictions = len(self._contradiction_log)

        supersedes_count = sum(
            1 for log in self._contradiction_log
            if log.get("type") == "supersedes"
        )

        return {
            "total_contradictions": total_contradictions,
            "supersedes_count": supersedes_count,
            "log_size": len(self._contradiction_log)
        }

    def clear_log(self):
        """Clear the contradiction log."""
        self._contradiction_log.clear()
