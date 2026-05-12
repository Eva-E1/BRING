"""Generate all world building blocks via LLM prompts (layered, rule‑first)."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List

from .llm import LLMClient
from .prompts import PROMPTS

logger = logging.getLogger(__name__)


def _safe_names(items: List, key: str = "name") -> str:
    """Build a comma‑separated list of names from a list that may contain dicts or strings."""
    names = []
    for it in items:
        if isinstance(it, dict):
            names.append(str(it.get(key, "")))
        else:
            names.append(str(it))
    return ", ".join(names)


class WorldGenerator:
    def __init__(self, llm: LLMClient, concurrency: int = 4):
        self.llm = llm
        self._sem = asyncio.Semaphore(concurrency)

    async def generate_world_frame(self) -> Dict[str, Any]:
        return await self.llm.generate_json(PROMPTS["world_frame"])

    # ── L2 expansion ─────────────────────────────────
    async def expand_character_L2(self, l1: dict, rules_summary: str, existing_names: str) -> dict:
        prompt = PROMPTS["character_L2"].format(
            l1_json=json.dumps(l1),
            rules_summary=rules_summary,
            existing_names=existing_names
        )
        return await self.llm.generate_json(prompt)

    async def expand_location_L2(self, l1: dict, rules_summary: str, existing_names: str) -> dict:
        prompt = PROMPTS["location_L2"].format(
            l1_json=json.dumps(l1),
            rules_summary=rules_summary,
            existing_names=existing_names
        )
        return await self.llm.generate_json(prompt)

    async def expand_item_L2(self, l1: dict, magic_rules: str, existing_names: str) -> dict:
        prompt = PROMPTS["item_L2"].format(
            l1_json=json.dumps(l1),
            magic_rules=magic_rules,
            existing_names=existing_names
        )
        return await self.llm.generate_json(prompt)

    async def expand_event_L2(self, l1: dict, existing_names: str) -> dict:
        prompt = PROMPTS["event_L2"].format(
            l1_json=json.dumps(l1),
            existing_names=existing_names
        )
        return await self.llm.generate_json(prompt)

    async def expand_faction_L2(self, l1: dict, existing_names: str) -> dict:
        prompt = PROMPTS["faction_L2"].format(
            l1_json=json.dumps(l1),
            existing_names=existing_names
        )
        return await self.llm.generate_json(prompt)

    async def expand_rule_L2(self, l1: dict, existing_names: str) -> dict:
        prompt = PROMPTS["rule_L2"].format(
            l1_json=json.dumps(l1),
            existing_names=existing_names
        )
        return await self.llm.generate_json(prompt)

    # ── L3 expansion ─────────────────────────────────
    async def expand_character_L3(self, l1: dict, l2: dict) -> dict:
        prompt = PROMPTS["character_L3"].format(
            l1_json=json.dumps(l1),
            l2_json=json.dumps(l2)
        )
        return await self.llm.generate_json(prompt)

    async def expand_location_L3(self, l1: dict, l2: dict) -> dict:
        prompt = PROMPTS["location_L3"].format(
            l1_json=json.dumps(l1),
            l2_json=json.dumps(l2)
        )
        return await self.llm.generate_json(prompt)

    async def expand_item_L3(self, l1: dict, l2: dict, magic_rules: str) -> dict:
        prompt = PROMPTS["item_L3"].format(
            l1_json=json.dumps(l1),
            l2_json=json.dumps(l2),
            magic_rules=magic_rules
        )
        return await self.llm.generate_json(prompt)

    async def expand_event_L3(self, l1: dict, l2: dict) -> dict:
        prompt = PROMPTS["event_L3"].format(
            l1_json=json.dumps(l1),
            l2_json=json.dumps(l2)
        )
        return await self.llm.generate_json(prompt)

    async def expand_faction_L3(self, l1: dict, l2: dict) -> dict:
        prompt = PROMPTS["faction_L3"].format(
            l1_json=json.dumps(l1),
            l2_json=json.dumps(l2)
        )
        return await self.llm.generate_json(prompt)

    async def expand_rule_L3(self, l1: dict, l2: dict) -> dict:
        prompt = PROMPTS["rule_L3"].format(
            l1_json=json.dumps(l1),
            l2_json=json.dumps(l2)
        )
        return await self.llm.generate_json(prompt)

    # ── Scene generation (unchanged) ──────────────────
    async def generate_scene(self, world_name, rules, context) -> Dict[str, Any]:
        prompt = PROMPTS["scene_generation"].format(
            world_name=world_name, rules=rules, context=context,
        )
        return await self.llm.generate_json(prompt)
