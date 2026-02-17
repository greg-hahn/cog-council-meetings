"""
Summarization and tagging for council agenda items.

Uses Claude API when ANTHROPIC_API_KEY is set, otherwise falls back to
deterministic keyword matching.
"""
import logging
import re

from backend.config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

VALID_TAGS = [
    "budget", "taxes", "zoning", "housing", "homelessness",
    "transit", "roads", "safety", "environment", "parks",
    "water", "governance", "development", "social_services",
]

TAG_KEYWORDS: dict[str, list[str]] = {
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


# ---------------------------------------------------------------------------
# Keyword-based fallback
# ---------------------------------------------------------------------------

def _keyword_summarize_and_tag(raw_text: str) -> tuple[str, list[str]]:
    """Deterministic summary + tag generation using keyword matching."""
    lines = [ln.strip() for ln in raw_text.split("\n") if ln.strip()]
    summary = ""
    for line in lines:
        if len(line) > 30:
            summary = line[:300]
            break
    if not summary and lines:
        summary = lines[0][:300]

    text_lower = raw_text.lower()
    tags: list[str] = []
    for tag, keywords in TAG_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            tags.append(tag)

    if not tags:
        tags.append("general")

    return summary, tags


# ---------------------------------------------------------------------------
# LLM-based summarization (Claude)
# ---------------------------------------------------------------------------

def _llm_summarize_and_tag(raw_text: str, title: str) -> tuple[str, list[str]]:
    """Summarize and tag using Claude API."""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    tag_list = ", ".join(VALID_TAGS)
    prompt = (
        "You are summarizing a city council agenda item for residents of Guelph, Ontario.\n\n"
        f"Title: {title}\n\n"
        f"Full text:\n{raw_text[:3000]}\n\n"
        "Instructions:\n"
        "1. Write a 1-2 sentence plain-English summary explaining what this item is about "
        "and why a resident might care. Avoid jargon.\n"
        f"2. Pick 1-3 tags from this list: {tag_list}\n\n"
        "Respond in exactly this format:\n"
        "SUMMARY: <your summary>\n"
        "TAGS: <tag1>, <tag2>"
    )

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text.strip()

    # Parse SUMMARY: and TAGS: lines
    summary = ""
    tags: list[str] = []

    for line in response_text.split("\n"):
        line = line.strip()
        if line.upper().startswith("SUMMARY:"):
            summary = line[len("SUMMARY:"):].strip()
        elif line.upper().startswith("TAGS:"):
            raw_tags = line[len("TAGS:"):].strip()
            for t in raw_tags.split(","):
                t = t.strip().lower().replace(" ", "_")
                if t in VALID_TAGS:
                    tags.append(t)

    if not summary:
        # If parsing failed, use the whole response as summary
        summary = response_text[:300]

    if not tags:
        tags.append("general")

    return summary, tags


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def summarize_and_tag(raw_text: str, title: str = "") -> tuple[str, list[str]]:
    """
    Given the raw text of an agenda item, return a resident-friendly summary
    and a list of topic tags.

    Uses Claude API if ANTHROPIC_API_KEY is configured, otherwise falls back
    to keyword-based matching.

    Returns:
        (summary_text, [tag1, tag2, ...])
    """
    if ANTHROPIC_API_KEY:
        try:
            return _llm_summarize_and_tag(raw_text, title)
        except Exception:
            logger.warning("LLM summarization failed, falling back to keywords", exc_info=True)

    return _keyword_summarize_and_tag(raw_text)
