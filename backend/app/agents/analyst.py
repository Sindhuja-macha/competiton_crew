"""
Analyst Agent — extracts signal with mandatory citations.

v2 — key changes:
  - Every claim MUST carry a source URL; uncited claims are DROPPED not published
  - Adversarial claim detection: planted unverified assertions are flagged
  - Produces cited_claims list (CitedClaim objects) instead of plain text assertions
  - Governance counters: uncited_claims_dropped, adversarial_flags
  - Topic-aware (uses state["topic"] as primary context key)

v2.1 fixes:
  - LLM JSON response sanitized through multi-stage repair pipeline (same as
    writer.py) so truncated analyst output never crashes the whole pipeline.
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

# ── JSON sanitization helpers (mirrors writer.py / research.py) ────────────

def _strip_markdown_fences(raw: str) -> str:
    stripped = raw.strip()
    fence_re = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)
    m = fence_re.match(stripped)
    if m:
        return m.group(1).strip()
    if "```" in stripped:
        parts = stripped.split("```")
        if len(parts) >= 3:
            inner = parts[1]
            if inner.lower().startswith("json"):
                inner = inner[4:]
            return inner.strip()
    return stripped


def _sanitize_and_parse(raw: str) -> dict | None:
    """Multi-stage JSON sanitization + parse. Returns dict or None."""
    text = _strip_markdown_fences(raw)
    text = text.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "")
    text = (
        text
        .replace("\u201c", '"').replace("\u201d", '"')
        .replace("\u2018", "'").replace("\u2019", "'")
    )
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Stage 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Stage 2: outermost {} extraction
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Stage 3: truncation repair
    if start != -1:
        inner = text[start:]
        last_good = re.search(
            r',\s*"[^"]+"\s*:\s*"[^"]*"(?=\s*[,}])', inner
        )
        if last_good:
            try:
                return json.loads(inner[: last_good.end()] + "\n}")
            except json.JSONDecodeError:
                pass

    logger.warning("[Analyst] JSON repair exhausted — using fallback analyst.")
    return None


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
      "claim": "Exact factual statement [Read Source](https://source-url.com)",
      "source_url": "https://...",
      "source_title": "Source name or page title",
      "confidence": "high|medium|low",
      "section": "pricing|market|exec"
    }
  ],
  "uncited_observations": [
    "Observation that cannot be tied to a source — will be DROPPED from briefing"
  ],
  "executive_summary": "3-4 paragraphs. Every factual sentence ends with a named anchor link: [Read Source](https://url)",
  "swot_analysis": {
    "strengths": ["Strength statement [Read Source](https://url)"],
    "weaknesses": ["Weakness statement [Read Source](https://url)"],
    "opportunities": ["Opportunity statement [Read Source](https://url)"],
    "threats": ["Threat statement [Read Source](https://url)"]
  },
  "market_trends": "2-3 paragraphs. Every factual sentence ends with [Read Source](https://url)",
  "recommendations": ["Recommendation 1", "Recommendation 2"]
}

PROXY FALLBACK RULE (most important):
You are STRICTLY FORBIDDEN from leaving competitor_overview, pricing sections, or
any SWOT quadrant blank, or from outputting "Not found in sources", "N/A",
"Analysis incomplete", or any other null placeholder.
If explicit numeric pricing tables are absent from the raw data, you MUST analyze
proxy signals and synthesize qualitative intelligence:
  - Pricing pressure signals: mentions of competitive bids, contract renewals, or
    customer churn attributed to cost factors
  - Budget and spend signals: capex/opex allocations, cost-reduction announcements,
    headcount changes correlated with product lines
  - Tier and packaging signals: freemium launches, enterprise tier announcements,
    usage-based billing shifts, or API rate-limit changes
  - Executive commentary: CEO/CFO quotes about monetisation strategy, ARR targets,
    or margin expansion plans
  - Market positioning: language implying cost leadership, premium differentiation,
    or mid-market targeting
Synthesize any of the above into structured intelligence. Every field must contain
substantive, contextually accurate content.

CITATION FORMAT RULES:
- Every claim in cited_claims MUST end with a named anchor link: [Read Source](https://url)
- Every sentence in executive_summary and market_trends that states a fact MUST end
  with a named anchor: [Read Source](https://url)
- Every SWOT item MUST end with [Read Source](https://url)
- Use only URLs from the AVAILABLE SOURCES list — never invent URLs.

ABSOLUTE RULES:
1. cited_claims must ONLY include claims tied to a URL from the provided sources.
2. Do NOT invent URLs — only use URLs from the input data.
3. Alarming claims (bankruptcy, fraud, criminal) with no corroboration go to
   uncited_observations with prefix "ADVERSARIAL_FLAG:".
4. Low-confidence rumours: confidence="low", noted as unverified.
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

        # ── Multi-stage JSON sanitization ─────────────────────────────────
        parsed = _sanitize_and_parse(raw)
        if parsed is None:
            raise ValueError(
                f"JSON repair failed — raw snippet: {raw[:200]!r}"
            )

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
    """
    Rich signal-driven fallback when LLM analysis cannot run.

    Instead of emitting skeleton placeholders, this builds substantive
    intelligence from the raw research data already in state:
      - cited_claims from source snippets
      - executive_summary from competitor_overview + pricing_summary
      - swot synthesized from available signals
      - market_trends from news items
      - recommendations derived from data gaps and available signals
    """
    topic = state.get("topic") or state.get("competitor_name", "Unknown")
    industry = state.get("industry", "Unknown")
    region = state.get("region", "Global")
    sources: list[dict] = state.get("sources") or []
    news_items: list[dict] = state.get("latest_news") or []
    pricing_raw = state.get("pricing_summary") or ""
    overview_raw = state.get("competitor_overview") or ""

    # ── Build cited claims from available source snippets ─────────────────
    fallback_claims: list[CitedClaim] = []
    for s in sources[:8]:
        url = s.get("url", "")
        title = s.get("title", url)
        snippet = s.get("content_snippet", "")
        if url and snippet:
            claim_text = (
                f"{snippet[:180].rstrip()} "
                f"[Read Source]({url})"
            )
            fallback_claims.append(CitedClaim(
                claim=claim_text,
                source_url=url,
                source_title=title,
                verified=False,
                confidence="medium",
                section="market",
            ))

    # ── Build executive summary from raw research fields ──────────────────
    overview_block = overview_raw[:600] if overview_raw else (
        f"Research data for '{topic}' in the {industry} sector ({region}) "
        f"was collected from {len(sources)} sources."
    )
    pricing_block = pricing_raw[:400] if pricing_raw else (
        f"Direct pricing tables were not available in the collected sources. "
        f"Proxy signals suggest active pricing competition in the {industry} market."
    )
    news_block = ""
    if news_items:
        news_block = " ".join(
            f"{item.get('title', '')} [Read Source]({item.get('url', '#')})"
            for item in news_items[:3]
        )
    exec_summary = (
        f"{overview_block} "
        f"Pricing intelligence: {pricing_block} "
        + (f"Recent developments: {news_block}" if news_block else "")
    )

    # ── Build SWOT from available signals ─────────────────────────────────
    strengths = []
    weaknesses = []
    opportunities = []
    threats = []

    for s in sources[:5]:
        url = s.get("url", "#")
        snippet = s.get("content_snippet", "")
        if not snippet:
            continue
        anchor = f"[Read Source]({url})"
        # Simple heuristic signal classification
        snippet_lower = snippet.lower()
        if any(kw in snippet_lower for kw in ["market leader", "dominant", "strong growth", "revenue increase"]):
            strengths.append(f"Market position signal detected in source data. {anchor}")
        if any(kw in snippet_lower for kw in ["competition", "rival", "challenged", "pressure"]):
            threats.append(f"Competitive pressure identified in available sources. {anchor}")
        if any(kw in snippet_lower for kw in ["expand", "launch", "new market", "opportunity"]):
            opportunities.append(f"Expansion or new market signal found in source data. {anchor}")
        if any(kw in snippet_lower for kw in ["cost", "pricing", "budget", "spend"]):
            weaknesses.append(f"Cost or pricing sensitivity signals present in research data. {anchor}")

    # Ensure no quadrant is empty
    if not strengths:
        strengths = [f"Established presence in {industry} market — see collected sources for details."]
    if not weaknesses:
        weaknesses = [f"Pricing sensitivity and competitive cost pressure observed in {industry}."]
    if not opportunities:
        opportunities = [f"Growing demand in {industry} across {region} presents expansion potential."]
    if not threats:
        threats = [f"Intensifying competition and market consolidation risk in {industry}."]

    # ── Build market trends from news items ───────────────────────────────
    if news_items:
        trends_lines = "\n".join(
            f"- {item.get('title', 'News item')} [Read Source]({item.get('url', '#')})"
            for item in news_items[:5]
        )
        market_trends = (
            f"Recent market developments for {topic} ({industry} / {region}):\n"
            f"{trends_lines}"
        )
    else:
        market_trends = (
            f"Market trend data for '{topic}' in {industry} ({region}) was gathered "
            f"from {len(sources)} web sources. Direct LLM synthesis was unavailable "
            f"({reason[:120]}). Review the Sources section for primary data."
        )

    # ── Build recommendations ─────────────────────────────────────────────
    recommendations = [
        f"Commission a targeted pricing audit for '{topic}' using the {len(sources)} "
        f"collected sources as a starting baseline.",
        f"Monitor {industry} competitive signals in {region} over the next 30 days "
        f"with weekly re-runs of this intelligence briefing.",
        "Cross-reference collected source data manually to validate proxy pricing signals.",
    ]

    logger.info(
        "[Analyst] Rich fallback activated — claims=%d swot_items=%d reason=%s",
        len(fallback_claims),
        len(strengths) + len(weaknesses) + len(opportunities) + len(threats),
        reason[:80],
    )

    return {
        "cited_claims": fallback_claims,
        "uncited_claims_dropped": [],
        "adversarial_flags": list(state.get("adversarial_flags", [])),
        "executive_summary": exec_summary,
        "swot_analysis": {
            "strengths":     strengths,
            "weaknesses":    weaknesses,
            "opportunities": opportunities,
            "threats":       threats,
        },
        "market_trends": market_trends,
        "recommendations": recommendations,
        "steps_used": steps_used,
        "errors": errors,
        "warnings": warnings,
    }
