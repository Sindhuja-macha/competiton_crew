"""
Writer Agent — produces the 3 required structured briefing sections.

Speed optimisation v2:
  - Single LLM call for all 3 sections (was 3 separate calls = 3x slower)
  - Reduced context size passed to LLM
  - Fallback template if LLM fails
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import BriefingSection, CitedClaim, GraphState
from app.utils.llm_client import chat_with_fallback

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Senior Intelligence Report Writer for a Strategy team.

Write ALL THREE sections of a competitive intelligence briefing in ONE response.

Output ONLY a valid JSON object:
{
  "section_pricing": "Markdown content for Section 1: Competitor Pricing & Product Moves",
  "section_market": "Markdown content for Section 2: Market Signals & Trends",
  "section_exec": "Markdown content for Section 3: Executive Summary & Strategic Recommendation"
}

RULES for every section:
1. Every factual statement MUST end with an inline citation: [[Source Title]](URL)
2. Verified claims (2+ sources) stated directly. Single-source claims hedged: "According to [Source], ..."
3. 3-5 concise paragraphs or bullet points per section.
4. Professional executive tone. No filler phrases.
5. Section 3 must end with ONE clear, actionable recommendation.

Output ONLY the JSON. No extra text."""


def _format_claims_block(claims: list[CitedClaim], max_claims: int = 12) -> str:
    lines = []
    for c in claims[:max_claims]:
        tag = "✓" if c.get("verified") else "⚠"
        lines.append(
            f"[{tag}] {c.get('claim', '')} "
            f"| Source: {c.get('source_title', '')} ({c.get('source_url', '#')})"
        )
    return "\n".join(lines) if lines else "No verified claims available."


def _build_citation_footer(sources: list[dict]) -> str:
    if not sources:
        return "_No sources available._"
    return "\n".join(
        f"{i+1}. [{s.get('title', s.get('url', 'Unknown'))}]({s.get('url', '#')}) — *{s.get('source', 'Web')}*"
        for i, s in enumerate(sources[:12], 0)
    )


