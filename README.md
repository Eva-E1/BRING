# 🌟 BRING v2 – Building Rich Interactive Narrative Games

**BRING v2** is a **production‑ready**, AI‑powered platform for building, exploring, and **living** in persistent fantasy worlds.  
It combines generative world construction, graph‑based knowledge management, deterministic probability systems, intelligent narrative orchestration, and immersive roleplay – all driven by large language models (LLMs) and FAISS‑accelerated memory.

> *“From a single prompt to a living, breathing world – where every NPC remembers, every action has a chance, and the story never stops.”*

---

## ✨ Wonderful Features at a Glance

| Feature | Description |
|---------|-------------|
| 🏗️ **Layered World Building** | Every entity (character, location, item, faction, event, rule) has three layers: **L1** (classification), **L2** (detailed description), **L3** (secrets). Generate incrementally, resume anytime. |
| 🕸️ **Graph‑First Knowledge** | All relationships stored in a directed graph. Traverse, visualise, and validate connections. **Self‑healing graph** repairs broken links automatically. |
| 🧠 **Self‑Optimising Memory** | FAISS‑accelerated vector memory for NPCs **and** world events. Background consolidation, pruning, clustering, and time‑based partitioning. |
| 🎲 **Probability System** | Deterministic outcomes for combat, persuasion, stealth, romance, investigation, etc. Dynamic parameters (skill, health, mood, environment, luck) with temporary modifiers. No more arbitrary LLM decisions. |
| 💖 **Romance System** | Full romantic relationship management – affection, compatibility, status (crush/dating/engaged/married). Probability‑driven actions: flirt, confess, date, kiss, propose, breakup. |
| 🌱 **Advanced Birth / Isekai** | Probability‑based race, social class, magic affinity, innate talents. Full three‑generation family tree, heirlooms, family secrets. Optional **reincarnation mode** with cheat ability and past‑life memories. |
| 🎭 **Living Narrative Director** | Background agent advances story arcs, villain agendas, NPC interactions, chance events, and scheduled story beats – even when you’re not playing. |
| 💬 **Immersive Roleplay** | Third‑person narrative, NPC dialogue, scene transitions. The LLM **never** speaks or acts for your character. Natural language actions, movement, and slash commands. |
| 📜 **Quest & Social System** | Dynamic quest generation, objective tracking, social simulation between NPCs (alliances, betrayals, arguments). |
| 🌿 **World Evolution** | The Director periodically adds new NPCs, locations, and items based on story progression. The world grows organically. |
| 🌿 **Branching Storylines** | Create alternate branches without touching the main graph – merge them back when ready. |
| 🧠 **Pain Signals** | The system learns from failures – pain keywords trigger warnings, helping the narrative avoid repeating mistakes. |
| 🔌 **Unified CLI & Web UI** | One command (`world newgame`) launches the full experience. Beautiful terminal‑style web interface with real‑time memory, romance, and probability dashboards. |
| 🛠️ **One‑Command New Game** | `world newgame --hints "noble mage half-elf" --isekai` creates a complete world, a unique character with family tree, and starts the web UI. |

---

## 🧱 Architecture Overview (v2)

```
User (CLI / Web UI)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                      world_cli.py (unified)                 │
│   Routes to builder, explorer, intelligence, narrative,     │
│   and new commands: newgame, continue, serve                │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      RoleplayEngine                          │
│  (narrator / NPC / scene agents, probability system,        │
│   romance engine, memory, start resolver)                   │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────┐    ┌────────────────────────────┐
│      StoryEngine         │    │        Director            │
│  (event generation,      │    │ (villains, story planner,  │
│   effect application,    │    │  NPC simulator, tick loop) │
│   probability actions)   │    └──────────────┬─────────────┘
└──────────────┬───────────┘                   │
               │                               │
               ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Unified EntityStore + GraphStore            │
│   O(1) name index, batch saves, mutation callbacks.        │
│   Lazy graph rebuild, branch manager.                      │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     WorldMemory (FAISS)                     │
│   Partitioned storage, embedding queue, write‑behind,      │
│   cognitive pipeline (entity extraction, contradiction,    │
│   pain signals), background optimizer.                     │
└─────────────────────────────────────────────────────────────┘
```

