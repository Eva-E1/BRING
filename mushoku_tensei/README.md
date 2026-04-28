# Mushoku Tensei Knowledge Graph Builder (English Edition)

This module ingests the official English version of *Mushoku Tensei*
and builds a multi-layer graph database optimized for the BRING memory engine.

## Features
- **English-native extraction** - tuned prompts and schema for light novel text.
- **Chapter-aware segmentation** - detects volume, chapter, prologue, epilogue, and interlude boundaries.
- **Timeline reconstruction** - parses ages, calendar years, and relative time markers.
- **Extended ontology** - adds abilities, world rules, historical events, arcs, and concepts.
- **Portable output** - exports a packaged database archive with a manifest for reuse in other BRING projects.

## Usage
1. Place your English PDF volumes inside `mushoku_tensei/pdfs/`.
2. Create `.bring.env` in the project root with your shared LLM and memory settings.
3. Set a dedicated memory namespace for this dataset, for example:
   ```env
   MEMORY_DATABASE_ROOT=./memory_databases
   MEMORY_DATABASE_ID=mushoku-tensei-v2
   ```
4. Install dependencies:
   ```bash
   pip install pdfplumber
   ```
5. Run the ingester:
   ```bash
   python -m mushoku_tensei.ingest_v2
   ```

The ingester uses the shared `llm_gateway` configuration, registers the extended
Mushoku ontology with `memory`, preserves precomputed extraction results during
ingestion, and exports a reusable database archive when it finishes.
