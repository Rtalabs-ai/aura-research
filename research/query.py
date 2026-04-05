# SPDX-License-Identifier: Apache-2.0
"""
Q&A engine for Aura Research.

Answers questions by reading wiki context, Memory OS facts, and optional web search.
Can save answers back into the wiki.
"""

import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

from .config import LLMClient, ResearchConfig
from .prompts import SYSTEM_QUERY, QUERY_ANSWER
from .web import search_web, format_search_results

logger = logging.getLogger(__name__)


def _load_wiki_context_aura(state_dir: Path, question: str, max_chars: int = 12000) -> str:
    """Load wiki context from wiki.aura archive via RAG (token-efficient)."""
    wiki_aura = state_dir / "wiki.aura"
    if not wiki_aura.exists():
        return ""

    try:
        from aura.rag import AuraRAGLoader
    except ImportError:
        return ""

    context_parts = []
    total_chars = 0

    with AuraRAGLoader(wiki_aura) as loader:
        # Get all document IDs and their text
        doc_ids = loader.get_all_ids()

        # Simple keyword relevance scoring against all documents
        query_words = question.lower().split()
        scored = []
        for doc_id in doc_ids:
            record = loader.get_by_id(doc_id)
            text = record["meta"].get("text_content", "")
            source = record["meta"].get("source", doc_id)
            if not text.strip():
                continue
            text_lower = text.lower()
            score = sum(text_lower.count(w) for w in query_words)
            # Boost index and summary
            if "_index" in source or "_summary" in source:
                score += 100
            scored.append((score, source, text))

        # Sort by relevance
        scored.sort(key=lambda x: x[0], reverse=True)

        for score, source, text in scored:
            if total_chars >= max_chars:
                break
            remaining = max_chars - total_chars
            truncated = text[:remaining]
            context_parts.append(f"### {source}\n{truncated}")
            total_chars += len(truncated)

    return "\n\n".join(context_parts)


def _load_wiki_context(wiki_dir: Path, state_dir: Path, question: str, max_chars: int = 12000) -> str:
    """
    Load relevant wiki context for answering a question.

    Prefers wiki.aura (RAG-optimized) when available, falls back to .md files.
    """
    # Try wiki.aura first (token-efficient RAG)
    aura_context = _load_wiki_context_aura(state_dir, question, max_chars)
    if aura_context:
        return aura_context

    # Fallback: scan .md files directly
    if not wiki_dir.exists():
        return ""

    from .search import search_wiki
    results = search_wiki(wiki_dir, question, max_results=5)

    context_parts = []
    total_chars = 0

    # Always include index and summary if they exist
    for special in ["_index.md", "_summary.md"]:
        path = wiki_dir / special
        if path.exists():
            content = path.read_text(encoding="utf-8")
            truncated = content[:2000]
            context_parts.append(f"### {special}\n{truncated}")
            total_chars += len(truncated)

    # Add search results
    for result in results:
        if total_chars >= max_chars:
            break
        filepath = Path(result["file"])
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            remaining = max_chars - total_chars
            truncated = content[:remaining]
            rel_path = filepath.relative_to(wiki_dir) if wiki_dir in filepath.parents else filepath.name
            context_parts.append(f"### {rel_path}\n{truncated}")
            total_chars += len(truncated)

    # If no search results, load all articles up to limit
    if not results:
        for md_file in sorted(wiki_dir.rglob("*.md")):
            if total_chars >= max_chars:
                break
            if md_file.name.startswith("_"):
                continue
            content = md_file.read_text(encoding="utf-8")
            remaining = max_chars - total_chars
            truncated = content[:remaining]
            rel_path = md_file.relative_to(wiki_dir)
            context_parts.append(f"### {rel_path}\n{truncated}")
            total_chars += len(truncated)

    return "\n\n".join(context_parts)


def _load_memory_context(config: ResearchConfig) -> str:
    """Load relevant facts from Memory OS."""
    if not config.memory_enabled:
        return ""

    try:
        from aura.memory import AuraMemoryOS
        memory = AuraMemoryOS()
        # Load all facts for broad context
        results = memory.query(query_text="", namespace="fact", top_k=20)
        if results:
            facts = []
            for r in results:
                facts.append(f"- {r['content']}")
            return "Known facts from previous sessions:\n" + "\n".join(facts)
    except Exception as e:
        logger.debug(f"Memory query failed: {e}")

    return ""


def query_wiki(
    config: ResearchConfig,
    llm: LLMClient,
    question: str,
    use_web: bool = True,
    save_response: bool = False,
) -> str:
    """
    Answer a research question using wiki context + memory + web search.

    Args:
        config: Project configuration
        llm: LLM client instance
        question: The research question
        use_web: Whether to include web search results
        save_response: Whether to save the answer to wiki/queries/

    Returns:
        The answer as markdown text
    """
    wiki_dir = config.wiki_dir

    print(f"🔍 Researching: {question}\n")

    # Gather context from multiple sources
    print("  📚 Reading wiki context...")
    wiki_context = _load_wiki_context(wiki_dir, config.state_dir, question)

    print("  🧠 Checking memory...")
    memory_context = _load_memory_context(config)

    web_context = ""
    if use_web and config.web_search_enabled:
        print("  🌐 Searching the web...")
        web_results = search_web(question, max_results=config.data["web_search"]["max_results"])
        web_context = format_search_results(web_results)

    # Build prompt
    prompt = QUERY_ANSWER.format(
        question=question,
        wiki_context=wiki_context or "No wiki articles found.",
        memory_context=memory_context or "",
        web_context=f"\nWeb search results:\n---\n{web_context}\n---" if web_context else "",
    )

    print("  💭 Thinking...\n")

    answer = llm.chat([
        {"role": "system", "content": SYSTEM_QUERY},
        {"role": "user", "content": prompt},
    ])

    # Display answer
    print("─" * 60)
    print(answer)
    print("─" * 60)

    # Save to wiki if requested
    if save_response:
        queries_dir = wiki_dir / "queries"
        queries_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_q = question[:50].replace(" ", "_").replace("/", "_")
        filename = f"{timestamp}_{safe_q}.md"
        filepath = queries_dir / filename

        header = f"# Query: {question}\n\n*Generated: {datetime.utcnow().isoformat()}Z*\n\n"
        filepath.write_text(header + answer, encoding="utf-8")
        print(f"\n💾 Saved to: {filepath}")

    # Write to episodic memory
    if config.memory_enabled and config.auto_memory:
        try:
            from aura.memory import AuraMemoryOS
            memory = AuraMemoryOS()
            memory.write(
                namespace="episodic",
                content=f"Answered query: {question[:200]}",
                source="research-query",
            )
        except Exception:
            pass

    return answer
