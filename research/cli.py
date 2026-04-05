# SPDX-License-Identifier: Apache-2.0
"""
CLI entry point for Aura Research.

Commands:
    research init            Initialize a new knowledge base project
    research ingest <dir>    Ingest raw documents into .aura archive
    research compile         Compile wiki from ingested sources
    research query "..."     Ask a question against the wiki
    research search "..."    Search wiki articles
    research lint            Run health checks on the wiki
    research status          Show knowledge base stats
    research memory ...      Memory OS management
"""

import sys
import argparse
import logging
from pathlib import Path

from . import __version__


def _find_project_dir() -> Path:
    """Find the project root by looking for research.yaml or .research/."""
    cwd = Path.cwd()
    # Check current dir and parents
    for d in [cwd] + list(cwd.parents):
        if (d / "research.yaml").exists() or (d / ".research").exists():
            return d
    return cwd


def _agent_instructions() -> str:
    """Return universal agent instructions for using the research CLI."""
    return """# Aura Research Knowledge Base

This project uses **Aura Research** (`pip install aura-research`) as a CLI tool for querying and managing a compiled knowledge base.

## Available Shell Commands

The `research` command is installed on the system PATH. Execute it directly as a shell command. Do NOT search for it in the file system — it is a pip-installed CLI tool.

### Query the knowledge base
```bash
research query "your question here"
```
This searches the compiled `.aura` archive and returns an AI-synthesized answer using only relevant context. **Always prefer this for research questions.**

### Search for keywords
```bash
research search "keyword"
```

### Show project status
```bash
research status
```

### Memory commands
```bash
research memory show              # Full overview of all memory tiers
research memory show --tier fact   # Filter by tier
research memory query "topic"      # Search memory
research memory write fact "..."   # Write to memory
```

## Important
- `research` is a **shell command on PATH**, not a file. Do not look for it.
- When asked a research question, run `research query "..."` instead of reading wiki `.md` files manually.
- The wiki is in the `wiki/` directory if you need to browse articles directly.
"""


def cmd_init(args):
    """Initialize a new research knowledge base project."""
    from .config import ResearchConfig

    project_dir = Path(args.directory).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)

    # Create directory structure
    (project_dir / "raw").mkdir(exist_ok=True)
    (project_dir / "wiki").mkdir(exist_ok=True)
    (project_dir / "wiki" / "sources").mkdir(exist_ok=True)
    (project_dir / "wiki" / "concepts").mkdir(exist_ok=True)
    (project_dir / "wiki" / "queries").mkdir(exist_ok=True)
    (project_dir / ".research").mkdir(exist_ok=True)

    # Create default config
    config = ResearchConfig(project_dir)
    config.save_default()

    # Generate agent instruction files
    instructions = _agent_instructions()

    # Universal (any agent that reads AGENTS.md)
    (project_dir / "AGENTS.md").write_text(instructions, encoding="utf-8")

    # Gemini CLI
    (project_dir / "GEMINI.md").write_text(instructions, encoding="utf-8")

    # Claude Code
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (project_dir / "CLAUDE.md").write_text(instructions, encoding="utf-8")

    # Codex / OpenClaw (reads AGENTS.md, already created above)

    print(f"✅ Initialized research project: {project_dir}")
    print(f"   📁 raw/       — drop your source documents here")
    print(f"   📁 wiki/      — compiled wiki (auto-generated)")
    print(f"   ⚙️  research.yaml — configuration")
    print(f"   🤖 AGENTS.md  — agent instructions (Gemini, Claude, Codex, OpenClaw)")
    print(f"\nNext steps:")
    print(f"   1. Copy your research documents into raw/")
    print(f"   2. Set your LLM API key (e.g., export OPENAI_API_KEY=sk-...)")
    print(f"   3. Run: research ingest raw/")
    print(f"   4. Run: research compile")


