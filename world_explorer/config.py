"""Global configuration with sensible defaults."""
import os
from pathlib import Path

# Path to the world_db directory (where entities.json lives)
DEFAULT_DB_PATH = Path(os.getenv("WORLD_DB_PATH", "./world_db"))

# ── Embedding API settings ──────────────────────────────
# Set these via environment or edit directly.
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "http://localhost:8043/v1")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
# Model name: either "text-embedding-3-small" (OpenAI) or "bge-m3" (local/open-source)
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "bge-m3")

# Layers to embed by default (L3 excluded to avoid secrets in search)
DEFAULT_EMBED_LAYERS = ["l1", "l2"]

# Embedding batch size for API calls (max 2048 for text-embedding-3-small)
EMBEDDING_BATCH_SIZE = 64

# Self‑healing settings
AUTO_HEAL = True          # automatically repair broken links on startup
DEAD_REF_TYPE = "BROKEN"  # edge type for unresolvable references

def embedding_is_configured() -> bool:
    """Return True if at least a base URL is set (API key may be empty for local servers)."""
    return bool(EMBEDDING_BASE_URL)
