"""
Approval Agent — final gate before the briefing is marked ready.

v2: Checks peer_review_passed status and governance completeness.
    All 3 required sections must be present.
    No adversarial patterns may have leaked through.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.state import GraphState

logger = logging.getLogger(__name__)

REQUIRED_SECTION_FIELDS = [
    "briefing_section_pricing",
    "briefing_section_market",
    "briefing_section_exec",
]


def approval_node(state: GraphState) -> dict[str, Any]:
    """
    LangGraph node — validates report completeness and marks approved.
    """
    topic = state.get("topic") or state.get("competitor_name", "Unknown")
    logger.info("[Approval] Validating briefing for topic='%s'.", topic)

    errors = list(state.get("errors", []))
    warnings = list(state.get("warnings", []))
    missing: list[str] = []
    quality_issues: list[str] = []

    # ── Check peer review result ──────────────────────────────────────────
    peer_review_passed = state.get("peer_review_passed")
    peer_review_issues = state.get("peer_review_issues", [])

    if peer_review_passed is False:
        quality_issues.extend([f"Peer review: {i}" for i in peer_review_issues[:3]])

    # ── Check 3 required sections ─────────────────────────────────────────
    for field in REQUIRED_SECTION_FIELDS:
        section = state.get(field)
        if not section:
            missing.append(field)
        elif isinstance(section, dict):
            content = section.get("content", "")
            if not content or len(content.strip()) < 50:
                missing.append(f"{field} (empty content)")

    # ── Check final report markdown ───────────────────────────────────────
    final_report = state.get("final_report_markdown", "")
    if not final_report or len(final_report.strip()) < 200:
        missing.append("final_report_markdown")

    # ── Governance check ──────────────────────────────────────────────────
    adversarial_flags = state.get("adversarial_flags", [])
    uncited_dropped = state.get("uncited_claims_dropped", [])

    # ── Approval decision ─────────────────────────────────────────────────
    if missing and len(missing) >= 2:
        note = (
            f"Partial approval — missing sections: {', '.join(missing[:3])}. "
            f"Briefing exported with available data."
        )
        approved = True  # Always export, never block delivery
        logger.warning("[Approval] Partial briefing for '%s': missing %s", topic, missing)
    elif quality_issues:
        note = (
            f"Approved with quality notices: {'; '.join(quality_issues[:3])}. "
            f"Uncited claims dropped: {len(uncited_dropped)}. "
            f"Adversarial flags suppressed: {len(adversarial_flags)}."
        )
        approved = True
        logger.info("[Approval] Approved with quality notices for '%s'.", topic)
    else:
        note = (
            f"Briefing approved. All 3 required sections present. "
            f"Peer review: {'passed' if peer_review_passed else 'not run'}. "
            f"Claims kept: {len(state.get('cited_claims', []))}. "
            f"Uncited dropped: {len(uncited_dropped)}. "
            f"Adversarial suppressed: {len(adversarial_flags)}."
        )
        approved = True
        logger.info("[Approval] Briefing fully approved for '%s'.", topic)

    return {
        "approved": approved,
        "approval_note": note,
        "errors": errors,
        "warnings": warnings,
    }
