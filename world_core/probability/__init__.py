"""Advanced probability system for world narrative engine.

Provides deterministic, contextual probability calculations with:
- Multiple parameter types (static, dynamic, relationship, external)
- Modifier system with duration, stacking rules
- Outcome quality bands (critical failure to critical success)
- Custom expression formulas
- Integration with RoleplayEngine and StoryEngine
"""

from .models import (
    ParameterType,
    ModifierType,
    StackingRule,
    OutcomeQuality,
    ProbabilityModifier,
    ProbabilityParameter,
    ProbabilityProfile,
)
from .engine import ProbabilityEngine
from .resolver import ProbabilityContextResolver
from .profiles import (
    COMBAT,
    PERSUASION,
    STEALTH,
    ROMANCE,
    INVESTIGATION,
    ATHLETICS,
    PROFILES,
    get_profile,
)
from .expression import safe_eval

__all__ = [
    # Enums
    "ParameterType",
    "ModifierType",
    "StackingRule",
    "OutcomeQuality",
    # Models
    "ProbabilityModifier",
    "ProbabilityParameter",
    "ProbabilityProfile",
    # Core
    "ProbabilityEngine",
    "ProbabilityContextResolver",
    # Profiles
    "COMBAT",
    "PERSUASION",
    "STEALTH",
    "ROMANCE",
    "INVESTIGATION",
    "ATHLETICS",
    "PROFILES",
    "get_profile",
    # Utilities
    "safe_eval",
]
