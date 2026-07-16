"""
Shared LangGraph state for the Competitive Intelligence Briefing Crew.

GraphState is the single "memory" object that flows through all nodes.
Each agent reads from it and writes its outputs back.

Version 2 — adds:
  - topic-based input (replaces competitor_name-only approach)
  - run/step budget tracking
  - per-source partial-failure notes
  - cited_claims list with mandatory source refs
  - governance flags (uncited_claims_dropped, adversarial_flags)
  - fact-check and peer-review outputs
  - structured 3-section briefing fields
  - run metadata for export
"""

from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict

# ---------------------------------------------------------------------------
# Budget defaults (can be overridden at runtime via config)
# ---------------------------------------------------------------------------
DEFAULT_MAX_SOURCES = 15
DEFAULT_MAX_STEPS = 50


class CitedClaim(TypedDict, total=False):
    """A single claim with mandatory source attribution."""
    claim: str                          # The assertion being made
    source_url: str                     # URL of supporting source
    source_title: str                   # Human-readable source title
    verified: bool                      # True if cross-verified by fact-check
    confidence: str                     # high | medium | low
    section: str                        # which briefing section this belongs to


class SourceResult(TypedDict, total=False):
    """A single gathered source with status."""
    title: str
    url: str
    source: str                         # DuckDuckGo | Scraped | NewsRSS
    content_snippet: str
    status: str                         # ok | failed | timeout | skipped
    failure_reason: Optional[str]       # populated when status != ok


class BriefingSection(TypedDict, total=False):
    """One of the 3 required briefing sections."""
    title: str
    content: str                        # Markdown prose
    cited_claims: list[CitedClaim]      # every claim in this section


class GraphState(TypedDict, total=False):
    # ── Inputs ─────────────────────────────────────────────────────────────
    # Topic-based input — may or may not include a specific competitor name
    topic: str                          # "EV market pricing 2025" | "cloud AI competitors"
    competitor_name: str                # optional specific competitor focus
    industry: str
    region: str
    report_id: str

    # ── Budget / governance config ──────────────────────────────────────────
    max_sources: int                    # hard cap on sources gathered
    max_steps: int                      # hard cap on total workflow steps
    steps_used: int                     # counter incremented each node
    sources_attempted: int              # total sources attempted (ok + failed)
    sources_succeeded: int              # sources that returned usable data

    # ── Planner outputs ─────────────────────────────────────────────────────
    plan: list[str]

    # ── Research outputs ────────────────────────────────────────────────────
    search_results: list[dict[str, Any]]        # raw DuckDuckGo results
    scraped_pages: list[dict[str, Any]]         # scraped content
    source_results: list[SourceResult]          # structured per-source status
    failed_sources: list[str]                   # URLs that failed (for notes)
    competitor_overview: str
    pricing_summary: str
    sources: list[dict[str, str]]               # final deduplicated source list

    # ── News outputs ────────────────────────────────────────────────────────
    latest_news: list[dict[str, Any]]

    # ── Analyst outputs — all claims MUST carry citations ──────────────────
    cited_claims: list[CitedClaim]              # ALL extracted claims with sources
    uncited_claims_dropped: list[str]           # claims dropped due to no source
    adversarial_flags: list[str]               # suspicious/unverified assertions
    executive_summary: str
    swot_analysis: dict[str, list[str]]         # {strengths, weaknesses, …}
    market_trends: str
    recommendations: list[str]

    # ── Fact-check outputs ──────────────────────────────────────────────────
    fact_check_results: list[dict[str, Any]]   # per-claim verification details
    fact_check_passed: int                      # claims with 2+ source confirmation
    fact_check_failed: int                      # claims that could not be verified

    # ── Writer outputs — 3 required sections ──────────────────────────────
    briefing_section_pricing: BriefingSection  # Section 1: Pricing & Product Moves
    briefing_section_market: BriefingSection   # Section 2: Market Signals
    briefing_section_exec: BriefingSection     # Section 3: Exec Summary + Recommendation
    final_report_markdown: str                  # Complete assembled Markdown
    report_sections: list[str]                  # Section names present

    # ── Peer-review outputs ─────────────────────────────────────────────────
    peer_review_passed: bool
    peer_review_issues: list[str]              # issues found
    peer_review_note: str                       # summary note

    # ── Approval outputs ────────────────────────────────────────────────────
    approved: bool
    approval_note: str

    # ── Run metadata ────────────────────────────────────────────────────────
    run_metadata: dict[str, Any]               # timing, budget usage, governance stats

    # ── Error tracking ──────────────────────────────────────────────────────
    errors: list[str]
    warnings: list[str]
