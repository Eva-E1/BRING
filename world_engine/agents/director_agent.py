from __future__ import annotations
from world_core.llm_queue import GlobalLLMQueue
from world_director.models import TaskPriority
from typing import Optional


class DirectorAgent:
    """Integrates the director's story plan into the narrative."""

    def __init__(self, llm_queue: GlobalLLMQueue):
        self.llm_queue = llm_queue

    async def inject_beat(self, beat_description: str, current_narrative: str) -> str:
        """Insert a story beat into the existing narrative."""
        prompt = f"""You are integrating a story beat into the current narrative.
Current narrative: {current_narrative}

Story beat to inject: {beat_description}

Modify the narrative to naturally include this beat. Do not change the user's actions or dialogue.
Keep the same tone and style. Output only the modified narrative.
"""
        return await self.llm_queue.generate_text(
            prompt, priority=TaskPriority.HIGH, temperature=0.7
        )
