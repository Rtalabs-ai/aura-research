<p align="center">
  <img src="https://github.com/Rtalabs-ai/aura-core/raw/main/logo.png" alt="Rta Labs Logo" width="120" />
</p>

<h1 align="center">Aura Research</h1>

<p align="center">
  <strong>Turn raw research into a living wiki your LLM agents can read, query, and enhance.</strong>
</p>

<p align="center">
  <a href="https://github.com/Rtalabs-ai/aura-research/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License" /></a>
  <a href="https://github.com/Rtalabs-ai/aura-core"><img src="https://img.shields.io/badge/powered%20by-Aura%20Core-purple" alt="Powered by Aura Core" /></a>
</p>

---

**Aura Research** is an LLM-powered research knowledge base that compiles raw documents into a structured markdown wiki. Drop your papers, articles, data, and notes into a folder — the LLM reads everything, builds a navigable wiki with summaries and concept articles, and then answers your research questions using that compiled knowledge.

Built on [Aura Core](https://github.com/Rtalabs-ai/aura-core) for document compilation (60+ formats) and the three-tier Memory OS for persistent agent memory across sessions.

## Quick Start

```bash
# Install
pip install 'aura-research[openai]'

# Set your API key
export OPENAI_API_KEY=sk-...

# Initialize a project
research init my-project
cd my-project

# Drop your documents in raw/
cp ~/papers/*.pdf raw/

# Ingest and compile
research ingest raw/
research compile

# Ask questions
research query "what are the key findings across all papers?"

# Search the wiki
research search "attention mechanism"

# Check wiki health
research lint
```

### Agent-Native Mode (no API key)

If you're already using an AI coding agent (Claude Code, Codex, Gemini CLI, Cursor, etc.), **you don't need an API key**. The agent IS the LLM:

```bash
# In your AI agent's terminal:
research init my-project
# Copy documents to raw/
research ingest raw/

# The agent reads the docs and writes wiki articles directly
# (it's an LLM — it doesn't need to call another one)

research build          # compile wiki/ → wiki.aura
research search "topic" # search the wiki
research memory show    # see what the agent remembers
```

The API mode (`research compile`, `research query`) exists for headless/batch use when no agent is at the keyboard.

## How It Works

```
Raw Documents  ──→  Aura Core (.aura)  ──→  LLM Compiler  ──→  Markdown Wiki
  papers/              compiled &              generates          wiki/
  articles/            indexed                 summaries,         ├── _index.md
  data/                (60+ formats)           concepts,          ├── concepts/
  code/                                        backlinks          ├── sources/
                                                                  └── queries/
                              ↕
                        Memory OS
                   /pad  /episodic  /fact
                   (persistent agent memory)
```

1. **Ingest** — Compile your raw documents into a searchable `.aura` archive using Aura Core
2. **Compile** — LLM reads all sources and generates a structured wiki: per-source summaries, cross-cutting concept articles, master index, and executive summary
3. **Query** — Ask questions against the wiki. The LLM uses wiki context + Memory OS facts + optional web search to give you thorough, cited answers
4. **Remember** — Memory OS automatically stores key findings (`/fact`), session logs (`/episodic`), and working notes (`/pad`) — so the agent never starts cold

## Commands

| Command | Description |
|---|---|
| `research init [dir]` | Initialize a new project |
| `research ingest <dir>` | Ingest raw documents into `.aura` archive |
| `research ingest <dir> --watch` | Watch directory and auto-re-ingest on changes |
| `research compile` | Compile wiki using LLM API (needs API key) |
| `research compile --full` | Full recompile (ignore cache) |
| `research build` | Build `wiki.aura` from `wiki/` markdown (no LLM needed) |
| `research query "..."` | Ask a research question (needs API key) |
| `research query "..." --save` | Ask and save the answer to `wiki/queries/` |
| `research query "..." --no-web` | Ask without web search |
| `research search "..."` | Keyword search across wiki articles |
| `research lint` | Run wiki health checks |
| `research lint --ai` | Health checks + AI-powered analysis |
| `research status` | Show knowledge base statistics |
| `research memory show` | Full overview of all 3 memory tiers |
| `research memory show --tier fact` | Overview filtered to one tier |
| `research memory usage` | Show Memory OS storage |
| `research memory query "..."` | Search agent memory |
| `research memory write <tier> "..."` | Manually write to memory (pad/episodic/fact) |
| `research memory list` | List memory shards |
| `research memory prune --before DATE` | Prune old memory entries |

## LLM Providers

Supports **OpenAI**, **Anthropic**, and **Google Gemini**. Install the one you prefer:

```bash
pip install 'aura-research[openai]'      # GPT-4o (default)
pip install 'aura-research[anthropic]'    # Claude 3.5 Sonnet
pip install 'aura-research[gemini]'       # Gemini 2.0 Flash
pip install 'aura-research[all]'          # Everything
```

Configure via environment variables or `research.yaml`:

```yaml
llm:
  provider: openai          # openai, anthropic, or gemini
  model: gpt-4o             # override default model
  temperature: 0.3

memory:
  enabled: true
  auto_write: true           # agent writes to memory automatically

web_search:
  enabled: true
  max_results: 5

watch:
  enabled: false
  interval: 5               # seconds between checks
```

## Memory OS

Aura's three-tier **Memory OS v2.1** gives the agent persistent memory across sessions — so it never starts cold:

| Tier | What's Stored | Persistence |
|---|---|---|
| `/pad` | Working notes, draft observations | Transient — scratch space |
| `/episodic` | Session logs, what was compiled/queried | Auto-archived |
| `/fact` | Key findings, verified observations | Persistent — survives indefinitely |

### How It Operates

Memory OS works **both autonomously and manually**:

- **Autonomous**: During `research compile`, the LLM auto-extracts key facts and writes them to `/fact`. After every compile/query session, an episodic log → `/episodic`. Controlled by `auto_write: true` in config.
- **Manual**: Write directly with `research memory write <tier> "content"` whenever you (or the agent) want to persist something.

### v2.1 Features

| Feature | What It Does |
|---|---|
| **Entry deduplication** | Prevents writing the same fact twice (SimHash fuzzy matching) |
| **Temporal decay** | Recent memories score higher in queries — older context naturally fades |
| **Bloom filters** | Skip irrelevant shards during search — fast even with thousands of entries |
| **Append-only** | Old entries are never overwritten — new ones are added alongside them |
| **Tiered priority** | Facts > episodic > pad when returning query results |

### Examples

```bash
# Write a verified fact
research memory write fact "The model achieves 94.2% accuracy on the test set"

# Log what you did this session
research memory write episodic "Analyzed training curves, found overfitting at epoch 12"

# Jot a working note
research memory write pad "TODO: re-run experiment with lower learning rate"

# Search memory by keyword
research memory query "accuracy"

# Full overview — see everything across all 3 tiers
research memory show

# Filter to just facts
research memory show --tier fact

# Storage usage
research memory usage
```

## Web Search

During `research query`, the agent can search the web to supplement wiki answers with current information. This is enabled by default and uses DuckDuckGo (no API key required).

```bash
pip install 'aura-research[search]'

# Query with web search (default)
research query "latest advances in attention mechanisms"

# Query without web search
research query "what does our data show" --no-web
```

## Watch Mode

Auto-detect new files and re-ingest:

```bash
pip install 'aura-research[watch]'

# Watch for changes (uses watchdog if installed, falls back to polling)
research ingest ./papers --watch
```

## Wiki Output

The compiled wiki lives in two places:

**`wiki.aura`** — The primary artifact. An `.aura` archive containing all wiki articles, optimized for agent RAG retrieval. Token-efficient — agents read only what's relevant.

**`wiki/`** — Markdown export for human browsing. Open in **Obsidian**, **VS Code**, **GitHub**, or any markdown viewer:

```
.research/
├── knowledge.aura      ← Raw ingested documents
└── wiki.aura           ← Compiled wiki (agent reads from here)

wiki/
├── _index.md           ← Master index with links to all articles
├── _summary.md         ← Executive summary of the knowledge base
├── concepts/           ← Cross-cutting concept articles
│   ├── attention.md
│   ├── tokenization.md
│   └── ...
├── sources/            ← Per-source summary articles
│   ├── vaswani2017.md
│   ├── devlin2019.md
│   └── ...
└── queries/            ← Saved Q&A responses
    └── ...
```

After editing wiki articles (or having the agent write them), run `research build` to recompile `wiki.aura`.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## Links

- **Aura Core**: [github.com/Rtalabs-ai/aura-core](https://github.com/Rtalabs-ai/aura-core) — the universal context compiler
- **Rta Labs**: [rtalabs.org](https://rtalabs.org)
