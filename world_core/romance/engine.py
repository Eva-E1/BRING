"""Romance Engine - manages romantic relationships, computes probabilities,
and interacts with the director for story arcs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from world_builder.graph_manager import GraphManager

from .models import (
    RomanceEvent,
    RomanceParams,
    RomanceProgression,
    RomanceStatus,
    RelationshipMemory,
)
from .profiles import (
    ROMANCE_BREAKUP,
    ROMANCE_CONFESSION,
    ROMANCE_DATE,
    ROMANCE_KISS,
    ROMANCE_PROPOSAL,
    get_romance_profile,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from world_core.probability import ProbabilityEngine
    from world_core.memory import WorldMemory
    from world_narrative.memory_optimized import OptimizedMemoryStore
    from world_director.director import Director


class RomanceEngine:
    """Manages romantic relationships with deterministic outcomes based on probability."""

    def __init__(
        self,
        prob_engine: "ProbabilityEngine",
        world_memory: "WorldMemory",
        gm: GraphManager,
        npc_mgr: "OptimizedMemoryStore",
        director: "Director",
        data_dir: Optional[Path] = None,
    ):
        self.prob_engine = prob_engine
        self.world_memory = world_memory
        self.gm = gm
        self.npc_mgr = npc_mgr
        self.director = director
        self.data_dir = data_dir or Path("world_db/romance")
        self._relationships: Dict[str, RelationshipMemory] = {}
        self._load()

    def _pair_id(self, a: str, b: str) -> str:
        """Generate a consistent pair ID regardless of order."""
        return "_".join(sorted([a.lower(), b.lower()]))

    async def get_relationship(self, a: str, b: str) -> Optional[RelationshipMemory]:
        """Get the relationship memory for a pair of characters."""
        pid = self._pair_id(a, b)
        return self._relationships.get(pid)

    async def get_or_create_relationship(
        self, a: str, b: str
    ) -> RelationshipMemory:
        """Get existing relationship or create a new one."""
        pid = self._pair_id(a, b)
        if pid not in self._relationships:
            compatibility = await self.compute_compatibility(a, b)
            self._relationships[pid] = RelationshipMemory(
                pair_id=pid,
                status=RomanceStatus.STRANGER,
                progression_stage=RomanceProgression.ATTRACTION,
                compatibility=compatibility,
                affection=0.3,
                history=[],
                last_interaction=datetime.now(),
            )
        return self._relationships[pid]

    async def update_relationship(self, rel: RelationshipMemory) -> None:
        """Update relationship and persist to storage."""
        pid = rel.pair_id
        self._relationships[pid] = rel
        self._save()
        await self._index_relationship_memory(rel)

    async def compute_compatibility(self, a: str, b: str) -> float:
        """Compute base compatibility from race, class, traits, and world rules."""
        actor_node = self.gm.store.get_by_name_and_type(a, "Character")
        target_node = self.gm.store.get_by_name_and_type(b, "Character")

        if not actor_node or not target_node:
            return 0.5

        actor_race = actor_node.profile.l1.get("tags", ["human"])[0] if actor_node.profile.l1 else "human"
        target_race = target_node.profile.l1.get("tags", ["human"])[0] if target_node.profile.l1 else "human"

        actor_class = actor_node.profile.l2.get("social_class", "commoner") if actor_node.profile.l2 else "commoner"
        target_class = target_node.profile.l2.get("social_class", "commoner") if target_node.profile.l2 else "commoner"

        race_match = 1.0 if actor_race == target_race else 0.8
        class_match = 1.0 if actor_class == target_class else 0.9

        forbidden_modifier = 1.0
        world_rules = self.world_memory.world_frame.get("world_rules", [])
        for rule in world_rules:
            if "forbidden" in rule.get("name", "").lower() and "love" in rule.get("name", "").lower():
                forbidden_modifier = rule.get("effect", {}).get("compatibility_modifier", 0.5)
                break

        compatibility = (race_match + class_match) / 2.0 * forbidden_modifier
        return max(0.1, min(1.0, compatibility))

    async def _build_context(
        self, actor: str, target: str, location: str, rel: RelationshipMemory
    ) -> Dict:
        """Build probability context for romance actions."""
        context = {
            "current_affection": rel.affection,
            "compatibility": rel.compatibility,
            "actor_charisma": await self._get_charisma(actor),
            "target_mood_factor": await self._get_mood(target),
            "environment_modifier": await self._get_location_romance_modifier(location),
            "luck": 0.5,
            "past_positive_interactions": self._count_positive_interactions(rel),
            "relationship_duration": self._get_relationship_duration(rel),
            "family_approval": await self._get_family_approval(actor, target),
            "time_of_day_modifier": self._get_time_modifier(),
            "conflict_level": 1.0 - rel.affection,
            "external_pressure": 0.0,
        }
        return context

    async def _get_charisma(self, name: str) -> float:
        """Get character's charisma value."""
        profile = self.npc_mgr.get(name)
        if profile and profile.skills:
            return profile.skills.get("charisma", 0.5)
        node = self.gm.store.get_by_name_and_type(name, "Character")
        if node and node.profile.l3:
            innate_skills = node.profile.l3.get("innate_skills", [])
            for skill in innate_skills:
                if skill.get("name") == "charisma":
                    return skill.get("base_value", 0.5)
        return 0.5

    async def _get_mood(self, name: str) -> float:
        """Get character's mood factor (0.0-1.0)."""
        profile = self.npc_mgr.get(name)
        if profile:
            mood_map = {
                "joy": 0.9, "happy": 0.85, "excited": 0.8,
                "neutral": 0.5, "calm": 0.6,
                "sad": 0.3, "depressed": 0.2, "grief": 0.1,
                "fear": 0.2, "anxious": 0.3,
                "anger": 0.2, "furious": 0.1, "annoyed": 0.4,
            }
            return mood_map.get(profile.mood, 0.5)
        return 0.5

    async def _get_location_romance_modifier(self, location: str) -> float:
        """Get location's romance modifier."""
        loc_node = self.gm.store.get_by_name_and_type(location, "Location")
        if loc_node and loc_node.profile.l2:
            return loc_node.profile.l2.get("romance_modifier", 0.0)
        return 0.0

    def _count_positive_interactions(self, rel: RelationshipMemory) -> float:
        """Count positive interactions from history."""
        positive = sum(
            1 for h in rel.history
            if h.get("success") and h.get("type") in ("date", "kiss", "gift")
        )
        return min(1.0, positive * 0.15)

    def _get_relationship_duration(self, rel: RelationshipMemory) -> float:
        """Get relationship duration as a factor (0.0-1.0)."""
        if not rel.last_interaction:
            return 0.1
        days = (datetime.now() - rel.last_interaction).days
        return min(1.0, days / 365.0)

    async def _get_family_approval(self, actor: str, target: str) -> float:
        """Get family approval for the relationship."""
        return 0.5

    def _get_time_modifier(self) -> float:
        """Get time of day modifier for romantic activities."""
        hour = datetime.now().hour
        if 18 <= hour <= 22:
            return 0.2
        elif 10 <= hour <= 22:
            return 0.0
        else:
            return -0.1

    async def attempt_attraction(
        self, actor: str, target: str, location: str
    ) -> Tuple[bool, str, float]:
        """Attempt to develop attraction - returns (success, narrative, new_affection)."""
        from .profiles import ROMANCE_ATTRACTION

        rel = await self.get_or_create_relationship(actor, target)
        context = await self._build_context(actor, target, location, rel)

        result = self.prob_engine.roll(ROMANCE_ATTRACTION, context, actor)

        affection_delta = 0.15 if result.success else -0.05
        if result.critical_success:
            affection_delta = 0.25
        elif result.critical_failure:
            affection_delta = -0.10

        new_affection = min(1.0, max(0.0, rel.affection + affection_delta))

        rel.affection = new_affection
        rel.last_interaction = datetime.now()

        if result.success and rel.status == RomanceStatus.STRANGER:
            rel.status = RomanceStatus.ACQUAINTANCE
        elif result.success and rel.affection > 0.6 and rel.status in (RomanceStatus.ACQUAINTANCE, RomanceStatus.FRIEND):
            rel.status = RomanceStatus.CRUSH

        rel.history.append({
            "type": "attraction_check",
            "success": result.success,
            "quality": result.quality.value,
            "timestamp": datetime.now().isoformat(),
            "affection_change": affection_delta,
        })

        await self.update_relationship(rel)

        narrative = await self._generate_narrative(
            actor, target, "attraction_check", result.success, result.quality.value
        )

        return result.success, narrative, new_affection

    async def attempt_confession(
        self, actor: str, target: str, location: str, message: str = ""
    ) -> Tuple[bool, str, float]:
        """Attempt to confess feelings - returns (success, narrative, new_affection)."""
        from .profiles import ROMANCE_CONFESSION

        rel = await self.get_or_create_relationship(actor, target)

        if rel.affection < 0.4:
            return False, f"{actor} doesn't feel strongly enough to confess yet. (Affection: {rel.affection:.0%})", rel.affection

        context = await self._build_context(actor, target, location, rel)
        result = self.prob_engine.roll(ROMANCE_CONFESSION, context, actor)

        if result.success:
            affection_delta = 0.25
            new_status = RomanceStatus.DATING
            new_stage = RomanceProgression.CONFESSION
        else:
            affection_delta = -0.15
            new_status = RomanceStatus.ESTRANGED
            new_stage = RomanceProgression.BREAKUP

        new_affection = min(1.0, max(0.0, rel.affection + affection_delta))

        rel.affection = new_affection
        rel.status = new_status
        rel.progression_stage = new_stage
        rel.last_interaction = datetime.now()

        if message and result.success:
            rel.notes = message

        rel.history.append({
            "type": "confession",
            "success": result.success,
            "quality": result.quality.value,
            "timestamp": datetime.now().isoformat(),
            "affection_change": affection_delta,
            "message": message,
        })

        await self.update_relationship(rel)

        narrative = await self._generate_narrative(
            actor, target, "confession", result.success, result.quality.value, message
        )

        if result.success:
            await self._schedule_romance_arc(actor, target, "dating")

        return result.success, narrative, new_affection

    async def attempt_date(
        self, actor: str, target: str, location: str
    ) -> Tuple[bool, str, float]:
        """Attempt to go on a date - returns (success, narrative, affection_change)."""
        from .profiles import ROMANCE_DATE

        rel = await self.get_or_create_relationship(actor, target)

        if rel.status == RomanceStatus.STRANGER:
            return False, f"{actor} and {target} don't know each other well enough to date.", 0.0

        context = await self._build_context(actor, target, location, rel)
        result = self.prob_engine.roll(ROMANCE_DATE, context, actor)

        affection_delta = 0.15 if result.success else -0.05
        if result.critical_success:
            affection_delta = 0.25
        elif result.critical_failure:
            affection_delta = -0.10

        new_affection = min(1.0, max(0.0, rel.affection + affection_delta))

        rel.affection = new_affection
        if result.success and rel.status in (RomanceStatus.CRUSH, RomanceStatus.ACQUAINTANCE):
            rel.status = RomanceStatus.DATING
        rel.progression_stage = RomanceProgression.DATE
        rel.last_interaction = datetime.now()

        rel.history.append({
            "type": "date",
            "success": result.success,
            "quality": result.quality.value,
            "timestamp": datetime.now().isoformat(),
            "affection_change": affection_delta,
            "location": location,
        })

        await self.update_relationship(rel)

        narrative = await self._generate_narrative(
            actor, target, "date", result.success, result.quality.value, location=location
        )

        return result.success, narrative, affection_delta

    async def attempt_kiss(
        self, actor: str, target: str, location: str
    ) -> Tuple[bool, str, float]:
        """Attempt to kiss - returns (success, narrative, affection_change)."""
        from .profiles import ROMANCE_KISS

        rel = await self.get_or_create_relationship(actor, target)

        if rel.status not in (RomanceStatus.DATING, RomanceStatus.CRUSH, RomanceStatus.CLOSE_FRIEND):
            return False, f"{actor} and {target} aren't close enough for a kiss yet.", 0.0

        context = await self._build_context(actor, target, location, rel)
        result = self.prob_engine.roll(ROMANCE_KISS, context, actor)

        affection_delta = 0.10 if result.success else -0.08
        new_affection = min(1.0, max(0.0, rel.affection + affection_delta))

        rel.affection = new_affection
        rel.progression_stage = RomanceProgression.KISS
        rel.last_interaction = datetime.now()

        rel.history.append({
            "type": "kiss",
            "success": result.success,
            "quality": result.quality.value,
            "timestamp": datetime.now().isoformat(),
            "affection_change": affection_delta,
            "location": location,
        })

        await self.update_relationship(rel)

        narrative = await self._generate_narrative(
            actor, target, "kiss", result.success, result.quality.value
        )

        return result.success, narrative, affection_delta

    async def attempt_proposal(
        self, actor: str, target: str, location: str
    ) -> Tuple[bool, str, float]:
        """Attempt to propose - returns (success, narrative, new_affection)."""
        from .profiles import ROMANCE_PROPOSAL

        rel = await self.get_or_create_relationship(actor, target)

        if rel.status != RomanceStatus.DATING:
            return False, f"{actor} and {target} aren't in a serious relationship yet.", rel.affection

        if rel.affection < 0.7:
            return False, f"{target} doesn't love {actor} enough to marry yet. (Affection: {rel.affection:.0%})", rel.affection

        context = await self._build_context(actor, target, location, rel)
        result = self.prob_engine.roll(ROMANCE_PROPOSAL, context, actor)

        affection_delta = 0.15 if result.success else -0.25
        new_affection = min(1.0, max(0.0, rel.affection + affection_delta))

        rel.affection = new_affection
        if result.success:
            rel.status = RomanceStatus.ENGAGED
            rel.progression_stage = RomanceProgression.PROPOSAL
        else:
            rel.status = RomanceStatus.ESTRANGED
            rel.progression_stage = RomanceProgression.BREAKUP

        rel.last_interaction = datetime.now()

        rel.history.append({
            "type": "proposal",
            "success": result.success,
            "quality": result.quality.value,
            "timestamp": datetime.now().isoformat(),
            "affection_change": affection_delta,
            "location": location,
        })

        await self.update_relationship(rel)

        narrative = await self._generate_narrative(
            actor, target, "proposal", result.success, result.quality.value
        )

        if result.success:
            await self._schedule_romance_arc(actor, target, "engaged")

        return result.success, narrative, new_affection

    async def attempt_breakup(
        self, actor: str, target: str, reason: str = ""
    ) -> Tuple[bool, str, float]:
        """Attempt to break up - returns (success, narrative, new_affection)."""
        from .profiles import ROMANCE_BREAKUP

        rel = await self.get_relationship(actor, target)

        if not rel or rel.status not in (RomanceStatus.DATING, RomanceStatus.ENGAGED, RomanceStatus.MARRIED):
            return False, f"{actor} and {target} aren't in a relationship.", 0.0

        context = {
            "current_affection": rel.affection,
            "conflict_level": 1.0 - rel.affection,
            "external_pressure": 0.0,
            "luck": 0.5,
        }

        result = self.prob_engine.roll(ROMANCE_BREAKUP, context, actor)

        affection_delta = -0.4 if result.success else 0.1
        new_affection = min(1.0, max(0.0, rel.affection + affection_delta))

        rel.affection = new_affection
        rel.status = RomanceStatus.ESTRANGED
        rel.progression_stage = RomanceProgression.BREAKUP
        rel.last_interaction = datetime.now()

        rel.history.append({
            "type": "breakup",
            "success": result.success,
            "quality": result.quality.value,
            "timestamp": datetime.now().isoformat(),
            "affection_change": affection_delta,
            "reason": reason,
        })

        await self.update_relationship(rel)

        narrative = await self._generate_narrative(
            actor, target, "breakup", result.success, result.quality.value, reason
        )

        return result.success, narrative, new_affection

    async def give_gift(
        self, actor: str, target: str, gift_name: str
    ) -> Tuple[bool, str, float]:
        """Give a gift to increase affection."""
        rel = await self.get_or_create_relationship(actor, target)

        gift_bonus = 0.1
        affection_delta = gift_bonus
        new_affection = min(1.0, rel.affection + affection_delta)

        rel.affection = new_affection
        rel.gifts_given.append(gift_name)
        rel.last_interaction = datetime.now()

        rel.history.append({
            "type": "gift",
            "gift": gift_name,
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "affection_change": affection_delta,
        })

        await self.update_relationship(rel)

        narrative = f"{actor} gives {target} a {gift_name}. {target} appreciates the gesture."

        return True, narrative, affection_delta

    async def _generate_narrative(
        self,
        actor: str,
        target: str,
        action: str,
        success: bool,
        quality: str,
        message: str = "",
        location: str = "",
        reason: str = "",
    ) -> str:
        """Generate narrative text for a romantic action."""

        quality_desc = {
            "critical_success": "amazingly",
            "success": "successfully",
            "marginal_success": "barely",
            "marginal_failure": "almost",
            "failure": "unsuccessfully",
            "critical_failure": "disastrously",
        }.get(quality, "unexpectedly")

        templates = {
            "attraction_check": (
                f"{actor} feels {quality_desc} drawn to {target}. "
                ('There seems to be a spark between them.' if success else 'Perhaps it just wasn''t meant to be.')
            ),
            "confession": (
                f"{actor} confesses their feelings to {target} {quality_desc}. "
                f"{message if message else ''} "
                f"{f'{target} accepts!' if success else f'{target} rejects {actor}.'}"
            ),
            "date": (
                f"{actor} and {target} go on a date{(' at ' + location) if location else ''}. "
                f"It goes " + quality_desc + "!" if success else "It doesn't go well."
            ),
            "kiss": (
                f"{actor} kisses {target} {quality_desc}. "
                "It\'s magical!" if success else "They pull away."
            ),
            "proposal": (
                f"{actor} proposes to {target} {quality_desc}. "
                f"{'They say yes!' if success else 'They say no...'}"
            ),
            "breakup": (
                f"{actor} breaks up with {target} {quality_desc}. "
                f"{reason if reason else ''} {'They part on bad terms.' if not success else 'They remain friends.'}"
            ),
        }

        return templates.get(action, f"{actor} attempts {action} with {target}.")

    async def _schedule_romance_arc(self, a: str, b: str, phase: str) -> None:
        """Schedule romantic story arc events with the director."""
        if hasattr(self.director, 'clock'):
            await self.director.clock.schedule_event(
                datetime.now() + timedelta(days=3),
                "romance_event",
                {
                    "type": phase,
                    "actor": a,
                    "target": b,
                    "phase": phase,
                }
            )
            logger.info(f"Scheduled romance arc: {a} & {b} - {phase}")

    async def _index_relationship_memory(self, rel: RelationshipMemory) -> None:
        """Index relationship in world memory for semantic search."""
        summary = f"Romantic relationship between {rel.pair_id}: {rel.status.value}, affection {rel.affection:.0%}"

        await self.world_memory.add(
            content=summary,
            source_type="relationship",
            source_id=rel.pair_id,
            importance=0.6,
            tags=["romance", rel.status.value],
        )

    def _load(self) -> None:
        """Load relationships from disk."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        relationships_file = self.data_dir / "relationships.json"

        if relationships_file.exists():
            try:
                data = json.loads(relationships_file.read_text())
                for pid, rel_data in data.items():
                    self._relationships[pid] = RelationshipMemory.from_dict(rel_data)
                logger.info(f"Loaded {len(self._relationships)} relationships")
            except Exception as e:
                logger.warning(f"Failed to load relationships: {e}")

    def _save(self) -> None:
        """Save relationships to disk."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        relationships_file = self.data_dir / "relationships.json"

        data = {
            pid: rel.to_dict()
            for pid, rel in self._relationships.items()
        }

        relationships_file.write_text(json.dumps(data, indent=2, default=str))

    async def get_all_relationships_for(self, character: str) -> List[RelationshipMemory]:
        """Get all romantic relationships for a character."""
        char_lower = character.lower()
        return [
            rel for pid, rel in self._relationships.items()
            if char_lower in pid.split("_")
        ]

    async def get_relationship_status(self, a: str, b: str) -> RomanceStatus:
        """Get the current status of a relationship."""
        rel = await self.get_relationship(a, b)
        return rel.status if rel else RomanceStatus.STRANGER

    async def get_relationships_by_status(
        self, status: RomanceStatus
    ) -> List[RelationshipMemory]:
        """Get all relationships with a specific status."""
        return [rel for rel in self._relationships.values() if rel.status == status]

    async def get_dating_pairs(self) -> List[Tuple[str, str]]:
        """Get all dating couples."""
        pairs = []
        for rel in self._relationships.values():
            if rel.status == RomanceStatus.DATING:
                names = rel.pair_id.split("_")
                if len(names) == 2:
                    pairs.append((names[0], names[1]))
        return pairs
