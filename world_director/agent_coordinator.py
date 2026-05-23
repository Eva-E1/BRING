"""Agent coordinator for prioritized task execution."""
from __future__ import annotations
import asyncio
import heapq
import logging
from typing import Dict, List, Callable, Awaitable, Any
from datetime import datetime
from uuid import uuid4

from .models import DirectorTask, TaskPriority

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """
    Schedules and executes tasks using a priority queue.
    Allows multiple worker coroutines, respects priorities, and can throttle concurrency.
    """

    def __init__(self, max_concurrent_tasks: int = 5):
        self.max_concurrent = max_concurrent_tasks
        self._task_queue: List[tuple] = []  # (priority_order, task)
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._handlers: Dict[str, Callable[[DirectorTask], Awaitable[Any]]] = {}

    def register_handler(self, task_type: str, handler: Callable[[DirectorTask], Awaitable[Any]]):
        self._handlers[task_type] = handler

    async def submit(self, task: DirectorTask):
        """Add a task to the queue."""
        heapq.heappush(self._task_queue, (task.priority.value, task.created_at.timestamp(), task))
        logger.debug(f"Submitted task {task.id} ({task.type}) with priority {task.priority.name}")

    async def _worker(self, worker_id: int):
        while self._running:
            if not self._task_queue:
                await asyncio.sleep(0.5)
                continue
            _, _, task = heapq.heappop(self._task_queue)
            handler = self._handlers.get(task.type)
            if not handler:
                logger.error(f"No handler for task type {task.type}")
                continue
            try:
                await handler(task)
                logger.info(f"Worker {worker_id} completed task {task.id}")
            except Exception as e:
                logger.error(f"Worker {worker_id} failed task {task.id}: {e}")

    async def start(self):
        self._running = True
        for i in range(self.max_concurrent):
            self._workers.append(asyncio.create_task(self._worker(i)))
        logger.info(f"Agent coordinator started with {self.max_concurrent} workers")

    async def stop(self):
        self._running = False
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("Agent coordinator stopped")

    async def submit_and_wait(self, task: DirectorTask, timeout: float = 30.0) -> Any:
        """Submit a task and wait for its result (if handler returns something)."""
        future = asyncio.Future()
        original_handler = self._handlers.get(task.type)

        async def wrapped_handler(t: DirectorTask):
            try:
                result = await original_handler(t) if original_handler else None
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)

        self._handlers[task.type] = wrapped_handler
        await self.submit(task)
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            # Restore original handler if any
            if original_handler:
                self._handlers[task.type] = original_handler
            else:
                del self._handlers[task.type]
