"""
Unified configuration file for World Explorer.
Loads LLM settings from environment variables with sensible defaults.

Usage:
    # Set environment variables before running:
    export WORLD_LLM_BASE_URL="http://localhost:20128/v1"
    export WORLD_LLM_API_KEY="sk-your-api-key"
    export WORLD_LLM_MODEL="gpt-4o-mini"

    # Or create a .env file in the project root:
    # WORLD_LLM_BASE_URL=http://localhost:20128/v1
    # WORLD_LLM_API_KEY=sk-your-api-key
    # WORLD_LLM_MODEL=gpt-4o-mini
"""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("world_config")

# ═══════════════════════════════════════════════════════════════════════════════
# LLM (Language Model) Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# Base URL for LLM API (OpenAI-compatible)
# Examples:
#   - http://localhost:20128/v1 (Liara local)
#   - https://api.openai.com/v1 (OpenAI)
#   - https://api.anthropic.com/v1 (Anthropic)
#   - http://localhost:11434/v1 (Ollama)
WORLD_LLM_BASE_URL: str = os.getenv("WORLD_LLM_BASE_URL", "")

# API key for LLM
WORLD_LLM_API_KEY: str = os.getenv("WORLD_LLM_API_KEY", "")

# Model name to use
# Examples: "gpt-4o-mini", "gpt-4o", "claude-3-haiku", "llama3"
WORLD_LLM_MODEL: str = os.getenv("WORLD_LLM_MODEL", "gpt-4o-mini")

# Embedding model configuration
WORLD_EMBEDDING_MODEL: str = os.getenv("WORLD_EMBEDDING_MODEL", "text-embedding-3-small")
WORLD_EMBEDDING_BASE_URL: str = os.getenv("WORLD_EMBEDDING_BASE_URL", "")
WORLD_EMBEDDING_API_KEY: str = os.getenv("WORLD_EMBEDDING_API_KEY", "")

# LLM behavior settings
WORLD_LLM_TIMEOUT: float = float(os.getenv("WORLD_LLM_TIMEOUT", "120.0"))
WORLD_LLM_MAX_TOKENS: int = int(os.getenv("WORLD_LLM_MAX_TOKENS", "4096"))
WORLD_LLM_TEMPERATURE: float = float(os.getenv("WORLD_LLM_TEMPERATURE", "0.7"))
WORLD_LLM_MAX_RETRIES: int = int(os.getenv("WORLD_LLM_MAX_RETRIES", "3"))
WORLD_LLM_MAX_CONCURRENT: int = int(os.getenv("WORLD_LLM_MAX_CONCURRENT", "8"))

# ═══════════════════════════════════════════════════════════════════════════════
# Database Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# Path to the world database directory
WORLD_DB_PATH: Path = Path(os.getenv("WORLD_DB_PATH", "./world_db"))

# Ensure DB path exists
WORLD_DB_PATH.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════════
# Application Settings
# ═══════════════════════════════════════════════════════════════════════════════

# Server configuration
WORLD_SERVER_HOST: str = os.getenv("WORLD_SERVER_HOST", "127.0.0.1")
WORLD_SERVER_PORT: int = int(os.getenv("WORLD_SERVER_PORT", "8000"))
WORLD_SERVER_RELOAD: bool = os.getenv("WORLD_SERVER_RELOAD", "false").lower() == "true"

# Self-healing graph settings
WORLD_AUTO_HEAL: bool = os.getenv("WORLD_AUTO_HEAL", "true").lower() == "true"

# ═══════════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════════

def is_llm_configured() -> bool:
    """Check if LLM is properly configured."""
    return bool(WORLD_LLM_BASE_URL and WORLD_LLM_API_KEY)

def get_llm_config() -> dict:
    """Get LLM configuration as a dictionary (safe for logging - masks API key)."""
    return {
        "base_url": WORLD_LLM_BASE_URL,
        "model": WORLD_LLM_MODEL,
        "embedding_model": WORLD_EMBEDDING_MODEL,
        "timeout": WORLD_LLM_TIMEOUT,
        "max_tokens": WORLD_LLM_MAX_TOKENS,
        "api_key_set": bool(WORLD_LLM_API_KEY),
    }

def validate_config() -> bool:
    """Validate the configuration and log warnings."""
    issues = []

    if not WORLD_LLM_BASE_URL:
        issues.append("WORLD_LLM_BASE_URL is not set")

    if not WORLD_LLM_API_KEY:
        issues.append("WORLD_LLM_API_KEY is not set")

    if not WORLD_LLM_MODEL:
        issues.append("WORLD_LLM_MODEL is not set")

    if issues:
        logger.warning("Configuration issues detected:")
        for issue in issues:
            logger.warning(f"  - {issue}")
        logger.warning("Set environment variables or create a .env file")
        return False

    logger.info(f"LLM configured: {WORLD_LLM_BASE_URL} with model {WORLD_LLM_MODEL}")
    return True

# Validate on import (optional - can be disabled in production)
if __name__ != "__main__":
    # Skip validation when imported as a module to allow partial config
    pass
else:
    # Run validation when executed directly
    print("World Explorer Configuration")
    print("=" * 50)
    if validate_config():
        print(f"✓ LLM: {WORLD_LLM_BASE_URL}")
        print(f"✓ Model: {WORLD_LLM_MODEL}")
        print(f"✓ DB Path: {WORLD_DB_PATH}")
    else:
        print("✗ Configuration incomplete - check .env file")
