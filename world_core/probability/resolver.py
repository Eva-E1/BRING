"""Context Resolver - Builds context dictionaries from world state."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from .models import ParameterType

logger = logging.getLogger(__name__)

# Type hints to avoid circular imports
if TYPE_CHECKING:
    from world_builder.graph_manager import GraphManager
    from world_narrative.memory_optimized import OptimizedMemoryStore
    from world_core.memory import WorldMemory


class ProbabilityContextResolver:
    """
    Resolves context values from the world state for probability calculations.

    Gathers data from:
    - Entity profiles (L1, L2, L3)
    - NPC memory store (health, mood, goals)
    - Graph relationships
    - World memory
    - Location/environment
    - Faction reputation
    - World rules
    """

    def __init__(
        self,
        gm: "GraphManager",
        npc_mgr: "OptimizedMemoryStore",
        world_memory: "WorldMemory" = None,
        world_frame: Dict[str, Any] = None,
    ):
        self.gm = gm
        self.npc_mgr = npc_mgr
        self.world_memory = world_memory
        self.world_frame = world_frame or {}

        # Mood to factor mapping
        self._mood_factors = {
            "joy": 0.9, "happiness": 0.9, "excited": 0.85, "content": 0.7,
            "neutral": 0.5, "calm": 0.5, "worried": 0.4, "sad": 0.3,
            "fear": 0.2, "anger": 0.2, "rage": 0.1, "depressed": 0.1,
        }

        # Action type to skill mapping
        self._skill_map = {
            "combat": "strength", "attack": "strength", "fight": "strength",
            "persuasion": "charisma", "persuade": "charisma", "diplomacy": "charisma",
            "deception": "charisma", "stealth": "dexterity", "sneak": "dexterity",
            "lockpick": "dexterity", "investigation": "intelligence",
            "investigate": "intelligence", "search": "intelligence",
            "arcana": "intelligence", "religion": "intelligence",
            "athletics": "strength", "climb": "strength", "swim": "strength",
            "acrobats": "dexterity", "perception": "wisdom", "perceive": "wisdom",
            "survival": "wisdom", "medicine": "wisdom", "insight": "wisdom",
            "performance": "charisma", "intimidation": "charisma",
            "nature": "wisdom", "animal_handling": "wisdom",
        }

    async def build_context(
        self,
        actor: str,
        target: Optional[str] = None,
        action_type: str = "generic",
        location: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a complete context dictionary for probability calculations."""
        context = {
            "actor": actor,
            "target": target,
            "action_type": action_type,
            "location": location,
        }

        # Actor stats from NPC memory store
        await self._add_actor_stats(context, actor)

        # Actor skills from entity profile
        await self._add_actor_skills(context, actor, action_type)

        # Target stats if present
        if target:
            await self._add_target_stats(context, target, action_type)

        # Relationship strength
        if actor and target:
            context["relationship_strength"] = await self._get_relationship_strength(actor, target)

        # Faction reputation
        if actor:
            context["faction_reputation"] = await self._get_faction_reputation(actor)

        # Environment modifiers from location
        if location:
            await self._add_environment_modifiers(context, location)

        # World rules (e.g., magic laws)
        if location:
            await self._apply_world_rules(context, location, action_type)

        # World memory context
        if self.world_memory and actor:
            await self._add_world_memory_context(context, actor, action_type)

        # Extra user-provided values
        if extra:
            for key, value in extra.items():
                context[f"extra_{key}"] = value

        # Set defaults for any missing required values
        self._fill_defaults(context)

        return context

    async def _add_actor_stats(self, context: Dict[str, Any], actor: str):
        """Add actor health, mood, and other stats from NPC memory store."""
        try:
            actor_state = self.npc_mgr.get(actor)
            if actor_state:
                context["actor_health"] = actor_state.health / 100.0
                mood = actor_state.mood.lower() if actor_state.mood else "neutral"
                context["actor_mood_factor"] = self._mood_factors.get(mood, 0.5)
                context["actor_has_goals"] = float(len(actor_state.goals) > 0)
                context["actor_resources"] = min(1.0, len(actor_state.inventory) / 10.0)
            else:
                context["actor_health"] = 0.5
                context["actor_mood_factor"] = 0.5
                context["actor_has_goals"] = 0.0
                context["actor_resources"] = 0.0
        except Exception as e:
            logger.warning(f"Failed to get actor stats for {actor}: {e}")
            context["actor_health"] = 0.5
            context["actor_mood_factor"] = 0.5

    async def _add_actor_skills(self, context: Dict[str, Any], actor: str, action_type: str):
        """Add actor skill levels from entity profile L2."""
        try:
            skill = self._skill_map.get(action_type.lower(), "strength")
            actor_node = self.gm.store.get_by_name_and_type(actor, "Character")

            if actor_node and actor_node.profile and actor_node.profile.l2:
                l2 = actor_node.profile.l2
                abilities = l2.get("abilities", [])
                stats = l2.get("stats", {})
                skills = l2.get("skills", {})

                skill_value = stats.get(skill, skills.get(skill, 0.5))
                for ability in abilities:
                    if isinstance(ability, dict) and skill in ability.get("name", "").lower():
                        skill_value = ability.get("level", ability.get("proficiency", 0.5))
                        break
                    elif isinstance(ability, str) and skill in ability.lower():
                        skill_value = 0.6
                        break

                context[f"actor_{skill}"] = skill_value

                # Combat-specific
                if action_type.lower() in ("combat", "attack", "fight"):
                    context["actor_combat_skill"] = skill_value
                    weapons = l2.get("weapons", [])
                    context["actor_weapon_proficiency"] = min(1.0, len(weapons) / 5.0)

                # Persuasion-specific
                if action_type.lower() in ("persuasion", "persuade", "diplomacy"):
                    context["actor_charisma"] = skill_value

                # Stealth-specific
                if action_type.lower() in ("stealth", "sneak"):
                    context["actor_dexterity"] = skill_value
            else:
                context[f"actor_{skill}"] = 0.5
                if action_type.lower() in ("combat", "attack", "fight"):
                    context["actor_combat_skill"] = 0.5
                if action_type.lower() in ("persuasion", "persuade"):
                    context["actor_charisma"] = 0.5
                if action_type.lower() in ("stealth", "sneak"):
                    context["actor_dexterity"] = 0.5
        except Exception as e:
            logger.warning(f"Failed to get actor skills for {actor}: {e}")
            context["actor_strength"] = 0.5
            context["actor_dexterity"] = 0.5
            context["actor_charisma"] = 0.5
            context["actor_intelligence"] = 0.5
            context["actor_wisdom"] = 0.5

    async def _add_target_stats(self, context: Dict[str, Any], target: str, action_type: str):
        """Add target's defensive capabilities."""
        try:
            target_node = self.gm.store.get_by_name_and_type(target, "Character")
            if target_node and target_node.profile and target_node.profile.l2:
                l2 = target_node.profile.l2
                if action_type.lower() in ("combat", "attack", "fight"):
                    context["target_defense"] = l2.get("armor_class", 0.5)
                    context["target_health"] = l2.get("hit_points", 50) / 100.0
                if action_type.lower() in ("persuasion", "persuade", "deception"):
                    context["target_resistance"] = l2.get("wisdom", l2.get("willpower", 0.5))

                target_state = self.npc_mgr.get(target)
                if target_state:
                    mood = target_state.mood.lower() if target_state.mood else "neutral"
                    context["target_mood_factor"] = self._mood_factors.get(mood, 0.5)
                else:
                    context["target_mood_factor"] = 0.5
            else:
                if action_type.lower() in ("combat", "attack", "fight"):
                    context["target_defense"] = 0.5
                    context["target_health"] = 0.5
                context["target_mood_factor"] = 0.5
                context["target_resistance"] = 0.5
        except Exception as e:
            logger.warning(f"Failed to get target stats for {target}: {e}")
            context["target_defense"] = 0.5
            context["target_health"] = 0.5
            context["target_mood_factor"] = 0.5
            context["target_resistance"] = 0.5

    async def _get_relationship_strength(self, actor: str, target: str) -> float:
        """Get relationship strength between two entities from the graph."""
        try:
            uid_actor = self.gm._resolve_entity_uid(actor)
            uid_target = self.gm._resolve_entity_uid(target)
            if not uid_actor or not uid_target:
                return 0.5
            edges = self.gm.graph.get_edges_between(uid_actor, uid_target)
            for edge_type, attrs in edges:
                if edge_type in ("ally_of", "friend_of", "lover_of", "friend", "ally"):
                    return attrs.get("strength", 0.8)
                if edge_type in ("enemy_of", "rival_of", "enemy", "rival"):
                    return attrs.get("strength", 0.2)
                if "strength" in attrs:
                    return attrs["strength"]
            return 0.5
        except Exception as e:
            logger.warning(f"Failed to get relationship between {actor} and {target}: {e}")
            return 0.5

    async def _get_faction_reputation(self, actor: str) -> float:
        """Average reputation of factions the actor belongs to."""
        try:
            actor_node = self.gm.store.get_by_name_and_type(actor, "Character")
            if not actor_node:
                return 0.5

            # Get factions the actor belongs to
            faction_uids = []
            try:
                for neighbor, etype, _ in self.gm.graph.get_neighbors(actor_node.uid, direction='out'):
                    if etype == "member_of":
                        faction_uids.append(neighbor)
            except Exception:
                pass

            if not faction_uids:
                return 0.5

            # Calculate average reputation across all factions
            total = 0.0
            count = 0
            for fid in faction_uids:
                faction_node = self.gm.store.get(fid)
                if faction_node and faction_node.profile and faction_node.profile.l2:
                    rep = faction_node.profile.l2.get("reputation", 0.5)
                    total += rep
                    count += 1

            return total / count if count > 0 else 0.5
        except Exception as e:
            logger.warning(f"Failed to get faction reputation for {actor}: {e}")
            return 0.5

    async def _apply_world_rules(self, context: Dict[str, Any], location: str, action_type: str) -> None:
        """Apply world rules that affect probability at the given location."""
        try:
            loc_node = self.gm.store.get_by_name_and_type(location, "Location")
            if not loc_node or not loc_node.profile or not loc_node.profile.l2:
                return

            l2 = loc_node.profile.l2
            rules_at_loc = l2.get("active_rules", [])

            if not rules_at_loc:
                return

            # Get world rules from world frame
            world_rules = self.world_frame.get("world_rules", [])

            for rule_name in rules_at_loc:
                # Find matching rule
                rule = next((r for r in world_rules if r.get("name") == rule_name), None)
                if not rule:
                    continue

                rule_category = rule.get("category", "")
                action_category = rule.get("action_category", "")

                # Apply magic law penalty if casting spells
                if rule_category == "magic_law" and action_type.lower() == "cast_spell":
                    context["rule_penalty"] = context.get("rule_penalty", 0.0) - 0.3

                # Apply combat law if fighting
                if rule_category == "combat_law" and action_type.lower() in ("combat", "attack", "fight"):
                    context["rule_penalty"] = context.get("rule_penalty", 0.0) - 0.2

                # Apply social law if persuasion/deception
                if rule_category == "social_law" and action_type.lower() in ("persuasion", "persuade", "deception"):
                    context["rule_penalty"] = context.get("rule_penalty", 0.0) - 0.15

        except Exception as e:
            logger.warning(f"Failed to apply world rules at {location}: {e}")

    async def _add_environment_modifiers(self, context: Dict[str, Any], location: str):
        """Add environmental modifiers from location entity."""
        try:
            loc_node = self.gm.store.get_by_name_and_type(location, "Location")
            if loc_node and loc_node.profile and loc_node.profile.l2:
                l2 = loc_node.profile.l2
                context["environment_light"] = l2.get("light_level", l2.get("light", 0.5))
                context["environment_noise"] = l2.get("noise_level", l2.get("noise", 0.5))
                context["environment_modifier"] = l2.get("probability_modifier", 0.0)

                terrain = l2.get("terrain", "normal")
                terrain_mods = {"difficult": -0.2, "hazardous": -0.3, "favorable": 0.2, "normal": 0.0}
                context["environment_terrain_mod"] = terrain_mods.get(terrain, 0.0)
            else:
                context["environment_light"] = 0.5
                context["environment_noise"] = 0.5
                context["environment_modifier"] = 0.0
                context["environment_terrain_mod"] = 0.0
        except Exception as e:
            logger.warning(f"Failed to get environment for {location}: {e}")
            context["environment_light"] = 0.5
            context["environment_noise"] = 0.5
            context["environment_modifier"] = 0.0
            context["environment_terrain_mod"] = 0.0

    async def _add_world_memory_context(self, context: Dict[str, Any], actor: str, action_type: str):
        """Add relevant world memory context."""
        try:
            if not self.world_memory:
                return
            memories = await self.world_memory.retrieve(
                query=f"{actor} recent events", top_k=3, entity_filter={actor},
                min_importance=0.3,
            )
            context["actor_recent_memories"] = len(memories) if memories else 0
            recent_failures = [m for m in memories if "failure" in m.get("content", "").lower()] if memories else []
            context["actor_recent_failures"] = len(recent_failures) / max(1, len(memories)) if memories else 0.0
        except Exception as e:
            logger.debug(f"Failed to get world memory context: {e}")
            context["actor_recent_memories"] = 0
            context["actor_recent_failures"] = 0.0

    def _fill_defaults(self, context: Dict[str, Any]):
        """Fill in default values for any missing required parameters."""
        defaults = {
            "actor_health": 0.5, "actor_mood_factor": 0.5,
            "actor_strength": 0.5, "actor_dexterity": 0.5, "actor_charisma": 0.5,
            "actor_intelligence": 0.5, "actor_wisdom": 0.5, "actor_combat_skill": 0.5,
            "actor_weapon_proficiency": 0.5, "actor_has_goals": 0.0, "actor_resources": 0.0,
            "actor_luck": 0.5, "target_defense": 0.5, "target_health": 0.5,
            "target_resistance": 0.5, "target_mood_factor": 0.5, "relationship_strength": 0.5,
            "faction_reputation": 0.5, "rule_penalty": 0.0,
            "environment_light": 0.5, "environment_noise": 0.5, "environment_modifier": 0.0,
            "environment_terrain_mod": 0.0, "item_bonus": 0.0, "argument_quality": 0.5,
        }
        for key, default_value in defaults.items():
            if key not in context:
                context[key] = default_value
