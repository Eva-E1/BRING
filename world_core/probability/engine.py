"""Probability Engine - Core calculations for the probability system."""
from __future__ import annotations

import json
import math
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from .models import (
    ProbabilityProfile,
    ProbabilityModifier,
    ProbabilityParameter,
    ProbabilityResult,
    ModifierType,
    OutcomeQuality,
    ParameterType,
    StackingRule,
)
from .expression import safe_eval


class ProbabilityEngine:
    """
    Core probability calculation engine.

    Handles modifier lifecycle, computes parameter values, applies formulas,
    and determines outcome quality.
    """

    def __init__(self, global_luck: float = 0.5):
        # entity_uid -> list of modifiers
        self.modifiers: Dict[str, List[ProbabilityModifier]] = {}
        self.global_luck = global_luck
        self._context_resolver = None
        self._npc_mgr = None
        self._world_memory = None

    def set_context_resolver(self, resolver):
        """Set the context resolver for dynamic parameter resolution."""
        self._context_resolver = resolver

    def set_npc_manager(self, npc_mgr):
        """Set the NPC manager for skill progression."""
        self._npc_mgr = npc_mgr

    def set_world_memory(self, world_memory):
        """Set world memory for logging outcomes."""
        self._world_memory = world_memory

    def set_world_clock(self, world_clock):
        """Set world clock for global luck tracking."""
        self._world_clock = world_clock

    # ─────────────────────────────────────────────────────────────────
    # Modifier Management
    # ─────────────────────────────────────────────────────────────────

    def apply_modifier(self, entity_uid: str, modifier: ProbabilityModifier):
        """Apply a modifier to an entity."""
        if modifier.duration_seconds:
            modifier.expires_at = datetime.now().timestamp() + modifier.duration_seconds
        self.modifiers.setdefault(entity_uid, []).append(modifier)

    def remove_modifier(self, entity_uid: str, parameter_name: str, source: str = None) -> bool:
        """Remove a specific modifier. Returns True if found and removed."""
        if entity_uid not in self.modifiers:
            return False

        original_count = len(self.modifiers[entity_uid])
        if source:
            self.modifiers[entity_uid] = [
                m for m in self.modifiers[entity_uid]
                if not (m.parameter_name == parameter_name and m.source == source)
            ]
        else:
            self.modifiers[entity_uid] = [
                m for m in self.modifiers[entity_uid]
                if m.parameter_name != parameter_name
            ]
        return len(self.modifiers[entity_uid]) < original_count

    def remove_expired_modifiers(self, entity_uid: str, current_time: Optional[float] = None):
        """Remove all expired modifiers for an entity."""
        if current_time is None:
            current_time = datetime.now().timestamp()

        if entity_uid not in self.modifiers:
            return

        self.modifiers[entity_uid] = [
            m for m in self.modifiers[entity_uid]
            if not m.is_expired(current_time)
        ]

    def get_active_modifiers(
        self,
        entity_uid: str,
        param_name: str
    ) -> List[ProbabilityModifier]:
        """Get active modifiers for a specific parameter, respecting stacking rules."""
        mods = self.modifiers.get(entity_uid, [])
        relevant = [m for m in mods if m.parameter_name == param_name and not m.is_expired()]

        if not relevant:
            return []

        # Group by stacking rule
        by_rule: Dict[StackingRule, List[ProbabilityModifier]] = {}
        for m in relevant:
            by_rule.setdefault(m.stacking_rule, []).append(m)

        result = []
        for rule, group in by_rule.items():
            if rule == StackingRule.STACK:
                # All modifiers stack additively
                result.extend(group)
            elif rule == StackingRule.TAKE_HIGHEST:
                if group:
                    result.append(max(group, key=lambda x: x.value))
            elif rule == StackingRule.TAKE_LOWEST:
                if group:
                    result.append(min(group, key=lambda x: x.value))
            elif rule == StackingRule.OVERRIDE:
                if group:
                    # Last applied wins (sort by expiry to prefer longer-lasting)
                    result.append(sorted(group, key=lambda x: x.expires_at or float('inf'))[-1])

        return result

    def get_all_modifiers(self, entity_uid: str) -> List[ProbabilityModifier]:
        """Get all active modifiers for an entity."""
        if entity_uid not in self.modifiers:
            return []
        current_time = datetime.now().timestamp()
        return [m for m in self.modifiers[entity_uid] if not m.is_expired(current_time)]

    def clear_all_modifiers(self, entity_uid: str):
        """Clear all modifiers for an entity."""
        self.modifiers[entity_uid] = []

    # ─────────────────────────────────────────────────────────────────
    # Parameter Value Computation
    # ─────────────────────────────────────────────────────────────────

    def compute_parameter_value(
        self,
        param: ProbabilityParameter,
        context: Dict[str, Any],
        entity_uid: str,
    ) -> float:
        """Compute the final value of a parameter with modifiers applied."""
        # Resolve base value based on parameter type
        if param.param_type == ParameterType.DYNAMIC and param.dynamic_source:
            try:
                val = safe_eval(param.dynamic_source, context)
            except (ValueError, SyntaxError):
                val = param.base_value
        elif param.param_type == ParameterType.RELATIONSHIP:
            val = context.get("relationship_strength", 0.5)
        elif param.param_type == ParameterType.EXTERNAL:
            # Try to get from context using the dynamic_source as key
            if param.dynamic_source:
                val = context.get(param.dynamic_source, param.base_value)
            else:
                val = param.base_value
        else:  # STATIC
            val = param.base_value

        # Apply modifiers
        active = self.get_active_modifiers(entity_uid, param.name)

        add_mods = []
        mul_mods = []
        replace_val = None

        for mod in active:
            if mod.modifier_type == ModifierType.ADD:
                add_mods.append(mod.value)
            elif mod.modifier_type == ModifierType.MULTIPLY:
                mul_mods.append(mod.value)
            elif mod.modifier_type == ModifierType.REPLACE:
                if replace_val is None or mod.stacking_rule == StackingRule.OVERRIDE:
                    replace_val = mod.value

        # Apply in order: replace -> multiply -> add
        if replace_val is not None:
            val = replace_val

        for m in mul_mods:
            val *= m

        if add_mods:
            val += sum(add_mods)

        # Clamp to min/max
        return max(param.min_value, min(param.max_value, val))

    # ─────────────────────────────────────────────────────────────────
    # Main Probability Computation
    # ─────────────────────────────────────────────────────────────────

    def compute(
        self,
        profile: ProbabilityProfile,
        context: Dict[str, Any],
        entity_uid: Optional[str] = None,
    ) -> float:
        """
        Compute the probability of success for a given profile and context.

        Args:
            profile: The probability profile to use
            context: Context dictionary with dynamic values
            entity_uid: The entity performing the action (for modifier lookup)

        Returns:
            Probability value between 0.0 and 1.0
        """
        if not profile.parameters:
            return 0.5

        raw_values: Dict[str, float] = {}
        total_weight = 0.0

        # Compute each parameter value
        for pname, param in profile.parameters.items():
            val = self.compute_parameter_value(param, context, entity_uid or "")
            weighted = val * param.weight
            raw_values[pname] = weighted
            total_weight += param.weight

        # Apply formula
        if profile.formula == "sum_weighted":
            if total_weight > 0:
                prob = sum(raw_values.values()) / total_weight
            else:
                prob = 0.5
        elif profile.formula == "product":
            # Geometric mean
            valid_vals = [v for v in raw_values.values() if v > 0]
            if valid_vals:
                prod = math.prod(valid_vals)
                prob = prod ** (1 / max(1, len(valid_vals)))
            else:
                prob = 0.0
        elif profile.formula == "logistic":
            # Sigmoid function
            avg = sum(raw_values.values()) / max(1, len(raw_values))
            k = 4.0  # Steepness
            prob = 1 / (1 + math.exp(-k * (avg - 0.5)))
        elif profile.formula.startswith("expression:"):
            # Custom expression
            expr = profile.formula.split(":", 1)[1]
            prob = safe_eval(expr, raw_values)
        else:
            # Default: weighted average
            prob = sum(raw_values.values()) / total_weight if total_weight > 0 else 0.5

        # Apply difficulty modifier
        prob *= profile.difficulty_modifier

        # Apply global luck (shifts probability toward 0.5)
        prob = prob * (0.5 + self.global_luck)

        # Final clamp
        return max(0.0, min(1.0, prob))

    def roll(
        self,
        profile: ProbabilityProfile,
        context: Dict[str, Any],
        entity_uid: Optional[str] = None,
        explicit_roll: Optional[float] = None,
    ) -> ProbabilityResult:
        """
        Compute probability, roll, and determine outcome.

        Args:
            profile: Probability profile to use
            context: Context dictionary
            entity_uid: Entity performing the action
            explicit_roll: If provided, use this value instead of random roll

        Returns:
            ProbabilityResult with all outcome details
        """
        # Compute probability
        probability = self.compute(profile, context, entity_uid)

        # Perform roll with global luck adjustment
        if explicit_roll is not None:
            roll = explicit_roll
        else:
            roll = random.random()
            # Apply global luck from world clock
            if hasattr(self, '_world_clock') and self._world_clock:
                global_luck = self._world_clock.get_global_luck()
                # Shift roll towards 1.0 (success) for good luck, towards 0.0 for bad luck
                roll = max(0.0, min(1.0, roll + (global_luck - 0.5) * 0.2))

        # Determine success/failure
        success = roll < probability

        # Determine quality from margin bands
        quality = self._determine_quality(roll, probability, profile)

        # Build result
        result = ProbabilityResult(
            probability=probability,
            roll=roll,
            success=success,
            quality=quality,
            details={
                "probability": probability,
                "roll": roll,
                "margin": probability - roll if success else roll - probability,
            },
        )

        return result

    def _determine_quality(
        self,
        roll: float,
        probability: float,
        profile: ProbabilityProfile,
    ) -> OutcomeQuality:
        """Determine outcome quality based on roll and probability."""

        # Calculate margin as proportion of probability (0 to 1)
        # This tells us how "decisive" the outcome was
        if roll < probability:
            # Success - margin is how far below threshold we rolled
            margin = probability - roll
            max_margin = probability
        else:
            # Failure - margin is how far above threshold we rolled
            margin = roll - probability
            max_margin = 1.0 - probability

        # Normalize margin to 0-1 scale
        if max_margin > 0:
            normalized_margin = margin / max_margin
        else:
            normalized_margin = 0.0

        # Determine quality based on success/failure and margin
        if roll < probability:
            # SUCCESS cases
            if normalized_margin < 0.1:
                # Barely succeeded (within 10% of threshold)
                return OutcomeQuality.MARGINAL_SUCCESS
            elif normalized_margin > 0.8 and roll > profile.critical_success_threshold:
                # Decisive success with extreme roll
                return OutcomeQuality.CRITICAL_SUCCESS
            else:
                return OutcomeQuality.SUCCESS
        else:
            # FAILURE cases
            if normalized_margin < 0.1:
                # Barely failed (within 10% of threshold)
                return OutcomeQuality.MARGINAL_SUCCESS  # Close call
            elif normalized_margin > 0.8 and roll < profile.critical_failure_threshold:
                # Decisive failure with extreme roll
                return OutcomeQuality.CRITICAL_FAILURE
            else:
                return OutcomeQuality.FAILURE

    def get_success_chance(
        self,
        profile: ProbabilityProfile,
        context: Dict[str, Any],
        entity_uid: Optional[str] = None,
    ) -> float:
        """Get just the success probability without rolling."""
        return self.compute(profile, context, entity_uid)

    # ─────────────────────────────────────────────────────────────────
    # Utility Methods
    # ─────────────────────────────────────────────────────────────────

    def set_global_luck(self, luck: float):
        """Set global luck modifier (0.0 to 1.0, 0.5 is neutral)."""
        self.global_luck = max(0.0, min(1.0, luck))

    def get_modifier_summary(self, entity_uid: str) -> Dict[str, Any]:
        """Get a summary of all modifiers for an entity."""
        mods = self.get_all_modifiers(entity_uid)

        by_param: Dict[str, List[Dict]] = {}
        for m in mods:
            by_param.setdefault(m.parameter_name, []).append({
                "value": m.value,
                "type": m.modifier_type.value,
                "source": m.source,
                "expires_at": m.expires_at,
                "description": m.description,
            })

        return {
            "total_modifiers": len(mods),
            "by_parameter": by_param,
            "global_luck": self.global_luck,
        }

    def serialize_modifiers(self) -> Dict[str, List[dict]]:
        """Serialize all modifiers for persistence."""
        return {
            uid: [m.to_dict() for m in mods]
            for uid, mods in self.modifiers.items()
        }

    def deserialize_modifiers(self, data: Dict[str, List[dict]]):
        """Load modifiers from serialized data."""
        self.modifiers = {}
        for uid, mod_list in data.items():
            self.modifiers[uid] = [
                ProbabilityModifier.from_dict(m) for m in mod_list
            ]
        # Clean up expired
        current_time = datetime.now().timestamp()
        for uid in self.modifiers:
            self.remove_expired_modifiers(uid, current_time)

    # ─────────────────────────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────────────────────────

    def save_modifiers(self, path: Path) -> None:
        """Save all modifiers to a JSON file."""
        data = self.serialize_modifiers()
        data["global_luck"] = self.global_luck
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load_modifiers(self, path: Path) -> None:
        """Load modifiers from a JSON file."""
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            # Load modifiers
            if "global_luck" in data:
                self.global_luck = data["global_luck"]
            mod_data = {k: v for k, v in data.items() if k != "global_luck"}
            self.deserialize_modifiers(mod_data)

    # ─────────────────────────────────────────────────────────────────
    # Skill Progression
    # ─────────────────────────────────────────────────────────────────

    def improve_skill(self, entity_uid: str, skill_name: str, delta: float = 0.01) -> bool:
        """Increase skill with diminishing returns. Returns True if improved."""
        if not self._npc_mgr:
            return False

        # Extract character name from UID (e.g., "Character:Kaelen" -> "Kaelen")
        if ":" in entity_uid:
            name = entity_uid.split(":", 1)[1]
        else:
            name = entity_uid

        profile = self._npc_mgr.get(name)
        if not profile:
            return False

        # Initialize skills dict if not exists
        if not hasattr(profile, 'skills') or not profile.skills:
            profile.skills = {
                "strength": 0.5, "dexterity": 0.5, "charisma": 0.5,
                "intelligence": 0.5, "wisdom": 0.5, "luck": 0.5,
                "combat_skill": 0.5, "persuasion": 0.5, "stealth": 0.5,
            }

        current = profile.skills.get(skill_name, 0.5)
        # Diminishing returns: increment scales down as skill approaches 1.0
        increment = delta * (1.0 - current)
        new_val = min(1.0, current + increment)
        profile.skills[skill_name] = new_val

        # Save changes
        self._npc_mgr._save()
        return True

    def get_skill(self, entity_uid: str, skill_name: str) -> float:
        """Get current skill value for an entity."""
        if not self._npc_mgr:
            return 0.5

        if ":" in entity_uid:
            name = entity_uid.split(":", 1)[1]
        else:
            name = entity_uid

        profile = self._npc_mgr.get(name)
        if not profile or not hasattr(profile, 'skills') or not profile.skills:
            return 0.5

        return profile.skills.get(skill_name, 0.5)

    # ─────────────────────────────────────────────────────────────────
    # World Memory Logging
    # ─────────────────────────────────────────────────────────────────

    async def log_outcome(self, profile: ProbabilityProfile, result: ProbabilityResult, context: Dict[str, Any]) -> None:
        """Log probability outcome to world memory."""
        if not self._world_memory:
            return

        actor = context.get("actor", "unknown")
        quality = result.quality.value
        importance = 0.6 if result.quality.is_critical() else 0.3

        await self._world_memory.add_event(
            event_description=f"{actor} {profile.name}: {quality} "
                              f"(prob={result.probability:.2f}, roll={result.roll:.2f})",
            group="probability",
            importance=importance,
            metadata={
                "profile": profile.name,
                "quality": quality,
                "success": result.success,
            }
        )
