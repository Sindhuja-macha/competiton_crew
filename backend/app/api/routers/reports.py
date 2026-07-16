"""
Reports router — CRUD, AI workflow trigger, and export endpoints.

v2 endpoints:
  POST   /api/v1/reports/                        – Create briefing run (topic-based)
  GET    /api/v1/reports/                        – List reports (paginated)
  GET    /api/v1/reports/{report_id}             – Get full report
  DELETE /api/v1/reports/{report_id}             – Delete report
  GET    /api/v1/reports/{report_id}/status      – Lightweight status check
  GET    /api/v1/reports/{report_id}/export/markdown  – Download Markdown file
  GET    /api/v1/reports/{report_id}/export/pdf       – Download PDF file
  GET    /api/v1/reports/{report_id}/metadata    – Run metadata + governance stats
"""

from __future__ import annotations

import math
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import get_db
from app.core.logging_config import get_logger
from app.models.report import Report
from app.schemas.report import (
    ReportCreate,
    ReportListItem,
    ReportListResponse,
    ReportResponse,
)
from app.schemas.common import MessageResponse
from app.services.agent_service import run_workflow_background

router = APIRouter()
logger = get_logger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_report_or_404(report_id: str, db: Session) -> Report:
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report '{report_id}' not found.",
        )
    return report


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a briefing run and trigger the AI workflow",
)
async def create_report(
    payload: ReportCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ReportResponse:
    """
    Accepts intelligence topic details, creates a DB record,
    and kicks off the LangGraph v2 workflow as a background task.

    The topic field is the primary input. competitor_name is optional.
    """
    report = Report(
        id=str(uuid.uuid4()),
        topic=payload.topic,
        competitor_name=payload.competitor_name or payload.topic,
        industry=payload.industry,
        region=payload.region,
        max_sources=payload.max_sources,
        max_steps=payload.max_steps,
        status="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    logger.info(
        "Created briefing report %s for topic='%s' competitor='%s'.",
        report.id, report.topic, report.competitor_name,
    )

    background_tasks.add_task(run_workflow_background, report.id)
    return ReportResponse.model_validate(report)


@router.get(
    "/",
    response_model=ReportListResponse,
    summary="List briefing reports (paginated)",
)
async def list_reports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Filter by status: pending|running|completed|failed",
    ),
    db: Session = Depends(get_db),
) -> ReportListResponse:
    query = db.query(Report)
    if status_filter:
        query = query.filter(Report.status == status_filter)

    total = query.count()
    pages = math.ceil(total / page_size) if total else 1
    offset = (page - 1) * page_size
    reports = (
        query.order_by(Report.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return ReportListResponse(
        items=[ReportListItem.model_validate(r) for r in reports],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/{report_id}",
    response_model=ReportResponse,
    summary="Get a single report",
)
async def get_report(
    report_id: str,
    db: Session = Depends(get_db),
) -> ReportResponse:
    report = _get_report_or_404(report_id, db)
    return ReportResponse.model_validate(report)


@router.get(
    "/{report_id}/status",
    summary="Lightweight status check",
)
async def get_report_status(
    report_id: str,
    db: Session = Depends(get_db),
) -> dict:
    report = _get_report_or_404(report_id, db)
    return {
        "report_id": report.id,
        "status": report.status,
        "topic": report.topic,
        "competitor_name": report.competitor_name,
        "updated_at": report.updated_at.isoformat(),
        "error_message": report.error_message,
        "peer_review_passed": report.peer_review_passed,
        "fact_check_passed": report.fact_check_passed,
    }


@router.get(
    "/{report_id}/metadata",
    summary="Run metadata, budget usage, and governance stats",
)
async def get_report_metadata(
    report_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Returns detailed run metadata: budget usage, governance counters, peer review."""
    report = _get_report_or_404(report_id, db)

    return {
        "report_id": report.id,
        "topic": report.topic,
        "competitor_name": report.competitor_name,
        "industry": report.industry,
        "region": report.region,
        "status": report.status,
        "budget": {
            "max_sources": report.max_sources,
            "max_steps": report.max_steps,
            "sources_attempted": report.sources_attempted,
            "sources_succeeded": report.sources_succeeded,
        },
        "governance": {
            "cited_claims_kept": len(report.cited_claims or []),
            "uncited_claims_dropped": len(report.uncited_claims_dropped or []),
            "adversarial_flags": len(report.adversarial_flags or []),
            "fact_check_passed": report.fact_check_passed or 0,
            "fact_check_failed": report.fact_check_failed or 0,
            "pct_claims_cited": (
                round(
                    len(report.cited_claims or []) /
                    max(1, len(report.cited_claims or []) + len(report.uncited_claims_dropped or []))
                    * 100,
                    1,
                )
            ),
        },
        "quality": {
            "peer_review_passed": report.peer_review_passed,
            "peer_review_issues": report.peer_review_issues or [],
            "peer_review_note": report.peer_review_note,
            "sections_present": report.report_sections or [],
        },
        "timing": {
            "duration_seconds": report.duration_seconds,
            "created_at": report.created_at.isoformat(),
            "updated_at": report.updated_at.isoformat(),
        },
        "warnings": report.warnings or [],
        "failed_sources": (report.run_metadata or {}).get("failed_sources", []),
        "run_metadata": report.run_metadata,
    }


# ---------------------------------------------------------------------------
# Export endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/{report_id}/export/markdown",
    summary="Download briefing as Markdown file",
    response_class=PlainTextResponse,
)
async def export_markdown(
    report_id: str,
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """
    Returns the full Markdown briefing as a downloadable file.
    If a pre-saved file exists, serves it; otherwise generates on-the-fly.
    """
    report = _get_report_or_404(report_id, db)

    if report.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Report is not yet complete (status={report.status}).",
        )

    # Serve existing file if available
    if report.markdown_path and os.path.exists(report.markdown_path):
        with open(report.markdown_path, "r", encoding="utf-8") as f:
            content = f.read()
    elif report.final_report_markdown:
        # Save and serve
        export_dir = settings.export_dir
        os.makedirs(export_dir, exist_ok=True)
        fname = f"briefing_{report_id}.md"
        fpath = os.path.join(export_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(report.final_report_markdown)
        report.markdown_path = fpath
        db.commit()
        content = report.final_report_markdown
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Markdown content not available for this report.",
        )

    topic_slug = (report.topic or "report").replace(" ", "_")[:40]
    filename = f"competitive_intel_{topic_slug}_{report_id[:8]}.md"
    return PlainTextResponse(
        content=content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        media_type="text/markdown",
    )


@router.get(
    "/{report_id}/export/pdf",
    summary="Download briefing as PDF",
)
async def export_pdf(
    report_id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    """
    Generates or serves the PDF export.
    Uses ReportLab to produce a formatted multi-page PDF.
    """
    report = _get_report_or_404(report_id, db)

    if report.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Report is not yet complete (status={report.status}).",
        )

    # Serve existing PDF if already generated
    if report.pdf_path and os.path.exists(report.pdf_path):
        topic_slug = (report.topic or "report").replace(" ", "_")[:40]
        return FileResponse(
            path=report.pdf_path,
            filename=f"competitive_intel_{topic_slug}_{report_id[:8]}.pdf",
            media_type="application/pdf",
        )

    # Generate PDF
    try:
        from app.services.pdf_service import generate_pdf

        report_data = {
            "topic": report.topic or report.competitor_name,
            "competitor_name": report.competitor_name or report.topic,
            "industry": report.industry,
            "region": report.region,
            "created_at": report.created_at,
            "executive_summary": report.executive_summary,
            "competitor_overview": report.competitor_overview,
            "pricing_summary": report.pricing_summary,
            "swot_analysis": report.swot_analysis,
            "recommendations": report.recommendations,
            "latest_news": report.latest_news,
            "sources": report.sources,
            # v2 briefing sections
            "briefing_section_pricing": report.briefing_section_pricing,
            "briefing_section_market": report.briefing_section_market,
            "briefing_section_exec": report.briefing_section_exec,
            "final_report_markdown": report.final_report_markdown,
            # Governance stats
            "peer_review_passed": report.peer_review_passed,
            "fact_check_passed": report.fact_check_passed,
            "fact_check_failed": report.fact_check_failed,
            "uncited_claims_dropped": report.uncited_claims_dropped,
        }

        pdf_path = generate_pdf(
            report_data=report_data,
            export_dir=settings.export_dir,
            report_id=report_id,
        )

        report.pdf_path = pdf_path
        db.commit()

        topic_slug = (report.topic or "report").replace(" ", "_")[:40]
        return FileResponse(
            path=pdf_path,
            filename=f"competitive_intel_{topic_slug}_{report_id[:8]}.pdf",
            media_type="application/pdf",
        )

    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PDF export requires the 'reportlab' package. Install it with: pip install reportlab",
        )
    except Exception as exc:
        logger.exception("PDF generation failed for report %s: %s", report_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed: {exc}",
        )


@router.delete(
    "/{report_id}",
    response_model=MessageResponse,
    summary="Delete a report",
)
async def delete_report(
    report_id: str,
    db: Session = Depends(get_db),
) -> MessageResponse:
    report = _get_report_or_404(report_id, db)
    db.delete(report)
    db.commit()
    logger.info("Deleted report %s.", report_id)
    return MessageResponse(message=f"Report '{report_id}' deleted successfully.")
