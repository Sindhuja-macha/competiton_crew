"""Core package — config, logging, and shared dependencies."""

from app.core.config import Settings, get_settings
from app.core.logging_config import setup_logging, get_logger
from app.core.dependencies import get_db, get_app_settings

__all__ = [
    "Settings",
    "get_settings",
    "setup_logging",
    "get_logger",
    "get_db",
    "get_app_settings",
]
