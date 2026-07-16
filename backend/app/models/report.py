"""
ORM model for the `reports` table.

v2 — adds briefing-specific fields:
  - topic (replaces competitor_name as primary input)
  - 3 structured briefing sections (JSON)
  - governance fields: cited_claims, uncited_claims_dropped, adversarial_flags
  - fact_check results and counts
  - peer_review fields
  - run_metadata dict
  - warnings list
  - final_report_markdown (full text storage)
  - max_sources / max_steps budget fields
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, DateTime, JSON, Float, Integer, Boolean
from app.models.database import Base


class Report(Base):
    __tablename__ = "reports"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )

    # ── Input parameters ───────────────────────────────────────────────────
    topic = Column(String(512), nullable=True, index=True)           # PRIMARY topic input
    competitor_name = Column(String(255), nullable=True, index=True) # optional competitor focus
    industry = Column(String(255), nullable=False, default="Unknown")
    region = Column(String(255), nullable=False, default="Global")

    # ── Budget / governance config ──────────────────────────────────────────
    max_sources = Column(Integer, nullable=True, default=15)
    max_steps = Column(Integer, nullable=True, default=50)

    # ── Standard report content sections ──────────────────────────────────
    executive_summary = Column(Text, nullable=True)
    competitor_overview = Column(Text, nullable=True)
    latest_news = Column(JSON, nullable=True)           # list[dict]
    pricing_summary = Column(Text, nullable=True)
    swot_analysis = Column(JSON, nullable=True)         # {strengths, weaknesses, ...}
    recommendations = Column(JSON, nullable=True)       # list[str]
    sources = Column(JSON, nullable=True)               # list[{title, url, source}]

    # ── Structured 3 required briefing sections (stored as JSON) ──────────
    briefing_section_pricing = Column(JSON, nullable=True)  # BriefingSection
    briefing_section_market = Column(JSON, nullable=True)   # BriefingSection
    briefing_section_exec = Column(JSON, nullable=True)     # BriefingSection
    final_report_markdown = Column(Text, nullable=True)     # Full assembled Markdown
    report_sections = Column(JSON, nullable=True)           # list of section names present

    # ── Governance & citation tracking ─────────────────────────────────────
    cited_claims = Column(JSON, nullable=True)              # list[CitedClaim]
    uncited_claims_dropped = Column(JSON, nullable=True)    # list[str]
    adversarial_flags = Column(JSON, nullable=True)         # list[str]

    # ── Fact-check results ─────────────────────────────────────────────────
    fact_check_results = Column(JSON, nullable=True)        # list[dict]
    fact_check_passed = Column(Integer, nullable=True, default=0)
    fact_check_failed = Column(Integer, nullable=True, default=0)

    # ── Peer-review ────────────────────────────────────────────────────────
    peer_review_passed = Column(Boolean, nullable=True)
    peer_review_issues = Column(JSON, nullable=True)        # list[str]
    peer_review_note = Column(Text, nullable=True)

    # ── Run metadata ───────────────────────────────────────────────────────
    run_metadata = Column(JSON, nullable=True)              # {budget, governance, quality, ...}
    sources_attempted = Column(Integer, nullable=True, default=0)
    sources_succeeded = Column(Integer, nullable=True, default=0)
    warnings = Column(JSON, nullable=True)                  # list[str]

    # ── File paths for exports ─────────────────────────────────────────────
    pdf_path = Column(String(512), nullable=True)
    markdown_path = Column(String(512), nullable=True)

    # ── Status: pending | running | completed | failed ─────────────────────
    status = Column(String(50), nullable=False, default="pending", index=True)
    error_message = Column(Text, nullable=True)

    # ── Timing ────────────────────────────────────────────────────────────
    duration_seconds = Column(Float, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        topic_display = self.topic or self.competitor_name or "Unknown"
        return (
            f"<Report id={self.id!r} topic={topic_display!r} "
            f"status={self.status!r}>"
        )
