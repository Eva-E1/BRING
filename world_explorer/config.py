"""Global configuration with sensible defaults for World Explorer.

This module provides unified configuration by importing from world_config.
All settings should be configured via environment variables or .env file.

Configuration:
    WORLD_LLM_BASE_URL    - Base URL for LLM API (e.g., http://localhost:20128/v1)
    WORLD_LLM_API_KEY     - API key for LLM
    WORLD_LLM_MODEL       - Model name (e.g., gpt-4o-mini)
    WORLD_EMBEDDING_BASE_URL - Base URL for embedding API
    WORLD_EMBEDDING_API_KEY  - API key for embeddings
    WORLD_EMBEDDING_MODEL    - Embedding model name
    WORLD_DB_PATH         - Path to world database
    WORLD_SERVER_HOST     - Server host
    WORLD_SERVER_PORT     - Server port
    WORLD_AUTO_HEAL       - Enable graph self-healing

Or create a .env file in the project root with:
    WORLD_LLM_BASE_URL=http://localhost:20128/v1
    WORLD_LLM_API_KEY=your-api-key
    WORLD_LLM_MODEL=gpt-4o-mini
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

# Try to import from unified config, fall back to environment variables
try:
    from world_config import (
        WORLD_LLM_BASE_URL,
        WORLD_LLM_API_KEY,
        WORLD_LLM_MODEL,
        WORLD_EMBEDDING_BASE_URL,
        WORLD_EMBEDDING_API_KEY,
        WORLD_EMBEDDING_MODEL,
        WORLD_DB_PATH,
        WORLD_LLM_TIMEOUT,
        WORLD_LLM_MAX_TOKENS,
        WORLD_LLM_MAX_RETRIES,
        WORLD_LLM_MAX_CONCURRENT,
        WORLD_SERVER_HOST,
        WORLD_SERVER_PORT,
        WORLD_SERVER_RELOAD,
        WORLD_AUTO_HEAL,
        is_llm_configured,
        get_llm_config,
        validate_config,
    )
    _USING_UNIFIED_CONFIG = True
except ImportError:
    _USING_UNIFIED_CONFIG = False

# ═══════════════════════════════════════════════════════════════════════════════
# Legacy/Environment-based Configuration (fallback)
# ═══════════════════════════════════════════════════════════════════════════════

if not _USING_UNIFIED_CONFIG:
    # Load .env file if it exists
    from dotenv import load_dotenv
    load_dotenv()

# Path to the world_db directory (where entities.json lives)
DEFAULT_DB_PATH: Path = (
    Path(os.getenv("WORLD_DB_PATH", "./world_db"))
    if not _USING_UNIFIED_CONFIG
    else WORLD_DB_PATH
)

# ── Embedding API settings ──────────────────────────────
# Set these via environment or edit directly.
EMBEDDING_BASE_URL: str = (
    os.getenv("EMBEDDING_BASE_URL", "http://localhost:8043/v1")
    if not _USING_UNIFIED_CONFIG
    else WORLD_EMBEDDING_BASE_URL
)
EMBEDDING_API_KEY: str = (
    os.getenv("EMBEDDING_API_KEY", "")
    if not _USING_UNIFIED_CONFIG
    else WORLD_EMBEDDING_API_KEY
)
# Model name: either "text-embedding-3-small" (OpenAI) or "bge-m3" (local/open-source)
EMBEDDING_MODEL_NAME: str = (
    os.getenv("EMBEDDING_MODEL_NAME", "bge-m3")
    if not _USING_UNIFIED_CONFIG
    else WORLD_EMBEDDING_MODEL
)

# Layers to embed by default (L3 excluded to avoid secrets in search)
DEFAULT_EMBED_LAYERS = ["l1", "l2"]

# Embedding batch size for API calls (max 2048 for text-embedding-3-small)
EMBEDDING_BATCH_SIZE = 64

# Self‑healing settings
AUTO_HEAL: bool = (
    os.getenv("WORLD_AUTO_HEAL", "true").lower() == "true"
    if not _USING_UNIFIED_CONFIG
    else WORLD_AUTO_HEAL
)
DEAD_REF_TYPE = "BROKEN"  # edge type for unresolvable references

# LLM settings (used by some modules directly)
LLM_BASE_URL: str = (
    os.getenv("WORLD_LLM_BASE_URL") or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    if not _USING_UNIFIED_CONFIG
    else WORLD_LLM_BASE_URL
)
LLM_API_KEY: str = (
    os.getenv("WORLD_LLM_API_KEY") or os.getenv("LLM_API_KEY", "")
    if not _USING_UNIFIED_CONFIG
    else WORLD_LLM_API_KEY
)
LLM_MODEL: str = (
    os.getenv("WORLD_LLM_MODEL", "gpt-4o-mini")
    if not _USING_UNIFIED_CONFIG
    else WORLD_LLM_MODEL
)


def embedding_is_configured() -> bool:
    """Return True if at least a base URL is set (api key may be empty for local servers)."""
    return bool(EMBEDDING_BASE_URL)


def get_config_summary() -> dict:
    """Get a summary of the current configuration (safe for logging)."""
    if _USING_UNIFIED_CONFIG:
        config = get_llm_config()
        config["db_path"] = str(DEFAULT_DB_PATH)
        config["embedding_model"] = EMBEDDING_MODEL_NAME
        config["using_unified_config"] = True
        return config

    return {
        "base_url": LLM_BASE_URL or "NOT SET",
        "model": LLM_MODEL,
        "embedding_model": EMBEDDING_MODEL_NAME,
        "db_path": str(DEFAULT_DB_PATH),
        "using_unified_config": False,
    }