All modules share `world_db/` – everything is persistent, atomic, and crash‑safe.

---

## 🚀 Quick Start (5 minutes)

### 1. Install & Configure

```bash
git clone https://github.com/Eva.E1/BRING.git
cd BRING

# Install dependencies
pip install -r requirements.txt

# For FAISS (highly recommended)
pip install faiss-cpu   # or faiss-gpu if you have CUDA
```

Create a `.env` file (or copy the template):

```ini
cp .env.example .env
```

Edit `.env`:

```ini
# LLM (OpenAI or compatible)
WORLD_LLM_BASE_URL=https://api.openai.com/v1
WORLD_LLM_API_KEY=your_openai_api_key
WORLD_LLM_MODEL=gpt-4o-mini

# Optional: Local embeddings (e.g., BGE‑M3 via LiteLLM or local server)
WORLD_EMBEDDING_BASE_URL=http://localhost:8043/v1
WORLD_EMBEDDING_MODEL=bge-m3

# Database location
WORLD_DB_PATH=./world_db
```

### 2. Build Your First World (or jump straight to a new game)

```bash
# Classic: build world, layers, relationships
python -m world_builder.cli build --episodes 3 --relationships

# Or start a new game immediately (birth wizard + web UI)
python world_cli.py newgame --hints "a young elven ranger" --isekai
```

The `newgame` command:
- Checks system (LLM, FAISS, disk space)
- Prepares world (creates frame if missing)
- Runs the advanced **birth wizard** (probability rolls for race, class, magic, talents)
- Generates a full family tree, heirloom, and family secret
- Schedules childhood milestones (first word, first step, magic awakening)
- Launches the **web UI** at `http://localhost:8000`

### 3. Explore Your World

```bash
# CLI summary
python -m world_builder.cli view summary

# List all characters
python -m world_builder.cli view characters

# Detailed entity view
python -m world_builder.cli view entity "Kaelen" --level 2

# Semantic search
python -m world_explorer.cli search "ancient prophecy" --semantic
```

### 4. Play a Roleplay Session (CLI)

```bash
python -m world_narrative.cli play --character Kaelen --location Silverwood
```

Inside the session:

- **Natural language**: `I search the old chest for clues.`
- **Talk to NPCs**: `talk to Elara "What do you know about the ruins?"`
- **Move**: `go to Riverfall`
- **Probability actions**: `/attack Goblin`, `/persuade Elara "We should help"`, `/stealth`
- **Romance**: `/romance Kaelen Elara` (shows status), `/romance-attempt confess --character Kaelen --target Elara`
- **Slash commands**: `/look`, `/inventory`, `/status`, `/quests`, `/time`, `/save`, `/quit`

The **Director** runs in the background – villains advance, chance events occur, story beats trigger.

### 5. Launch the Web UI (if not already open)

```bash
python world_cli.py serve --port 8000
```

Then open `http://localhost:8000`.  
The UI provides a **terminal‑style** interface with:
- Real‑time memory event feed
- Character and romance dashboards
- Quest tracking
- Probability sparkline
- Full command palette (`Ctrl+K`)

---

## 🗂️ Detailed Module Guides

### 1. 🌍 World Builder (`world_builder`)

**Purpose:** Create and expand the world skeleton.

| Command | Description | Example |
|---------|-------------|---------|
| `build` | Full world generation (resumable). | `python -m world_builder.cli build` |
| `add npc <faction/race>` | Add a new NPC on the fly. | `add npc "Order of the Echo"` |
| `add item <type> [--rarity]` | Add a new item. | `add item weapon --rarity rare` |
| `view entity <name> [--level]` | Show layered data. | `view entity "Kaelen" --level 2` |
| `validate` | Check relationship consistency. | `validate` |
| `repair [--intelligent] [--merge] [--create]` | Fix broken relationships (fuzzy matching + auto‑create). | `repair --merge --create` |

