"""Advanced birth & reincarnation system with probability-driven attribute generation,
deep family lineage, reincarnation (isekai) support, automatic world expansion,
and novel-grade narrative output."""

from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from world_builder.graph_manager import GraphManager
from world_builder.builder import WorldBuilder
from world_builder.llm import LLMClient
from world_builder.entity_profile import LayeredProfile

from .memory_optimized import OptimizedMemoryStore
from .chronicler import Chronicler
from world_core.memory import WorldMemory
from world_core.probability.engine import ProbabilityEngine
from world_core.probability.resolver import ProbabilityContextResolver
from world_core.probability.profiles import get_profile

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# ENUMS & DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class SocialClass(Enum):
    """Character social class."""
    SLAVE = "slave"
    PEASANT = "peasant"
    COMMONER = "commoner"
    MERCHANT = "merchant"
    NOBILITY = "nobility"
    ROYALTY = "royalty"


class BirthCircumstance(Enum):
    """Special circumstances around birth."""
    NORMAL = "normal"
    PROPHECY = "prophecy"
    OMEN = "omen"
    TRAGEDY = "tragedy"
    MIRACLE = "miracle"
    SECRET = "secret"


class Gender(Enum):
    """Character gender."""
    MALE = "male"
    FEMALE = "female"
    NON_BINARY = "non_binary"
    OTHER = "other"


@dataclass
class InnateSkill:
    """An innate skill with base value, cap, and growth rate."""
    name: str
    base_value: float
    cap: float
    growth_rate: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "base_value": self.base_value,
            "cap": self.cap,
            "growth_rate": self.growth_rate,
        }


@dataclass
class FamilyMember:
    """A family member with basic information."""
    name: str
    relation: str  # father, mother, paternal_grandfather, etc.
    age: Optional[int] = None
    occupation: Optional[str] = None
    personality: Optional[str] = None
    alive: bool = True
    magic_affinity: Optional[str] = None
    uid: Optional[str] = None


@dataclass
class FamilyTree:
    """Complete family tree with three generations."""
    father: Optional[FamilyMember] = None
    mother: Optional[FamilyMember] = None
    paternal_grandparents: List[FamilyMember] = field(default_factory=list)
    maternal_grandparents: List[FamilyMember] = field(default_factory=list)
    siblings: List[FamilyMember] = field(default_factory=list)
    aunts_uncles: List[FamilyMember] = field(default_factory=list)
    family_head: Optional[str] = None
    family_motto: Optional[str] = None
    heirloom_name: Optional[str] = None
    heirloom_description: Optional[str] = None


@dataclass
class ReincarnationData:
    """Data for isekai/reincarnation mode."""
    past_name: str
    past_world: str
    death_cause: str
    cheat_ability: str
    key_memories: List[str] = field(default_factory=list)


@dataclass
class ProbabilityRoll:
    """Record of a probability roll for display."""
    attribute: str
    probability: float
    roll_result: float
    success: bool
    critical: bool = False
    value: Any = None

    def __str__(self) -> str:
        status = "✓" if self.success else "✗"
        if self.critical:
            status = "✨ CRITICAL!"
        return f"[Probability] {self.attribute}: prob {self.probability:.2f}, roll {self.roll_result:.2f} → {status} {self.value or ''}"


@dataclass
class BirthParameters:
    """Complete birth parameters for character creation."""
    character_name: str
    gender: Gender
    race: str
    social_class: SocialClass
    birthplace: str
    initial_location: str
    magic_affinity: Optional[str]
    family: FamilyTree
    innate_traits: List[str]
    innate_skills: List[InnateSkill]
    birth_circumstance: BirthCircumstance
    family_secret: Optional[str]
    reincarnation: Optional[ReincarnationData] = None
    starting_age_years: int = 5
    opening_narrative: str = ""
    probability_rolls: List[ProbabilityRoll] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# PROBABILITY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

