<div align="center">

<img src="assets/poster.png" alt="BRING Project Poster" width="600" style="border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);"/>

# 🌌 BRING Project

**B**ackground AI | **R**emembrance | **I**nteractive | **N**arrative | **G**raph

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](#)
[![Status](https://img.shields.io/badge/Status-Active%20Development-orange.svg)](#)
[![Architecture](https://img.shields.io/badge/Architecture-Multi--Agent-purple.svg)](#)

> **BRING** is a multi-agent framework for AI-driven role-play, narrative orchestration, and graph-based long-term memory. It combines LLM routing, structured extraction, point-in-time memory retrieval, and portable graph databases so story worlds can stay coherent, reusable, and shareable.

</div>

---

## 📑 Table of Contents
- [The Core Problem](#-the-core-problem-flaws-in-current-llms)
- [Our Solution](#-our-solution-a-living-graph-driven-ecosystem)
- [System Architecture](#-system-architecture-the-tri-layer-design)
- [Project Capabilities](#-project-capabilities)
- [Technical Status](#-technical-status--architecture)
- [Getting Started](#-getting-started)
- [CLI Workflow](#-cli-workflow)
- [Portable Memory Databases](#-portable-memory-databases)
- [Dataset Pipeline: Mushoku Tensei](#-dataset-pipeline-mushoku-tensei)
- [Project Layout](#-project-layout)
- [Contributing](#-contributing)

---

## 🛑 The Core Problem (Flaws in Current LLMs)

Current AI models suffer from two major structural weaknesses when it comes to role-playing and world-building:

1. **Context Degradation & Hallucination**  
   As conversations grow longer, the AI tends to forget the established rules of the world. It hallucinates facts and ultimately breaks narrative consistency.

2. **Passive Storytelling & The "People-Pleasing" Flaw**  
   Most models are reactive. They converse, but they do not meaningfully drive the plot, escalate tension, or maintain independent world momentum unless the user constantly pushes them to do so.

---

## 💡 Our Solution: A Living, Graph-Driven Ecosystem

The core philosophy of **BRING** is an invisible background framework that keeps world logic, memory, and narrative pressure active at all times. Instead of relying on one monolithic agent, BRING coordinates multiple LLM-driven roles with a graph-backed memory layer.

To manage large-scale lore, BRING does not store information linearly. It uses a **graph-based memory system** that supports structured extraction, targeted retrieval, and bi-temporal reasoning. This allows the framework to inject relevant knowledge when needed instead of flooding prompts with entire histories.

---

## 🧠 System Architecture (The Tri-Layer Design)

BRING is designed around three complementary agent layers:

<details open>
<summary><b>🎭 Layer 1: The Actor (Frontend UI / Interaction LLM)</b></summary>
This is the frontline agent that interacts directly with the user.

- **Role:** Executes the story, role-plays characters, and manages natural dialogue.
- **Focus:** Voice, expression, responsiveness, and character-consistent delivery.
- **Implementation:** `memory/actor.py` provides `ActorContext`, a point-in-time knowledge query interface for a specific character.
</details>

<details open>
<summary><b>🎬 Layer 2: The Director & Antagonist (Background Orchestrator LLM)</b></summary>
The system-level planner operating behind the scenes.

- **Role:** Maintains the narrative arc, enforces world rules, and injects pressure into the story.
- **Special Feature:** This layer can function as the **Antagonist**, generating unexpected events, steering villains, and preserving dramatic tension.
- **Implementation:** `memory/director.py` provides `Director`, which combines current state and relevant history into narrative context.
</details>

<details open>
<summary><b>⏳ Layer 3: The Chronicler (Timeline & Memory LLM)</b></summary>
A dedicated memory/timekeeper layer.

- **Role:** Logs events, keeps chronology stable, and answers what-was-known-when queries.
- **Focus:** Prevents temporal contradictions and supports bi-temporal story memory.
- **Implementation:** `memory/chronicler.py` works on top of Graphiti + Kuzu to query state at a given story time.
</details>

---

## ✨ Project Capabilities

BRING already includes several coordinated features that are easy to miss if you only look at the core modules:

- **Shared root configuration** through `.bring.env`
- **Independent embedding provider configuration** separate from the main LLM provider
- **Async LLM gateway** with retries, caching, and structured output support
- **Bi-temporal graph memory** with normalized search and timeline queries
- **Portable multi-database memory** with isolated namespaces and manifests
- **Interactive CLI** for guided setup and database management
- **Reference dataset ingestion pipeline** in `mushoku_tensei/`
- **Archive export/import/clone workflows** for sharing databases across projects

---

## 🛠 Technical Status & Architecture

The project is being developed with a modular architecture and a strong separation between provider access, memory, ingestion, and orchestration.

### ✅ Completed Modules

| Module | Path | Description |
| :--- | :--- | :--- |
| **LLM Gateway** | `llm_gateway/` | Async-first provider abstraction with caching, retries, structured output, and multi-provider support. |
| **Gateway Settings** | `llm_gateway/settings.py` | Root-config driven provider resolution for both text generation and embeddings. |
| **Memory Engine** | `memory/engine.py` | Lifecycle, ingestion, search orchestration, and metadata-aware extraction reuse. |
| **Graph Wrapper** | `memory/graph.py` | Initializes Kuzu + Graphiti and wires in custom LLM/embedder adapters. |
| **Portable Databases** | `memory/database.py` | Database manifests, archive export/import, and safe clone workflows. |
| **Ontology** | `memory/ontology.py` | Typed entity and relationship models for graph ingestion. |
| **Extraction** | `memory/extraction.py` | Structured ontology-safe extraction using the gateway. |
| **Bi-temporal Memory** | `memory/chronicler.py` | Point-in-time queries and timeline-aware access patterns. |
| **Agent Contexts** | `memory/actor.py`, `memory/director.py` | Role-specific narrative and memory retrieval helpers. |
| **Maintenance** | `memory/maintenance.py` | Batch deduplication, search result normalization, and scoped cache invalidation. |
| **Project CLI** | `bring_cli.py` | Guided setup, config inspection, and database lifecycle commands. |
| **Shared Config Helpers** | `bring_settings.py`, `bring_cli_support.py` | Clean settings parsing, smart defaults, provider inference, and env generation. |
| **Dataset Pipeline** | `mushoku_tensei/` | PDF ingestion, segmentation, time estimation, extended ontology extraction, and portable DB packaging. |

### 🔧 Tech Stack & Foundation

- ⚡ **`any-llm`** + **`instructor`** for provider abstraction and structured output
- 🗄️ **`graphiti-core`** + **`kuzu`** for embedded graph memory
- 🧰 **`typer`** + **`rich`** for smart terminal UX, progress bars, and live logging
- 🛡️ **`pydantic`** for typed config and ontology models
- 🔄 **`tenacity`** for retry handling
- 🧮 **`tiktoken`** for token estimation
- 📄 **`pdfplumber`** for PDF dataset ingestion
- 🚀 **`asyncio`** throughout the runtime design

### 🚧 Work in Progress

- [ ] **Full agent loops:** Actor and Director are context-capable, but not yet complete autonomous conversation loops.
- [ ] **Higher-level app/API UX:** setup and DB management CLI exist, but end-user storytelling interfaces are still evolving.
- [ ] **Distributed graph operation:** embedded Kuzu is current; broader deployment patterns are still ahead.
- [ ] **Production-grade embedding fallback:** current fallback behavior is intentionally conservative.

---

## 🚀 Getting Started

### Installation

```bash
git clone https://github.com/appleblack2062-eng/BRING.git
cd BRING
pip install -r requirements.txt
```

### Quick Start

```bash
python bring_cli.py setup
python bring_cli.py show-config
python bring_cli.py db create default
```

### Configuration

Copy `.bring.env.example` to `.bring.env` in the project root, or let the CLI generate it for you.

Example:

```bash
LLM_PROVIDER=openai
LLM_PROVIDER_TYPE=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=your_key_here
LLM_BASE_URL=https://api.openai.com/v1

LLM_EMBEDDING_PROVIDER=openai
LLM_EMBEDDING_PROVIDER_TYPE=openai
LLM_EMBEDDING_MODEL=text-embedding-3-small
LLM_EMBEDDING_API_KEY=your_embedding_key_here
LLM_EMBEDDING_BASE_URL=https://api.openai.com/v1
LLM_EMBEDDING_DIM=1536

MEMORY_DATABASE_ROOT=./memory_databases
MEMORY_DATABASE_ID=default
MEMORY_SEARCH_RESULT_LIMIT=50
```

Important details:

- `llm_gateway` and `memory` both read from the same root config file by default.
- embeddings can use a completely separate provider from the main LLM.
- `MEMORY_DATABASE_ID` isolates one memory graph from another under the same root.

---

## 🖥 CLI Workflow

The CLI is designed to reduce manual setup and make project operations friendlier.

### Guided Setup

Run:

```bash
python bring_cli.py setup
```

The CLI asks for:

- LLM base URL
- LLM API key
- LLM model
- embedding base URL
- embedding API key
- embedding model
- database root
- default database id

Then it automatically fills in:

- provider/provider type
- embedding provider/provider type
- embedding dimensions for common models
- sensible memory defaults

### Inspect Resolved Settings

```bash
python bring_cli.py show-config
```

### Database Commands

```bash
python bring_cli.py db list
python bring_cli.py db create mushoku-tensei-v2
python bring_cli.py db inspect mushoku-tensei-v2
python bring_cli.py db export mushoku-tensei-v2
python bring_cli.py db import ./memory_databases/mushoku-tensei-v2.zip shared-copy
python bring_cli.py db clone mushoku-tensei-v2 working-copy
python bring_cli.py db remove working-copy
```

The CLI uses `rich` progress bars and live terminal logging to make setup and packaging steps easier to monitor.

---

## 🗃 Portable Memory Databases

BRING memory is organized around isolated databases instead of one global shared store.

Typical structure:

```text
memory_databases/
  mushoku-tensei-v2/
    kuzu/
    attachments/
    manifest.json
```

Each database includes:

- **`kuzu/`** for graph storage
- **`attachments/`** for related assets or future sidecar files
- **`manifest.json`** for metadata such as dataset source, model context, and embedding settings

Why this matters:

- **No accidental cross-database mixing**
- **Safer cloning before edits**
- **Simple archive export/import**
- **Easier collaboration between project owners**

This is especially useful when one user creates a dataset-specific database, shares it with another BRING project owner, and that person wants to import it locally, clone it, and modify it without corrupting the original.

---

## 📚 Dataset Pipeline: Mushoku Tensei

The `mushoku_tensei/` section is a reference pipeline for ingesting a real narrative corpus into BRING memory.

It includes:

- English PDF extraction via `pdfplumber`
- heading-aware segmentation
- story-time estimation from age/year markers
- an extended ontology for abilities, arcs, concepts, world rules, and historical events
- structured extraction that is preserved through ingestion
- packaging into a reusable portable BRING memory database

Run it with:

```bash
python -m mushoku_tensei.ingest_v2
```

Recommended database config:

```bash
MEMORY_DATABASE_ROOT=./memory_databases
MEMORY_DATABASE_ID=mushoku-tensei-v2
```

For module-specific details, see `mushoku_tensei/README.md`.

---

## 🧱 Project Layout

```text
BRING/
  bring_cli.py
  bring_cli_support.py
  bring_settings.py
  llm_gateway/
  memory/
  mushoku_tensei/
  requirements.txt
  .bring.env.example
```

High-level responsibilities:

- `llm_gateway/` handles provider access and structured generation
- `memory/` handles graph persistence, search, and portable database workflows
- `mushoku_tensei/` demonstrates how to build a dataset-specific ingestion pipeline on top of BRING

---

## 🤝 Contributing

We are open to ideas, fixes, and extensions. Useful contribution areas include:

- additional providers and embedding backends
- more dataset pipelines
- stronger manifest compatibility/version checks
- higher-level story orchestration loops
- APIs and frontend interfaces for end-user interaction

<div align="center">
  <i>Built with ❤️ to push AI storytelling beyond stateless chat.</i>
</div>
