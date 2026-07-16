"""
ORM model for the `executions` table.
Tracks each LangGraph workflow run tied to a report.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, DateTime, Float, ForeignKey, JSON
from app.models.database import Base


class Execution(Base):
    __tablename__ = "executions"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        index=True,
    )

    # Link back to the parent report
    report_id = Column(
        String(36),
        ForeignKey("reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Which agent ran in this execution step
    agent_name = Column(String(100), nullable=False, index=True)

    # Status: queued | running | completed | failed | skipped
    status = Column(String(50), nullable=False, default="queued", index=True)

    # Input/output payloads as JSON blobs
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<Execution id={self.id!r} agent={self.agent_name!r} "
            f"status={self.status!r}>"
        )