class BirthProbabilityHelper:
    """Helper class for birth-related probability calculations."""

    def __init__(
        self,
        prob_engine: ProbabilityEngine,
        prob_resolver: ProbabilityContextResolver,
        world_frame: Dict[str, Any],
    ):
        self.prob_engine = prob_engine
        self.prob_resolver = prob_resolver
        self.world_frame = world_frame

    def _get_race_rarity(self, race: str) -> float:
        """Get race rarity (0.0 = very rare, 1.0 = common)."""
        races = self.world_frame.get("races", [])
        for r in races:
            if r.get("name", "").lower() == race.lower():
                return 1.0 - r.get("rarity", 0.5)
        return 0.5  # Default if not found

    def _get_class_demographics(self, social_class: SocialClass) -> float:
        """Get demographic weight for social class."""
        demographics = {
            SocialClass.SLAVE: 0.05,
            SocialClass.PEASANT: 0.30,
            SocialClass.COMMONER: 0.40,
            SocialClass.MERCHANT: 0.15,
            SocialClass.NOBILITY: 0.08,
            SocialClass.ROYALTY: 0.02,
        }
        return demographics.get(social_class, 0.05)

    def _get_magic_density(self) -> float:
        """Get world magic density."""
        return self.world_frame.get("magic_system", {}).get("density", 0.5)

    async def roll_race(self, user_hints: str = "") -> tuple[str, float]:
        """Roll for race using probability engine."""
        races = self.world_frame.get("races", [])
        if not races:
            return "human", 0.5

        # Build weighted list based on rarity
        race_weights = []
        for r in races:
            rarity = 1.0 - r.get("rarity", 0.5)
            # Check if user hinted at this race
            hint_bonus = 0.0
            if user_hints and r.get("name", "").lower() in user_hints.lower():
                hint_bonus = 0.3
            race_weights.append((r["name"], rarity + hint_bonus))

        # Use weighted random for selection
        total = sum(w for _, w in race_weights)
        race_names = [r for r, _ in race_weights]
        weights = [w / total for _, w in race_weights]

        selected = random.choices(race_names, weights=weights)[0]
        probability = weights[race_names.index(selected)]
        roll = random.random()

        return selected, probability

    async def roll_social_class(self, user_hints: str = "") -> tuple[SocialClass, float]:
        """Roll for social class using probability engine."""
        classes = list(SocialClass)

        # Build weights based on demographics
        class_weights = {}
        for cls in classes:
            weight = self._get_class_demographics(cls)
            # Check hint
            if user_hints and cls.value in user_hints.lower():
                weight += 0.3
            class_weights[cls] = weight

        total = sum(class_weights.values())
        weights = [class_weights[c] / total for c in classes]

        selected = random.choices(classes, weights=weights)[0]
        probability = weights[classes.index(selected)]
        roll = random.random()

        return selected, probability

    async def roll_magic_affinity(self, parent_affinity: Optional[str] = None) -> tuple[Optional[str], float]:
        """Roll for magic affinity."""
        magic_system = self.world_frame.get("magic_system", {})
        affinities = magic_system.get("affinities", [])

        if not affinities:
            return None, 0.0

        # Base chance for having magic
        base_chance = self._get_magic_density()
        if parent_affinity:
            base_chance += 0.2  # Bloodline bonus

        roll = random.random()
        has_magic = roll < base_chance

        if not has_magic:
            return None, base_chance

        # Select affinity
        affinity_weights = []
        for aff in affinities:
            rarity = 1.0 - aff.get("rarity", 0.5)
            affinity_weights.append((aff["name"], rarity))

        total = sum(w for _, w in affinity_weights)
        aff_names = [a for a, _ in affinity_weights]
        weights = [w / total for _, w in affinity_weights]

        selected = random.choices(aff_names, weights=weights)[0]
        probability = weights[aff_names.index(selected)]

        return selected, probability

    async def roll_talents(
        self,
        social_class: SocialClass,
        race: str,
        user_hints: str = ""
    ) -> List[InnateSkill]:
        """Roll for innate talents."""
        talents = []

        # Possible talent categories
        talent_categories = [
            ("strength", "physical power"),
            ("dexterity", "agility and reflexes"),
            ("constitution", "health and endurance"),
            ("intelligence", "mental capacity"),
            ("wisdom", "perception and insight"),
            ("charisma", "social influence"),
            ("magic", "magical aptitude"),
            ("artistry", "creative expression"),
            ("leadership", "command and inspiration"),
            ("stealth", "concealment and subtlety"),
        ]

        # Class-based education bonuses
        education_bonus = {
            SocialClass.SLAVE: -0.2,
            SocialClass.PEASANT: 0.0,
            SocialClass.COMMONER: 0.1,
            SocialClass.MERCHANT: 0.15,
            SocialClass.NOBILITY: 0.25,
            SocialClass.ROYALTY: 0.3,
        }

        class_bonus = education_bonus.get(social_class, 0.0)

        # Race talent bonus (simplified)
        race_talent_bonus = 0.1  # Could be expanded based on race definitions

        for talent_name, talent_desc in talent_categories:
            base_chance = 0.3 + class_bonus + race_talent_bonus

            # Check user hints
            if user_hints and talent_name in user_hints.lower():
                base_chance += 0.3

            roll = random.random()
            if roll < base_chance:
                # Success! Generate skill values
                base_value = 0.4 + random.random() * 0.3  # 0.4-0.7
                cap = 0.85 + random.random() * 0.15  # 0.85-1.0
                growth_rate = 0.03 + random.random() * 0.04  # 0.03-0.07

                talents.append(InnateSkill(
                    name=talent_name,
                    base_value=round(base_value, 2),
                    cap=round(cap, 2),
                    growth_rate=round(growth_rate, 2),
                ))

        return talents

    def roll_circumstance(self) -> BirthCircumstance:
        """Roll for birth circumstance."""
        circumstances = [
            (BirthCircumstance.NORMAL, 0.60),
            (BirthCircumstance.PROPHECY, 0.08),
            (BirthCircumstance.OMEN, 0.10),
            (BirthCircumstance.TRAGEDY, 0.10),
            (BirthCircumstance.MIRACLE, 0.07),
            (BirthCircumstance.SECRET, 0.05),
        ]

        weights = [w for _, w in circumstances]
        selected = random.choices([c for c, _ in circumstances], weights=weights)[0]
        return selected


