"""Write-behind buffer for asynchronous batch persistence."""
import asyncio
from typing import List, Callable, Awaitable, Any, Optional
import logging

logger = logging.getLogger(__name__)

class WriteBehindBuffer:
    """Batches writes to disk asynchronously for improved performance."""

    def __init__(
        self,
        flush_interval: float = 5.0,
        max_size: int = 100
    ):
        self.flush_interval = flush_interval
        self.max_size = max_size
        self._buffer: List[Any] = []
        self._lock = asyncio.Lock()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._flush_callback: Optional[Callable[[List[Any]], Awaitable[None]]] = None
        self._stats = {
            "flush_count": 0,
            "total_items_flushed": 0,
            "last_flush_time": None,
        }

    async def start(
        self,
        flush_callback: Callable[[List[Any]], Awaitable[None]]
    ):
        """Start the background worker with the given flush callback."""
        self._flush_callback = flush_callback
        self._running = True
        self._task = asyncio.create_task(self._worker())
        logger.info("WriteBehindBuffer started")

    async def stop(self):
        """Stop the background worker and flush remaining items."""
        self._running = False
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.flush_now()
        logger.info("WriteBehindBuffer stopped")

    async def append(self, data: Any):
        """Add an item to the buffer."""
        async with self._lock:
            self._buffer.append(data)
            if len(self._buffer) >= self.max_size:
                await self._flush()

    async def flush_now(self):
        """Force a flush of all buffered items."""
        async with self._lock:
            if self._buffer:
                await self._flush()

    async def _worker(self):
        """Background worker that periodically flushes the buffer."""
        while self._running:
            await asyncio.sleep(self.flush_interval)
            async with self._lock:
                if self._buffer:
                    await self._flush()

    async def _flush(self):
        """Process all buffered items through the callback with retry logic."""
        if not self._buffer or not self._flush_callback:
            return

        batch = self._buffer[:]
        self._buffer.clear()

        attempt = 0
        while attempt < 3:
            try:
                await self._flush_callback(batch)
                self._stats["flush_count"] += 1
                self._stats["total_items_flushed"] += len(batch)
                self._stats["last_flush_time"] = asyncio.get_event_loop().time()
                logger.debug(f"Flushed {len(batch)} items to storage")
                return
            except Exception as e:
                attempt += 1
                logger.error(f"Flush attempt {attempt} failed: {e}")
                if attempt < 3:
                    await asyncio.sleep(2 ** attempt)  # exponential backoff
        logger.error(f"Dropping {len(batch)} items after 3 flush failures")

    def get_buffer_size(self) -> int:
        return len(self._buffer)

    def get_stats(self) -> dict:
        """Return buffer statistics."""
        return {
            **self._stats,
            "current_buffer_size": len(self._buffer),
        }
