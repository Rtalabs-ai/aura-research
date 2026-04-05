# SPDX-License-Identifier: Apache-2.0
"""
LLM-powered wiki compiler for Aura Research.

The core feature: reads documents from .aura archives, sends them to an LLM,
and produces a structured markdown wiki with source summaries, concept articles,
master index, and executive summary.

Supports incremental compilation — only new sources are processed.
Automatically writes key findings to Memory OS.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from .config import LLMClient, ResearchConfig
from .prompts import (
    SYSTEM_COMPILER,
    COMPILE_SOURCE,
    COMPILE_CONCEPTS,
    COMPILE_CONCEPT_ARTICLE,
    COMPILE_INDEX,
    COMPILE_SUMMARY,
    MEMORY_EXTRACT_FACTS,
)

logger = logging.getLogger(__name__)


def _load_compile_state(state_dir: Path) -> Dict:
    """Load compilation state tracking compiled sources."""
    state_path = state_dir / "compiled.json"
    if state_path.exists():
        with open(state_path, "r") as f:
            return json.load(f)
    return {"compiled_sources": [], "last_compile": None}


def _save_compile_state(state_dir: Path, state: Dict):
    """Save compilation state."""
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "compiled.json"
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


def _slugify(name: str) -> str:
    """Convert a name to a filename-safe slug."""
    slug = name.lower().strip()
    slug = slug.replace(" ", "-")
    safe = ""
    for c in slug:
        if c.isalnum() or c == "-":
            safe += c
    # Collapse multiple dashes
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-")


def _write_article(path: Path, content: str):
    """Write a markdown article, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info(f"  Written: {path}")


def _get_memory():
    """Get Memory OS instance if available."""
    try:
        from aura.memory import AuraMemoryOS
        return AuraMemoryOS()
    except (ImportError, Exception) as e:
        logger.debug(f"Memory OS not available: {e}")
        return None


def _write_memory_facts(llm: LLMClient, content: str, memory):
    """Extract and write key facts to Memory OS /fact tier."""
    if not memory:
        return
    try:
        prompt = MEMORY_EXTRACT_FACTS.format(content=content[:3000])
        response = llm.chat([
            {"role": "system", "content": "Extract key facts as a JSON array of strings."},
            {"role": "user", "content": prompt},
        ])
        # Parse JSON from response
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        facts = json.loads(text)
        for fact in facts[:5]:  # Max 5 facts per source
            memory.write(namespace="fact", content=fact, source="research-compiler")
        logger.info(f"  Wrote {len(facts[:5])} facts to Memory OS")
    except Exception as e:
        logger.debug(f"Failed to extract facts: {e}")


def _compile_wiki_aura(wiki_dir: Path, output_path: Path):
    """
    Compile all wiki markdown articles into a wiki.aura archive.

    This is the primary artifact for agent RAG — token-efficient and
    searchable. The wiki/ markdown files remain as a human-readable
    export for Obsidian, VS Code, GitHub, etc.
    """
    try:
        from aura.compiler import compile_directory
    except ImportError:
        logger.warning("aura-core not available — skipping wiki.aura compilation")
        return

    if not wiki_dir.exists():
        return

    md_count = len(list(wiki_dir.rglob("*.md")))
    if md_count == 0:
        return

    print(f"\n📦 Phase 4: Compiling wiki → wiki.aura ({md_count} articles)")
    try:
        stats = compile_directory(
            input_dir=str(wiki_dir),
            output_path=str(output_path),
            show_progress=False,
        )
        print(f"   ✅ wiki.aura: {stats.processed_files} articles, {stats.total_tokens:,} words")
    except Exception as e:
        logger.warning(f"Failed to compile wiki.aura: {e}")
        print(f"   ⚠️  wiki.aura compilation failed: {e}")