# ═══════════════════════════════════════════════════════════════════════════════
# FAMILY TREE GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

class FamilyTreeGenerator:
    """Generates detailed family trees using LLM."""

    def __init__(self, llm: LLMClient, world_frame: Dict[str, Any]):
        self.llm = llm
        self.world_frame = world_frame

    async def generate(
        self,
        race: str,
        social_class: SocialClass,
        magic_affinity: Optional[str],
        user_hints: str = "",
    ) -> FamilyTree:
        """Generate a complete family tree with three generations."""

        races = ", ".join(r["name"] for r in self.world_frame.get("races", [])) or "unknown"
        factions = ", ".join(f["name"] for f in self.world_frame.get("factions", [])) or "unknown"

        prompt = f"""You are generating a detailed family tree for a newborn character in a fantasy world.

World: {self.world_frame.get('world_name', 'Unknown')}
Available races: {races}
Available factions: {factions}
User hints: {user_hints if user_hints else 'None'}

The newborn is:
- Race: {race}
- Social class: {social_class.value}
- Magic affinity: {magic_affinity or 'none'}

Generate a JSON object representing this family. Use your creativity to make the family interesting and appropriate for the social class:

{{
    "father": {{
        "name": "full name appropriate to culture and class",
        "age": 25-40,
        "occupation": "job or role appropriate to social class",
        "personality": "brief personality description",
        "alive": true or false (if tragic backstory)
    }},
    "mother": {{
        "name": "full name appropriate to culture and class",
        "age": 23-35,
        "occupation": "job or role appropriate to social class",
        "personality": "brief personality description",
        "alive": true or false
    }},
    "paternal_grandparents": [
        {{"name": "name", "relation": "paternal_grandfather" or "paternal_grandmother", "occupation": "former occupation", "alive": true or false}}
    ],
    "maternal_grandparents": [
        {{"name": "name", "relation": "maternal_grandfather" or "maternal_grandmother", "occupation": "former occupation", "alive": true or false}}
    ],
    "siblings": [
        {{"name": "name", "age": 3-18, "gender": "male" or "female", "personality": "brief description"}}
    ],
    "aunts_uncles": [
        {{"name": "name", "relation": "paternal_aunt" or "paternal_uncle" or "maternal_aunt" or "maternal_uncle", "occupation": "occupation"}}
    ],
    "family_head": "name of the person with authority",
    "family_motto": "optional family motto or saying",
    "heirloom": {{
        "name": "name of the heirloom",
        "description": "description of appearance and significance"
    }},
    "family_secret": "optional secret that could form a story arc"
}}

Return ONLY the JSON object. Be creative but keep it appropriate to the social class."""

        try:
            result = await self.llm.generate_json(prompt, temperature=0.8)
        except Exception as e:
            logger.warning(f"Failed to generate full family tree: {e}. Using minimal family.")
            return self._generate_minimal_family(social_class)

        return self._parse_family_tree(result)

    def _generate_minimal_family(self, social_class: SocialClass) -> FamilyTree:
        """Generate a minimal family if LLM fails."""
        return FamilyTree(
            father=FamilyMember(
                name="Unknown Father",
                relation="father",
                age=30,
                occupation=self._class_occupation(social_class),
                personality="stern but loving",
                alive=True,
            ),
            mother=FamilyMember(
                name="Unknown Mother",
                relation="mother",
                age=28,
                occupation="homemaker",
                personality="caring",
                alive=True,
            ),
            family_head="Unknown Father",
        )

    def _class_occupation(self, social_class: SocialClass) -> str:
        """Get occupation based on social class."""
        occupations = {
            SocialClass.SLAVE: "laborer",
            SocialClass.PEASANT: "farmer",
            SocialClass.COMMONER: "craftsperson",
            SocialClass.MERCHANT: "trader",
            SocialClass.NOBILITY: "lord",
            SocialClass.ROYALTY: "royal advisor",
        }
        return occupations.get(social_class, "worker")

    def _parse_family_tree(self, data: Dict[str, Any]) -> FamilyTree:
        """Parse LLM response into FamilyTree object."""

        def parse_member(d: Dict[str, str], relation: str) -> FamilyMember:
            return FamilyMember(
                name=d.get("name", "Unknown"),
                relation=relation,
                age=d.get("age"),
                occupation=d.get("occupation"),
                personality=d.get("personality"),
                alive=d.get("alive", True),
            )

        family = FamilyTree()

        if "father" in data:
            family.father = parse_member(data["father"], "father")

        if "mother" in data:
            family.mother = parse_member(data["mother"], "mother")

        if "paternal_grandparents" in data:
            family.paternal_grandparents = [
                parse_member(p, p.get("relation", "paternal_grandparent"))
                for p in data["paternal_grandparents"]
            ]

        if "maternal_grandparents" in data:
            family.maternal_grandparents = [
                parse_member(p, p.get("relation", "maternal_grandparent"))
                for p in data["maternal_grandparents"]
            ]

        if "siblings" in data:
            family.siblings = [
                FamilyMember(
                    name=s.get("name", "Unknown"),
                    relation="sibling",
                    age=s.get("age"),
                    personality=s.get("personality"),
                )
                for s in data["siblings"]
            ]

        if "aunts_uncles" in data:
            family.aunts_uncles = [
                parse_member(a, a.get("relation", "aunt_uncle"))
                for a in data["aunts_uncles"]
            ]

        family.family_head = data.get("family_head")
        family.family_motto = data.get("family_motto")

        if "heirloom" in data:
            family.heirloom_name = data["heirloom"].get("name")
            family.heirloom_description = data["heirloom"].get("description")

        return family