def writer_node(state: GraphState) -> dict[str, Any]:
    """
    LangGraph node — single LLM call produces all 3 briefing sections.
    Dramatically faster than 3 separate calls.
    """
    topic = state.get("topic") or state.get("competitor_name", "Unknown")
    industry = state.get("industry", "Unknown")
    region = state.get("region", "Global")
    errors = list(state.get("errors", []))
    warnings = list(state.get("warnings", []))
    steps_used = (state.get("steps_used") or 0) + 1

    logger.info("[Writer] Generating 3-section briefing (single LLM call) for '%s'.", topic)

    now = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    cited_claims: list[CitedClaim] = list(state.get("cited_claims", []))
    sources = state.get("sources", [])
    latest_news = state.get("latest_news", [])
    recommendations = state.get("recommendations", [])
    fact_check_passed = state.get("fact_check_passed", 0)
    fact_check_failed = state.get("fact_check_failed", 0)
    uncited_dropped = state.get("uncited_claims_dropped", [])
    adversarial_flags = state.get("adversarial_flags", [])
    failed_sources = state.get("failed_sources", [])

    # Partition claims by section tag
    pricing_claims = [c for c in cited_claims if c.get("section") == "pricing"] or cited_claims[:6]
    market_claims  = [c for c in cited_claims if c.get("section") == "market"]  or cited_claims[:6]
    exec_claims    = [c for c in cited_claims if c.get("section") == "exec"]    or \
                     sorted(cited_claims, key=lambda c: 0 if c.get("confidence") == "high" else 1)[:6]

    news_lines = "\n".join(
        f"- {item['title']} [{item.get('source','?')}] ({item.get('url','#')})"
        for item in latest_news[:5]
    ) or "No recent news."

    rec_lines = "\n".join(f"- {r}" for r in recommendations[:5]) or "No recommendations."

    context = (
        f"Topic: {topic} | Industry: {industry} | Region: {region} | Date: {now}\n\n"
        f"PRICING/OVERVIEW:\n{state.get('pricing_summary','')[:500]}\n\n"
        f"PRICING CLAIMS:\n{_format_claims_block(pricing_claims)}\n\n"
        f"MARKET TRENDS:\n{state.get('market_trends','')[:400]}\n\n"
        f"MARKET CLAIMS:\n{_format_claims_block(market_claims)}\n\n"
        f"RECENT NEWS:\n{news_lines}\n\n"
        f"EXEC CLAIMS:\n{_format_claims_block(exec_claims)}\n\n"
        f"RECOMMENDATIONS:\n{rec_lines}"
    )

    # ── Single LLM call for all 3 sections ───────────────────────────────
    section_pricing_content = ""
    section_market_content  = ""
    section_exec_content    = ""

    try:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Write all 3 briefing sections for:\n\n{context[:4500]}"),
        ]
        response = chat_with_fallback(messages)
        raw = response.content.strip()

        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)
        section_pricing_content = parsed.get("section_pricing", "")
        section_market_content  = parsed.get("section_market", "")
        section_exec_content    = parsed.get("section_exec", "")
        logger.info("[Writer] All 3 sections generated in single LLM call.")

    except Exception as exc:
        logger.warning("[Writer] LLM failed, using fallback template: %s", exc)
        errors.append(f"Writer LLM error: {exc}")

        # Fallback: build sections from available data
        section_pricing_content = (
            f"{state.get('pricing_summary', 'Pricing data not available.')}\n\n"
            + "\n".join(f"- {c.get('claim','')} [[source]]({c.get('source_url','#')})"
                        for c in pricing_claims[:5])
        )
        section_market_content = (
            f"{state.get('market_trends', 'Market data not available.')}\n\n"
            f"**Recent News:**\n{news_lines}"
        )
        section_exec_content = (
            f"{state.get('executive_summary', f'Intelligence briefing for {topic}.')}\n\n"
            f"**Recommendation:**\n{rec_lines}"
        )

    # ── Build BriefingSection objects ────────────────────────────────────
    section_pricing = BriefingSection(
        title="Competitor Pricing & Product Moves",
        content=section_pricing_content,
        cited_claims=pricing_claims,
    )
    section_market = BriefingSection(
        title="Market Signals & Trends",
        content=section_market_content,
        cited_claims=market_claims,
    )
    section_exec = BriefingSection(
        title="Executive Summary & Strategic Recommendation",
        content=section_exec_content,
        cited_claims=exec_claims,
    )

    # ── Assemble full Markdown ────────────────────────────────────────────
    sources_footer = _build_citation_footer(sources)

    failed_note = ""
    if failed_sources:
        failed_note = (
            f"\n\n> **⚠ Data Gaps:** {len(failed_sources)} source(s) unreachable and skipped:\n"
            + "\n".join(f"> - {u}" for u in failed_sources[:5])
        )

    governance_note = (
        f"\n\n---\n### Governance\n"
        f"- Uncited claims dropped: **{len(uncited_dropped)}**\n"
        f"- Adversarial flags suppressed: **{len(adversarial_flags)}**\n"
        f"- Claims verified (2+ sources): **{fact_check_passed}**\n"
        f"- Claims single-source (hedged): **{fact_check_failed}**\n"
    ) if (uncited_dropped or adversarial_flags or fact_check_passed) else ""

    final_report_markdown = f"""# Competitive Intelligence Briefing: {topic}
**Industry:** {industry} | **Region:** {region} | **Generated:** {now}

---

## 1. Competitor Pricing & Product Moves

{section_pricing_content}

---

## 2. Market Signals & Trends

{section_market_content}

---

## 3. Executive Summary & Strategic Recommendation

{section_exec_content}
{failed_note}

---

## Sources & References

{sources_footer}
{governance_note}

---
*Competitive Intelligence Briefing Crew | {now}*
*Verified claims: {fact_check_passed} | Single-source (hedged): {fact_check_failed}*
"""

    logger.info("[Writer] Briefing assembled: %d chars.", len(final_report_markdown))

    return {
        "briefing_section_pricing": section_pricing,
        "briefing_section_market":  section_market,
        "briefing_section_exec":    section_exec,
        "final_report_markdown":    final_report_markdown,
        "report_sections": [
            "Competitor Pricing & Product Moves",
            "Market Signals & Trends",
            "Executive Summary & Strategic Recommendation",
        ],
        "steps_used": steps_used,
        "errors":     errors,
        "warnings":   warnings,
    }
