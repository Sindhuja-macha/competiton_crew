"""
Server-Sent Events (SSE) router — real-time agent status streaming.

Endpoint:
  GET /api/v1/stream/{report_id}

The client opens a persistent SSE connection. Every 1.5 seconds this endpoint
pushes the latest report status + execution steps as a JSON event. The stream
closes automatically when the workflow reaches a terminal state
(completed | failed) or after a 5-minute timeout.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.core.logging_config import get_logger
from app.models.execution import Execution
from app.models.report import Report

router = APIRouter()
logger = get_logger(__name__)

POLL_INTERVAL = 1.5          # seconds between pushes
MAX_STREAM_SECONDS = 300     # 5-minute hard timeout


def _serialize_report(report: Report) -> dict:
    """Return a lean dict safe for JSON serialisation."""
    return {
        "id": report.id,
        "topic": report.topic,
        "competitor_name": report.competitor_name,
        "industry": report.industry,
        "region": report.region,
        "status": report.status,
        "error_message": report.error_message,
        "duration_seconds": report.duration_seconds,
        "peer_review_passed": report.peer_review_passed,
        "fact_check_passed": report.fact_check_passed,
        "updated_at": report.updated_at.isoformat() if report.updated_at else None,
    }


def _serialize_execution(ex: Execution) -> dict:
    return {
        "id": ex.id,
        "agent_name": ex.agent_name,
        "status": ex.status,
        "started_at": ex.started_at.isoformat() if ex.started_at else None,
        "completed_at": ex.completed_at.isoformat() if ex.completed_at else None,
        "duration_seconds": ex.duration_seconds,
        "error_message": ex.error_message,
    }


async def _event_generator(report_id: str, db: Session):
    """Async generator that yields SSE-formatted text chunks."""
    elapsed = 0.0

    while elapsed < MAX_STREAM_SECONDS:
        try:
            # Re-query every tick so we get fresh DB data
            report: Report | None = (
                db.query(Report).filter(Report.id == report_id).first()
            )

            if report is None:
                payload = json.dumps({"error": f"Report {report_id!r} not found."})
                yield f"event: error\ndata: {payload}\n\n"
                return

            executions = (
                db.query(Execution)
                .filter(Execution.report_id == report_id)
                .order_by(Execution.created_at.asc())
                .all()
            )

            payload = json.dumps(
                {
                    "report": _serialize_report(report),
                    "executions": [_serialize_execution(e) for e in executions],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            yield f"event: status\ndata: {payload}\n\n"

            # Stop streaming once the workflow is done
            if report.status in ("completed", "failed"):
                yield "event: done\ndata: {}\n\n"
                return

        except Exception as exc:
            logger.warning("SSE stream error for report %s: %s", report_id, exc)
            payload = json.dumps({"error": str(exc)})
            yield f"event: error\ndata: {payload}\n\n"
            return

        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

    # Timeout
    yield "event: timeout\ndata: {}\n\n"


@router.get(
    "/{report_id}",
    summary="Stream real-time agent status for a report (SSE)",
    response_class=StreamingResponse,
)
async def stream_report_status(
    report_id: str,
    db: Session = Depends(get_db),
):
    """
    Opens a Server-Sent Events stream for the given report.
    Pushes JSON status events every ~1.5 s until the workflow finishes.

    Event types:
      - status : { report, executions, timestamp }
      - done   : workflow reached terminal state
      - error  : something went wrong
      - timeout: 5-minute hard limit reached
    """
    return StreamingResponse(
        _event_generator(report_id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",      # disable nginx buffering if present
            "Connection": "keep-alive",
        },
    )
