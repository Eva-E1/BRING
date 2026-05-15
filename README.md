# 🌟 BRING – Building Rich Interactive Narrative Games

**BRING** is a modular, AI‑powered platform for building, exploring, and **living** in persistent fantasy worlds.  
It combines generative world construction, graph‑based knowledge management, intelligent narrative orchestration, and immersive roleplay – all driven by large language models (LLMs).

> *“From a single prompt to a living, breathing world – where every NPC remembers, every rule matters, and the story never stops.”*

---

## ✨ Wonderful Features at a Glance

| Feature | Description |
|---------|-------------|
| 🏗️ **Layered World Building** | Every entity (character, location, item, faction, event, rule) has three layers: **L1** (classification), **L2** (detailed description), **L3** (secrets). Generate them incrementally, resume anytime. |
| 🕸️ **Graph‑First Knowledge** | All relationships are stored in a directed graph. Traverse, visualise, and validate connections. Self‑healing graph repairs broken links automatically. |
| 🧠 **Intelligent Enrichment** | Social network analysis, missing relationship recommendations, rule violation detection & auto‑fix, duplicate merging, subgraph expansion – all powered by embeddings and graph algorithms. |
| 🎭 **Living Narrative Director** | Background agent advances story arcs, villain agendas, NPC interactions, chance events, and scheduled story beats – even when you’re not playing. |
| 💬 **Immersive Roleplay** | Third‑person narrative, NPC dialogue, scene transitions. The LLM **never** speaks or acts for your character. Supports natural language actions, movement, and slash commands. |
| 🧠 **NPC Memory** | Each NPC has episodic (short‑term & long‑term) and semantic memory, with background consolidation and embedding‑based retrieval. NPCs remember past interactions, form relationships, and evolve. |
| 📜 **Quest & Social System** | Dynamic quest generation, objective tracking, social simulation between NPCs (alliances, betrayals, arguments). |
| 🌿 **World Evolution** | The Director periodically adds new NPCs, locations, and items based on story progression. The world grows organically. |
| 🌿 **Branching Storylines** | Create alternate branches without touching the main graph – merge them back when ready. |
| 🔌 **Unified CLI & API** | All functionality exposed via rich command‑line interfaces (`typer` + `rich`) and a FastAPI web API for the explorer. |

---

## 🧱 Architecture Overview

```
User (CLI / API)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                     world_narrative.cli                      │
│  (play, tick, timeline, director commands, newborn start)   │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      RoleplayEngine                          │
│  (narrator / NPC / scene agents, memory, start resolver)    │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────┐    ┌────────────────────────────┐
│      StoryEngine         │    │        Director            │
│  (event generation,      │    │ (villains, story planner,  │
│   effect application)    │    │  NPC simulator, tick loop) │
└──────────────┬───────────┘    └──────────────┬─────────────┘
               │                               │
               ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│                  OptimizedMemoryStore                        │
│  (episodic + semantic memory for NPCs, embeddings,          │
│   background consolidation)                                 │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      GraphManager + GraphStore               │
│   (entities.json, graph engine, NameIndex, branch manager)  │
└─────────────────────────────┬───────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                        world_builder                         │
│   (WorldBuilder, WorldGenerator, LLMClient, prompts)        │
└─────────────────────────────────────────────────────────────┘
```

All modules share a common database directory (`world_db/`) – everything is persistent.

---

## 🚀 Quick Start (5 minutes)

### 1. Install & Configure

```bash
git clone https://github.com/your-org/bring.git
cd bring

# Install dependencies (example – adjust per your environment)
pip install -r world_builder/requirements.txt \
            -r world_explorer/requirements.txt \
            -r world_intelligence/requirements.txt
```

Create a `.env` file:

```ini
LLM_API_KEY=your_openai_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

Optional for semantic search (uses local BGE‑M3 or any OpenAI‑compatible embeddings API):

```ini
EMBEDDING_BASE_URL=http://localhost:8043/v1
EMBEDDING_MODEL_NAME=bge-m3
```

### 2. Build Your First World

```bash
python -m world_builder.cli build --episodes 3 --relationships
```

This generates a complete world frame, expands L2/L3 for all entities, infers relationships, and writes three narrative scenes.

### 3. Explore the World

```bash
# Summary
python -m world_builder.cli view summary

# List all characters
python -m world_builder.cli view characters

