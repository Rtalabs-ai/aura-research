# SPDX-License-Identifier: Apache-2.0
"""
Wiki health checker for Aura Research.

Finds broken links, orphaned articles, stale content, and suggests improvements.
"""

import re
import logging
from pathlib import Path
from typing import List, Dict
from datetime import datetime

from .config import LLMClient, ResearchConfig
from .prompts import SYSTEM_LINTER, LINT_CHECK

logger = logging.getLogger(__name__)


def _find_markdown_links(content: str) -> List[str]:
    """Extract all markdown link targets from content."""
    # Match [text](path) and [[wikilink]] patterns
    standard = re.findall(r'\[.*?\]\((.*?)\)', content)
    wiki = re.findall(r'\[\[(.*?)\]\]', content)
    return standard + wiki


def _check_broken_links(wiki_dir: Path) -> List[Dict]:
    """Find broken internal links."""
    issues = []
    for md_file in wiki_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        links = _find_markdown_links(content)

        for link in links:
            # Skip external links
            if link.startswith(("http://", "https://", "mailto:")):
                continue
            # Skip anchors
            if link.startswith("#"):
                continue

            # Resolve relative to the file's directory
            target = md_file.parent / link
            if not target.exists():
                rel_source = md_file.relative_to(wiki_dir)
                issues.append({
                    "type": "broken_link",
                    "file": str(rel_source),
                    "link": link,
                    "message": f"Broken link: [{link}] in {rel_source}",
                })
    return issues


def _check_orphaned_articles(wiki_dir: Path) -> List[Dict]:
    """Find articles not linked from the index."""
    index_path = wiki_dir / "_index.md"
    if not index_path.exists():
        return []

    index_content = index_path.read_text(encoding="utf-8").lower()
    issues = []

    for md_file in wiki_dir.rglob("*.md"):
        if md_file.name.startswith("_"):
            continue
        rel = md_file.relative_to(wiki_dir)
        # Check if the filename appears in the index
        if md_file.name.lower() not in index_content and str(rel).lower() not in index_content:
            issues.append({
                "type": "orphaned",
                "file": str(rel),
                "message": f"Orphaned article not in index: {rel}",
            })
    return issues


def _check_thin_articles(wiki_dir: Path, min_words: int = 50) -> List[Dict]:
    """Find articles that are too short."""
    issues = []
    for md_file in wiki_dir.rglob("*.md"):
        if md_file.name.startswith("_"):
            continue
        content = md_file.read_text(encoding="utf-8")
        word_count = len(content.split())
        if word_count < min_words:
            rel = md_file.relative_to(wiki_dir)
            issues.append({
                "type": "thin_article",
                "file": str(rel),
                "word_count": word_count,
                "message": f"Thin article ({word_count} words): {rel}",
            })
    return issues


def _check_stale_articles(wiki_dir: Path, state_dir: Path) -> List[Dict]:
    """Find articles whose sources may have changed."""
    import json

    manifest_path = state_dir / "ingested.json"
    compiled_path = state_dir / "compiled.json"

    if not manifest_path.exists() or not compiled_path.exists():
        return []

    with open(manifest_path) as f:
        manifest = json.load(f)
    with open(compiled_path) as f:
        compiled = json.load(f)

    last_ingest = manifest.get("last_ingest", "")
    last_compile = compiled.get("last_compile", "")

    if last_ingest and last_compile and last_ingest > last_compile:
        return [{
            "type": "stale",
            "message": f"Sources updated ({last_ingest}) after last compile ({last_compile}). "
                       "Run 'research compile' to update the wiki.",
        }]
    return []


def lint_wiki(config: ResearchConfig, llm: LLMClient = None, use_llm: bool = False):
    """
    Run health checks on the wiki.

    Args:
        config: Project configuration
        llm: Optional LLM client for AI-powered analysis
        use_llm: Whether to use LLM for deeper analysis
    """
    wiki_dir = config.wiki_dir
    state_dir = config.state_dir

    if not wiki_dir.exists():
        print("❌ No wiki found. Run 'research compile' first.")
        return

    print("🔍 Running wiki health checks...\n")
    all_issues = []

    # Check broken links
    broken = _check_broken_links(wiki_dir)
    all_issues.extend(broken)

    # Check orphaned articles
    orphaned = _check_orphaned_articles(wiki_dir)
    all_issues.extend(orphaned)

    # Check thin articles
    thin = _check_thin_articles(wiki_dir)
    all_issues.extend(thin)

    # Check stale content
    stale = _check_stale_articles(wiki_dir, state_dir)
    all_issues.extend(stale)

    # Print results
    if not all_issues:
        print("✅ No issues found! Wiki looks healthy.\n")
    else:
        print(f"⚠️  Found {len(all_issues)} issue(s):\n")

        # Group by type
        by_type = {}
        for issue in all_issues:
            t = issue["type"]
            if t not in by_type:
                by_type[t] = []
            by_type[t].append(issue)

        type_labels = {
            "broken_link": "🔗 Broken Links",
            "orphaned": "👻 Orphaned Articles",
            "thin_article": "📄 Thin Articles",
            "stale": "⏰ Stale Content",
        }

        for issue_type, issues in by_type.items():
            label = type_labels.get(issue_type, issue_type)
            print(f"  {label} ({len(issues)}):")
            for issue in issues:
                print(f"    - {issue['message']}")
            print()

    # LLM-powered deeper analysis
    if use_llm and llm:
        print("🧠 Running AI-powered analysis...\n")
        index_path = wiki_dir / "_index.md"
        index_content = index_path.read_text(encoding="utf-8") if index_path.exists() else "No index."

        sample = ""
        articles = list(wiki_dir.rglob("*.md"))[:5]
        for a in articles:
            content = a.read_text(encoding="utf-8")
            sample += f"\n### {a.name}\n{content[:500]}\n---\n"

        prompt = LINT_CHECK.format(
            index_content=index_content[:3000],
            sample_articles=sample[:5000],
        )
        report = llm.chat([
            {"role": "system", "content": SYSTEM_LINTER},
            {"role": "user", "content": prompt},
        ])
        print(report)

    # Stats
    article_count = len(list(wiki_dir.rglob("*.md")))
    total_words = 0
    for md_file in wiki_dir.rglob("*.md"):
        total_words += len(md_file.read_text(encoding="utf-8").split())

    print(f"\n📊 Wiki Stats:")
    print(f"   Articles: {article_count}")
    print(f"   Words: {total_words:,}")
    print(f"   Issues: {len(all_issues)}")
