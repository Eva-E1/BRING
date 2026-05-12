"""Configuration for the intelligence engine."""
import os
from pathlib import Path

# Where the world_db lives (same as the other projects)
WORLD_DB_PATH = Path(os.getenv("WORLD_DB_PATH", "./world_db"))