**Key improvement (v2):** Batch saves and lazy graph rebuild drastically reduce I/O.

---

### 2. 🔍 World Explorer (`world_explorer`)

**Purpose:** Navigate the graph, visualise, manage branches, and now includes the **full web UI**.

| Command | Description | Example |
|---------|-------------|---------|
| `show <uid> [--layer l1] [--complete]` | Display entity data (auto‑complete missing layers). | `show "Character:Kaelen" --layer l2` |
| `neighbors <uid> --depth 2` | Show connected nodes. | `neighbors "Character:Kaelen" --depth 2` |
| `path <source> <target>` | Shortest path between entities. | `path "Kaelen" "Silverwood"` |
| `search --semantic <query>` | FAISS‑accelerated semantic search. | `search --semantic "ancient magic sword"` |
| `branch create/switch/merge` | Manage story branches. | `branch create "what-if-kaelen-dies"` |
| `visualize` | Export interactive HTML graph. | `visualize --output world.html` |
| `layer [l1/l2/l3/all]` | Generate missing layers via builder. | `layer l2` |
| `serve` | Start the FastAPI web server (used by `world_cli.py serve`). | `serve --port 8000` |

**New in v2:** The web UI is now the primary interface for `newgame`. It includes real‑time WebSocket feeds for memory and roleplay.

---

### 3. 🧠 World Intelligence (`world_intelligence`)

**Purpose:** Analyse, recommend, and enrich the world automatically.

| Command | Description | Example |
|---------|-------------|---------|
| `analyze` | Centrality, communities, path stats. | `analyze` |
| `recommend` | Suggest missing relationships & new entities. | `recommend` |
| `generate-scene <uid>` | Create narrative scene from a graph cluster. | `generate-scene "Character:Kaelen"` |
| `check-rules [--fix]` | Validate all entities against world rules (LLM). | `check-rules --fix` |
| `expand <uid> [--depth] [--fix-rules]` | Enrich subgraph (complete layers, check rules, generate scene). | `expand "Location:Silverwood" --depth 2` |
| `enrich [--fix-rules]` | **Full pipeline** – layers, relationships, rules, recommendations, duplicates. | `enrich --fix-rules` |
| `deduplicate [--dry-run]` | FAISS‑accelerated duplicate merging. | `deduplicate` |

**v2 performance:** All duplicate detection and relationship repair now use FAISS and tries, making them O(log n) instead of O(n²).

---

### 4. 📖 World Narrative (`world_narrative`)

**Purpose:** Run the living story – director, roleplay, probability, romance, memory, quests.

| Command | Description | Example |
|---------|-------------|---------|
| `newgame` | **One‑command launch** – birth wizard + web UI. | `world newgame --hints "noble mage" --isekai` |
| `continue` | Resume existing game from snapshot or session. | `world continue --session-id mygame` |
| `play` | Start CLI roleplay session. | `play --character Kaelen --session mygame` |
| `tick <ISO_time>` | Manually advance story and generate event. | `tick 2025-01-01T12:00:00` |
| `timeline [--since] [--group]` | Show event log. | `timeline --since 2025-01-01` |
| `schedule <callback> <minutes> <data>` | Schedule future event. | `schedule villain_event 30 '{"villain":"The Shadow"}'` |
| `npc-status <name>` | Show NPC memory, health, mood, goals, inventory. | `npc-status Elara` |
| `director-status` | Show villain progress, story plan. | `director-status` |
| `birth` | Advanced character creator (family tree, isekai). | `birth --hints "half-elf druid" --isekai` |
| `romance-status/attempt/list/gift` | Manage romantic relationships. | `romance-attempt confess --character Kaelen --target Elara` |
| `prob show/list/modify/skills` | Probability system introspection. | `prob show combat --character Kaelen --target Goblin` |
| `memory-maintenance/status/forget/summarise/export/import` | Advanced memory management. | `memory-maintenance --full` |

