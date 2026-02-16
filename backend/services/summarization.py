"""
Summarization and tagging abstraction.

The current implementation is a deterministic stub. To integrate a real LLM:
1. Replace the body of `summarize_and_tag` with an API call to your LLM of
   choice (OpenAI, Anthropic, local model, etc.).
2. The function signature stays the same — callers get (summary, tags) back.
"""
import re


def summarize_and_tag(raw_text: str) -> tuple[str, list[str]]:
    """
    Given the raw text of an agenda item, return a resident-friendly summary
    and a list of topic tags.

    Returns:
        (summary_text, [tag1, tag2, ...])
    """
    # --- Stub implementation ---
    # Summary: use the first meaningful sentence (skip very short lines).
    lines = [ln.strip() for ln in raw_text.split("\n") if ln.strip()]
    summary = ""
    for line in lines:
        # Skip the item number header line itself if it's short
        if len(line) > 30:
            summary = line[:300]
            break
    if not summary and lines:
        summary = lines[0][:300]

    # Tags: keyword matching against a small dictionary.
    text_lower = raw_text.lower()
    tag_keywords: dict[str, list[str]] = {
        "budget": ["budget", "operating budget", "capital budget", "fiscal", "surplus", "deficit"],
        "taxes": ["tax", "taxes", "levy", "tax rate"],
        "zoning": ["zoning", "zone", "rezone", "land use"],
        "housing": ["housing", "affordable housing", "rental", "residential development"],
        "homelessness": ["homeless", "shelter", "sheltering", "unsheltered"],
        "transit": ["transit", "bus", "guelph transit", "public transit"],
        "roads": ["road", "roads", "street", "traffic", "speed limit", "intersection"],
        "safety": ["safety", "safe", "speed limit", "pedestrian", "crosswalk"],
        "environment": ["climate", "environment", "emissions", "green", "sustainability"],
        "parks": ["park", "parks", "recreation", "trail", "green space"],
        "water": ["water", "wastewater", "stormwater", "sewer"],
        "governance": ["bylaw", "by-law", "council", "committee", "appointment", "vacancy"],
        "development": ["development", "site plan", "subdivision", "building permit"],
        "social_services": ["social", "community services", "shelter", "daytime"],
    }

    tags: list[str] = []
    for tag, keywords in tag_keywords.items():
        if any(kw in text_lower for kw in keywords):
            tags.append(tag)

    if not tags:
        tags.append("general")

    return summary, tags
