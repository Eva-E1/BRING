/home/ali/Lab/world_engine/start_resolver.py
```

```python
"""Allows user to specify a starting point in the story."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any, Dict
import json
import re
import logging
from difflib import get_close_matches

from world_builder.graph_manager import GraphManager
from world_narrative.memory_optimized import OptimizedMemoryStore
from world_narrative.director import Director

logger = logging.getLogger(__name__)


@dataclass
class StartingPoint:
    """User-specified story start configuration."""
    character: Optional[str] = None
    location: Optional[str] = None
    story_time: Optional[datetime] = None
    scenario: Optional[str] = None          # e.g., "tavern brawl", "morning in the forest"
    custom_context: Optional[str] = None    # user-provided initial scene description


class StartResolver:
    """Resolves a user's starting point specification into a usable state."""

    def __init__(self, gm: GraphManager, npc_mgr: OptimizedMemoryStore, director: Director):
        self.gm = gm
        self.npc_mgr = npc_mgr
        self.director = director

    def _find_closest_entity(self, name: str, entity_type: str) -> Optional[str]:
        """Fuzzy match an entity name against existing entities of given type."""
        entities = self.gm.store.list_by_type(entity_type)
        if not entities:
            return None
        names = [e.name for e in entities]
        matches = get_close_matches(name, names, n=1, cutoff=0.6)
        return matches[0] if matches else None

    def _get_default_location(self) -> Optional[str]:
        """Return the first location in the world, or None."""
        locations = self.gm.store.list_by_type("Location")
        return locations[0].name if locations else None

    async def resolve(
        self,
        user_spec: str,
        default_world_name: str,
        default_time: datetime,
    ) -> StartingPoint:
        """Parse user input and return a StartingPoint object.
        User_spec can be:
          - plain text: e.g., "as Kaelen in the Silverwood forest at dawn"
          - JSON: {"character": "Kaelen", "location": "Silverwood", "time": "2025-01-01T08:00:00", "scenario": "..."}
          - simple slash commands like "/start character=Kaelen location=Silverwood"
        """
        # Try JSON
        try:
            data = json.loads(user_spec)
            return StartingPoint(
                character=data.get("character"),
                location=data.get("location"),
                story_time=datetime.fromisoformat(data["time"]) if data.get("time") else None,
                scenario=data.get("scenario"),
                custom_context=data.get("custom_context"),
            )
        except (json.JSONDecodeError, ValueError):
            pass

        # Try simple key=value format
        if "=" in user_spec:
            parts = user_spec.split()
            data = {}
            for part in parts:
                if "=" in part:
                    k, v = part.split("=", 1)
                    data[k] = v
            return StartingPoint(
                character=data.get("character"),
                location=data.get("location"),
                story_time=datetime.fromisoformat(data["time"]) if data.get("time") else None,
                scenario=data.get("scenario"),
                custom_context=data.get("context"),
            )

        # Free-form: use LLM to extract
        prompt = f"""
Extract story starting parameters from the following user input.
Return a JSON object with keys: character, location, time (ISO format if mentioned), scenario (short description), custom_context (any extra description).
If not present, leave null.

User input: "{user_spec}"
"""
        try:
            result = await self.director.story_engine.llm.generate_json(prompt, temperature=0.3)
            return StartingPoint(
                character=result.get("character"),
                location=result.get("location"),
                story_time=datetime.fromisoformat(result["time"]) if result.get("time") else None,
                scenario=result.get("scenario"),
                custom_context=result.get("custom_context"),
            )
        except Exception:
            # Fallback: treat whole input as scenario
            return StartingPoint(scenario=user_spec, custom_context=user_spec)

    async def apply_to_session(
        self,
        session,
        start: StartingPoint,
        world_frame: dict,
    ) -> None:
        """Apply the resolved starting point to a user session (modifies in-place)."""
        if start.character:
            # Verify character exists
            node = self.gm.store.get_by_name_and_type(start.character, "Character")
            if not node:
                # Try fuzzy match
                closest = self._find_closest_entity(start.character, "Character")
                if closest:
                    logger.warning(f"Unknown character '{start.character}', using closest match: '{closest}'")
                    start.character = closest
                    node = self.gm.store.get_by_name_and_type(start.character, "Character")
                else:
                    raise ValueError(f"Unknown character: {start.character}")
            session.active_character = start.character
            # Register in NPC manager if not already
            if not self.npc_mgr.get(start.character):
                uid = f"Character:{start.character}"
                await self.npc_mgr.register(start.character, uid, start.location or "unknown")

        if start.location:
            # Verify location exists
            loc_node = self.gm.store.get_by_name_and_type(start.location, "Location")
            if not loc_node:
                # Try fuzzy match
                closest = self._find_closest_entity(start.location, "Location")
                if closest:
                    logger.warning(f"Unknown location '{start.location}', using closest match: '{closest}'")
                    start.location = closest
                    loc_node = self.gm.store.get_by_name_and_type(start.location, "Location")
                else:
                    # Fallback to a default location
                    default_loc = self._get_default_location()
                    if default_loc:
                        logger.warning(f"Unknown location '{start.location}', falling back to default: '{default_loc}'")
                        start.location = default_loc
                    else:
                        # No locations exist – leave location unchanged or set to "unknown"
                        logger.warning(f"Unknown location '{start.location}' and no default location found. Keeping current location.")
                        start.location = None
            if start.location:
                session.current_location = start.location

        if start.story_time:
            session.current_time = start.story_time

        if start.scenario or start.custom_context:
            # Store custom context in session flags
            if not hasattr(session, 'flags'):
                session.flags = {}
            session.flags["start_scenario"] = start.scenario or start.custom_context
            # Log an initial event to chronicler
            await self.director.chronicler.log_event(
                f"Story begins: {start.scenario or start.custom_context}",
                session.current_time,
                group="start",
            )