def compile_wiki(
    config: ResearchConfig,
    llm: LLMClient,
    incremental: bool = True,
):
    """
    Compile ingested sources into a structured markdown wiki.

    Args:
        config: Project configuration
        llm: LLM client instance
        incremental: Only process new sources
    """
    aura_path = config.state_dir / "knowledge.aura"
    wiki_dir = config.wiki_dir
    state_dir = config.state_dir

    if not aura_path.exists():
        print("❌ No ingested data found. Run 'research ingest <dir>' first.")
        return

    # Load .aura archive
    try:
        from aura.rag import AuraRAGLoader
    except ImportError:
        print("❌ aura-core not installed. Run: pip install auralith-aura")
        return

    compile_state = _load_compile_state(state_dir)
    already_compiled = set(compile_state["compiled_sources"])

    # Get Memory OS if enabled
    memory = _get_memory() if config.memory_enabled else None

    with AuraRAGLoader(aura_path) as loader:
        doc_ids = loader.get_all_ids()
        print(f"📦 Archive contains {len(doc_ids)} documents")

        # Determine what to compile
        if incremental:
            new_ids = [d for d in doc_ids if d not in already_compiled]
            if not new_ids:
                print("✅ All sources already compiled. Use --full to recompile.")
                return
            print(f"🆕 {len(new_ids)} new source(s) to compile")
        else:
            new_ids = doc_ids
            print(f"🔄 Full recompile of {len(new_ids)} sources")

        # Create wiki directories
        sources_dir = wiki_dir / "sources"
        concepts_dir = wiki_dir / "concepts"
        queries_dir = wiki_dir / "queries"
        sources_dir.mkdir(parents=True, exist_ok=True)
        concepts_dir.mkdir(parents=True, exist_ok=True)
        queries_dir.mkdir(parents=True, exist_ok=True)

        # ─── Phase 1: Compile source summaries ───
        print(f"\n📝 Phase 1: Compiling source articles...")
        source_summaries = {}

        for i, doc_id in enumerate(new_ids, 1):
            record = loader.get_by_id(doc_id)
            text = record["meta"].get("text_content", "")
            source = record["meta"].get("source", doc_id)

            if not text.strip():
                logger.debug(f"Skipping empty source: {source}")
                continue

            print(f"  [{i}/{len(new_ids)}] {source}")

            # Truncate very long documents for LLM context
            content = text[:12000] if len(text) > 12000 else text

            prompt = COMPILE_SOURCE.format(
                source_path=source,
                content=content,
            )
            article = llm.chat([
                {"role": "system", "content": SYSTEM_COMPILER},
                {"role": "user", "content": prompt},
            ])

            # Write source article
            slug = _slugify(Path(source).stem)
            article_path = sources_dir / f"{slug}.md"
            _write_article(article_path, article)

            source_summaries[slug] = {
                "source": source,
                "article": article[:500],  # Brief summary for concept extraction
            }
            already_compiled.add(doc_id)

            # Write facts to memory
            if config.auto_memory:
                _write_memory_facts(llm, article, memory)

        # ─── Phase 2: Extract concepts ───
        if source_summaries:
            print(f"\n🧠 Phase 2: Identifying concepts...")

            # Gather all source summaries (including previously compiled)
            all_summaries = ""
            for md_file in sorted(sources_dir.glob("*.md")):
                content = md_file.read_text(encoding="utf-8")
                all_summaries += f"\n### {md_file.stem}\n{content[:500]}\n"

            prompt = COMPILE_CONCEPTS.format(summaries=all_summaries[:8000])
            response = llm.chat([
                {"role": "system", "content": SYSTEM_COMPILER},
                {"role": "user", "content": prompt},
            ])

            # Parse concepts
            try:
                text = response.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1].rsplit("```", 1)[0]
                concepts = json.loads(text)
            except json.JSONDecodeError:
                logger.warning("Failed to parse concepts JSON, skipping concept generation")
                concepts = []

            print(f"  Found {len(concepts)} concepts")

            # Write concept articles
            for concept in concepts:
                name = concept.get("name", "")
                desc = concept.get("description", "")
                slug = _slugify(name)

                if not slug:
                    continue

                # Skip if already exists (incremental)
                concept_path = concepts_dir / f"{slug}.md"
                if incremental and concept_path.exists():
                    continue

                print(f"  📖 Writing: {name}")

                # Gather related source content
                related = all_summaries[:6000]

                prompt = COMPILE_CONCEPT_ARTICLE.format(
                    concept_name=name,
                    concept_description=desc,
                    related_sources=related,
                )
                article = llm.chat([
                    {"role": "system", "content": SYSTEM_COMPILER},
                    {"role": "user", "content": prompt},
                ])
                _write_article(concept_path, article)

        # ─── Phase 3: Generate index and summary ───
        print(f"\n📋 Phase 3: Generating index and summary...")

        # Build lists for index
        source_list = ""
        for md_file in sorted(sources_dir.glob("*.md")):
            first_line = md_file.read_text(encoding="utf-8").split("\n")[0].strip("# ")
            source_list += f"- [{first_line}](sources/{md_file.name})\n"

        concept_list = ""
        for md_file in sorted(concepts_dir.glob("*.md")):
            first_line = md_file.read_text(encoding="utf-8").split("\n")[0].strip("# ")
            concept_list += f"- [{first_line}](concepts/{md_file.name})\n"

        # Generate index
        prompt = COMPILE_INDEX.format(
            source_list=source_list or "No source articles yet.",
            concept_list=concept_list or "No concept articles yet.",
        )
        index_content = llm.chat([
            {"role": "system", "content": SYSTEM_COMPILER},
            {"role": "user", "content": prompt},
        ])
        _write_article(wiki_dir / "_index.md", index_content)

        # Generate executive summary
        concepts_content = ""
        for md_file in sorted(concepts_dir.glob("*.md")):
            content = md_file.read_text(encoding="utf-8")
            concepts_content += f"\n{content[:800]}\n---\n"

        if concepts_content:
            prompt = COMPILE_SUMMARY.format(concepts_content=concepts_content[:8000])
            summary = llm.chat([
                {"role": "system", "content": SYSTEM_COMPILER},
                {"role": "user", "content": prompt},
            ])
            _write_article(wiki_dir / "_summary.md", summary)

    # Save compile state
    compile_state["compiled_sources"] = list(already_compiled)
    compile_state["last_compile"] = datetime.utcnow().isoformat() + "Z"
    _save_compile_state(state_dir, compile_state)

    # ─── Phase 4: Compile wiki into .aura archive ───
    wiki_aura_path = state_dir / "wiki.aura"
    _compile_wiki_aura(wiki_dir, wiki_aura_path)

    # Write session to episodic memory
    if memory and config.auto_memory:
        try:
            memory.write(
                namespace="episodic",
                content=f"Compiled {len(new_ids)} sources into wiki. "
                        f"Generated {len(concepts) if 'concepts' in dir() else 0} concept articles.",
                source="research-compiler",
            )
        except Exception:
            pass

    # Stats
    source_count = len(list(sources_dir.glob("*.md")))
    concept_count = len(list(concepts_dir.glob("*.md")))
    print(f"\n✅ Wiki compiled successfully!")
    print(f"   📄 {source_count} source articles")
    print(f"   🧠 {concept_count} concept articles")
    print(f"   📦 wiki.aura: {wiki_aura_path}")
    print(f"   📁 wiki/ (markdown): {wiki_dir}")