**Director background loop:** Wakes every 60 real seconds, advances story time by 30 minutes, processes NPC interactions, villain ticks, chance events, and scheduled story beats.

---

### 5. 🎲 Probability System (`world_core/probability`)

Now integrated into `RoleplayEngine` and `StoryEngine`. Used for:

- **Combat** – `/attack`
- **Persuasion** – `/persuade`
- **Stealth** – `/stealth`
- **Intimidation** – `/intimidate`
- **Deception** – `/deception`
- **Romance** – all romance actions
- **Birth** – race, social class, magic affinity, talents
- **Quest objectives** – chance‑based objectives

**Profiles:** combat, persuasion, stealth, romance, investigation, athletics, deception, intimidation, generic, birth_race, birth_social_class, birth_magic_affinity, birth_talent.

**Modifiers:** temporary bonuses/penalties via `/prob modify`.

---

### 6. 💖 Romance System (`world_core/romance`)

Automatically tracks relationships between characters. CLI commands:

- `romance-status --character Kaelen --target Elara`
- `romance-attempt confess --character Kaelen --target Elara --location "Moonlight Garden"`
- `romance-list --status dating`
- `romance-gift --character Kaelen --target Elara --gift "Silver Necklace"`

**Integration:** Romance events are logged to the chronicler and can trigger director story arcs.

---

### 7. 🚀 Professional Launcher (`world_narrative/launcher.py`)

Used internally by `newgame` and `continue`. Features:

- **System check** – verifies LLM, FAISS, disk space.
- **World preparation** – creates world frame if missing.
- **Memory health check** – runs consolidation before start.
- **Birth wizard** – probability rolls + LLM generation.
- **Post‑birth tasks** – repairs relationships, schedules childhood milestones, adds welcome quest.
- **Snapshot save/load** – instantly resume games.

---

### 8. 🔌 World Core (`world_core`)

New components:

- `UnifiedEntityStore` – O(1) name resolution, batch saves, mutation callbacks.
- `EventBus` – decoupled publish/subscribe for all modules.
- `WorldMemory` – FAISS‑based, partitioned, self‑optimising.
- `ProbabilityEngine` – deterministic rolls with modifiers.
- `RomanceEngine` – relationship management.

---

## 🎮 Roleplay Session – In‑Depth Example

### Starting Your First Game

Start a new game with web UI:

```bash
python world_cli.py newgame --hints "a young elven ranger named Kaelen" --isekai
```

The browser opens with a terminal‑style interface.  
You see the opening narrative (birth scene), family tree, and a status panel.

### Basic Interaction Patterns

**Natural Language Actions:**

```
> I look around the forest clearing.

[Narrator] Sunlight filters through the ancient oaks, dappling the mossy ground. A small stream babbles nearby. You notice a worn path leading east, and a strange symbol carved into a stone.
```

**Movement:**

```
> go to Riverfall
> head north through the archway
> climb the old tower stairs
```

**Talking to NPCs:**

```
> talk to Elara "Do you know about the symbol on that stone?"

Elara says: "Ah, that's the mark of the Wardens. They used to guard this forest, but they vanished a century ago. Some say a curse drove them out."
```

**Multi-turn Conversations:**

```
> ask Elara about the Wardens
> follow up with "Where did they go?"
> persuade Elara "We should investigate together"
```

### Probability-Based Actions

All skill-based actions use the deterministic probability system:

```
> /attack Goblin

[Narrator] Kaelen attacks Goblin: success (prob 72%, roll 0.34). The goblin takes 10 damage!
```

**Available Action Types:**

