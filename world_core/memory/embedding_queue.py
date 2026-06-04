"""High-throughput batching of embedding requests."""
import asyncio
import hashlib
import logging
from typing import List, Optional, Tuple
from world_builder.llm import LLMClient

logger = logging.getLogger(__name__)


class EmbeddingQueue:
    """Batches embedding requests for efficient processing."""

    def __init__(
        self,
        llm: LLMClient,
        batch_size: int = 50,
        flush_interval: float = 5.0,
        embedding_dim: int = 384,
    ):
        self.llm = llm
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.embedding_dim = embedding_dim
        self._queue: List[Tuple[str, asyncio.Future]] = []
        self._lock = asyncio.Lock()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the background worker."""
        self._running = True
        self._task = asyncio.create_task(self._worker())

    async def stop(self):
        """Stop the background worker and flush remaining items."""
        self._running = False
        if self._task:
            await self._task
        await self._flush()

    async def embed(self, text: str) -> List[float]:
        """Queue an embedding request and return the embedding."""
        future = asyncio.Future()
        async with self._lock:
            self._queue.append((text, future))
            if len(self._queue) >= self.batch_size:
                await self._flush()
        return await future

    async def _worker(self):
        """Background worker that periodically flushes the queue with error handling."""
        backoff = self.flush_interval
        max_backoff = 300

        while self._running:
            try:
                await asyncio.sleep(self.flush_interval)
                async with self._lock:
                    if self._queue:
                        await self._flush()
                backoff = self.flush_interval  # Reset backoff on successful flush
            except Exception as e:
                logger.error(f"EmbeddingQueue worker error: {e}", exc_info=True)
                logger.info(f"Retrying in {backoff} seconds (exponential backoff)")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

    def _generate_fallback_embedding(self, text: str) -> List[float]:
        """Generate a deterministic hash-based embedding when API fails."""
        # Use SHA256 to generate a deterministic vector from text
        hash_bytes = hashlib.sha256(text.encode()).digest()

        # Convert hash bytes to float values in range [-1, 1]
        embedding = []
        for i in range(self.embedding_dim):
            byte_idx = i % len(hash_bytes)
            value = (hash_bytes[byte_idx] - 128) / 128.0
            embedding.append(value)

        return embedding

    async def _flush(self):
        """Process all queued embedding requests in a batch."""
        if not self._queue:
            return

        batch = self._queue[:self.batch_size]
        self._queue = self._queue[len(batch):]
        texts = [t for t, _ in batch]

        try:
            embeddings = await self.llm.embed_many(texts)
        except Exception as e:
            # Fallback: generate deterministic hash-based embeddings
            embeddings = [self._generate_fallback_embedding(t) for t in texts]

        for (_, future), emb in zip(batch, embeddings):
            if not future.done():
                future.set_result(emb)

    def get_queue_size(self) -> int:
        """Return current queue size."""
        return len(self._queue)
