"""Romance probability profiles for the romantic relationships system."""
from __future__ import annotations

from world_core.probability.models import (
    ProbabilityProfile,
    ProbabilityParameter,
    ParameterType,
)

# ─────────────────────────────────────────────────────────────────
# Romance Attraction Profile
# ─────────────────────────────────────────────────────────────────
ROMANCE_ATTRACTION = ProbabilityProfile(
    name="romance_attraction",
    parameters={
        "charisma": ProbabilityParameter(
            name="charisma",
            base_value=0.5,
            weight=0.25,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_charisma",
        ),
        "compatibility": ProbabilityParameter(
            name="compatibility",
            base_value=0.5,
            weight=0.30,
            param_type=ParameterType.RELATIONSHIP,
            dynamic_source="relationship_compatibility",
        ),
        "mood": ProbabilityParameter(
            name="mood",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="target_mood_factor",
        ),
        "environment": ProbabilityParameter(
            name="environment",
            base_value=0.0,
            weight=0.10,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="environment_modifier",
        ),
        "past_affection": ProbabilityParameter(
            name="past_affection",
            base_value=0.3,
            weight=0.20,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="current_affection",
        ),
    },
    formula="logistic",
    difficulty_modifier=1.0,
    critical_success_threshold=0.85,
    critical_failure_threshold=0.15,
)

