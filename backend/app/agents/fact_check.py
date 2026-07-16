"""
Fact-Check Agent — cross-verifies every analyst claim across 2+ sources.

Stretch goal implemented:
  - Takes cited_claims from analyst_node
  - For each claim, checks whether it can be corroborated by 2+ distinct sources
  - Claims verified by 2+ sources get verified=True
  - Claims only supported by 1 source remain unverified but are kept (hedged)
  - Claims that actively conflict with other sources are flagged as adversarial
  - Produces fact_check_results summary
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import CitedClaim, GraphState
from app.utils.llm_client import chat_with_fallback

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Fact-Checking Specialist for competitive intelligence.

You will receive a list of claims and a set of source documents.
For EACH claim, determine:
1. How many distinct sources support it (count_supporting)
2. Whether any sources actively contradict it (contradicted: true/false)
3. Your confidence assessment

Output ONLY a valid JSON object:
{
  "verification_results": [
    {
      "claim": "The exact claim text",
      "count_supporting": 2,
      "contradicted": false,
      "verified": true,
      "confidence": "high",
      "supporting_urls": ["https://...", "https://..."],
      "notes": "Brief note on verification"
    }
  ],
  "summary": {
    "total_claims": 10,
    "verified_2plus": 7,
    "single_source": 2,
    "contradicted": 1
  }
}

RULES:
- A claim is "verified" ONLY if count_supporting >= 2.
- If a claim is contradicted by another source, set contradicted=true and verified=false.
- For claims about alarming events (bankruptcy, fraud, etc.) with no corroboration, set contradicted=true.
- Be conservative — "not disproven" is NOT the same as "verified."
Output ONLY the JSON."""


def fact_check_node(state: GraphState) -> dict[str, Any]:
    """
    LangGraph node — cross-verifies analyst claims across multiple sources.

    For each cited_claim:
    - verified=True if 2+ distinct sources corroborate it
    - adversarial_flags updated if contradictions found
    """
    errors = list(state.get("errors", []))
    warnings = list(state.get("warnings", []))
    steps_used = (state.get("steps_used") or 0) + 1
    max_steps = state.get("max_steps") or 50

    cited_claims: list[CitedClaim] = list(state.get("cited_claims", []))
    adversarial_flags: list[str] = list(state.get("adversarial_flags", []))

    logger.info("[FactCheck] Verifying %d claims.", len(cited_claims))

    # ── Budget guard ──────────────────────────────────────────────────────
    if steps_used > max_steps or not cited_claims:
        if steps_used > max_steps:
            warnings.append(f"Fact-check skipped: step budget exhausted ({steps_used}/{max_steps})")
        return {
            "fact_check_results": [],
            "fact_check_passed": 0,
            "fact_check_failed": 0,
            "cited_claims": cited_claims,
            "steps_used": steps_used,
            "errors": errors,
            "warnings": warnings,
        }

    # ── Build source corpus for verification ─────────────────────────────
    sources = state.get("sources", [])
    source_corpus = "\n\n".join(
        f"[{s.get('url', '#')}]\n{s.get('content_snippet', s.get('title', ''))[:300]}"
        for s in sources[:12]
    )

    # Also add scraped pages
    scraped = state.get("scraped_pages", [])
    for page in scraped[:3]:
        source_corpus += f"\n\n[{page.get('url', '#')}]\n{page.get('content', '')[:500]}"

    # Build claim list for LLM
    claims_block = json.dumps(
        [{"claim": c.get("claim", ""), "source_url": c.get("source_url", "")}
         for c in cited_claims[:20]],  # cap at 20 to stay within token budget
        indent=2,
    )

    try:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=(
                f"Claims to verify:\n{claims_block}\n\n"
                f"Source corpus:\n{source_corpus[:5000]}"
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
        verification_results = parsed.get("verification_results", [])
        summary = parsed.get("summary", {})

    except Exception as exc:
        logger.warning("[FactCheck] LLM verification failed: %s", exc)
        errors.append(f"Fact-check LLM error: {exc}")
        # Graceful fallback — mark all claims as single-source (unverified but kept)
        verification_results = [
            {
                "claim": c.get("claim", ""),
                "count_supporting": 1,
                "contradicted": False,
                "verified": False,
                "confidence": "low",
                "supporting_urls": [c.get("source_url", "")],
                "notes": "Automated verification unavailable",
            }
            for c in cited_claims
        ]
        summary = {
            "total_claims": len(cited_claims),
            "verified_2plus": 0,
            "single_source": len(cited_claims),
            "contradicted": 0,
        }

    # ── Update cited_claims with verification status ──────────────────────
    # Build lookup by claim text
    verify_map: dict[str, dict] = {
        vr["claim"]: vr
        for vr in verification_results
        if vr.get("claim")
    }

    updated_claims: list[CitedClaim] = []
    for claim in cited_claims:
        claim_text = claim.get("claim", "")
        vr = verify_map.get(claim_text)

        if vr:
            if vr.get("contradicted", False):
                # Contradicted claim — add to adversarial flags, drop from briefing
                adversarial_flags.append(
                    f"CONTRADICTED: {claim_text} — {vr.get('notes', 'contradicted by sources')}"
                )
                logger.info("[FactCheck] Contradicted claim removed: %s", claim_text[:80])
                continue  # drop this claim

            updated_claim = CitedClaim(
                claim=claim_text,
                source_url=claim.get("source_url", ""),
                source_title=claim.get("source_title", ""),
                verified=vr.get("verified", False),
                confidence=vr.get("confidence", claim.get("confidence", "medium")),
                section=claim.get("section", "market"),
            )
            updated_claims.append(updated_claim)
        else:
            # Not found in verification results — keep as-is (single source)
            updated_claims.append(claim)

    verified_count = sum(1 for c in updated_claims if c.get("verified", False))
    unverified_count = len(updated_claims) - verified_count

    logger.info(
        "[FactCheck] Complete. verified=%d unverified=%d dropped=%d",
        verified_count, unverified_count,
        len(cited_claims) - len(updated_claims),
    )

    return {
        "cited_claims": updated_claims,
        "adversarial_flags": adversarial_flags,
        "fact_check_results": verification_results,
        "fact_check_passed": verified_count,
        "fact_check_failed": unverified_count,
        "steps_used": steps_used,
        "errors": errors,
        "warnings": warnings,
    }
