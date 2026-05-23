"""Predefined probability profiles for various action types."""
from __future__ import annotations

from .models import (
    ProbabilityProfile,
    ProbabilityParameter,
    ParameterType,
)

# ─────────────────────────────────────────────────────────────────
# Combat Profile
# ─────────────────────────────────────────────────────────────────
COMBAT = ProbabilityProfile(
    name="combat",
    parameters={
        "combat_skill": ProbabilityParameter(
            name="combat_skill",
            base_value=0.5,
            weight=0.30,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_combat_skill",
        ),
        "health_factor": ProbabilityParameter(
            name="health_factor",
            base_value=1.0,
            weight=0.15,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_health",
        ),
        "weapon_proficiency": ProbabilityParameter(
            name="weapon_proficiency",
            base_value=0.0,
            weight=0.10,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_weapon_proficiency",
        ),
        "target_defense": ProbabilityParameter(
            name="target_defense",
            base_value=0.5,
            weight=0.20,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="target_defense",
        ),
        "terrain_modifier": ProbabilityParameter(
            name="terrain_modifier",
            base_value=0.0,
            weight=0.10,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="environment_terrain_mod",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="sum_weighted",
    difficulty_modifier=1.0,
    critical_success_threshold=0.90,
    critical_failure_threshold=0.10,
)

# ─────────────────────────────────────────────────────────────────
# Persuasion Profile
# ─────────────────────────────────────────────────────────────────
PERSUASION = ProbabilityProfile(
    name="persuasion",
    parameters={
        "charisma": ProbabilityParameter(
            name="charisma",
            base_value=0.5,
            weight=0.25,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_charisma",
        ),
        "relationship": ProbabilityParameter(
            name="relationship",
            base_value=0.3,
            weight=0.25,
            param_type=ParameterType.RELATIONSHIP,
            dynamic_source="relationship_strength",
        ),
        "argument_quality": ProbabilityParameter(
            name="argument_quality",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="extra_argument_quality",
        ),
        "target_mood": ProbabilityParameter(
            name="target_mood",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="target_mood_factor",
        ),
        "target_resistance": ProbabilityParameter(
            name="target_resistance",
            base_value=0.5,
            weight=0.10,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="target_resistance",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.10,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="logistic",
    difficulty_modifier=0.9,
    critical_success_threshold=0.85,
    critical_failure_threshold=0.15,
)

# ─────────────────────────────────────────────────────────────────
# Stealth Profile
# ─────────────────────────────────────────────────────────────────
STEALTH = ProbabilityProfile(
    name="stealth",
    parameters={
        "dexterity": ProbabilityParameter(
            name="dexterity",
            base_value=0.5,
            weight=0.30,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_dexterity",
        ),
        "light_level": ProbabilityParameter(
            name="light_level",
            base_value=0.5,
            weight=0.20,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="environment_light",
        ),
        "noise_level": ProbabilityParameter(
            name="noise_level",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="environment_noise",
        ),
        "actor_mood": ProbabilityParameter(
            name="actor_mood",
            base_value=0.5,
            weight=0.10,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_mood_factor",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.25,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="product",
    difficulty_modifier=1.0,
    critical_success_threshold=0.85,
    critical_failure_threshold=0.15,
)

# ─────────────────────────────────────────────────────────────────
# Romance Profile
# ─────────────────────────────────────────────────────────────────
ROMANCE = ProbabilityProfile(
    name="romance",
    parameters={
        "charisma": ProbabilityParameter(
            name="charisma",
            base_value=0.5,
            weight=0.25,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_charisma",
        ),
        "relationship": ProbabilityParameter(
            name="relationship",
            base_value=0.5,
            weight=0.35,
            param_type=ParameterType.RELATIONSHIP,
            dynamic_source="relationship_strength",
        ),
        "romantic_setting": ProbabilityParameter(
            name="romantic_setting",
            base_value=0.0,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="environment_modifier",
        ),
        "actor_mood": ProbabilityParameter(
            name="actor_mood",
            base_value=0.5,
            weight=0.10,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_mood_factor",
        ),
        "target_mood": ProbabilityParameter(
            name="target_mood",
            base_value=0.5,
            weight=0.10,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="target_mood_factor",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.05,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="sum_weighted",
    difficulty_modifier=1.1,
    critical_success_threshold=0.90,
    critical_failure_threshold=0.10,
)

# ─────────────────────────────────────────────────────────────────
# Investigation Profile
# ─────────────────────────────────────────────────────────────────
INVESTIGATION = ProbabilityProfile(
    name="investigation",
    parameters={
        "intelligence": ProbabilityParameter(
            name="intelligence",
            base_value=0.5,
            weight=0.35,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_intelligence",
        ),
        "perception": ProbabilityParameter(
            name="perception",
            base_value=0.5,
            weight=0.25,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_wisdom",
        ),
        "environment_light": ProbabilityParameter(
            name="environment_light",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="environment_light",
        ),
        "time_pressure": ProbabilityParameter(
            name="time_pressure",
            base_value=0.5,
            weight=0.10,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="extra_time_pressure",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="sum_weighted",
    difficulty_modifier=1.0,
    critical_success_threshold=0.85,
    critical_failure_threshold=0.15,
)

# ─────────────────────────────────────────────────────────────────
# Athletics Profile
# ─────────────────────────────────────────────────────────────────
ATHLETICS = ProbabilityProfile(
    name="athletics",
    parameters={
        "strength": ProbabilityParameter(
            name="strength",
            base_value=0.5,
            weight=0.35,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_strength",
        ),
        "health": ProbabilityParameter(
            name="health",
            base_value=0.5,
            weight=0.20,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_health",
        ),
        "terrain": ProbabilityParameter(
            name="terrain",
            base_value=0.0,
            weight=0.20,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="environment_terrain_mod",
        ),
        "actor_mood": ProbabilityParameter(
            name="actor_mood",
            base_value=0.5,
            weight=0.10,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_mood_factor",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="sum_weighted",
    difficulty_modifier=1.0,
    critical_success_threshold=0.85,
    critical_failure_threshold=0.15,
)

# ─────────────────────────────────────────────────────────────────
# Deception Profile
# ─────────────────────────────────────────────────────────────────
DECEPTION = ProbabilityProfile(
    name="deception",
    parameters={
        "charisma": ProbabilityParameter(
            name="charisma",
            base_value=0.5,
            weight=0.30,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_charisma",
        ),
        "target_wisdom": ProbabilityParameter(
            name="target_wisdom",
            base_value=0.5,
            weight=0.20,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="target_resistance",
        ),
        "relationship": ProbabilityParameter(
            name="relationship",
            base_value=0.3,
            weight=0.15,
            param_type=ParameterType.RELATIONSHIP,
            dynamic_source="relationship_strength",
        ),
        "lie_quality": ProbabilityParameter(
            name="lie_quality",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="extra_lie_quality",
        ),
        "actor_mood": ProbabilityParameter(
            name="actor_mood",
            base_value=0.5,
            weight=0.05,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_mood_factor",
        ),
        "target_mood": ProbabilityParameter(
            name="target_mood",
            base_value=0.5,
            weight=0.10,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="target_mood_factor",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.05,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="logistic",
    difficulty_modifier=1.2,
    critical_success_threshold=0.85,
    critical_failure_threshold=0.15,
)

# ─────────────────────────────────────────────────────────────────
# Intimidation Profile
# ─────────────────────────────────────────────────────────────────
INTIMIDATION = ProbabilityProfile(
    name="intimidation",
    parameters={
        "strength": ProbabilityParameter(
            name="strength",
            base_value=0.5,
            weight=0.25,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_strength",
        ),
        "charisma": ProbabilityParameter(
            name="charisma",
            base_value=0.5,
            weight=0.20,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_charisma",
        ),
        "target_wisdom": ProbabilityParameter(
            name="target_wisdom",
            base_value=0.5,
            weight=0.20,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="target_resistance",
        ),
        "actor_reputation": ProbabilityParameter(
            name="actor_reputation",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="extra_reputation",
        ),
        "target_mood": ProbabilityParameter(
            name="target_mood",
            base_value=0.5,
            weight=0.10,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="target_mood_factor",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.10,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="sum_weighted",
    difficulty_modifier=1.1,
    critical_success_threshold=0.85,
    critical_failure_threshold=0.15,
)

# ─────────────────────────────────────────────────────────────────
# Generic/Simple Profile for custom actions
# ─────────────────────────────────────────────────────────────────
GENERIC = ProbabilityProfile(
    name="generic",
    parameters={
        "skill": ProbabilityParameter(
            name="skill",
            base_value=0.5,
            weight=0.60,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="extra.skill",
        ),
        "difficulty": ProbabilityParameter(
            name="difficulty",
            base_value=0.5,
            weight=0.20,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="extra.difficulty",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.20,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="sum_weighted",
    difficulty_modifier=1.0,
    critical_success_threshold=0.90,
    critical_failure_threshold=0.10,
)

# ─────────────────────────────────────────────────────────────────
# Birth Race Profile
# ─────────────────────────────────────────────────────────────────
BIRTH_RACE = ProbabilityProfile(
    name="birth_race",
    parameters={
        "world_rarity": ProbabilityParameter(
            name="world_rarity",
            base_value=0.5,
            weight=0.40,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="race_rarity",
        ),
        "user_hint": ProbabilityParameter(
            name="user_hint",
            base_value=0.0,
            weight=0.30,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="hint_weight",
        ),
        "demographic_weight": ProbabilityParameter(
            name="demographic_weight",
            base_value=0.3,
            weight=0.20,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="race_demographic",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.10,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="sum_weighted",
    difficulty_modifier=1.0,
    critical_success_threshold=0.85,
    critical_failure_threshold=0.15,
)

# ─────────────────────────────────────────────────────────────────
# Birth Social Class Profile
# ─────────────────────────────────────────────────────────────────
BIRTH_SOCIAL_CLASS = ProbabilityProfile(
    name="birth_social_class",
    parameters={
        "demographic_weight": ProbabilityParameter(
            name="demographic_weight",
            base_value=0.3,
            weight=0.35,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="class_demographic",
        ),
        "parental_influence": ProbabilityParameter(
            name="parental_influence",
            base_value=0.5,
            weight=0.25,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="parent_class",
        ),
        "user_hint": ProbabilityParameter(
            name="user_hint",
            base_value=0.0,
            weight=0.25,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="hint_weight",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="logistic",
    difficulty_modifier=0.9,
    critical_success_threshold=0.80,
    critical_failure_threshold=0.20,
)

# ─────────────────────────────────────────────────────────────────
# Birth Magic Affinity Profile
# ─────────────────────────────────────────────────────────────────
BIRTH_MAGIC_AFFINITY = ProbabilityProfile(
    name="birth_magic_affinity",
    parameters={
        "world_magic_density": ProbabilityParameter(
            name="world_magic_density",
            base_value=0.5,
            weight=0.30,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="magic_density",
        ),
        "bloodline_magic": ProbabilityParameter(
            name="bloodline_magic",
            base_value=0.3,
            weight=0.35,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="parent_magic_affinity",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.35,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="sum_weighted",
    difficulty_modifier=1.0,
    critical_success_threshold=0.85,
    critical_failure_threshold=0.15,
)

# ─────────────────────────────────────────────────────────────────
# Birth Talent Profile
# ─────────────────────────────────────────────────────────────────
BIRTH_TALENT = ProbabilityProfile(
    name="birth_talent",
    parameters={
        "base_chance": ProbabilityParameter(
            name="base_chance",
            base_value=0.3,
            weight=0.40,
            param_type=ParameterType.EXTERNAL,
        ),
        "social_class_bonus": ProbabilityParameter(
            name="social_class_bonus",
            base_value=0.0,
            weight=0.30,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="class_education_bonus",
        ),
        "race_bonus": ProbabilityParameter(
            name="race_bonus",
            base_value=0.0,
            weight=0.20,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="race_talent_bonus",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.10,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="logistic",
    difficulty_modifier=1.0,
    critical_success_threshold=0.90,
    critical_failure_threshold=0.10,
)

# ─────────────────────────────────────────────────────────────────
# Profile Registry
# ─────────────────────────────────────────────────────────────────
PROFILES = {
    "combat": COMBAT,
    "persuasion": PERSUASION,
    "persuade": PERSUASION,
    "stealth": STEALTH,
    "sneak": STEALTH,
    "romance": ROMANCE,
    "investigation": INVESTIGATION,
    "investigate": INVESTIGATION,
    "search": INVESTIGATION,
    "athletics": ATHLETICS,
    "climb": ATHLETICS,
    "swim": ATHLETICS,
    "deception": DECEPTION,
    "lie": DECEPTION,
    "bluff": DECEPTION,
    "intimidation": INTIMIDATION,
    "intimidate": INTIMIDATION,
    "generic": GENERIC,
    "default": GENERIC,
    # Birth profiles
    "birth_race": BIRTH_RACE,
    "birth_social_class": BIRTH_SOCIAL_CLASS,
    "birth_magic_affinity": BIRTH_MAGIC_AFFINITY,
    "birth_talent": BIRTH_TALENT,
}


def get_profile(name: str) -> ProbabilityProfile:
    """
    Get a probability profile by name.

    Args:
        name: Profile name (case-insensitive)

    Returns:
        ProbabilityProfile instance, or GENERIC if not found
    """
    return PROFILES.get(name.lower(), GENERIC)


def list_profiles() -> list[str]:
    """Get list of available profile names."""
    return sorted(set(PFILES.keys()))


def register_profile(profile: ProbabilityProfile):
    """
    Register a custom probability profile.

    Args:
        profile: The profile to register
    """
    PROFILES[profile.name.lower()] = profile
