"""
Logs router — read-only access to audit logs.

Endpoints:
  GET /api/v1/logs/                        – List logs (paginated, filterable)
  GET /api/v1/logs/{log_id}                – Get a single log entry
  GET /api/v1/logs/report/{report_id}      – Get logs for a specific report
"""

from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.models.log import Log
from app.schemas.log import LogListResponse, LogResponse

router = APIRouter()


def _get_log_or_404(log_id: str, db: Session) -> Log:
    log = db.query(Log).filter(Log.id == log_id).first()
    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log entry '{log_id}' not found.",
        )
    return log


@router.get(
    "/",
    response_model=LogListResponse,
    summary="List audit logs (paginated & filterable)",
)
async def list_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    level: Optional[str] = Query(
        default=None,
        description="Filter by log level: DEBUG|INFO|WARNING|ERROR|CRITICAL",
    ),
    agent_name: Optional[str] = Query(default=None, description="Filter by agent name"),
    db: Session = Depends(get_db),
) -> LogListResponse:
    query = db.query(Log)
    if level:
        query = query.filter(Log.level == level.upper())
    if agent_name:
        query = query.filter(Log.agent_name == agent_name)

    total = query.count()
    pages = math.ceil(total / page_size) if total else 1
    offset = (page - 1) * page_size
    items = (
        query.order_by(Log.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    return LogListResponse(
        items=[LogResponse.model_validate(l) for l in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/report/{report_id}",
    response_model=LogListResponse,
    summary="Get all logs for a specific report",
)
async def list_logs_for_report(
    report_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> LogListResponse:
    query = db.query(Log).filter(Log.report_id == report_id)
    total = query.count()
    pages = math.ceil(total / page_size) if total else 1
    offset = (page - 1) * page_size
    items = (
        query.order_by(Log.created_at.asc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return LogListResponse(
        items=[LogResponse.model_validate(l) for l in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/{log_id}",
    response_model=LogResponse,
    summary="Get a single log entry",
)
async def get_log(
    log_id: str,
    db: Session = Depends(get_db),
) -> LogResponse:
    log = _get_log_or_404(log_id, db)
    return LogResponse.model_validate(log)