def cmd_ingest(args):
    """Ingest raw documents into .aura archive."""
    from .config import ResearchConfig
    from .ingest import ingest_documents, watch_and_ingest

    project_dir = _find_project_dir()
    config = ResearchConfig(project_dir)

    raw_dir = Path(args.directory).resolve()
    aura_path = config.state_dir / "knowledge.aura"

    if args.watch:
        interval = config.data["watch"].get("interval", 5)
        watch_and_ingest(raw_dir, aura_path, config.state_dir, interval=interval)
    else:
        ingest_documents(
            raw_dir=raw_dir,
            output_path=aura_path,
            state_dir=config.state_dir,
            incremental=not args.full,
        )


def cmd_compile(args):
    """Compile wiki from ingested sources using LLM."""
    from .config import ResearchConfig, LLMClient
    from .compiler import compile_wiki

    project_dir = _find_project_dir()
    config = ResearchConfig(project_dir)

    try:
        llm = LLMClient(config)
    except (ImportError, Exception) as e:
        print(f"\u274c LLM setup failed: {e}")
        print(f"\nMake sure you have:")
        print(f"  1. Installed a provider: pip install 'aura-research[{config.provider}]'")
        print(f"  2. Set the API key (e.g., export OPENAI_API_KEY=sk-...)")
        sys.exit(1)

    compile_wiki(config, llm, incremental=not args.full)


def cmd_build(args):
    """Compile wiki/ markdown into wiki.aura (no LLM needed)."""
    from .config import ResearchConfig
    from .compiler import _compile_wiki_aura

    project_dir = _find_project_dir()
    config = ResearchConfig(project_dir)

    wiki_aura_path = config.state_dir / "wiki.aura"
    _compile_wiki_aura(config.wiki_dir, wiki_aura_path)
    print(f"\n✅ wiki.aura ready at: {wiki_aura_path}")


def cmd_query(args):
    """Query the wiki with a research question."""
    from .config import ResearchConfig, LLMClient
    from .query import query_wiki

    project_dir = _find_project_dir()
    config = ResearchConfig(project_dir)

    try:
        llm = LLMClient(config)
    except (ImportError, Exception) as e:
        print(f"\u274c LLM setup failed: {e}")
        print(f"\nMake sure you have:")
        print(f"  1. Installed a provider: pip install 'aura-research[{config.provider}]'")
        print(f"  2. Set the API key (e.g., export OPENAI_API_KEY=sk-...)")
        sys.exit(1)

    question = " ".join(args.question)
    query_wiki(
        config, llm, question,
        use_web=not args.no_web,
        save_response=args.save,
    )


def cmd_search(args):
    """Search wiki articles."""
    from .config import ResearchConfig
    from .search import search_wiki, print_search_results

    project_dir = _find_project_dir()
    config = ResearchConfig(project_dir)

    query = " ".join(args.query)
    results = search_wiki(config.wiki_dir, query, max_results=args.limit)
    print_search_results(results, config.wiki_dir)


def cmd_lint(args):
    """Run health checks on the wiki."""
    from .config import ResearchConfig, LLMClient
    from .linter import lint_wiki

    project_dir = _find_project_dir()
    config = ResearchConfig(project_dir)

    llm = None
    if args.ai:
        llm = LLMClient(config)

    lint_wiki(config, llm=llm, use_llm=args.ai)


def cmd_status(args):
    """Show knowledge base stats."""
    import json
    from .config import ResearchConfig

    project_dir = _find_project_dir()
    config = ResearchConfig(project_dir)

    print(f"📊 Aura Research — {project_dir.name}\n")

    # Config
    print(f"  Provider: {config.provider}/{config.model}")
    print(f"  Memory:   {'enabled' if config.memory_enabled else 'disabled'}")
    print(f"  Search:   {'enabled' if config.web_search_enabled else 'disabled'}")

    # Ingestion stats
    manifest_path = config.state_dir / "ingested.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
        print(f"\n  📥 Ingested: {len(manifest.get('files', {}))} files")
        if manifest.get("last_ingest"):
            print(f"     Last: {manifest['last_ingest']}")
    else:
        print(f"\n  📥 No files ingested yet")

    # Wiki stats
    wiki_dir = config.wiki_dir
    if wiki_dir.exists():
        articles = list(wiki_dir.rglob("*.md"))
        total_words = sum(
            len(f.read_text(encoding="utf-8").split()) for f in articles
        )
        sources = len(list((wiki_dir / "sources").glob("*.md"))) if (wiki_dir / "sources").exists() else 0
        concepts = len(list((wiki_dir / "concepts").glob("*.md"))) if (wiki_dir / "concepts").exists() else 0
        queries = len(list((wiki_dir / "queries").glob("*.md"))) if (wiki_dir / "queries").exists() else 0

        print(f"\n  📚 Wiki:")
        print(f"     Sources:  {sources} articles")
        print(f"     Concepts: {concepts} articles")
        print(f"     Queries:  {queries} saved")
        print(f"     Words:    {total_words:,}")
    else:
        print(f"\n  📚 Wiki not compiled yet")

    # Memory stats
    if config.memory_enabled:
        try:
            from aura.memory import AuraMemoryOS
            memory = AuraMemoryOS()
            memory.show_usage()
        except Exception:
            print(f"\n  🧠 Memory OS: not available")