# ═══════════════════════════════════════════════════════════════════════════════
# REINCARNATION GENERATOR (ISEKAI MODE)
# ═══════════════════════════════════════════════════════════════════════════════

class ReincarnationGenerator:
    """Generates past life data for isekai/reincarnation mode."""

    def __init__(self, llm: LLMClient, world_frame: Dict[str, Any]):
        self.llm = llm
        self.world_frame = world_frame

    async def generate(self, user_hints: str = "") -> ReincarnationData:
        """Generate past life information."""

        world_name = self.world_frame.get("world_name", "Unknown Fantasy World")

        prompt = f"""You are generating a reincarnation (isekai) backstory for a character being reborn into a fantasy world.

Target world: {world_name}
User hints: {user_hints if user_hints else 'None'}

Generate a JSON object representing their past life:

{{
    "past_name": "full name from past life",
    "past_world": "description of the past world (e.g., 'Modern Earth - Tokyo, Japan' or 'Space Station Artemis')",
    "death_cause": "how they died (be creative - truck isekai, illness, accident, heroics, etc.)",
    "cheat_ability": "a special ability they bring from their past life that seems like magic/ superpower in this world",
    "key_memories": [
        "a fading memory from their past life - something sensory like a smell, sound, or feeling",
        "another fragment - perhaps a skill they had",
        "one more - maybe something about people they loved"
    ]
}}

The cheat ability should be something that would seem extraordinary in this fantasy world but plausible as a 'gift from their past life'.
Examples: 'Perfect musical pitch', 'Knowledge of future events', 'Superhuman reflexes', 'Language intuition', 'Mathematical genius', etc.

Return ONLY the JSON object. Be creative!"""

        try:
            result = await self.llm.generate_json(prompt, temperature=0.9)
        except Exception as e:
            logger.warning(f"Failed to generate reincarnation data: {e}")
            return ReincarnationData(
                past_name="Unknown",
                past_world="Unknown",
                death_cause="mysterious",
                cheat_ability="Mysterious Power",
                key_memories=["A fading memory"],
            )

        return ReincarnationData(
            past_name=result.get("past_name", "Unknown"),
            past_world=result.get("past_world", "Unknown"),
            death_cause=result.get("death_cause", "unknown"),
            cheat_ability=result.get("cheat_ability", "Unknown Power"),
            key_memories=result.get("key_memories", ["A fading memory"]),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# BIRTH GENERATOR - MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

class BirthGenerator:
    """Main orchestrator for birth generation using probability + LLM."""

    def __init__(
        self,
        ctx: "NarrativeContext",
        user_hints: str = "",
        isekai: bool = False,
        starting_age: int = 5,
        display_probabilities: bool = False,
    ):
        self.ctx = ctx
        self.user_hints = user_hints
        self.isekai = isekai
        self.starting_age = starting_age
        self.display_probabilities = display_probabilities

        self.prob_helper = BirthProbabilityHelper(
            ctx.prob_engine,
            ctx.prob_resolver,
            ctx.world_frame,
        )
        self.family_generator = FamilyTreeGenerator(ctx.llm, ctx.world_frame)
        self.reincarnation_generator = ReincarnationGenerator(ctx.llm, ctx.world_frame)

    async def generate(self) -> BirthParameters:
        """Generate complete birth parameters."""

        # 1. Roll for race
        race, race_prob = await self.prob_helper.roll_race(self.user_hints)
        race_roll = random.random()
        race_success = race_roll < race_prob
        race_critical = race_roll < race_prob * 0.3

        if self.display_probabilities:
            print(f"[Probability] Race: {race} (prob {race_prob:.2f}, roll {race_roll:.2f}) → {'✓' if race_success else '✗'}")

        # 2. Roll for social class
        social_class, class_prob = await self.prob_helper.roll_social_class(self.user_hints)
        class_roll = random.random()
        class_success = class_roll < class_prob

        if self.display_probabilities:
            print(f"[Probability] Social class: {social_class.value} (prob {class_prob:.2f}, roll {class_roll:.2f}) → {'✓' if class_success else '✗'}")

        # 3. Roll for magic affinity
        magic_affinity, magic_prob = await self.prob_helper.roll_magic_affinity()

        if self.display_probabilities:
            if magic_affinity:
                print(f"[Probability] Magic affinity: {magic_affinity} (prob {magic_prob:.2f}) → ✓")
            else:
                print(f"[Probability] Magic affinity: none (prob {magic_prob:.2f}) → ✗")

        # 4. Roll for birth circumstance
        circumstance = self.prob_helper.roll_circumstance()

        # 5. Generate family tree
        logger.info("Generating family tree...")
        family = await self.family_generator.generate(
            race, social_class, magic_affinity, self.user_hints
        )

        # 6. Roll for talents
        talents = await self.prob_helper.roll_talents(social_class, race, self.user_hints)

        if self.display_probabilities:
            print(f"[Probability] Talents: {len(talents)} innate talents rolled")
            for talent in talents:
                print(f"  - {talent.name}: base {talent.base_value}, cap {talent.cap}, growth {talent.growth_rate}")

        # 7. Determine innate traits based on talents and circumstance
        innate_traits = self._derive_traits(talents, circumstance, magic_affinity)

        # 8. Generate isekai data if requested
        reincarnation = None
        if self.isekai:
            logger.info("Generating reincarnation data...")
            reincarnation = await self.reincarnation_generator.generate(self.user_hints)

        # 9. Generate character name
        name = await self._generate_name(race, social_class, family)

        # 10. Determine birthplace and initial location
        birthplace, initial_location = await self._determine_locations(family, race)

        # 11. Generate family secret
        family_secret = family.family_head  # Simplified - could be expanded

        # 12. Determine gender (random or based on hints)
        gender = self._determine_gender()

        # 13. Generate opening narrative
        opening_narrative = await self._generate_opening_narrative(
            name, race, social_class, circumstance, birthplace, reincarnation
        )

        return BirthParameters(
            character_name=name,
            gender=gender,
            race=race,
            social_class=social_class,
            birthplace=birthplace,
            initial_location=initial_location,
            magic_affinity=magic_affinity,
            family=family,
            innate_traits=innate_traits,
            innate_skills=talents,
            birth_circumstance=circumstance,
            family_secret=family_secret,
            reincarnation=reincarnation,
            starting_age_years=self.starting_age,
            opening_narrative=opening_narrative,
        )

    def _derive_traits(
        self,
        talents: List[InnateSkill],
        circumstance: BirthCircumstance,
        magic_affinity: Optional[str],
    ) -> List[str]:
        """Derive character traits from talents and circumstances."""
        traits = []

        # Add trait names from successful talents
        for talent in talents:
            if talent.base_value > 0.6:
                traits.append(f"high {talent.name}")

        # Add circumstance-based traits
        if circumstance == BirthCircumstance.PROPHECY:
            traits.append("marked by destiny")
        elif circumstance == BirthCircumstance.OMEN:
            traits.append("sign of power")
        elif circumstance == BirthCircumstance.TRAGEDY:
            traits.append("survivor")
        elif circumstance == BirthCircumstance.MIRACLE:
            traits.append("blessed")

        # Add magic trait
        if magic_affinity:
            traits.append(f"magically awakened")

        return traits

    async def _generate_name(
        self,
        race: str,
        social_class: SocialClass,
        family: FamilyTree,
    ) -> str:
        """Generate a unique character name."""

        # Check if user specified a name
        import re
        name_match = re.search(r'name[:\s]+([A-Za-z]+)', self.user_hints, re.I)
        if name_match:
            base_name = name_match.group(1)
        else:
            # Generate name using LLM
            parent_name = family.father.name if family.father else "Unknown"

            prompt = f"""Generate a unique name appropriate for:
- Race: {race}
- Social class: {social_class.value}
- Parent name: {parent_name}

Return ONLY a first name, no last name. Be creative and appropriate to the culture implied by the race and class."""

            try:
                result = await self.ctx.llm.generate_json(prompt, temperature=0.8)
                base_name = result.get("name", "Unknown")
            except Exception:
                base_name = "Newborn"

        # Ensure unique
        counter = 1
        name = base_name
        while self.ctx.gm.store.get_by_name_and_type(name, "Character"):
            name = f"{base_name}_{counter}"
            counter += 1

        return name

    async def _determine_locations(
        self,
        family: FamilyTree,
        race: str,
    ) -> tuple[str, str]:
        """Determine birthplace and initial location."""

        # Use existing locations from world frame
        locations = self.ctx.world_frame.get("locations", [])

        if not locations:
            # Create default
            return "The Capital City", "The Capital City"

        # Select appropriate location based on social class
        location_names = [loc.get("name", "Unknown") for loc in locations]

        # For now, select randomly but weighted toward common
        birthplace = random.choice(location_names[:5]) if len(location_names) > 5 else location_names[0]

        return birthplace, birthplace

    def _determine_gender(self) -> Gender:
        """Determine character gender."""
        # Check hints
        if self.user_hints:
            if "male" in self.user_hints.lower():
                return Gender.MALE
            elif "female" in self.user_hints.lower():
                return Gender.FEMALE
            elif "non-binary" in self.user_hints.lower():
                return Gender.NON_BINARY

        # Random
        return random.choice(list(Gender))

    async def _generate_opening_narrative(
        self,
        name: str,
        race: str,
        social_class: SocialClass,
        circumstance: BirthCircumstance,
        birthplace: str,
        reincarnation: Optional[ReincarnationData],
    ) -> str:
        """Generate the opening narrative."""

        circumstance_desc = {
            BirthCircumstance.NORMAL: "a quiet, uneventful birth",
            BirthCircumstance.PROPHECY: "a birth accompanied by prophecies of greatness",
            BirthCircumstance.OMEN: "a birth marked by strange omens in the sky",
            BirthCircumstance.TRAGEDY: "a birth shadowed by tragedy and loss",
            BirthCircumstance.MIRACLE: "a miraculous birth that defied expectation",
            BirthCircumstance.SECRET: "a birth kept secret from the world",
        }

        isekai_intro = ""
        if reincarnation:
            isekai_intro = f"\n\nIn another life, they were {reincarnation.past_name} from {reincarnation.past_world}. They died {reincarnation.death_cause}, only to wake in this new world with fragments of their past life lingering like fading dreams..."

        prompt = f"""Write a 2-3 paragraph novel-grade opening narrative for a character birth.

Character: {name}
Race: {race}
Social class: {social_class.value}
Birthplace: {birthplace}
Circumstance: {circumstance_desc.get(circumstance, 'a normal birth')}
{isekai_intro}

Write in third person, immersive and atmospheric. Focus on:
- The moment of birth and first sensations
- The setting and atmosphere of the birthplace
- Any unusual elements from the circumstance
- A hint of the character's future potential

Keep it to 3 paragraphs maximum. Make it feel like the opening of a high-quality anime or fantasy novel."""

        try:
            result = await self.ctx.llm.generate_json(prompt, temperature=0.9)
            return result.get("narrative", f"{name} was born into the world.")
        except Exception:
            return f"{name} was born to a {social_class.value} family in {birthplace}. The world awaits their journey."


# ═══════════════════════════════════════════════════════════════════════════════
# BIRTH APPLIER - CREATES ENTITIES AND RELATIONSHIPS IN THE WORLD
# ═══════════════════════════════════════════════════════════════════════════════

class BirthApplier:
    """Applies birth parameters to create entities in the world."""

    def __init__(
        self,
        ctx: "NarrativeContext",
        params: BirthParameters,
    ):
        self.ctx = ctx
        self.params = params

    async def apply(self) -> str:
        """Apply birth to the world and return opening narrative."""

        logger.info(f"Applying birth for {self.params.character_name}")

        # 1. Create main character entity
        character_node = await self._create_character_entity()

        # 2. Create family members
        await self._create_family_members()

        # 3. Create heirloom if exists
        if self.params.family.heirloom_name:
            await self._create_heirloom()

        # 4. Register character in memory store
        await self._register_in_memory_store()

        # 5. Initialize memories
        await self._initialize_memories()

        # 6. Create reincarnation memories if isekai
        if self.params.reincarnation:
            await self._create_reincarnation_memories()

        # 7. Schedule childhood milestones
        await self._schedule_childhood_milestones()

        # 8. Log birth event
        await self._log_birth_event()

        return self.params.opening_narrative

    async def _create_character_entity(self):
        """Create the main character entity in the graph."""

        # Build L1 profile
        l1 = {
            "name": self.params.character_name,
            "type": "Character",
            "group": "characters",
            "summary": f"A {self.params.race} {self.params.social_class.value} born in {self.params.birthplace}",
            "tags": [self.params.race, self.params.social_class.value],
            "relationships": [],
        }

        # Build L2 profile
        l2 = {
            "age": self.params.starting_age_years,
            "gender": self.params.gender.value,
            "birthplace": self.params.birthplace,
            "current_location": self.params.initial_location,
            "social_class": self.params.social_class.value,
            "family_head": self.params.family.family_head,
            "family_motto": self.params.family.family_motto,
            "affiliations": [self.params.social_class.value],
            "backstory_short": f"Born to a {self.params.social_class.value} family in {self.params.birthplace}",
            "circumstance_of_birth": self.params.birth_circumstance.value,
        }

        # Build L3 profile (secrets)
        l3 = {
            "innate_traits": self.params.innate_traits,
            "innate_skills": [s.to_dict() for s in self.params.innate_skills],
            "family_secret": self.params.family_secret,
        }

        # Add magic affinity if present
        if self.params.magic_affinity:
            l3["magic_affinity"] = self.params.magic_affinity

        # Add reincarnation data if isekai
        if self.params.reincarnation:
            l3["reincarnation"] = {
                "past_name": self.params.reincarnation.past_name,
                "past_world": self.params.reincarnation.past_world,
                "death_cause": self.params.reincarnation.death_cause,
                "cheat_ability": self.params.reincarnation.cheat_ability,
                "memories_unlocked": False,
            }

        profile = LayeredProfile(l1=l1, l2=l2, l3=l3)

        # Add to graph
        node = await self.ctx.gm.add_entity(
            self.params.character_name,
            "Character",
            profile,
            group_id="characters"
        )

        logger.info(f"Created character entity: {self.params.character_name}")
        return node

    async def _create_family_members(self):
        """Create all family members as NPC entities."""

        # Helper to create a family member
        async def create_member(member: FamilyMember, char_uid: str):
            if not member.name or member.name == "Unknown":
                return None

            # Check if already exists
            existing = self.ctx.gm.store.get_by_name_and_type(member.name, "Character")
            if existing:
                member.uid = existing.uid
                return existing

            # Create new NPC
            l1 = {
                "name": member.name,
                "type": "Character",
                "group": "family",
                "summary": f"{member.relation} of {self.params.character_name}",
                "tags": ["family", member.relation],
                "relationships": [],
            }

            l2 = {
                "age": member.age,
                "occupation": member.occupation,
                "personality": member.personality,
                "alive": member.alive,
            }

            if member.magic_affinity:
                l2["magic_affinity"] = member.magic_affinity

            profile = LayeredProfile(l1=l1, l2=l2, l3={})
            node = await self.ctx.gm.add_entity(member.name, "Character", profile, group_id="family")
            member.uid = node.uid

            # Create relationship in graph
            await self._create_relationship(char_uid, node.uid, member.relation)

            return node

        # Get character UID
        char_node = self.ctx.gm.store.get_by_name_and_type(
            self.params.character_name, "Character"
        )
        if not char_node:
            logger.error("Character node not found!")
            return

        # Create all family members
        members = []
        if self.params.family.father:
            members.append((self.params.family.father, "father"))
        if self.params.family.mother:
            members.append((self.params.family.mother, "mother"))

        for gp in self.params.family.paternal_grandparents:
            members.append((gp, gp.relation))
        for gp in self.params.family.maternal_grandparents:
            members.append((gp, gp.relation))
        for sib in self.params.family.siblings:
            members.append((sib, "sibling"))
        for au in self.params.family.aunts_uncles:
            members.append((au, au.relation))

        for member, relation in members:
            await create_member(member, char_node.uid)

        # Create parent relationships
        if self.params.family.father and self.params.family.father.uid:
            await self._create_relationship(
                self.params.family.father.uid, char_node.uid, "child_of"
            )
        if self.params.family.mother and self.params.family.mother.uid:
            await self._create_relationship(
                self.params.family.mother.uid, char_node.uid, "child_of"
            )

        # Create sibling relationships
        for sib in self.params.family.siblings:
            if sib.uid:
                await self._create_relationship(char_node.uid, sib.uid, "sibling_of")

    async def _create_relationship(self, source_uid: str, target_uid: str, relation: str):
        """Create a relationship edge in the graph."""
        try:
            self.ctx.gm.graph.add_edge(
                source_uid,
                target_uid,
                relation_type=relation,
                metadata={"created_at": datetime.now().isoformat()}
            )
        except Exception as e:
            logger.warning(f"Failed to create relationship {relation}: {e}")

    async def _create_heirloom(self):
        """Create family heirloom as an Item entity."""

        heirloom_name = self.params.family.heirloom_name
        if not heirloom_name:
            return

        # Check if exists
        existing = self.ctx.gm.store.get_by_name_and_type(heirloom_name, "Item")
        if existing:
            return

        l1 = {
            "name": heirloom_name,
            "type": "Item",
            "group": "items",
            "summary": self.params.family.heirloom_description or "A family heirloom",
            "tags": ["heirloom", "family"],
            "relationships": [],
        }

        l2 = {
            "description": self.params.family.heirloom_description,
            "type": "heirloom",
            "owned_by": self.params.family.family_head,
            "generations": random.randint(3, 10),
        }

        profile = LayeredProfile(l1=l1, l2=l2, l3={})
        await self.ctx.gm.add_entity(heirloom_name, "Item", profile, group_id="items")

        logger.info(f"Created heirloom: {heirloom_name}")

    async def _register_in_memory_store(self):
        """Register character in the memory store."""

        char_node = self.ctx.gm.store.get_by_name_and_type(
            self.params.character_name, "Character"
        )

        if not char_node:
            logger.error("Character node not found for memory registration")
            return

        await self.ctx.npc_mgr.register(
            self.params.character_name,
            char_node.uid,
            location=self.params.initial_location
        )

        # Set initial NPC profile data
        profile = self.ctx.npc_mgr.get(self.params.character_name)
        if profile:
            profile.health = 100
            profile.mood = "neutral"
            profile.goals = ["grow up", "discover abilities"]

            # Add innate skills to inventory-like tracking
            for skill in self.params.innate_skills:
                # Could track in a skills dict
                pass

            self.ctx.npc_mgr._save()

    async def _initialize_memories(self):
        """Create initial memories for the character."""

        # Birth memory
        await self.ctx.npc_mgr.add_memory(
            self.params.character_name,
            f"Born in {self.params.birthplace} to a {self.params.social_class.value} family.",
            importance=0.9,
            emotion="confusion",
            tags=["birth", "origin"],
        )

        # Circumstance memory
        if self.params.birth_circumstance != BirthCircumstance.NORMAL:
            await self.ctx.npc_mgr.add_memory(
                self.params.character_name,
                f"My birth was marked by {self.params.birth_circumstance.value}.",
                importance=0.7,
                emotion="wonder",
                tags=["birth", "circumstance"],
            )

    async def _create_reincarnation_memories(self):
        """Create isekai past life memories."""

        if not self.params.reincarnation:
            return

        # Add past life as semantic memory in world memory
        for i, memory in enumerate(self.params.reincarnation.key_memories):
            await self.ctx.world_memory.add(
                content=f"Past life memory: {memory}",
                source_type="isekai",
                source_id=self.params.character_name,
                importance=0.5,
                tags=["reincarnation", "past_life", "memory_fragment"],
            )

        # Add cheat ability as a hidden skill
        logger.info(f"Cheat ability granted: {self.params.reincarnation.cheat_ability}")

    async def _schedule_childhood_milestones(self):
        """Schedule childhood milestone events."""

        if self.params.starting_age_years >= 15:
            # Too old for childhood milestones
            return

        now = self.ctx.clock.current_time

        milestones = [
            (30, "first_word", "First word spoken"),
            (180, "first_step", "First steps taken"),
            (365, "first_friend", "First friend met"),
            (730, "basic_education", "Started basic education"),
        ]

        # Add magic awakening if has magic
        if self.params.magic_affinity:
            milestones.append((1095, "magic_awakening", "Magic awakening"))

        for offset_days, event_type, description in milestones:
            when = now + timedelta(days=offset_days)
            await self.ctx.clock.schedule_event(
                when,
                "childhood_event",
                {
                    "type": event_type,
                    "description": description,
                    "character": self.params.character_name,
                    "age_at_event": offset_days // 365,
                }
            )

        logger.info(f"Scheduled {len(milestones)} childhood milestones for {self.params.character_name}")

    async def _log_birth_event(self):
        """Log the birth event in the chronicle."""

        await self.ctx.chronicler.log_event(
            f"{self.params.character_name} was born into the world. "
            f"Race: {self.params.race}, Class: {self.params.social_class.value}, "
            f"Birthplace: {self.params.birthplace}",
            datetime.now(),
            group="birth",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# BIRTH SCENARIO - MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

class BirthScenario:
    """
    Main entry point for the birth system.
    Orchestrates generation and application of birth parameters.
    """

    def __init__(self, ctx: "NarrativeContext"):
        self.ctx = ctx

    # ─────────────────────────────────────────────────────────────────────────────
    # Static compatibility methods for backward compatibility with old NewbornScenario API
    # ─────────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def prepare(
        character: str,
        gm: "GraphManager",
        builder: "WorldBuilder",
        npc_mgr: "OptimizedMemoryStore",
        chronicler: "Chronicler",
    ):
        """Prepare a newborn character (backward compatibility with NewbornScenario.prepare)."""
        from .context import NarrativeContext
        # Create a minimal context for preparation
        ctx = NarrativeContext.__new__(NarrativeContext)
        ctx.gm = gm
        ctx.builder = builder
        ctx.npc_mgr = npc_mgr
        ctx.chronicler = chronicler
        ctx.llm = builder.llm
        # Use BirthScenario to prepare the character
        scenario = BirthScenario(ctx)
        await scenario.generate_and_apply(user_hints=character, starting_age=0)

    @staticmethod
    async def generate_and_prepare(
        user_spec: str,
        gm: "GraphManager",
        builder: "WorldBuilder",
        npc_mgr: "OptimizedMemoryStore",
        chronicler: "Chronicler",
        llm: "LLMClient",
    ) -> tuple[str, BirthParameters]:
        """Generate and prepare a new character (backward compatibility with NewbornScenario.generate_and_prepare)."""
        from .context import NarrativeContext
        # Create a minimal context for generation
        ctx = NarrativeContext.__new__(NarrativeContext)
        ctx.gm = gm
        ctx.builder = builder
        ctx.npc_mgr = npc_mgr
        ctx.chronicler = chronicler
        ctx.llm = llm
        # Use BirthScenario to generate the character
        scenario = BirthScenario(ctx)
        opening_narrative, params = await scenario.generate_and_apply(
            user_hints=user_spec,
            starting_age=5,
            display_probabilities=True,
        )
        return params.character_name, opening_narrative

    async def generate_and_apply(
        self,
        user_hints: str = "",
        isekai: bool = False,
        starting_age: int = 5,
        display_probabilities: bool = False,
    ) -> tuple[str, BirthParameters]:
        """
        Generate a new character through birth and apply to the world.

        Returns:
            Tuple of (opening_narrative, birth_parameters)
        """

        # Generate birth parameters
        generator = BirthGenerator(
            self.ctx,
            user_hints=user_hints,
            isekai=isekai,
            starting_age=starting_age,
            display_probabilities=display_probabilities,
        )

        params = await generator.generate()

        # Apply to world
        applier = BirthApplier(self.ctx, params)
        opening_narrative = await applier.apply()

        return opening_narrative, params


# Type hint for NarrativeContext (imported in methods)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from world_narrative.context import NarrativeContext