| Action | Command | Description |
|--------|---------|-------------|
| Combat | `/attack <target>` | Physical attack with weapon/unarmed |
| Persuasion | `/persuade <npc> "<argument>"` | Convince someone to help/agree |
| Stealth | `/stealth` | Sneak past enemies or hide |
| Intimidation | `/intimidate <npc>` | Scare or threaten someone |
| Deception | `/deceive <npc> "<lie>"` | Lie convincingly |
| Investigation | `/investigate <object>` | Search for clues/details |
| Athletics | `/athletics <challenge>` | Physical feats (jump, swim, climb) |

### Romance System Deep Dive

Check current relationship status:

```
> /romance-status --character Kaelen --target Elara

💖 Kaelen & Elara
Status: crush
Affection: 55%
Compatibility: 68%
Stage: attraction
```

**Romance Progression Stages:**

1. **Neutral** → No romantic interest yet
2. **Attraction** → Mutual interest detected
3. **Crush** → One-sided strong feelings
4. **Dating** → Officially in a relationship
5. **Engaged** → Promise to marry
6. **Married** → Lifelong commitment

**Romance Actions:**

```
# Attempt to confess feelings
> /romance-attempt confess --character Kaelen --target Elara --location "Moonlight Garden"

✅ Confess result: Kaelen confesses his feelings to Elara amazingly. She accepts!

# Go on a date
> /romance-attempt date --character Kaelen --target Elara --activity "walk by the lake"

# Give a gift (boosts affection)
> /romance-gift --character Kaelen --target Elara --gift "Silver Necklace"

# Propose marriage (requires high affection & dating status)
> /romance-attempt propose --character Kaelen --target Elara --ring "Family Heirloom Ring"
```

**Factors Affecting Romance Success:**

- **Affection Level**: Higher = better success rate
- **Compatibility**: Based on personality traits, values, background
- **Current Mood**: NPCs have dynamic emotional states
- **Location**: Romantic settings provide bonuses
- **Gifts**: Thoughtful gifts boost affection
- **Previous Interactions**: History matters

### Advanced Commands Reference

**Character Status:**

```
> /status
> /inventory
> /quests
> /skills
> /relationships
```

**World Interaction:**

```
> /look          # Describe current location
> /time          # Show current in-game time
> /map           # Display known areas
> /who           # List NPCs in current location
```

**Session Management:**

```
> /save my_adventure    # Save current progress
> /load my_adventure    # Resume saved game
> /export character     # Export character data as JSON
> /quit                 # End session (auto-saves)
```

### Tips for Immersive Roleplay

1. **Use Third Person**: Describe your actions as "Kaelen draws his sword" not "I draw my sword"
2. **Be Specific**: "I carefully examine the lock for tumblers" works better than "I check the door"
3. **Engage with NPCs**: Ask follow-up questions, remember their stories
4. **Think About Consequences**: Actions affect reputation, relationships, and story direction
5. **Use the Environment**: Interact with objects, use terrain advantages
6. **Let the Story Unfold**: Sometimes failure creates better narratives than success

### Common Roleplay Scenarios

**Combat Encounter:**

```
> /attack the goblin raiders
> take cover behind the stone wall
> /intimidate the remaining goblins "Surrender or die!"
> loot the goblin chief's body
```

**Social Intrigue:**

```
> attend the noble's banquet
> talk to Lord Blackwood "Your reputation precedes you"
> /persuade Blackwood "We share common interests here"
> /deceive the guard "I'm a visiting merchant from the south"
> sneak into the private chambers
> /investigate the locked desk
```

**Romantic Subplot:**

```
> invite Elara to dinner at the inn
> /romance-gift --target Elara --gift "bouquet of moonflowers"
> talk to Elara "I've been thinking about what you said..."
> /romance-attempt confess --target Elara
```

**Mystery Investigation:**

```
> /investigate the crime scene
> examine the broken window
> talk to the witness "What did you see that night?"
> /investigate the muddy footprints
> connect the clues in my journal
> confront the suspect with the evidence
```