def _show_memory_overview(memory, tier=None):
    """Display a full overview of all memory entries across all tiers."""
    import json
    from pathlib import Path

    tiers = [tier] if tier else ["fact", "episodic", "pad"]
    tier_icons = {"fact": "📌", "episodic": "📝", "pad": "📋"}
    tier_descriptions = {
        "fact": "Verified facts — persistent, survives indefinitely",
        "episodic": "Session logs — what was done and when",
        "pad": "Working notes — transient scratch space",
    }

    mem_dir = Path.home() / ".aura" / "memory"

    print("🧠 Memory OS — Full Overview\n")
    total_entries = 0

    for t in tiers:
        icon = tier_icons.get(t, "📁")
        desc = tier_descriptions.get(t, "")
        print(f"  {icon} /{t} — {desc}")
        print(f"  {'─' * 56}")

        entries = []

        # Read from shards (archived entries)
        shard_dir = mem_dir / t / "shards"
        if shard_dir.exists():
            for shard_file in sorted(shard_dir.glob("*.jsonl")):
                try:
                    for line in open(shard_file, encoding="utf-8"):
                        line = line.strip()
                        if line:
                            entries.append(json.loads(line))
                except Exception:
                    pass

        # Read from WAL (buffered entries not yet flushed)
        wal_file = mem_dir / t / "wal" / "active.jsonl"
        if wal_file.exists():
            try:
                for line in open(wal_file, encoding="utf-8"):
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
            except Exception:
                pass

        # Sort by timestamp (newest first)
        entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

        if entries:
            for i, entry in enumerate(entries, 1):
                content = entry.get("content", "")[:150]
                source = entry.get("source", "unknown")
                timestamp = entry.get("timestamp", "")
                entry_id = entry.get("entry_id", "")[:8]

                # Format timestamp
                if timestamp and len(timestamp) > 10:
                    ts_display = f"{timestamp[:10]} {timestamp[11:16]}"
                else:
                    ts_display = timestamp or "unknown"

                print(f"  {i:3d}. {content}")
                print(f"       id: {entry_id}  |  src: {source}  |  {ts_display}")
            total_entries += len(entries)
        else:
            print("       (empty)")

        print()

    print(f"  Total: {total_entries} entries across {len(tiers)} tier(s)")
    print()
    memory.show_usage()


def cmd_memory(args):
    """Memory OS management."""
    try:
        from aura.memory import AuraMemoryOS
    except ImportError:
        print("❌ aura-core not installed. Run: pip install auralith-aura")
        sys.exit(1)

    memory = AuraMemoryOS()

    if args.memory_action == "query":
        query_text = " ".join(args.text)
        results = memory.query(
            query_text=query_text,
            namespace=args.namespace,
            top_k=args.top_k,
        )
        if results:
            print(f"🔍 Found {len(results)} result(s):\n")
            for i, r in enumerate(results, 1):
                print(f"  {i}. [{r['namespace']}] (score: {r['score']:.2f})")
                print(f"     {r['content'][:200]}")
                print(f"     Source: {r['source']}  |  {r['timestamp']}")
                print()
        else:
            print("No matching memories found.")

    elif args.memory_action == "write":
        entry = memory.write(
            namespace=args.tier,
            content=" ".join(args.content),
            source="user-manual",
        )
        print(f"✅ Written to /{args.tier}: {entry.entry_id}")

    elif args.memory_action == "usage":
        memory.show_usage()

    elif args.memory_action == "show":
        _show_memory_overview(memory, tier=args.tier)

    elif args.memory_action == "list":
        memory.list_shards()

    elif args.memory_action == "prune":
        if args.before:
            memory.prune_shards(before_date=args.before)
        elif args.shard_id:
            memory.prune_shards(shard_ids=[args.shard_id])
        else:
            print("Specify --before DATE or --id SHARD_ID")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="research",
        description="Aura Research — LLM-powered research knowledge base",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    research init my-project
    research ingest ./papers
    research compile
    research query "what are the key findings?"
    research search "attention mechanism"
    research lint
    research status
    research memory usage
