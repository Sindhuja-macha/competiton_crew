"""
FastAPI dependency injection helpers.
Import these functions with `Depends(...)` in route handlers.
"""

from __future__ import annotations

from typing import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.database import SessionLocal


# ---------------------------------------------------------------------------
# Database session
# ---------------------------------------------------------------------------

def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session; closes it after the request completes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_app_settings(settings: Settings = Depends(get_settings)) -> Settings:
    """Inject the cached Settings instance into route handlers."""
    return settings
