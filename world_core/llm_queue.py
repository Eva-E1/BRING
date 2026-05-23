"""Global LLM Queue for prioritized request handling."""
from __future__ import annotations
import asyncio
from datetime import datetime
from uuid import uuid4
from typing import Any, Optional

from world_director.agent_coordinator import AgentCoordinator
from world_director.models import DirectorTask, TaskPriority
from world_builder.llm import LLMClient


class GlobalLLMQueue:
    """
    Wraps LLMClient with a priority queue to prevent API overloading.
    User requests get HIGH priority, background tasks get LOW.
    """

    def __init__(self, llm_client: LLMClient, max_concurrent: int = 3):
        self.llm = llm_client
        self.coordinator = AgentCoordinator(max_concurrent_tasks=max_concurrent)
        self.coordinator.register_handler("llm_text", self._handle_text)
        self.coordinator.register_handler("llm_json", self._handle_json)

    async def start(self):
        """Start the queue coordinator."""
        await self.coordinator.start()

    async def stop(self):
        """Stop the queue coordinator."""
        await self.coordinator.stop()

    async def generate_text(
        self,
        prompt: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        temperature: float = 0.7,
    ) -> str:
        """Generate text with priority. User-facing calls should use HIGH priority."""
        task = DirectorTask(
            id=str(uuid4()),
            type="llm_text",
            priority=priority,
            data={"prompt": prompt, "temperature": temperature},
            created_at=datetime.now(),
        )
        return await self.coordinator.submit_and_wait(task)

    async def generate_json(
        self,
        prompt: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        temperature: float = 0.7,
    ) -> dict:
        """Generate JSON with priority."""
        task = DirectorTask(
            id=str(uuid4()),
            type="llm_json",
            priority=priority,
            data={"prompt": prompt, "temperature": temperature},
            created_at=datetime.now(),
        )
        return await self.coordinator.submit_and_wait(task)

    async def _handle_text(self, task: DirectorTask) -> str:
        """Handler for text generation tasks."""
        return await self.llm.generate_text(task.data["prompt"], task.data["temperature"])

    async def _handle_json(self, task: DirectorTask) -> dict:
        """Handler for JSON generation tasks."""
        return await self.llm.generate_json(task.data["prompt"], task.data["temperature"])