---

## 🧪 Advanced Usage & Tips

### 📌 Branching Storylines

Create alternate timelines without affecting the main story:

```bash
# Create a new branch
world branch create what-if-kaelen-dies

# Switch to the branch
world branch switch what-if-kaelen-dies

# Make changes (delete edges, add nodes, play differently)
# ...

# Merge back to main timeline when ready
world branch merge what-if-kaelen-dies
```

**Use Cases:**
- Test different story outcomes
- Explore "what if" scenarios
- Run parallel campaigns with same world
- Experiment with character decisions

### 📌 Starting Point Resolution

Begin your game at any point with natural language:

```bash
world narrative play --start "as Kaelen in the Silverwood forest at dawn, just after a storm"
```

The system will:
1. Locate relevant entities (Kaelen, Silverwood forest)
2. Set appropriate time and weather conditions
3. Generate an opening scene matching the context
4. Position NPCs based on their schedules and relationships

**Examples:**
```bash
# Start mid-action
world narrative play --start "during a tavern brawl, Kaelen is outnumbered"

# Start at a specific event
world narrative play --start "at the royal ball, moments before the assassination attempt"

# Start with a mystery
world narrative play --start "waking up in a locked room with no memory of how you got here"
```

### 📌 Probability Modifiers

Temporarily boost or penalize skill checks:

```bash
# Give Kaelen a temporary +20% combat boost for 5 minutes (300 seconds)
world narrative prob modify Kaelen combat_skill 0.2 --duration 300

# Add a situational penalty (-15% to stealth due to heavy armor)
world narrative prob modify Kaelen stealth -0.15 --reason "wearing plate armor"

# List all active modifiers
world narrative prob list --character Kaelen

# Remove a specific modifier
world narrative prob modify Kaelen combat_skill --remove

# Clear all modifiers for a character
world narrative prob modify Kaelen --clear-all
```

**Common Modifier Scenarios:**
- **Buffs**: Magic spells, potions, morale bonuses, terrain advantages
- **Debuffs**: Injuries, fatigue, curses, environmental hazards
- **Situational**: Night vision bonuses, ranged penalties in melee, language barriers

### 📌 Memory Maintenance

Manage the AI's long-term memory system:

```bash
# Full maintenance (prune old memories, merge similar events, archive)
world narrative memory-maintenance --full

# Check memory status and statistics
world narrative memory-status

# Forget low-importance memories from last 30 days
world narrative memory-forget 30 --min-importance 0.2

# Summarize memories tagged with specific keywords
world narrative memory-summarise --tag "isekai"
world narrative memory-summarise --tag "villain plot"

# Export memories for backup or analysis
world narrative memory-export --output memories_backup.json

# Import memories from another session
world narrative memory-import --file memories_from_other_game.json
```

**Memory System Features:**
- **Automatic Consolidation**: Similar events merge into cohesive narratives
- **Importance Scoring**: Critical events preserved, trivial details pruned
- **Time-Based Partitioning**: Recent memories more accessible than old ones
- **Semantic Search**: Find memories by meaning, not just keywords

### 📌 Enriching an Existing World

Automatically improve world consistency and depth:

```bash
# Full enrichment pipeline (recommended)
world intel enrich --fix-rules

# Individual enrichment steps
world intel check-rules --fix          # Validate entity consistency
world intel recommend                  # Suggest new relationships
world intel deduplicate                # Merge duplicate entities
world intel expand "Location:Silverwood" --depth 2  # Flesh out subgraph
```

**What Enrichment Does:**
- Completes missing L1/L2/L3 layers for entities
- Detects and fixes contradictory information
- Identifies isolated nodes and suggests connections
- Merges near-duplicate characters/locations
- Generates missing backstory elements
- Validates all entities against world rules

### 📌 Visualising the Graph

Export and explore your world as an interactive graph:

