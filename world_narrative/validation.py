from __future__ import annotations

from typing import Any, Dict, List, Optional
import re
from world_builder.graph_manager import GraphManager


class WorldValidator:
    def __init__(self, gm: GraphManager, world_frame: dict):
        self.gm = gm
        self.world_frame = world_frame
        self.rules = self._load_rules()

    def _load_rules(self) -> list:
        return self.world_frame.get("world_rules", [])

    async def validate_action(
        self,
        actor_name: str,
        action: str,
        location: Optional[str] = None,
        target: Optional[str] = None,
    ) -> tuple[bool, str, List[dict]]:
        """Returns (is_valid, message, forced_effects)"""
        forced = []
        actor_node = self.gm.store.get_by_name_and_type(actor_name, "Character")
        if not actor_node:
            return False, f"Actor '{actor_name}' is not a known character.", forced

        action_low = action.lower()
        loc_low = location.lower() if location else ""

        for rule in self.rules:
            rule_text = f"{rule.get('name', '')} {rule.get('description', '')}".lower()
            match = None
            if "no magic" in rule_text and action_low == "cast_magic":
                match = re.search(r"no magic in (?:the )?([a-z0-9' -]+)", rule_text)
                if match and match.group(1) in loc_low:
                    forced.append({"type": "npc_health", "entity": actor_name, "delta": -15})
                    forced.append({"type": "record_incident", "label": f"Magic backlash in {location}"})
                    return False, f"Rule '{rule['name']}' forbids magic here, and you suffer backlash!", forced

            if "no combat" in rule_text and action_low in {"attack", "fight"}:
                match = re.search(r"no combat in (?:the )?([a-z0-9' -]+)", rule_text) or re.search(r"no (?:violence|fighting) in (?:the )?([a-z0-9' -]+)", rule_text)
                if match and match.group(1) in loc_low:
                    return False, f"Rule '{rule['name']}' forbids combat in '{location}'.", forced

        return True, "ok", forced
