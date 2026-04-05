# SPDX-License-Identifier: Apache-2.0
"""
LLM prompt templates for Aura Research.

All prompts are centralized here for easy tuning and iteration.
"""

# ─────────────────────────────────────────────
# WIKI COMPILATION PROMPTS
# ─────────────────────────────────────────────

SYSTEM_COMPILER = """You are a research knowledge base compiler. Your job is to read raw source
documents and produce structured, well-written wiki articles in markdown format.

Rules:
- Write in clear, precise academic prose
- Include all important details, data points, and findings
- Use markdown headers (##, ###) to organize content
- Add a "## Key Findings" section at the top of each article
- Add a "## References" section linking back to source documents
- Use standard markdown links: [text](relative/path.md)
- Never fabricate information — only summarize what is in the source
- If the source contains numerical data, preserve exact numbers"""

COMPILE_SOURCE = """Analyze the following source document and produce a wiki article summarizing it.

Source file: {source_path}
Content:
---
{content}
---

Produce a well-structured markdown article with:
1. A title as H1 (# Title)
2. A brief abstract (2-3 sentences)
3. ## Key Findings — bullet points of the most important takeaways
4. ## Details — expanded discussion of the content
5. ## References — link back to the source as `[{source_path}](../raw/{source_path})`

Output ONLY the markdown content, no code fences."""

COMPILE_CONCEPTS = """You are analyzing a research knowledge base. Below are summaries of all source
documents in the wiki. Identify the key concepts, themes, and topics that appear
across multiple sources.

Source summaries:
---
{summaries}
---

For each concept you identify:
1. Give it a clear, concise name (this becomes the filename)
2. Write a brief description (1-2 sentences)

Return a JSON array of objects with "name" and "description" fields.
Example: [{{"name": "attention-mechanisms", "description": "How attention mechanisms route information in transformer architectures"}}]

Output ONLY the JSON array, no markdown fences."""

COMPILE_CONCEPT_ARTICLE = """Write a concept article for a research wiki.

Concept: {concept_name}
Description: {concept_description}

Related source articles:
---
{related_sources}
---

Write a markdown article that:
1. Explains the concept clearly (# {concept_name})
2. ## Overview — what this concept is and why it matters
3. ## Details — synthesize information from the related sources
4. ## Connections — how this concept relates to other topics in the research
5. ## Sources — link to the related source articles

Use standard markdown links: [article name](../sources/filename.md)
Output ONLY the markdown content, no code fences."""

COMPILE_INDEX = """Generate a master index for a research wiki.

The following articles exist in the wiki:

Source articles:
{source_list}

Concept articles:
{concept_list}

Generate a markdown index file with:
1. # Research Index
2. A brief overview paragraph describing the scope of this knowledge base
3. ## Concepts — bulleted list of concept articles with brief descriptions and links
4. ## Sources — bulleted list of source articles with brief descriptions and links

Use standard markdown links: [name](relative/path.md)
Output ONLY the markdown content, no code fences."""

COMPILE_SUMMARY = """Write an executive summary of a research knowledge base.

The following concept articles exist:
---
{concepts_content}
---

Write a markdown document with:
1. # Executive Summary
2. A 2-3 paragraph overview of the entire research domain covered
3. ## Key Themes — the most important recurring themes
4. ## Open Questions — gaps or unanswered questions you notice
5. ## Connections — interesting cross-cutting patterns

Output ONLY the markdown content, no code fences."""

# ─────────────────────────────────────────────
# QUERY PROMPTS
# ─────────────────────────────────────────────

SYSTEM_QUERY = """You are a research assistant with access to a compiled knowledge base.
Answer questions by referencing the wiki articles provided as context.
Be precise, cite your sources, and distinguish between what the sources say
and any inferences you make. If the context is insufficient, say so clearly."""

QUERY_ANSWER = """Answer the following research question using the provided context.

Question: {question}

{memory_context}

Wiki context:
---
{wiki_context}
---

{web_context}

Provide a thorough, well-structured answer in markdown. Cite specific articles
when referencing information. If information is missing, note what additional
sources might help."""

# ─────────────────────────────────────────────
# MEMORY PROMPTS
# ─────────────────────────────────────────────

MEMORY_EXTRACT_FACTS = """Review the following content and extract key facts that should be
remembered long-term. These are verified observations, important patterns,
or critical findings.

Content:
---
{content}
---

Return a JSON array of strings, each being a concise fact statement.
Example: ["The model achieves 94.2% accuracy on the test set", "Training requires 8x A100 GPUs"]
Output ONLY the JSON array."""

# ─────────────────────────────────────────────
# LINTER PROMPTS
# ─────────────────────────────────────────────

SYSTEM_LINTER = """You are a wiki health checker. Analyze the provided wiki content
for consistency, completeness, and quality issues."""

LINT_CHECK = """Review the following wiki for issues:

Index:
---
{index_content}
---

Sample articles (first 5):
---
{sample_articles}
---

Check for:
1. Broken or inconsistent internal links
2. Topics mentioned but not having their own article
3. Contradictory information across articles
4. Articles that seem thin or incomplete
5. Suggested improvements

Return a markdown report with sections for each category of issues found.
Output ONLY the markdown content."""
