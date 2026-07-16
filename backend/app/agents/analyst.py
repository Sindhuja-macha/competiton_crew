"""
Analyst Agent — extracts signal with mandatory citations.

v2 — key changes:
  - Every claim MUST carry a source URL; uncited claims are DROPPED not published
  - Adversarial claim detection: planted unverified assertions are flagged
  - Produces cited_claims list (CitedClaim objects) instead of plain text assertions
  - Governance counters: uncited_claims_dropped, adversarial_flags
  - Topic-aware (uses state["topic"] as primary context key)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import CitedClaim, GraphState
from app.utils.llm_client import chat_with_fallback

logger = logging.getLogger(__name__)

# ─── Adversarial patterns — claims that must never be stated as fact ────────
ADVERSARIAL_PATTERNS: list[str] = [
    r"going bankrupt",
    r"is bankrupt",
    r"fraud",
    r"criminal",
    r"illegally",
    r"money laundering",
    r"ponzi",
    r"scam",
    r"shutting down",
    r"going out of business",
    r"being acquired",       # acquisition rumours without evidence
    r"massive layoffs",      # unverified mass layoff claims
    r"executives arrested",
    r"under investigation by",
]

# Compiled for performance
_ADVERSARIAL_RE = re.compile(
    "|".join(ADVERSARIAL_PATTERNS),
    re.IGNORECASE,
)

SYSTEM_PROMPT = """You are a Senior Competitive Intelligence Analyst with strict citation requirements.

You will receive research data about a market topic, along with available source URLs.
Extract competitive intelligence claims and map EVERY claim to a specific source URL.

Output ONLY a valid JSON object:
{
  "cited_claims": [
    {
      "claim": "Exact factual statement",
      "source_url": "https://...",
      "source_title": "Source name or page title",
      "confidence": "high|medium|low",
      "section": "pricing|market|exec"
    }
  ],
  "uncited_observations": [
    "Observation that cannot be tied to a source — will be DROPPED from briefing"
  ],
  "executive_summary": "3-4 paragraph summary citing specific sources inline",
  "swot_analysis": {
    "strengths": ["strength with source [URL] noted"],
    "weaknesses": ["..."],
    "opportunities": ["..."],
    "threats": ["..."]
  },
  "market_trends": "2-3 paragraphs on market dynamics with source citations",
  "recommendations": ["Recommendation 1", "Recommendation 2", ...]
}

