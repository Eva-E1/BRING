"""Data models for the probability system."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ParameterType(Enum):
    """Types of probability parameters."""
    STATIC = "static"          # Base value from character sheet
    DYNAMIC = "dynamic"        # Computed from entity state (health, mood)
    RELATIONSHIP = "relationship"  # Edge strength from graph
    EXTERNAL = "external"      # Environment, global luck


class ModifierType(Enum):
    """How a modifier affects a probability parameter."""
    ADD = "add"
    MULTIPLY = "multiply"
    REPLACE = "replace"


class StackingRule(Enum):
    """How multiple modifiers of the same type combine."""
    STACK = "stack"            # Add all modifiers together
    TAKE_HIGHEST = "highest"   # Use only the highest modifier
    TAKE_LOWEST = "lowest"     # Use only the lowest modifier
    OVERRIDE = "override"      # Last applied wins


class OutcomeQuality(Enum):
    """Quality bands for action outcomes."""
    CRITICAL_FAILURE = "critical_failure"
    FAILURE = "failure"
    MARGINAL_FAILURE = "marginal_failure"
    MARGINAL_SUCCESS = "marginal_success"
    SUCCESS = "success"
    CRITICAL_SUCCESS = "critical_success"

    def is_success(self) -> bool:
        """Check if this quality represents a successful outcome."""
        return self in (OutcomeQuality.MARGINAL_SUCCESS, OutcomeQuality.SUCCESS, OutcomeQuality.CRITICAL_SUCCESS)

    def is_critical(self) -> bool:
        """Check if this is a critical outcome (either extreme)."""
        return self in (OutcomeQuality.CRITICAL_FAILURE, OutcomeQuality.CRITICAL_SUCCESS)


@dataclass
class ProbabilityModifier:
    """A modifier that affects probability calculations."""
    parameter_name: str
    value: float
    modifier_type: ModifierType
    duration_seconds: Optional[int] = None
    source: str = ""
    stacking_rule: StackingRule = StackingRule.STACK
    expires_at: Optional[float] = None   # Unix timestamp
    description: str = ""

    def is_expired(self, current_time: Optional[float] = None) -> bool:
        """Check if this modifier has expired."""
        if self.expires_at is None:
            return False
        if current_time is None:
            current_time = datetime.now().timestamp()
        return current_time >= self.expires_at

    def to_dict(self) -> dict:
        """Serialize to dictionary for persistence."""
        return {
            "parameter_name": self.parameter_name,
            "value": self.value,
            "modifier_type": self.modifier_type.value,
            "duration_seconds": self.duration_seconds,
            "source": self.source,
            "stacking_rule": self.stacking_rule.value,
            "expires_at": self.expires_at,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ProbabilityModifier:
        """Deserialize from dictionary."""
        return cls(
            parameter_name=d["parameter_name"],
            value=d["value"],
            modifier_type=ModifierType(d["modifier_type"]),
            duration_seconds=d.get("duration_seconds"),
            source=d.get("source", ""),
            stacking_rule=StackingRule(d.get("stacking_rule", "stack")),
            expires_at=d.get("expires_at"),
            description=d.get("description", ""),
        )


@dataclass
class ProbabilityParameter:
    """A single parameter in a probability profile."""
    name: str
    base_value: float = 0.5
    weight: float = 1.0
    param_type: ParameterType = ParameterType.STATIC
    dynamic_source: Optional[str] = None   # Expression to evaluate (e.g., "actor.health / 100")
    min_value: float = 0.0
    max_value: float = 1.0

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "base_value": self.base_value,
            "weight": self.weight,
            "param_type": self.param_type.value,
            "dynamic_source": self.dynamic_source,
            "min_value": self.min_value,
            "max_value": self.max_value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ProbabilityParameter:
        """Deserialize from dictionary."""
        return cls(
            name=d["name"],
            base_value=d.get("base_value", 0.5),
            weight=d.get("weight", 1.0),
            param_type=ParameterType(d.get("param_type", "static")),
            dynamic_source=d.get("dynamic_source"),
            min_value=d.get("min_value", 0.0),
            max_value=d.get("max_value", 1.0),
        )


@dataclass
class ProbabilityProfile:
    """A complete probability profile for an action type."""
    name: str
    parameters: Dict[str, ProbabilityParameter] = field(default_factory=dict)
    formula: str = "sum_weighted"   # "sum_weighted", "product", "logistic", "expression: ..."
    difficulty_modifier: float = 1.0
    critical_success_threshold: float = 0.95
    critical_failure_threshold: float = 0.05
    margin_bands: Dict[OutcomeQuality, float] = field(default_factory=lambda: {
        OutcomeQuality.CRITICAL_FAILURE: 0.05,
        OutcomeQuality.FAILURE: 0.30,
        OutcomeQuality.MARGINAL_SUCCESS: 0.60,
        OutcomeQuality.SUCCESS: 0.90,
        OutcomeQuality.CRITICAL_SUCCESS: 1.0,
    })

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "parameters": {k: v.to_dict() for k, v in self.parameters.items()},
            "formula": self.formula,
            "difficulty_modifier": self.difficulty_modifier,
            "critical_success_threshold": self.critical_success_threshold,
            "critical_failure_threshold": self.critical_failure_threshold,
            "margin_bands": {k.value: v for k, v in self.margin_bands.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> ProbabilityProfile:
        """Deserialize from dictionary."""
        margin_bands = {
            OutcomeQuality(k): v for k, v in d.get("margin_bands", {}).items()
        }
        parameters = {
            k: ProbabilityParameter.from_dict(v) for k, v in d.get("parameters", {}).items()
        }
        return cls(
            name=d["name"],
            parameters=parameters,
            formula=d.get("formula", "sum_weighted"),
            difficulty_modifier=d.get("difficulty_modifier", 1.0),
            critical_success_threshold=d.get("critical_success_threshold", 0.95),
            critical_failure_threshold=d.get("critical_failure_threshold", 0.05),
            margin_bands=margin_bands,
        )


@dataclass
class ProbabilityResult:
    """The result of a probability computation."""
    probability: float
    roll: float
    success: bool
    quality: OutcomeQuality
    details: Dict[str, float] = field(default_factory=dict)
    narrative: str = ""

    def __str__(self) -> str:
        return (f"ProbabilityResult(prob={self.probability:.2%}, roll={self.roll:.2%}, "
                f"outcome={self.quality.value}, success={self.success})")