# Detailed view of an entity
python -m world_builder.cli view entity "Kaelen"
```

### 4. Play a Roleplay Session

```bash
python -m world_narrative.cli play --character Kaelen --location "Silverwood"
```

Inside the session:

- Describe your action: `I search the old chest for clues.`
- Talk to NPCs: `talk to Elara "What do you know about the ruins?"`
- Move: `go to Riverfall`
- Slash commands: `/look`, `/inventory`, `/status`, `/quests`, `/time`, `/save`, `/quit`

The **Director** works in the background – advancing villains, generating chance events, and evolving the world.

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
| `search <query>` | Text search across entities. | `search "dragon"` |
| `validate` | Check relationship consistency. | `validate` |

**Key feature:** Resumable layer expansion. If the LLM fails or you interrupt, running `build` again will skip already‑completed layers.

### 2. 🔍 World Explorer (`world_explorer`)

**Purpose:** Navigate the graph, visualise, and manage branches.

| Command | Description | Example |
|---------|-------------|---------|
| `show <uid> [--layer l1] [--complete]` | Display entity data. | `show "Character:Kaelen" --layer l2` |
| `neighbors <uid> --depth 2` | Show connected nodes. | `neighbors "Character:Kaelen" --depth 2` |
| `path <source> <target>` | Shortest path between entities. | `path "Kaelen" "Silverwood"` |
| `search --semantic <query>` | Embedding‑based search. | `search --semantic "ancient magic sword"` |
| `branch create/switch/merge` | Manage story branches. | `branch create "what-if-kaelen-dies"` |
| `visualize` | Export interactive HTML graph (`pyvis`). | `visualize --output world.html` |
| `build [l1/l2/l3/all]` | Generate missing layers via builder. | `build l2` |

**Self‑healing graph:** On boot, the validator automatically repairs broken references, adds placeholder nodes for missing targets, and merges duplicates.

### 3. 🧠 World Intelligence (`world_intelligence`)

**Purpose:** Analyse, recommend, and enrich the world automatically.

| Command | Description | Example |
|---------|-------------|---------|
| `analyze` | Centrality, communities, path stats. | `analyze` |
| `recommend` | Suggest missing relationships & new entities. | `recommend` |
| `generate-scene <uid>` | Create narrative scene from a graph cluster. | `generate-scene "Character:Kaelen"` |
| `check-rules [--fix]` | Validate all entities against world rules. | `check-rules --fix` |
| `expand <uid> [--depth] [--fix-rules]` | Enrich subgraph (complete layers, check rules, generate scene). | `expand "Location:Silverwood" --depth 2` |
| `enrich [--fix-rules]` | **Full pipeline** – layers, relationships, rules, recommendations, duplicates. | `enrich --fix-rules` |
| `deduplicate [--dry-run]` | Merge duplicate entities via embeddings. | `deduplicate` |

**Rule checking:** Uses LLM to check each entity's L2/L3 against world rules (e.g., “No magic in the capital”). Can auto‑fix violations.

### 4. 📖 World Narrative (`world_narrative`)

**Purpose:** Run the living story – director, roleplay, memory, quests.

| Command | Description | Example |
|---------|-------------|---------|
| `play` | Start interactive roleplay session. | `play --character Kaelen --session mygame` |
| `tick <ISO_time>` | Manually advance story and generate event. | `tick 2025-01-01T12:00:00` |
| `timeline [--since] [--group]` | Show event log. | `timeline --since 2025-01-01` |
| `schedule <callback> <minutes> <data>` | Schedule future event. | `schedule villain_event 30 '{"villain":"The Shadow"}'` |
| `npc-status <name>` | Show NPC memory and state. | `npc-status Elara` |
| `director-status` | Show villain progress, story plan. | `director-status` |
| `newborn-play <character>` | Reset character to newborn (no memories/relationships). | `newborn-play "Kaelen"` |

**Director background loop:** Wakes every 60 real seconds, advances story time by 30 minutes, processes NPC interactions, villain ticks, chance events, and scheduled story beats.

### 5. ⚙️ World Engine (`world_engine`)

**Purpose:** Low‑level roleplay agents and session logic. Not directly called from CLI – used internally by `world_narrative.cli play`.

Components:
- `NarratorAgent` – describes environment, NPC actions, consequences.
- `NPCAgent` – generates dialogue in character.
- `SceneAgent` – handles travel descriptions.
- `DirectorAgent` – injects story beats into ongoing narrative.
- `StartResolver` – parses natural language starting points (“as Kaelen in Silverwood at dawn”).

### 6. 🧭 World Director (`world_director`)

**Purpose:** Background automation – task queue, story arcs, world evolution.

Not exposed directly; used by `world_narrative.Director`.

Features:
- `AgentCoordinator` – priority queue for LLM tasks (user = HIGH, background = LOW).
- `StoryArcManager` – tracks multi‑phase arcs for characters/factions.
- `WorldEvolver` – periodically adds new NPCs, locations, items (10‑20% chance per tick).
- `NewbornScenario` – wipes a character’s memory and graph edges.

### 7. 🔌 World Core (`world_core`)

**Purpose:** Global LLM queue with priority handling. Used by all modules to prevent API overloading.

---

## 🎮 Roleplay Session – In‑Depth Example

Start a session as Kaelen in Silverwood:

```bash
python -m world_narrative.cli play --character Kaelen --location Silverwood --session myadventure
```

You see:

```
World: Eldoria
Character: Kaelen
Location: Silverwood
You control your character. The narrator describes everything else.
Type /help for commands, /save to persist, /quit to exit.

You>
```

Now type actions:

```
You> I look around the forest clearing.

Narrator: Sunlight filters through the ancient oaks, dappling the mossy ground.
A small stream babbles nearby. You notice a worn path leading east, and
a strange symbol carved into a stone.
```

Talk to an NPC:

```
You> talk to Elara "Do you know about the symbol on that stone?"

