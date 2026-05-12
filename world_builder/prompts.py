"""Prompt templates for world generation (layer by layer)."""
from __future__ import annotations

_DEFAULT_PROMPTS = {
    "world_frame": """
You are a master world‑builder. Generate a brand‑new fantasy world.
Return ONLY a valid JSON object with the following structure, strictly obeying the field descriptions:

{
  "world_name": "string",
  "calendar_era": {"name": "string", "year_zero_event": "string"},
  "magic_system": {
    "name": "string",
    "rules": "string (hard limitations, costs, side‑effects)",
    "cost": "string (what casters must sacrifice)"
  },
  "races": [
    {"name": "string", "traits": "string", "culture": "string"}
  ],
  "factions": [
    {"name": "string", "goal": "string", "type": "political|religious|guild|secret"}
  ],
  "characters": [
    {
      "name": "string (unique)",
      "race": "string (must match a race name)",
      "age": int,
      "role": "string",
      "personality": "string",
      "abilities": ["string (max 3, must fit world rules)"],
      "affiliations": ["string (race, faction, or location names)"]
    }
  ],
  "locations": [
    {
      "name": "string",
      "type": "city|forest|ruin|mountain|desert|sea|underground",
      "description": "string (atmosphere, key feature)",
      "ruling_faction": "string or null (must match a faction name if present)"
    }
  ],
  "items": [
    {
      "name": "string",
      "type": "weapon|artifact|potion|armor|tool",
      "power": "string (mechanical effect within rules)",
      "origin": "string (creator or event)"
    }
  ],
  "historical_events": [
    {
      "name": "string",
      "year_ago": int,
      "description": "string",
      "involved_characters": ["name"],
      "involved_factions": ["name"]
    }
  ],
  "world_rules": [
    {
      "name": "string",
      "description": "string (concise law)",
      "category": "magic_law|physical_law|social_norm|divine_mandate"
    }
  ]
}

Constraints:
- Generate 3‑4 races, 3‑4 factions, 5‑6 characters, 3‑4 locations, 3 items, 3‑4 events, 3‑4 rules.
- Every affiliation, faction reference, and race must EXACTLY match an existing name in the same output.
- Magic system must be internally consistent.
Return ONLY the JSON object.
""",
    # ── L2 only prompts ─────────────────────────────────
    "character_L2": """
Character L1: {l1_json}
World rules: {rules_summary}
Existing entities: {existing_names}

Expand this character's **Level 2 details** (L2) only.
Return a JSON object with these keys:
{{
  "description": "physical appearance, mannerisms",
  "personality": "core traits, fears, desires",
  "backstory_short": "2-3 sentences origin",
  "abilities": ["max 3, obey world rules"],
  "goal": "short‑term objective",
  "affiliations": ["existing faction/race/location names"],
  "current_location": "existing location name or null",
  "moral_alignment": "lawful good, chaotic neutral, etc."
}}
Do NOT include Level 1 or Level 3 data. Return ONLY the L2 object.
""",
    "location_L2": """
Location L1: {l1_json}
World rules: {rules_summary}
Existing entities: {existing_names}

Generate only Level 2 (L2) details for this location:
{{
  "description": "atmosphere, appearance",
  "climate": "string",
  "population_estimate": int,
  "landmarks": ["2-3 notable places"],
  "lore": "local legends or history",
  "ruling_faction": "existing faction name or null"
}}
Return ONLY the L2 object.
""",
    "item_L2": """
Item L1: {l1_json}
Magic rules: {magic_rules}
Existing entities: {existing_names}

Generate only Level 2 (L2) details for this item:
{{
  "physical_description": "what it looks like",
  "primary_power": "mechanical effect within magic rules",
  "creation_myth": "how it was made",
  "required_affinity": "skill or trait needed",
  "rarity": "common, uncommon, rare, legendary"
}}
Return ONLY the L2 object.
""",
    "event_L2": """
Event L1: {l1_json}
Existing entities: {existing_names}

Generate only Level 2 (L2) details for this historical event:
{{
  "detailed_narrative": "3-4 sentence story",
  "immediate_consequences": "what happened right after",
  "location": "existing location name or null"
}}
Return ONLY the L2 object.
""",
    "faction_L2": """
Faction L1: {l1_json}
Existing entities: {existing_names}

Generate only Level 2 (L2) details for this faction:
{{
  "description": "culture, public face",
  "goal": "long‑term objective",
  "structure": "hierarchy",
  "notable_members": ["existing character names (max 3)"],
  "symbol": "emblem or icon",
  "history_short": "2‑3 sentences founding"
}}
Return ONLY the L2 object.
""",
    "rule_L2": """
World rule L1: {l1_json}
Existing rules: {existing_names}

Generate only Level 2 (L2) details for this world rule:
{{
  "description": "full explanation",
  "enforcement": "how it is upheld",
  "exceptions": "cases where it does not apply"
}}
Return ONLY the L2 object.
""",
    # ── L3 only prompts ─────────────────────────────────
    "character_L3": """
Character L1: {l1_json}
Character L2: {l2_json}

Generate only Level 3 (L3) secrets for this character:
{{
  "secret_background": "hidden past",
  "true_motivation": "real driving force",
  "hidden_relation": "unknown connection to another entity",
  "curse_or_blessing": "supernatural condition",
  "fear": "deepest fear",
  "regret": "greatest mistake",
  "unrevealed_power": "ability kept secret"
}}
Return ONLY the L3 object.
""",
    "location_L3": """
Location L1: {l1_json}
Location L2: {l2_json}

Generate only Level 3 (L3) secrets for this location:
{{
  "secret": "hidden underground or secret passage",
  "hidden_history": "forgotten past",
  "forgotten_event": "event no one remembers"
}}
Return ONLY the L3 object.
""",
    "item_L3": """
Item L1: {l1_json}
Item L2: {l2_json}
Magic rules: {magic_rules}

Generate only Level 3 (L3) secrets for this item:
{{
  "hidden_property": "unknown power",
  "curse": "negative effect",
  "true_origin": "real creator or event",
  "soul_bound_effect": "if attuned, extra ability"
}}
Return ONLY the L3 object.
""",
    "event_L3": """
Event L1: {l1_json}
Event L2: {l2_json}

Generate only Level 3 (L3) secrets for this event:
{{
  "hidden_truth": "what really happened",
  "long_term_consequences": "effects still visible",
  "forgotten_details": "lost facts",
  "alternate_interpretation": "different perspective"
}}
Return ONLY the L3 object.
""",
    "faction_L3": """
Faction L1: {l1_json}
Faction L2: {l2_json}

Generate only Level 3 (L3) secrets for this faction:
{{
  "secret_agenda": "true goal hidden from public",
  "internal_conflict": "power struggle within",
  "true_origin": "how it really started",
  "hidden_enemies": "secret rivals"
}}
Return ONLY the L3 object.
""",
    "rule_L3": """
World rule L1: {l1_json}
World rule L2: {l2_json}

Generate only Level 3 (L3) secrets for this world rule:
{{
  "hidden_consequence": "unknown side effect",
  "loophole": "how to bypass it",
  "origin_story": "myth behind the rule"
}}
Return ONLY the L3 object.
""",
    # ── Scene generation (unchanged) ────────────────────
    "scene_generation": """
World: {world_name}
Active world rules: {rules}
Scene context (characters, location): {context}

Write a short narrative scene (120‑180 words) that strictly follows all rules and character personalities.
Include a clear time marker. Return JSON:
{{
  "scene_text": "...",
  "time_markers": ["extracted phrases"],
  "entities_mentioned": [{{"name": "...", "type": "...", "attributes": {{}}}}],
  "relationships_mentioned": [{{"source": "...", "target": "...", "type": "..."}}]
}}
""",
    # ── Relationships generation ────────────────────────
    "relationships": """
You are an expert world‑building relationship generator.
Below is a list of existing entities in the world, with their names, types, and a one‑sentence summary.

Entities:
{entities_list}

Suggest **complex, non‑obvious relationships** between these entities.
- Use only the existing entity names; never invent new ones.
- Use the following relationship types (pick the most precise):
  - ally_of, enemy_of, rival_of, mentor_of, student_of, parent_of, child_of, sibling_of, lover_of, ex_lover_of
  - ruler_of, subject_of, works_for, employs, founded_by, member_of, leader_of
  - controls, trades_with, allied_with, at_war_with, spies_on, sabotages, worships, protects, fears, desires
  - located_in, part_of, contains, borders, connects_to, hidden_under
  - created_by, owns, stole_from, seeks, guards, destroys, repaired_by
- Each relationship should be **directional** (source → target).
- Prefer relationships that are **not obvious** from the summaries alone, but that could logically exist given the world rules and personalities.
- Avoid repeating relationships that are already obvious (e.g., don't say "Character is member_of Faction" if that's already stated in the summary).
- Output a JSON array of objects like:
  [
    {{"source": "Character:Varin Lume", "target": "Character:Lyra Quill", "type": "mentor_of"}},
    {{"source": "Faction:Order of the Echo", "target": "Item:Celestial Shard", "type": "seeks"}},
    ...
  ]
Return ONLY the JSON array, no other text.
"""
}

PROMPTS = _DEFAULT_PROMPTS