""",
    )
    parser.add_argument("-v", "--version", action="version", version=f"aura-research {__version__}")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = subparsers.add_parser("init", help="Initialize a new knowledge base project")
    p_init.add_argument("directory", nargs="?", default=".", help="Project directory (default: current)")

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Ingest raw documents")
    p_ingest.add_argument("directory", help="Directory containing raw documents")
    p_ingest.add_argument("--watch", action="store_true", help="Watch for changes and re-ingest")
    p_ingest.add_argument("--full", action="store_true", help="Full re-ingest (ignore cache)")

    # compile
    p_compile = subparsers.add_parser("compile", help="Compile wiki from ingested sources (needs LLM)")
    p_compile.add_argument("--full", action="store_true", help="Full recompile (ignore cache)")

    # build
    subparsers.add_parser("build", help="Build wiki.aura from wiki/ markdown (no LLM needed)")

    # query
    p_query = subparsers.add_parser("query", help="Ask a research question")
    p_query.add_argument("question", nargs="+", help="Your question")
    p_query.add_argument("--no-web", action="store_true", help="Disable web search")
    p_query.add_argument("--save", action="store_true", help="Save response to wiki/queries/")

    # search
    p_search = subparsers.add_parser("search", help="Search wiki articles")
    p_search.add_argument("query", nargs="+", help="Search query")
    p_search.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")

    # lint
    p_lint = subparsers.add_parser("lint", help="Run wiki health checks")
    p_lint.add_argument("--ai", action="store_true", help="Include AI-powered analysis")

    # status
    subparsers.add_parser("status", help="Show knowledge base stats")

    # memory
    p_memory = subparsers.add_parser("memory", help="Memory OS management")
    mem_sub = p_memory.add_subparsers(dest="memory_action", help="Memory commands")

    p_mem_query = mem_sub.add_parser("query", help="Search memory")
    p_mem_query.add_argument("text", nargs="+", help="Search query")
    p_mem_query.add_argument("--namespace", default=None, help="Filter by namespace")
    p_mem_query.add_argument("--top-k", type=int, default=5, help="Number of results")

    p_mem_write = mem_sub.add_parser("write", help="Write to memory")
    p_mem_write.add_argument("tier", choices=["pad", "episodic", "fact"], help="Memory tier")
    p_mem_write.add_argument("content", nargs="+", help="Content to write")

    mem_sub.add_parser("usage", help="Show memory usage")

    p_mem_show = mem_sub.add_parser("show", help="Full overview of all memory entries")
    p_mem_show.add_argument("--tier", choices=["pad", "episodic", "fact"], default=None, help="Filter to one tier")

    mem_sub.add_parser("list", help="List memory shards")

    p_mem_prune = mem_sub.add_parser("prune", help="Prune memory")
    p_mem_prune.add_argument("--before", help="Delete before date (YYYY-MM-DD)")
    p_mem_prune.add_argument("--id", dest="shard_id", help="Delete specific shard")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch
    commands = {
        "init": cmd_init,
        "ingest": cmd_ingest,
        "compile": cmd_compile,
        "build": cmd_build,
        "query": cmd_query,
        "search": cmd_search,
        "lint": cmd_lint,
        "status": cmd_status,
        "memory": cmd_memory,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
