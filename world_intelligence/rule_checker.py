"""Check each entity's L2/L3 against world rules and suggest repairs, with LLM queue and pre‑checks."""
import asyncio
import time
import logging
from typing import List, Dict, Any
from rich.console import Console
from world_explorer.store import GraphStore
from world_explorer.builder_integration import BuilderInterface

console = Console()
logger = logging.getLogger(__name__)

# ── Pre‑checks for relationship consistency (no LLM required) ──
def validate_relationship_sanity(src_entity, rel_type, target_entity) -> List[str]:
    """Return a list of violation descriptions, or empty if all good."""
    issues = []
    src_type = src_entity.entity_type
    tgt_type = target_entity.entity_type
    profile = src_entity.profile
    if rel_type in ("parent_of", "child_of"):
        # parent_of requires the source to be older than the target
        src_age = profile.l1.get("age") or profile.l2.get("age")
        tgt_age = target_entity.profile.l1.get("age") or target_entity.profile.l2.get("age")
        if src_age and tgt_age and isinstance(src_age, int) and isinstance(tgt_age, int):
            if rel_type == "parent_of" and src_age <= tgt_age:
                issues.append(f"parent_of: source {src_entity.name} age {src_age} <= target {target_entity.name} age {tgt_age}")
            elif rel_type == "child_of" and src_age >= tgt_age:
                issues.append(f"child_of: source {src_entity.name} age {src_age} >= target {target_entity.name} age {tgt_age}")
    if rel_type in ("located_at", "located_in"):
        if tgt_type != "Location":
            issues.append(f"located_at/in target must be a Location, got {tgt_type}")
    if rel_type == "controls":
        if src_type != "Faction" and src_type != "Character":
            issues.append(f"controls: source {src_type} is not a Faction/Character")
        if tgt_type != "Location":
            issues.append(f"controls: target must be a Location, got {tgt_type}")
    return issues


class RuleChecker:
    def __init__(self, store: GraphStore, builder: BuilderInterface,
                 max_concurrent_llm: int = 4, base_retry_delay: float = 1.0):
        self.store = store
        self.builder = builder
        self.entities = store.entities
        self.rules = self._get_rules_text()
        self.semaphore = asyncio.Semaphore(max_concurrent_llm)
        self.base_retry_delay = base_retry_delay

    def _get_rules_text(self) -> str:
        wf = self.builder.builder.world_frame
        if not wf:
            return ""
        return "\n".join(f"- {r['name']}: {r['description']}" for r in wf.get("world_rules", []))

    # ── Non‑LLM sanity checks on relationships ─────
    def precheck_relationships(self) -> List[Dict[str, Any]]:
        """Run fast, non‑LLM checks on existing relationships, return conflicts."""
        conflicts = []
        for ent in self.entities:
            for rel in ent.profile.l1.get("relationships", []):
                target_uid = rel.get("target")
                if not target_uid:
                    continue
                target_node = self.store.entities_by_uid.get(target_uid)
                if not target_node:
                    continue
                issues = validate_relationship_sanity(ent, rel.get("type", ""), target_node)
                for issue in issues:
                    conflicts.append({
                        "uid": ent.uid,
                        "name": ent.name,
                        "type": ent.entity_type,
                        "description": issue,
                        "source": "precheck",
                    })
        return conflicts

    # ── Main LLM‑based checker (async) ──────────────
    async def _check_one_entity(self, ent) -> List[Dict[str, Any]]:
        l2 = ent.profile.l2
        l3 = ent.profile.l3
        if not l2 and not l3:
            return []
        combined = f"Entity: {ent.name} ({ent.entity_type})\n"
        if l2:
            combined += f"L2: {l2}\n"
        if l3:
            combined += f"L3: {l3}\n"

        prompt = f"""
World rules:
{self.rules}

Check the following entity for violations of the world rules.
If there is a violation, answer with a JSON object:
{{"violation": true, "description": "brief explanation of what rule is broken and how", "suggestion": "how to fix it"}}
If no violation, answer:
{{"violation": false}}

Entity data:
{combined}
"""
        delay = self.base_retry_delay
        for attempt in range(3):
            async with self.semaphore:
                try:
                    result = await self.builder.builder.gen.llm.generate_json(prompt, temperature=0.3)
                    if result.get("violation"):
                        return [{
                            "uid": ent.uid,
                            "name": ent.name,
                            "type": ent.entity_type,
                            "description": result.get("description", ""),
                            "suggestion": result.get("suggestion", ""),
                        }]
                    return []
                except Exception as e:
                    logger.warning(f"LLM check failed for {ent.uid} (attempt {attempt+1}): {e}")
                    if attempt == 2:
                        raise
                    await asyncio.sleep(delay * (2 ** attempt))
        return []

    async def check_all_async(self, auto_fix: bool = False) -> List[Dict[str, Any]]:
        """Run entity checks concurrently, with optional auto‑fix."""
        tasks = [self._check_one_entity(ent) for ent in self.entities]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        conflicts = []
        for res in results_list:
            if isinstance(res, Exception):
                continue
            for c in res:
                conflicts.append(c)
                if auto_fix:
                    await self._auto_fix_async(c["uid"], c["suggestion"])

        # Add pre‑check conflicts
        conflicts.extend(self.precheck_relationships())
        return conflicts

    def check_all(self, auto_fix: bool = False) -> List[Dict[str, Any]]:
        """Synchronous wrapper for check_all_async."""
        return asyncio.run(self.check_all_async(auto_fix))

    # ── Auto‑fix methods (async) ───────────────────
    async def _auto_fix_async(self, uid: str, suggestion: str):
        ent = self.store.entities_by_uid.get(uid)
        if not ent:
            return
        logger.info(f"Auto‑fixing {uid}...")
        prompt = f"""
World rules:
{self.rules}

Entity current L2: {ent.profile.l2}
Entity current L3: {ent.profile.l3}
Violation: {suggestion}

Propose a corrected L2 and L3 that strictly obey the world rules.
Return a JSON object with keys "l2" and "l3" containing the fixed data.
"""
        delay = self.base_retry_delay
        for attempt in range(3):
            async with self.semaphore:
                try:
                    result = await self.builder.builder.gen.llm.generate_json(prompt, temperature=0.3)
                    new_l2 = result.get("l2")
                    new_l3 = result.get("l3")
                    if new_l2 and new_l2 != ent.profile.l2:
                        self.builder.gm.store.update_entity_level(uid, "l2", new_l2)
                    if new_l3 and new_l3 != ent.profile.l3:
                        self.builder.gm.store.update_entity_level(uid, "l3", new_l3)
                    logger.info(f"  Fixed {uid}")
                    return
                except Exception as e:
                    logger.warning(f"Auto‑fix attempt {attempt+1} failed for {uid}: {e}")
                    if attempt == 2:
                        raise
                    await asyncio.sleep(delay * (2 ** attempt))
