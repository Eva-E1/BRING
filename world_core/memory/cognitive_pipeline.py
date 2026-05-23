"""Cognitive pipeline for processing conversation turns with memory integration."""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4

from .world_memory import WorldMemory, WorldMemoryEntry, MemoryMetadata
from .entity_extractor import EntityExtractor
from .contradiction import ContradictionDetector
from .pain_signals import PainSignalManager

logger = logging.getLogger(__name__)

class CognitivePipeline:
    """
    Cognitive pipeline that processes conversation turns and integrates
    memory features: entity extraction, contradiction detection, pain signals,
    and context assembly.
    """

    def __init__(
        self,
        memory: WorldMemory,
        llm: Any,
        entity_extractor: EntityExtractor,
        pain_mgr: PainSignalManager,
        detector: ContradictionDetector,
    ):
        self.memory = memory
        self.llm = llm
        self.entity_extractor = entity_extractor
        self.pain_mgr = pain_mgr
        self.detector = detector
        self._stats = {
            "turns_processed": 0,
            "facts_extracted": 0,
            "entities_extracted": 0,
            "contradictions_found": 0,
            "warnings_raised": 0,
        }

    async def process_turn(
        self,
        user_message: str,
        assistant_response: str,
        turn_id: int,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Process a conversation turn through the cognitive pipeline.

        This method:
        1. Extracts important facts from the conversation
        2. Stores episodic memories
        3. Extracts and resolves entities
        4. Checks for contradictions
        5. Retrieves relevant context for the next turn
        6. Checks for pain warnings

        Args:
            user_message: The user's message
            assistant_response: The assistant's response
            turn_id: Unique identifier for this turn
            session_id: Optional session ID for delta tracking

        Returns:
            Dictionary containing extracted facts, memories, context, and warnings
        """
        logger.debug(f"Processing turn {turn_id}")
        self._stats["turns_processed"] += 1

        # Combine messages for analysis
        combined = f"User: {user_message}\nAssistant: {assistant_response}"

        # Step 1: Extract important facts from conversation
        facts = await self._extract_facts(combined)
        self._stats["facts_extracted"] += len(facts)

        # Step 2: Store each fact as an episodic memory
        episodic_ids = []
        for fact in facts:
            entry = WorldMemoryEntry(
                id=str(uuid4()),
                content=fact,
                timestamp=datetime.now(),
                source_type="turn",
                source_id=f"turn_{turn_id}",
                memory_type="episodic",
                importance=0.6,
                metadata=MemoryMetadata(
                    access_count=0,
                    last_accessed=datetime.now(),
                    emotional_valence=0.0,
                    story_relevance=0.5,
                    importance=0.6,
                ),
            )
            await self.memory.add_memory(entry)
            episodic_ids.append(entry.id)

        # Step 3: Extract entities from the conversation
        entity_entries = await self.entity_extractor.extract_from_text(
            combined,
            source_id=f"turn_{turn_id}"
        )
        self._stats["entities_extracted"] += len(entity_entries)

        for ent in entity_entries:
            await self.memory.add_memory(ent)

        # Step 4: Check for contradictions with existing memories
        contradicted_entries = []
        for eid in episodic_ids:
            entry = self.memory.active_entries.get(eid)
            if entry:
                updates = await self.detector.check_and_handle(entry)
                if updates:
                    contradicted_entries.extend(updates)
                    self._stats["contradictions_found"] += len(updates)

        # Step 5: Retrieve relevant context for next turn
        last_seen = None
        if session_id:
            last_seen = self.memory.get_last_seen(session_id)

        context = await self.memory.retrieve(
            query=user_message,
            top_k=15,
            session_id=session_id,
            last_seen=last_seen,
        )

        # Step 6: Check for pain warnings
        warnings = await self.pain_mgr.get_warnings(user_message)
        self._stats["warnings_raised"] += len(warnings)

        # Step 7: Update access counts for retrieved memories
        for result in context[:5]:
            await self.memory.update_access(result.get("id", ""))

        return {
            "extracted_facts": facts,
            "entity_memories": [e.id for e in entity_entries],
            "episodic_memory_ids": episodic_ids,
            "contradicted_entries": [e.id for e in contradicted_entries],
            "context": context,
            "pain_warnings": warnings,
            "turn_id": turn_id,
        }

    async def _extract_facts(self, text: str) -> List[str]:
        """Extract important facts from text using LLM."""
        fact_prompt = f"""
Extract important facts from this conversation turn. Return a JSON array of strings, each a concise fact.
Focus on: user preferences, decisions, corrections, knowledge updates, entity attributes, and significant events.

Conversation:
{text}

Facts (JSON array):"""

        try:
            result = await self.llm.generate_json(fact_prompt, temperature=0.3)
            if isinstance(result, list):
                return [f for f in result if isinstance(f, str)]
        except Exception as e:
            logger.warning(f"Fact extraction failed: {e}")

        return []

    async def process_action_result(
        self,
        action: str,
        result: str,
        success: bool,
        source_id: str,
    ) -> Dict[str, Any]:
        """
        Process an action result, potentially recording pain signals.

        This is called after an NPC or system action is executed to track
        successes and failures.
        """
        if not success:
            # Extract potential pain keywords from the failed action
            keywords = self._extract_keywords(action)
            pain_id = await self.pain_mgr.record_pain(
                description=f"Failed action: {action}. Result: {result}",
                keywords=keywords,
                source_id=source_id,
                importance=0.7,
            )
            return {
                "pain_recorded": True,
                "pain_id": pain_id,
                "keywords": keywords,
            }

        return {
            "pain_recorded": False,
        }

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract key terms from text for pain signal matching."""
        import re
        # Extract capitalized words and significant terms
        words = re.findall(r'\b[A-Z][a-z]+\b', text)
        # Also include significant lowercase words
        lowercase = re.findall(r'\b(failed|error|crash|wrong|incorrect|broken)\b', text.lower())
        return words[:5] + lowercase

    async def get_context_for_response(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        include_warnings: bool = True,
    ) -> Dict[str, Any]:
        """
        Get context for generating a response without processing a full turn.

        This is used when just need to retrieve context without storing
        the conversation as memory.
        """
        # Get last seen timestamp for delta
        last_seen = None
        if session_id:
            last_seen = self.memory.get_last_seen(session_id)

        # Retrieve relevant context
        context = await self.memory.retrieve(
            query=user_message,
            top_k=10,
            session_id=session_id,
            last_seen=last_seen,
        )

        result = {
            "context": context,
            "session_id": session_id,
        }

        # Optionally include pain warnings
        if include_warnings:
            warnings = await self.pain_mgr.get_warnings(user_message)
            result["pain_warnings"] = warnings

        return result

    async def consolidate_entity_memory(
        self,
        entity_uid: str,
    ) -> Optional[WorldMemoryEntry]:
        """
        Consolidate all memories related to a specific entity.

        This finds all memories for an entity and merges them into a
        summary if there are enough related entries.
        """
        # Get all memories for this entity
        related = await self.memory.retrieve(
            query=entity_uid,
            top_k=50,
            entity_filter={entity_uid},
        )

        if len(related) < 5:
            return None

        # Get actual entries
        entries = []
        for r in related:
            entry = self.memory.active_entries.get(r.get("id"))
            if entry:
                entries.append(entry)

        if len(entries) < 5:
            return None

        # Use cluster engine to merge
        summary = await self.memory.cluster.merge_cluster(entries, self.llm)

        if summary:
            await self.memory.add_memory(summary)
            logger.info(f"Created consolidated memory for entity {entity_uid}")

        return summary

    def get_statistics(self) -> Dict[str, Any]:
        """Get pipeline processing statistics."""
        return {
            **self._stats,
            "detector_stats": self.detector.get_statistics(),
            "pain_stats": self.pain_mgr.get_statistics(),
        }

    async def clear_old_memories(
        self,
        days: int = 60,
    ) -> int:
        """Clear old episodic memories beyond retention period."""
        return await self.memory.forget_old_entries(days)

    async def trigger_optimization(self):
        """Manually trigger memory optimization."""
        await self.memory.optimizer.run_manual()
