"""Load configuration for LLM and database."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
DATABASE_PATH = Path(os.getenv("WORLD_DB_PATH", "./world_db"))

LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "5"))
LLM_RATE_LIMIT_RPS = float(os.getenv("LLM_RATE_LIMIT_RPS", "3.0"))
LLM_MAX_CONCURRENT = int(os.getenv("LLM_MAX_CONCURRENT", "8"))
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120.0"))
LLM_CONNECT_TIMEOUT = float(os.getenv("LLM_CONNECT_TIMEOUT", "15.0"))
LLM_READ_TIMEOUT = float(os.getenv("LLM_READ_TIMEOUT", "90.0"))

ENTITY_STORE_PATH = DATABASE_PATH / "entities.json"
DEFAULT_WORLD_FRAME_PATH = DATABASE_PATH / "world_frame.json"

def get_world_frame_path(db_path: Path) -> Path:
    return db_path / "world_frame.json"

def get_entity_store_path(db_path: Path) -> Path:
    return db_path / "entities.json"
