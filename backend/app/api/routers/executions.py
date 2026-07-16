"""
Executions router — read-only access to agent execution steps.

Endpoints:
  GET /api/v1/executions/                        – List all executions (paginated)
  GET /api/v1/executions/{execution_id}          – Get a single execution
  GET /api/v1/executions/report/{report_id}      – List executions for a report
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.models.execution import Execution
from app.schemas.execution import ExecutionListResponse, ExecutionResponse

router = APIRouter()


def _get_execution_or_404(execution_id: str, db: Session) -> Execution:
    ex = db.query(Execution).filter(Execution.id == execution_id).first()
    if not ex:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution '{execution_id}' not found.",
        )
    return ex


@router.get(
    "/",
    response_model=ExecutionListResponse,
    summary="List all executions (paginated)",
)
async def list_executions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ExecutionListResponse:
    total = db.query(Execution).count()
    offset = (page - 1) * page_size
    items = (
        db.query(Execution)
        .order_by(Execution.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return ExecutionListResponse(
        items=[ExecutionResponse.model_validate(e) for e in items],
        total=total,
    )


@router.get(
    "/report/{report_id}",
    response_model=ExecutionListResponse,
    summary="List executions for a specific report",
)
async def list_executions_for_report(
    report_id: str,
    db: Session = Depends(get_db),
) -> ExecutionListResponse:
    items = (
        db.query(Execution)
        .filter(Execution.report_id == report_id)
        .order_by(Execution.created_at.asc())
        .all()
    )
    return ExecutionListResponse(
        items=[ExecutionResponse.model_validate(e) for e in items],
        total=len(items),
    )


@router.get(
    "/{execution_id}",
    response_model=ExecutionResponse,
    summary="Get a single execution by ID",
)
async def get_execution(
    execution_id: str,
    db: Session = Depends(get_db),
) -> ExecutionResponse:
    ex = _get_execution_or_404(execution_id, db)
    return ExecutionResponse.model_validate(ex)
