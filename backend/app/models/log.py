"""
ORM model for the `logs` table.
Persists structured audit/activity logs for every agent action.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON
from app.models.database import Base


class Log(Base):
    __tablename__ = "logs"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )

    # Optional link to a report
    report_id = Column(
        String(36),
        ForeignKey("reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Optional link to a specific execution step
    execution_id = Column(
        String(36),
        ForeignKey("executions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Log metadata
    level = Column(String(20), nullable=False, default="INFO", index=True)
    # Levels: DEBUG | INFO | WARNING | ERROR | CRITICAL

    agent_name = Column(String(100), nullable=True, index=True)
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)   # extra structured context

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Log id={self.id!r} level={self.level!r} "
            f"agent={self.agent_name!r}>"
        )
