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

Start a new game with web UI:

```bash
python world_cli.py newgame --hints "a young elven ranger named Kaelen" --isekai
```

The browser opens with a terminal‑style interface.  
You see the opening narrative (birth scene), family tree, and a status panel.

Now type actions in the web UI input box:

```
> I look around the forest clearing.

[Narrator] Sunlight filters through the ancient oaks, dappling the mossy ground. A small stream babbles nearby. You notice a worn path leading east, and a strange symbol carved into a stone.
```

Talk to an NPC:

```
> talk to Elara "Do you know about the symbol on that stone?"

Elara says: "Ah, that's the mark of the Wardens. They used to guard this forest, but they vanished a century ago. Some say a curse drove them out."
```

Use probability actions:

```
> /attack Goblin

[Narrator] Kaelen attacks Goblin: success (prob 72%, roll 0.34). The goblin takes 10 damage!
```

Check romance status:

```
> /romance-status --character Kaelen --target Elara

💖 Kaelen & Elara
Status: crush
Affection: 55%
Compatibility: 68%
Stage: attraction
```

Attempt a confession:

```
> /romance-attempt confess --character Kaelen --target Elara --location "Moonlight Garden"

✅ Confess result: Kaelen confesses his feelings to Elara amazingly. She accepts!
```

The relationship updates to `dating`.

---

## 🧪 Advanced Usage & Tips

### 📌 Branching Storylines

```bash
world branch create what-if-kaelen-dies
world branch switch what-if-kaelen-dies
# Make changes (delete edges, add nodes)
world branch merge what-if-kaelen-dies
```

### 📌 Starting Point Resolution (CLI)

```bash
world narrative play --start "as Kaelen in the Silverwood forest at dawn, just after a storm"
```

### 📌 Probability Modifiers

Give Kaelen a temporary +20% combat boost for 5 minutes:

```bash
world narrative prob modify Kaelen combat_skill 0.2 --duration 300
```

### 📌 Memory Maintenance

```bash
world narrative memory-maintenance --full   # prune, merge, archive
world narrative memory-status
world narrative memory-forget 30 --min-importance 0.2
world narrative memory-summarise --tag "isekai"
```

### 📌 Enriching an Existing World

```bash
world intel enrich --fix-rules
```

### 📌 Visualising the Graph

```bash
world explore visualize --output myworld.html
# open myworld.html in a browser
```

### 📌 Running the API Server Separately

```bash
world serve --port 8000
```

The API includes endpoints for:
- `/api/launch` – create new game
- `/api/continue` – resume session
- `/ws/roleplay/{session_id}` – real‑time narrative WebSocket
- `/ws/memory` – real‑time memory event stream
- `/api/romance/...` – romance queries
- `/api/probability/...` – probability queries
- `/api/maintenance/...` – trigger maintenance

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
