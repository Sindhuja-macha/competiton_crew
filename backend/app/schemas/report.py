"""
Pydantic schemas for the Report resource.

v2 — adds:
  - topic field (primary input)
  - 3 required briefing sections
  - governance fields (cited_claims, uncited_claims_dropped, adversarial_flags)
  - fact_check and peer_review fields
  - run_metadata
  - export download URLs
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Nested payload schemas
# ---------------------------------------------------------------------------

class NewsItem(BaseModel):
    title: str
    url: str
    source: str
    published_at: Optional[str] = None
    summary: Optional[str] = None


class SwotAnalysis(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    threats: list[str] = Field(default_factory=list)


class Source(BaseModel):
    title: str
    url: str
    source: str
    content_snippet: Optional[str] = None


class CitedClaimSchema(BaseModel):
    claim: str
    source_url: str
    source_title: str = ""
    verified: bool = False
    confidence: str = "medium"
    section: str = "market"


class BriefingSectionSchema(BaseModel):
    title: str
    content: str
    cited_claims: list[CitedClaimSchema] = Field(default_factory=list)


class GovernanceStats(BaseModel):
    cited_claims_kept: int = 0
    uncited_claims_dropped: int = 0
    adversarial_flags: int = 0
    fact_check_passed: int = 0
    fact_check_failed: int = 0


class BudgetStats(BaseModel):
    max_sources: int = 15
    max_steps: int = 50
    steps_used: int = 0
    sources_attempted: int = 0
    sources_succeeded: int = 0


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ReportCreate(BaseModel):
    """
    Input to create a new intelligence briefing run.

    topic is the primary field — a market intelligence topic.
    competitor_name is optional (focus on a specific company).
    """
    topic: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="Intelligence topic, e.g. 'EV pricing 2025' or 'cloud AI market'",
        examples=["EV pricing trends 2025"],
    )
    competitor_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional: specific competitor to focus on",
        examples=["Tesla"],
    )
    industry: str = Field(
        ...,
        min_length=1,
        max_length=255,
        examples=["Electric Vehicles"],
    )
    region: str = Field(
        ...,
        min_length=1,
        max_length=255,
        examples=["North America"],
    )
    max_sources: int = Field(
        default=15,
        ge=3,
        le=50,
        description="Hard cap on number of sources to gather",
    )
    max_steps: int = Field(
        default=50,
        ge=10,
        le=200,
        description="Hard cap on total workflow steps (runaway guard)",
    )

    @field_validator("topic", "industry", "region", mode="before")
    @classmethod
    def strip_whitespace(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("competitor_name", mode="before")
    @classmethod
    def strip_competitor(cls, v: Any) -> Optional[str]:
        if isinstance(v, str):
            return v.strip() or None
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class ReportResponse(BaseModel):
    id: str
    # Input fields
    topic: Optional[str] = None
    competitor_name: Optional[str] = None
    industry: str
    region: str
    # Standard sections (legacy compat)
    executive_summary: Optional[str] = None
    competitor_overview: Optional[str] = None
    latest_news: Optional[list[NewsItem]] = None
    pricing_summary: Optional[str] = None
    swot_analysis: Optional[SwotAnalysis] = None
    recommendations: Optional[list[str]] = None
    sources: Optional[list[Source]] = None
    # 3 required briefing sections
    briefing_section_pricing: Optional[BriefingSectionSchema] = None
    briefing_section_market: Optional[BriefingSectionSchema] = None
    briefing_section_exec: Optional[BriefingSectionSchema] = None
    final_report_markdown: Optional[str] = None
    report_sections: Optional[list[str]] = None
    # Governance
    cited_claims: Optional[list[CitedClaimSchema]] = None
    uncited_claims_dropped: Optional[list[str]] = None
    adversarial_flags: Optional[list[str]] = None
    fact_check_passed: Optional[int] = None
    fact_check_failed: Optional[int] = None
    # Peer review
    peer_review_passed: Optional[bool] = None
    peer_review_issues: Optional[list[str]] = None
    peer_review_note: Optional[str] = None
    # Run metadata
    run_metadata: Optional[dict[str, Any]] = None
    sources_attempted: Optional[int] = None
    sources_succeeded: Optional[int] = None
    warnings: Optional[list[str]] = None
    # Budget
    max_sources: Optional[int] = None
    max_steps: Optional[int] = None
    # Export paths
    pdf_path: Optional[str] = None
    markdown_path: Optional[str] = None
    # Status
    status: str
    error_message: Optional[str] = None
    duration_seconds: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReportListItem(BaseModel):
    """Lightweight response for list endpoints."""
    id: str
    topic: Optional[str] = None
    competitor_name: Optional[str] = None
    industry: str
    region: str
    status: str
    peer_review_passed: Optional[bool] = None
    fact_check_passed: Optional[int] = None
    duration_seconds: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ReportListResponse(BaseModel):
    items: list[ReportListItem]
    total: int
    page: int
    page_size: int
    pages: int