Elara says: "Ah, that's the mark of the Wardens. They used to guard this forest,
but they vanished a century ago. Some say a curse drove them out."
```

Move:

```
You> go east

Narrator: You follow the path deeper into the woods. The trees grow thicker,
and the air turns cool. After ten minutes, you reach a ruined tower covered in ivy.
```

Use slash commands:

```
You> /inventory
You are carrying: a rusty dagger, a waterskin

You> /quests
Active Quests:
- The Lost Wardens: Find out what happened to the Wardens of Silverwood.
```

The Director may inject a story beat:

```
Narrator: Suddenly, a twig snaps behind you. You spin around and see a hooded figure
watching from the shadows. They vanish before you can react.
```

Save and quit later:

```
You> /save
Session saved.

You> /quit
Goodbye!
```

To resume:

```bash
python -m world_narrative.cli play --session myadventure
```

---

## 🧪 Advanced Usage & Tips

### 📌 Branching Storylines

Create an alternate branch for “what if Kaelen died”:

```bash
python -m world_explorer.cli branch create what-if-kaelen-dies
python -m world_explorer.cli branch switch what-if-kaelen-dies
# Make changes (delete edges, add nodes) – they affect only this branch
python -m world_explorer.cli branch merge what-if-kaelen-dies   # apply to main
```

### 📌 Starting Point Resolution

Instead of `--character` and `--location`, you can use a natural language string:

```bash
python -m world_narrative.cli play --start "as Kaelen in the Silverwood forest at dawn, just after a storm"
```

The `StartResolver` will parse this and set up the session accordingly.

### 📌 Background Director Control

- `force-chance-event` – trigger a random event immediately.
- `force-beat` – force a major story beat (cooldown applies).
- `schedule` – schedule any callback (e.g., `villain_event`, `npc_event`, `quest_event`).

### 📌 Enriching an Existing World

If your world feels sparse, run:

```bash
python -m world_intelligence.cli enrich --fix-rules
```

This will complete all missing L2/L3, generate missing relationships, fix rule violations, and merge duplicates. Your world becomes richer without manual editing.

### 📌 Visualising the Graph

Generate an interactive HTML graph (requires `pyvis`):

```bash
python -m world_explorer.cli visualize --output myworld.html
# open myworld.html in a browser
```

---

## 🛠️ Configuration Reference

All settings via environment variables (`.env` file).

| Category | Variable | Default | Description |
|----------|----------|---------|-------------|
| **LLM** | `LLM_API_KEY` | `""` | API key (OpenAI or compatible). |
| | `LLM_BASE_URL` | `https://api.openai.com/v1` | Endpoint. |
| | `LLM_MODEL` | `gpt-4o-mini` | Model name. |
| | `LLM_MAX_RETRIES` | `5` | Retries on failure. |
| | `LLM_RATE_LIMIT_RPS` | `3.0` | Requests per second. |
| | `LLM_MAX_CONCURRENT` | `8` | Concurrent LLM calls. |
| | `LLM_TIMEOUT` | `120.0` | Total request timeout (seconds). |
| **Embeddings** | `EMBEDDING_BASE_URL` | `http://localhost:8043/v1` | Embedding API. |
| | `EMBEDDING_MODEL_NAME` | `bge-m3` | Embedding model. |
| | `EMBEDDING_BATCH_SIZE` | `64` | Batch size for API calls. |
| **Paths** | `WORLD_DB_PATH` | `./world_db` | Database directory. |
| **Behaviour** | `AUTO_HEAL` | `True` | Auto‑repair graph on explorer boot. |
| | `DEAD_REF_TYPE` | `BROKEN` | Edge type for unresolvable references. |

---

## 📁 Full Project Tree (Abridged)

```
bring/
├── world_builder/          # World generation
│   ├── builder.py          # Main orchestrator
│   ├── cli.py              # Typer CLI
│   ├── generator.py        # LLM prompt calls
│   ├── graph_manager.py    # Unified API over EntityStore + GraphEngine
│   └── ...
├── world_explorer/         # Graph navigation
│   ├── cli.py              # Explore, branch, visualise
│   ├── store.py            # GraphStore boot & caching
│   ├── navigator.py        # Queries (neighbors, path, search)
│   ├── branch_manager.py   # Branch overlay
│   └── ...
├── world_intelligence/     # Analysis & enrichment
│   ├── cli.py
│   ├── graph_analyzer.py
│   ├── recommender.py
│   ├── rule_checker.py
│   ├── duplicate_detector.py
│   └── pipeline.py
├── world_narrative/        # Story & roleplay
│   ├── cli.py
│   ├── context.py          # Dependency injection
│   ├── story_engine.py
│   ├── director.py         # Unified background director
│   ├── memory_optimized.py # NPC memory with embeddings
│   ├── user_agent.py       # Session handling
│   └── ...
├── world_engine/           # Roleplay agents
├── world_director/         # Task queue, arcs, evolution
├── world_core/             # LLM queue
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



**Enjoy building and living in your worlds with BRING!**  
*May your stories be legendary.*
