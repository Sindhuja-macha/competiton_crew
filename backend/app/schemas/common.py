"""
Shared/common Pydantic response schemas used across the API.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    environment: str


class MessageResponse(BaseModel):
    message: str


class ErrorDetail(BaseModel):
    field: Optional[str] = None
    message: str


class ErrorResponse(BaseModel):
    error: str
    details: Optional[list[ErrorDetail]] = None
    request_id: Optional[str] = None


class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