```bash
# Generate interactive HTML visualization
world explore visualize --output myworld.html

# Open in browser (Linux/Mac)
xdg-open myworld.html    # Linux
open myworld.html        # Mac
start myworld.html       # Windows
```

**Visualization Features:**
- Zoomable, pannable network graph
- Color-coded entity types (characters, locations, items, factions)
- Click nodes to see full details
- Highlight relationships and connection paths
- Filter by entity type or relationship type
- Search and highlight specific entities

### 📌 Running the API Server Separately

Start the backend server for custom integrations:

```bash
world serve --port 8000
```

**Available API Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/launch` | POST | Create new game session |
| `/api/continue` | POST | Resume existing session |
| `/ws/roleplay/{session_id}` | WebSocket | Real-time narrative stream |
| `/ws/memory` | WebSocket | Real-time memory event feed |
| `/api/romance/status` | GET | Query romance relationships |
| `/api/romance/attempt` | POST | Execute romance action |
| `/api/probability/show` | GET | Get success probabilities |
| `/api/probability/roll` | POST | Perform probability check |
| `/api/maintenance/memory` | POST | Trigger memory optimization |
| `/api/character/{id}` | GET | Retrieve character data |
| `/api/location/{id}` | GET | Retrieve location data |
| `/api/quest/active` | GET | List active quests |
| `/api/timeline` | GET | Get story event log |

**Example API Usage:**

```bash
# Start a new game via API
curl -X POST http://localhost:8000/api/launch \
  -H "Content-Type: application/json" \
  -d '{"hints": "dwarven cleric", "isekai": false}'

# Query romance status
curl http://localhost:8000/api/romance/status?character=Kaelen\&target=Elara

# Perform probability check
curl -X POST http://localhost:8000/api/probability/roll \
  -H "Content-Type: application/json" \
  -d '{"character": "Kaelen", "action": "persuade", "target": "Guard"}'
```

### 📌 Director Configuration

Customize the background story director behavior:

```bash
# View current director status
world narrative director-status

# Adjust tick rate (default: 60 real seconds = 30 game minutes)
# Edit .env: WORLD_DIRECT_TICK_INTERVAL=120

# Force immediate story advancement
world narrative tick now

# Schedule a custom event
world narrative schedule villain_event 30 '{"villain":"The Shadow","location":"Dark Tower"}'
```

**Director Responsibilities:**
- Advances story time automatically
- Processes NPC daily routines and interactions
- Triggers villain plot progression
- Generates random encounters and events
- Manages quest updates and completions
- Evolves the world (new NPCs, locations, items)

### 📌 Debugging & Diagnostics

Tools for troubleshooting and development:

```bash
# View detailed entity information
world explore show "Character:Kaelen" --complete

# Trace relationship paths
world explore path "Kaelen" "Ancient Prophecy" --depth 3

# Check graph health
world builder validate

# Repair broken relationships
world builder repair --intelligent --merge --create

# View system performance stats
world narrative memory-status --verbose

# Export session logs for debugging
world narrative export-session --format json --output debug_log.json
```

---

## 🛠️ Configuration Reference

All settings via environment variables (`.env`).

| Category | Variable | Default | Description |
|----------|----------|---------|-------------|
| **LLM** | `WORLD_LLM_BASE_URL` | `""` | LLM API endpoint (OpenAI‑compatible). |
| | `WORLD_LLM_API_KEY` | `""` | API key. |
| | `WORLD_LLM_MODEL` | `gpt-4o-mini` | Model name. |
| | `WORLD_LLM_MAX_RETRIES` | `3` | Retries on failure. |
| | `WORLD_LLM_MAX_CONCURRENT` | `8` | Concurrent LLM calls. |
| | `WORLD_LLM_TIMEOUT` | `120.0` | Total request timeout (seconds). |
| | `WORLD_LLM_MAX_TOKENS` | `4096` | Max tokens per response. |
| | `WORLD_LLM_TEMPERATURE` | `0.7` | Sampling temperature. |
| **Embeddings** | `WORLD_EMBEDDING_BASE_URL` | `""` | Embedding API endpoint. |
| | `WORLD_EMBEDDING_API_KEY` | `""` | Embedding API key (if separate from LLM). |
| | `WORLD_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model. |
| **Paths** | `WORLD_DB_PATH` | `./world_db` | Database directory. |
| **Server** | `WORLD_SERVER_HOST` | `127.0.0.1` | Web server host. |
| | `WORLD_SERVER_PORT` | `8000` | Web server port. |
| | `WORLD_SERVER_RELOAD` | `false` | Enable auto‑reload on code changes. |
| **Behaviour** | `WORLD_AUTO_HEAL` | `true` | Auto‑repair graph on explorer boot. |
| **Probability** | (modifiers saved in `world_db/probability_modifiers.json`) | |
| **Romance** | (data stored in `world_db/romance/`) | |

