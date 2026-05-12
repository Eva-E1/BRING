"""Remote embeddings using OpenAI‑compatible API (optional)."""
import pickle
import time
import logging
from pathlib import Path
import numpy as np
from typing import List, Dict, Optional, Callable
from openai import OpenAI
from .models import Entity
from .config import (
    EMBEDDING_BASE_URL,
    EMBEDDING_API_KEY,
    EMBEDDING_MODEL_NAME,
    DEFAULT_EMBED_LAYERS,
    EMBEDDING_BATCH_SIZE,
)

logger = logging.getLogger(__name__)

class EmbeddingManager:
    def __init__(self, base_url: str = EMBEDDING_BASE_URL,
                 api_key: str = EMBEDDING_API_KEY,
                 model: str = EMBEDDING_MODEL_NAME):
        self.model = model
        self.client = None
        if not base_url:
            logger.warning("Embedding API not configured (missing base_url). Semantic search disabled.")
        else:
            try:
                # Empty API key is allowed for local servers without authentication
                self.client = OpenAI(base_url=base_url, api_key=api_key or "none")
                logger.info(f"Embedding client enabled: {base_url} (model: {model})")
            except Exception as e:
                logger.warning(f"Failed to create embedding client: {e}. Semantic search disabled.")
        self.uid_to_embedding: Dict[str, np.ndarray] = {}
        self.uid_to_text: Dict[str, str] = {}
        self._entities: List[Entity] = []

    def build_embeddings(self, entities: List[Entity],
                         layers: List[str] = None,
                         cache_file: Optional[Path] = None,
                         progress_callback: Optional[Callable[[int], None]] = None):
        if layers is None:
            layers = DEFAULT_EMBED_LAYERS

        if self.client is None:
            logger.warning("Skipping embedding computation – no valid API client.")
            return

        # Load from cache if available
        if cache_file and cache_file.exists():
            try:
                with open(cache_file, "rb") as f:
                    data = pickle.load(f)
                self.uid_to_embedding = data["uid_to_embedding"]
                self.uid_to_text = data["uid_to_text"]
                self._entities = entities
                return
            except Exception:
                pass

        texts = []
        uids = []
        for ent in entities:
            parts = []
            for level in layers:
                data = ent.profile.get_layer(level)
                if level == "l1":
                    parts.append(f"Name: {data.get('name','')}. Type: {data.get('type','')}. Summary: {data.get('summary','')}")
                else:
                    strings = (str(v) for v in data.values() if isinstance(v, str))
                    parts.append(" ".join(strings))
            text = " ".join(parts).strip()
            if not text:
                text = ent.name
            texts.append(text)
            uids.append(ent.uid)

        all_embeddings = []
        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch_texts = texts[i:i+EMBEDDING_BATCH_SIZE]
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.client.embeddings.create(
                        model=self.model,
                        input=batch_texts
                    )
                    batch_emb = [item.embedding for item in response.data]
                    all_embeddings.extend(batch_emb)
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise RuntimeError(f"Embedding API failed: {e}")
                    time.sleep(2 ** attempt)

            if progress_callback:
                progress_callback(len(batch_texts))

        embeddings_array = np.array(all_embeddings)
        for uid, emb, txt in zip(uids, embeddings_array, texts):
            self.uid_to_embedding[uid] = emb
            self.uid_to_text[uid] = txt

        self._entities = entities
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "wb") as f:
                pickle.dump({
                    "uid_to_embedding": self.uid_to_embedding,
                    "uid_to_text": self.uid_to_text
                }, f)

    def search(self, query: str, top_k: int = 10) -> List[tuple]:
        if self.client is None or not self.uid_to_embedding:
            return []

        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = self.client.embeddings.create(model=self.model, input=[query])
                query_emb = np.array(resp.data[0].embedding)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Embedding query failed: {e}")
                time.sleep(2 ** attempt)

        norm_q = np.linalg.norm(query_emb)
        if norm_q == 0:
            return []

        scores = {}
        for uid, emb in self.uid_to_embedding.items():
            sim = np.dot(query_emb, emb) / (norm_q * np.linalg.norm(emb))
            scores[uid] = float(sim)

        sorted_uids = sorted(scores, key=scores.get, reverse=True)[:top_k]
        return [(uid, scores[uid]) for uid in sorted_uids]
