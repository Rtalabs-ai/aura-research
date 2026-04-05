# SPDX-License-Identifier: Apache-2.0
"""
Keyword search across wiki markdown files.

Fast text search with ranked results — no embeddings needed at wiki scale.
"""

import re
import logging
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)


def search_wiki(
    wiki_dir: Path,
    query: str,
    max_results: int = 10,
) -> List[Dict]:
    """
    Search all wiki articles for a query string.

    Args:
        wiki_dir: Path to the wiki directory
        query: Search query
        max_results: Maximum results to return

    Returns:
        List of dicts with 'file', 'line', 'context', 'score' keys
    """
    if not wiki_dir.exists():
        return []

    query_words = query.lower().split()
    if not query_words:
        return []

    results = []

    for md_file in wiki_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        content_lower = content.lower()
        lines = content.split("\n")

        # Score: how many query words appear in the file
        word_score = sum(1 for w in query_words if w in content_lower)
        if word_score == 0:
            continue

        # Frequency score: total occurrences
        freq_score = sum(content_lower.count(w) for w in query_words)

        # Find best matching line for context
        best_line = 0
        best_line_score = 0
        for i, line in enumerate(lines):
            line_lower = line.lower()
            line_score = sum(1 for w in query_words if w in line_lower)
            if line_score > best_line_score:
                best_line_score = line_score
                best_line = i

        # Get context around best matching line
        start = max(0, best_line - 1)
        end = min(len(lines), best_line + 3)
        context = "\n".join(lines[start:end]).strip()

        results.append({
            "file": str(md_file),
            "line": best_line + 1,
            "context": context[:300],
            "score": word_score * 10 + freq_score,
        })

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def print_search_results(results: List[Dict], wiki_dir: Path):
    """Pretty-print search results."""
    if not results:
        print("No matching articles found.")
        return

    print(f"🔍 Found {len(results)} matching article(s):\n")
    for i, r in enumerate(results, 1):
        filepath = Path(r["file"])
        try:
            rel = filepath.relative_to(wiki_dir)
        except ValueError:
            rel = filepath.name

        print(f"  [{i}] {rel} (line {r['line']}, score: {r['score']})")
        # Indent context
        for line in r["context"].split("\n"):
            print(f"      {line}")
        print()
