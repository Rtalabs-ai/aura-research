# SPDX-License-Identifier: Apache-2.0
"""
Web search module for Aura Research.

Provides internet search capabilities using DuckDuckGo (no API key required).
Falls back gracefully if duckduckgo-search is not installed.
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Search the web and return results.

    Args:
        query: Search query string
        max_results: Maximum number of results to return

    Returns:
        List of dicts with 'title', 'url', 'snippet' keys
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        logger.warning(
            "Web search unavailable. Install with: pip install 'aura-research[search]'"
        )
        return []

    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        logger.info(f"Web search for '{query}': {len(results)} results")
        return results
    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return []


def format_search_results(results: List[Dict[str, str]]) -> str:
    """Format search results as markdown for LLM context."""
    if not results:
        return ""

    lines = ["Web search results:"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n**[{i}] {r['title']}**")
        lines.append(f"URL: {r['url']}")
        lines.append(f"{r['snippet']}")

    return "\n".join(lines)
