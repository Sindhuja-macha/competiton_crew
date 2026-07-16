"""
Pydantic schemas for the Log resource.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class LogResponse(BaseModel):
    id: str
    report_id: Optional[str] = None
    execution_id: Optional[str] = None
    level: str
    agent_name: Optional[str] = None
    message: str
    details: Optional[dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LogListResponse(BaseModel):
    items: list[LogResponse]
    total: int
    page: int
    page_size: int
    pages: int


class LogCreate(BaseModel):
    """Internal schema used by the agent service to write logs."""

    report_id: Optional[str] = None
    execution_id: Optional[str] = None
    level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    agent_name: Optional[str] = None
    message: str = Field(..., min_length=1)
    details: Optional[dict[str, Any]] = None