---

## 📁 Full Project Tree (Abridged)

```
BRING/
├── world_builder/          # World generation
│   ├── builder.py          # Main orchestrator (batch saves, event bus)
│   ├── cli.py              # Typer CLI
│   ├── generator.py        # LLM prompt calls
│   ├── graph_manager.py    # Unified API over EntityStore
│   └── ...
├── world_explorer/         # Graph navigation & web UI
│   ├── cli.py
│   ├── store.py            # GraphStore with unified store
│   ├── navigator.py        # Queries (neighbors, path, search)
│   ├── branch_manager.py
│   ├── api.py              # FastAPI (serves UI + REST + WebSocket)
│   ├── templates.py        # Inline HTML/JS UI
│   └── routes/             # Modular API routes
├── world_intelligence/     # Analysis & enrichment (FAISS accelerated)
│   ├── cli.py
│   ├── graph_analyzer.py
│   ├── recommender.py
│   ├── rule_checker.py
│   ├── duplicate_detector.py (FAISS)
│   ├── relationship_repairer.py (Trie + fuzzy)
│   └── pipeline.py
├── world_narrative/        # Story & roleplay
│   ├── cli.py (includes newgame, continue, romance, prob)
│   ├── context.py          # Dependency injection (memory, probability, romance)
│   ├── story_engine.py
│   ├── director.py         # Unified background director
│   ├── memory_optimized.py # NPC memory
│   ├── birth.py            # Advanced character creation (family tree, isekai)
│   ├── launcher.py         # Professional game launcher
│   └── ...
├── world_engine/           # Roleplay agents (probability actions)
├── world_director/         # Task queue, arcs, evolution
├── world_core/             # Shared infrastructure
│   ├── models.py           # LayeredProfile, EntityNode, WorldFrame
│   ├── store.py            # UnifiedEntityStore (O(1) lookups)
│   ├── event_bus.py        # Async pub/sub
│   ├── history_manager.py  # Persistent session turns
│   ├── probability/        # Probability engine & profiles
│   ├── romance/            # Romance engine & models
│   └── memory/             # FAISS‑based self‑optimising memory
│       ├── world_memory.py
│       ├── optimizer.py
│       ├── partition.py
│       └── ...
└── world_db/               # Persistent data (auto‑created)
```

---

## 🤝 Contributing

We welcome contributions! Please:

1. Open an issue describing the change.
2. Fork the repo and create a feature branch.
3. Add tests for new features.
4. Run `black` and `isort` (if configured).
5. Submit a pull request.

**Development setup:**

```bash
git clone https://github.com/Eva.E1/BRING.git
cd BRING
pip install -r requirements.txt
pip install faiss-cpu
cp .env.example .env
```

**Testing the new game pipeline:**

```bash
python world_cli.py newgame --hints "test" --no-browser
python test_integration.py
```

---

## 📜 License

[Apache 2.0](LICENSE)

---

**Enjoy building and living in your worlds with BRING v2!**  
*May your stories be legendary.*