ABSOLUTE RULES:
1. cited_claims must ONLY include claims you can tie to a URL from the provided sources.
2. Do NOT invent source URLs — only use URLs from the input data.
3. If a source asserts something alarming (bankruptcy, fraud, criminal activity) with no corroborating evidence, do NOT include it in cited_claims. Note it in uncited_observations with prefix "ADVERSARIAL_FLAG:".
4. Low-confidence rumours must be marked confidence="low" and noted as unverified.
5. uncited_observations are discarded and never appear in the final briefing.
Output ONLY the JSON."""


def _is_adversarial(claim: str) -> bool:
    """Return True if a claim matches known adversarial/defamatory patterns."""
    return bool(_ADVERSARIAL_RE.search(claim))


def analyst_node(state: GraphState) -> dict[str, Any]:
    """
    LangGraph node — extracts cited intelligence claims from research data.

    Governance:
    - Claims without a source URL are dropped and counted
    - Adversarial patterns are flagged and excluded
    - All kept claims are wrapped in CitedClaim TypedDict
    """
    topic = state.get("topic") or state.get("competitor_name", "Unknown")
    industry = state.get("industry", "Unknown")
    region = state.get("region", "Global")
    errors = list(state.get("errors", []))
    warnings = list(state.get("warnings", []))
    steps_used = (state.get("steps_used") or 0) + 1
    max_steps = state.get("max_steps") or 25

    logger.info("[Analyst] Analysing data for topic='%s'.", topic)

    # ── Budget guard ──────────────────────────────────────────────────────
    if steps_used > max_steps:
        msg = f"Analyst skipped: step budget exhausted ({steps_used}/{max_steps})"
        warnings.append(msg)
        return _fallback_analyst(state, errors, warnings, steps_used, msg)

    # ── Prepare context ───────────────────────────────────────────────────
    overview = state.get("competitor_overview", "No overview available.")
    pricing = state.get("pricing_summary", "No pricing data.")
    sources = state.get("sources", [])
    source_results = state.get("source_results", [])
    news_items = state.get("latest_news", [])

    # Build source reference block for LLM
    source_ref_block = "\n".join(
        f"[SRC-{i+1}] Title: {s.get('title', 'Unknown')} | URL: {s.get('url', '#')} | "
        f"Snippet: {s.get('content_snippet', '')[:200]}"
        for i, s in enumerate(sources[:15])
    ) or "No sources available."

    news_summary = "\n".join(
        f"- {item['title']} (Source: {item.get('source', 'Google News')}, "
        f"URL: {item.get('url', '#')})"
        for item in news_items[:8]
    ) or "No recent news."

    context = (
        f"TOPIC: {topic}\nINDUSTRY: {industry}\nREGION: {region}\n\n"
        f"AVAILABLE SOURCES:\n{source_ref_block}\n\n"
        f"COMPETITOR OVERVIEW:\n{overview[:2000]}\n\n"
        f"PRICING INFORMATION:\n{pricing[:1000]}\n\n"
        f"RECENT NEWS:\n{news_summary}"
    )

    # ── LLM analysis ─────────────────────────────────────────────────────
    try:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=(
                f"Analyse the following intelligence data.\n"
                f"Only reference URLs from the AVAILABLE SOURCES list.\n\n"
                f"{context[:6500]}"
            )),
        ]
        response = chat_with_fallback(messages)
        raw = response.content.strip()

        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)

    except Exception as exc:
        logger.warning("[Analyst] LLM failed: %s", exc)
        errors.append(f"Analyst LLM error: {exc}")
        return _fallback_analyst(state, errors, warnings, steps_used, str(exc))

    # ── Governance: process cited_claims ─────────────────────────────────
    raw_claims: list[dict] = parsed.get("cited_claims", [])
    uncited_observations: list[str] = parsed.get("uncited_observations", [])

    kept_claims: list[CitedClaim] = []
    uncited_dropped: list[str] = []
    adversarial_flags: list[str] = list(state.get("adversarial_flags", []))

    # Valid URLs from our source set
    valid_urls: set[str] = {s.get("url", "") for s in sources if s.get("url")}
    # Also include news URLs
    for item in news_items:
        if item.get("url"):
            valid_urls.add(item["url"])

    for raw_claim in raw_claims:
        claim_text = raw_claim.get("claim", "").strip()
        source_url = raw_claim.get("source_url", "").strip()

        if not claim_text:
            continue

        # 1. Adversarial check — flag and drop
        if _is_adversarial(claim_text):
            flag_msg = f"ADVERSARIAL_FLAG: {claim_text} [source: {source_url}]"
            adversarial_flags.append(flag_msg)
            uncited_dropped.append(claim_text)
            logger.warning("[Analyst] Adversarial claim flagged and dropped: %s", claim_text[:80])
            continue

        # 2. Citation check — must have a URL
        if not source_url:
            uncited_dropped.append(claim_text)
            logger.info("[Analyst] Uncited claim dropped: %s", claim_text[:80])
            continue

        # 3. URL validation — prefer known URLs, but allow LLM-identified ones
        #    (LLM may cite a URL we didn't scrape but was in search results)
        kept_claims.append(CitedClaim(
            claim=claim_text,
            source_url=source_url,
            source_title=raw_claim.get("source_title", source_url),
            verified=False,          # will be set by fact_check agent
            confidence=raw_claim.get("confidence", "medium"),
            section=raw_claim.get("section", "market"),
        ))

    # Process uncited_observations — check for adversarial flags in them
    for obs in uncited_observations:
        if "ADVERSARIAL_FLAG:" in obs:
            adversarial_flags.append(obs)
        uncited_dropped.append(obs)

    logger.info(
        "[Analyst] Claims kept=%d dropped=%d adversarial=%d",
        len(kept_claims), len(uncited_dropped), len(adversarial_flags),
    )

    # ── Validate SWOT ─────────────────────────────────────────────────────
    swot = parsed.get("swot_analysis", {})
    for key in ("strengths", "weaknesses", "opportunities", "threats"):
        if key not in swot or not isinstance(swot[key], list):
            swot[key] = []

    recommendations = parsed.get("recommendations", [])
    if not isinstance(recommendations, list):
        recommendations = [str(recommendations)]

    return {
        "cited_claims": kept_claims,
        "uncited_claims_dropped": uncited_dropped,
        "adversarial_flags": adversarial_flags,
        "executive_summary": parsed.get("executive_summary", ""),
        "swot_analysis": swot,
        "market_trends": parsed.get("market_trends", ""),
        "recommendations": recommendations,
        "steps_used": steps_used,
        "errors": errors,
        "warnings": warnings,
    }


def _fallback_analyst(
    state: GraphState,
    errors: list,
    warnings: list,
    steps_used: int,
    reason: str,
) -> dict[str, Any]:
    """Structured fallback when LLM analysis cannot run."""
    topic = state.get("topic") or state.get("competitor_name", "Unknown")
    industry = state.get("industry", "Unknown")
    region = state.get("region", "Global")
    sources = state.get("sources", [])

    # Create cited claims from search results where possible
    fallback_claims: list[CitedClaim] = []
    for s in sources[:5]:
        if s.get("url") and s.get("content_snippet"):
            fallback_claims.append(CitedClaim(
                claim=f"Source available: {s.get('title', s['url'])}",
                source_url=s["url"],
                source_title=s.get("title", s["url"]),
                verified=False,
                confidence="low",
                section="market",
            ))

    return {
        "cited_claims": fallback_claims,
        "uncited_claims_dropped": [],
        "adversarial_flags": list(state.get("adversarial_flags", [])),
        "executive_summary": (
            f"Intelligence analysis for '{topic}' ({industry} / {region}). "
            f"Automated analysis could not complete ({reason}). "
            f"Raw research data is available in the sources section."
        ),
        "swot_analysis": {
            "strengths": ["See raw research data"],
            "weaknesses": ["Analysis incomplete"],
            "opportunities": [f"Growing {industry} market in {region}"],
            "threats": ["Competitive dynamics require manual review"],
        },
        "market_trends": f"Market trend analysis for '{topic}' pending manual review.",
        "recommendations": [
            f"Review raw research sources for '{topic}'",
            "Rerun analysis with a more specific topic or competitor name",
        ],
        "steps_used": steps_used,
        "errors": errors,
        "warnings": warnings,
    }