# ─────────────────────────────────────────────────────────────────
# Romance Confession Profile
# ─────────────────────────────────────────────────────────────────
ROMANCE_CONFESSION = ProbabilityProfile(
    name="romance_confession",
    parameters={
        "affection": ProbabilityParameter(
            name="affection",
            base_value=0.5,
            weight=0.35,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="current_affection",
        ),
        "compatibility": ProbabilityParameter(
            name="compatibility",
            base_value=0.5,
            weight=0.25,
            param_type=ParameterType.RELATIONSHIP,
            dynamic_source="compatibility",
        ),
        "charisma": ProbabilityParameter(
            name="charisma",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_charisma",
        ),
        "location_romance": ProbabilityParameter(
            name="location_romance",
            base_value=0.0,
            weight=0.10,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="environment_modifier",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="logistic",
    difficulty_modifier=1.2,  # harder than simple attraction
    critical_success_threshold=0.80,
    critical_failure_threshold=0.20,
)

# ─────────────────────────────────────────────────────────────────
# Romance Date Profile
# ─────────────────────────────────────────────────────────────────
ROMANCE_DATE = ProbabilityProfile(
    name="romance_date",
    parameters={
        "affection": ProbabilityParameter(
            name="affection",
            base_value=0.5,
            weight=0.30,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="current_affection",
        ),
        "charisma": ProbabilityParameter(
            name="charisma",
            base_value=0.5,
            weight=0.20,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_charisma",
        ),
        "compatibility": ProbabilityParameter(
            name="compatibility",
            base_value=0.5,
            weight=0.20,
            param_type=ParameterType.RELATIONSHIP,
            dynamic_source="compatibility",
        ),
        "location_romance": ProbabilityParameter(
            name="location_romance",
            base_value=0.0,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="environment_modifier",
        ),
        "timing": ProbabilityParameter(
            name="timing",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="time_of_day_modifier",
        ),
    },
    formula="logistic",
    difficulty_modifier=1.0,
    critical_success_threshold=0.85,
    critical_failure_threshold=0.15,
)

# ─────────────────────────────────────────────────────────────────
# Romance Proposal Profile
# ─────────────────────────────────────────────────────────────────
ROMANCE_PROPOSAL = ProbabilityProfile(
    name="romance_proposal",
    parameters={
        "affection": ProbabilityParameter(
            name="affection",
            base_value=0.7,
            weight=0.35,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="current_affection",
        ),
        "compatibility": ProbabilityParameter(
            name="compatibility",
            base_value=0.6,
            weight=0.25,
            param_type=ParameterType.RELATIONSHIP,
            dynamic_source="compatibility",
        ),
        "charisma": ProbabilityParameter(
            name="charisma",
            base_value=0.5,
            weight=0.10,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_charisma",
        ),
        "relationship_duration": ProbabilityParameter(
            name="relationship_duration",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="relationship_duration",
        ),
        "family_approval": ProbabilityParameter(
            name="family_approval",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="family_approval",
        ),
    },
    formula="logistic",
    difficulty_modifier=1.3,  # hardest romantic action
    critical_success_threshold=0.75,
    critical_failure_threshold=0.25,
)

# ─────────────────────────────────────────────────────────────────
# Romance Breakup Profile
# ─────────────────────────────────────────────────────────────────
ROMANCE_BREAKUP = ProbabilityProfile(
    name="romance_breakup",
    parameters={
        "affection": ProbabilityParameter(
            name="affection",
            base_value=0.5,
            weight=0.35,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="current_affection",
        ),
        "conflict_level": ProbabilityParameter(
            name="conflict_level",
            base_value=0.3,
            weight=0.25,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="conflict_level",
        ),
        "external_pressure": ProbabilityParameter(
            name="external_pressure",
            base_value=0.0,
            weight=0.20,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="external_pressure",
        ),
        "luck": ProbabilityParameter(
            name="luck",
            base_value=0.5,
            weight=0.20,
            param_type=ParameterType.EXTERNAL,
        ),
    },
    formula="sum_weighted",
    difficulty_modifier=0.8,  # easier to break than to stay together
    critical_success_threshold=0.25,
    critical_failure_threshold=0.75,
)

# ─────────────────────────────────────────────────────────────────
# Romance Kiss Profile
# ─────────────────────────────────────────────────────────────────
ROMANCE_KISS = ProbabilityProfile(
    name="romance_kiss",
    parameters={
        "affection": ProbabilityParameter(
            name="affection",
            base_value=0.6,
            weight=0.35,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="current_affection",
        ),
        "mood": ProbabilityParameter(
            name="mood",
            base_value=0.5,
            weight=0.20,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="target_mood_factor",
        ),
        "charisma": ProbabilityParameter(
            name="charisma",
            base_value=0.5,
            weight=0.15,
            param_type=ParameterType.DYNAMIC,
            dynamic_source="actor_charisma",
        ),
        "environment": ProbabilityParameter(
            name="environment",
            base_value=0.0,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="environment_modifier",
        ),
        "past_moments": ProbabilityParameter(
            name="past_moments",
            base_value=0.3,
            weight=0.15,
            param_type=ParameterType.EXTERNAL,
            dynamic_source="past_positive_interactions",
        ),
    },
    formula="logistic",
    difficulty_modifier=1.1,
    critical_success_threshold=0.85,
    critical_failure_threshold=0.15,
)

# ─────────────────────────────────────────────────────────────────
# Profile Registry
# ─────────────────────────────────────────────────────────────────
ROMANCE_PROFILES = {
    "romance_attraction": ROMANCE_ATTRACTION,
    "attraction": ROMANCE_ATTRACTION,
    "romance_confession": ROMANCE_CONFESSION,
    "confess": ROMANCE_CONFESSION,
    "confession": ROMANCE_CONFESSION,
    "romance_date": ROMANCE_DATE,
    "date": ROMANCE_DATE,
    "romance_proposal": ROMANCE_PROPOSAL,
    "proposal": ROMANCE_PROPOSAL,
    "propose": ROMANCE_PROPOSAL,
    "romance_breakup": ROMANCE_BREAKUP,
    "breakup": ROMANCE_BREAKUP,
    "romance_kiss": ROMANCE_KISS,
    "kiss": ROMANCE_KISS,
}


def get_romance_profile(name: str) -> ProbabilityProfile:
    """Get a romance profile by name (case-insensitive)."""
    return ROMANCE_PROFILES.get(name.lower())
