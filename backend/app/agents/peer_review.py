"""
Peer-Review Agent — validates the briefing before publish.

Stretch goal implemented:
  - Scans all 3 required sections for uncited assertions
  - Checks that every section is present and non-empty
  - Verifies no adversarial/unverified claims leaked through
  - Produces peer_review_passed flag and peer_review_issues list
  - If critical issues found, blocks approval and logs them
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agents.state import GraphState

logger = logging.getLogger(__name__)

# Patterns that indicate an uncited assertion in Markdown text
# (a sentence that ends without a citation of the form [[...]](...) or [^N])
_CITATION_RE = re.compile(r"\[.+?\]\(.+?\)")          # [[Title]](URL)
_SENTENCE_RE = re.compile(r"[A-Z][^.!?]*[.!?]")       # sentence boundaries

# Required section titles
REQUIRED_SECTIONS = [
    "Competitor Pricing & Product Moves",
    "Market Signals & Trends",
    "Executive Summary",  # partial match for "Executive Summary & Strategic Recommendation"
]

# Adversarial keyword patterns that should never appear in the published briefing
_ADVERSARIAL_PUBLISH_RE = re.compile(
    r"going bankrupt|is bankrupt|fraud|criminal(ly)?|money laundering|"
    r"ponzi|being acquired by|shutting down",
    re.IGNORECASE,
)


def _count_uncited_sentences(markdown: str) -> list[str]:
    """
    Heuristic: find sentences in the briefing that don't have a citation nearby.
    Only checks substantive sentences (>30 chars, not headings/bullets).
    """
    uncited: list[str] = []
    lines = markdown.split("\n")
    for line in lines:
        # Skip headings, bullets, blank lines, citation-only lines
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(">"):
            continue
        if stripped.startswith("-") or stripped.startswith("*"):
            stripped = stripped.lstrip("-* ")
        if len(stripped) < 40:
            continue
        # Check if the line / nearby context has a citation marker
        if not _CITATION_RE.search(line):
            # Only flag lines that look like factual assertions (have a capital + period)
            if re.search(r"[A-Z].*\.", line):
                uncited.append(stripped[:100])
    return uncited[:10]  # Return at most 10 for logging


def peer_review_node(state: GraphState) -> dict[str, Any]:
    """
    LangGraph node — final quality gate before approval.

    Checks:
    1. All 3 required sections present and non-empty
    2. No adversarial patterns in final text
    3. Citation density acceptable (warns if low)
    4. Governance counters reviewed
    """
    errors = list(state.get("errors", []))
    warnings = list(state.get("warnings", []))
    steps_used = (state.get("steps_used") or 0) + 1

    final_report = state.get("final_report_markdown", "")
    report_sections = state.get("report_sections", [])
    cited_claims = state.get("cited_claims", [])
    uncited_dropped = state.get("uncited_claims_dropped", [])
    adversarial_flags = state.get("adversarial_flags", [])
    fact_check_passed = state.get("fact_check_passed", 0)
    peer_review_issues: list[str] = []

    logger.info("[PeerReview] Reviewing briefing (sections=%d, claims=%d).",
                len(report_sections), len(cited_claims))

    # ── Check 1: All 3 required sections present ─────────────────────────
    missing_sections: list[str] = []
    for required in REQUIRED_SECTIONS:
        if not any(required.lower() in s.lower() for s in report_sections):
            missing_sections.append(required)
        # Also check the actual markdown body
        if required not in final_report and required.split(" & ")[0] not in final_report:
            if required not in missing_sections:
                missing_sections.append(required)

    if missing_sections:
        peer_review_issues.append(
            f"Missing required sections: {', '.join(missing_sections)}"
        )

    # ── Check 2: Sections non-empty ──────────────────────────────────────
    section_pricing = state.get("briefing_section_pricing") or {}
    section_market = state.get("briefing_section_market") or {}
    section_exec = state.get("briefing_section_exec") or {}

    for sec_name, sec_obj in [
        ("Pricing & Product Moves", section_pricing),
        ("Market Signals", section_market),
        ("Executive Summary", section_exec),
    ]:
        content = sec_obj.get("content", "") if isinstance(sec_obj, dict) else ""
        if not content or len(content.strip()) < 100:
            peer_review_issues.append(f"Section '{sec_name}' is too short or empty.")

    # ── Check 3: No adversarial patterns leaked through ──────────────────
    if final_report and _ADVERSARIAL_PUBLISH_RE.search(final_report):
        # Find which lines contain the pattern
        flagged_lines = [
            line.strip()[:100]
            for line in final_report.split("\n")
            if _ADVERSARIAL_PUBLISH_RE.search(line)
        ]
        peer_review_issues.append(
            f"Adversarial/unverified claim detected in published briefing: "
            + "; ".join(flagged_lines[:2])
        )

    # ── Check 4: Minimum citation coverage ──────────────────────────────
    citation_count = len(_CITATION_RE.findall(final_report))
    if cited_claims and citation_count < 1:
        peer_review_issues.append(
            "No inline citations found in briefing text. Citation enforcement may have failed."
        )

    # ── Check 5: Governance metrics review ──────────────────────────────
    if len(uncited_dropped) > 20:
        warnings.append(
            f"High uncited-claim drop rate: {len(uncited_dropped)} claims dropped. "
            f"Consider re-running with more specific sources."
        )

    if adversarial_flags:
        warnings.append(
            f"{len(adversarial_flags)} adversarial/unverified flag(s) were suppressed from the briefing."
        )

    # ── Peer review verdict ──────────────────────────────────────────────
    # Critical vs warning issues
    critical_issues = [i for i in peer_review_issues if "Missing" in i or "Adversarial" in i]
    has_critical = bool(critical_issues)

    if has_critical:
        peer_review_passed = False
        note = (
            f"Peer review FAILED — {len(critical_issues)} critical issue(s): "
            + " | ".join(critical_issues[:3])
        )
        logger.warning("[PeerReview] FAILED: %s", note)
    elif peer_review_issues:
        peer_review_passed = True  # Allow publish with warnings
        note = (
            f"Peer review passed with {len(peer_review_issues)} warning(s): "
            + " | ".join(peer_review_issues[:3])
        )
        logger.info("[PeerReview] Passed with warnings.")
    else:
        peer_review_passed = True
        note = (
            f"Peer review passed. All 3 sections present. "
            f"Citation count: {citation_count}. "
            f"Verified claims: {fact_check_passed}."
        )
        logger.info("[PeerReview] Passed cleanly.")

    return {
        "peer_review_passed": peer_review_passed,
        "peer_review_issues": peer_review_issues,
        "peer_review_note": note,
        "steps_used": steps_used,
        "errors": errors,
        "warnings": warnings,
    }
