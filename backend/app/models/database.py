"""
Database engine, session factory, and Base declarative class.
All models import Base from here; the engine is created once at startup.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# ---------------------------------------------------------------------------
# Resolve the database URL from the environment (with sensible default)
# ---------------------------------------------------------------------------
DATABASE_URL: str = os.getenv(
    "DATABASE_URL", "sqlite:///./data/competitive_intel.db"
)

# SQLite requires check_same_thread=False when used with FastAPI's thread pool
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,          # set True for SQL debug output
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


def get_db():
    """FastAPI dependency that yields a DB session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_tables() -> None:
    """Create all tables defined by models that import Base."""
    # Import models so SQLAlchemy knows about them before creating tables
    from app.models import report, execution, log  # noqa: F401
    Base.metadata.create_all(bind=engine)
    # Apply incremental migrations for existing SQLite DBs
    _migrate_sqlite()


def _migrate_sqlite() -> None:
    """
    Safe ALTER TABLE additions for existing SQLite databases.
    SQLite does not support ADD COLUMN IF NOT EXISTS, so we check
    the existing columns first and add only what's missing.
    Each new column introduced in v2 is listed here.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return  # Only needed for SQLite; PostgreSQL uses Alembic

    NEW_COLUMNS = [
        # (table, column_name, column_def)
        ("reports", "topic",                    "TEXT"),
        ("reports", "max_sources",              "INTEGER DEFAULT 15"),
        ("reports", "max_steps",                "INTEGER DEFAULT 50"),
        ("reports", "briefing_section_pricing", "JSON"),
        ("reports", "briefing_section_market",  "JSON"),
        ("reports", "briefing_section_exec",    "JSON"),
        ("reports", "final_report_markdown",    "TEXT"),
        ("reports", "report_sections",          "JSON"),
        ("reports", "cited_claims",             "JSON"),
        ("reports", "uncited_claims_dropped",   "JSON"),
        ("reports", "adversarial_flags",        "JSON"),
        ("reports", "fact_check_results",       "JSON"),
        ("reports", "fact_check_passed",        "INTEGER DEFAULT 0"),
        ("reports", "fact_check_failed",        "INTEGER DEFAULT 0"),
        ("reports", "peer_review_passed",       "BOOLEAN"),
        ("reports", "peer_review_issues",       "JSON"),
        ("reports", "peer_review_note",         "TEXT"),
        ("reports", "run_metadata",             "JSON"),
        ("reports", "sources_attempted",        "INTEGER DEFAULT 0"),
        ("reports", "sources_succeeded",        "INTEGER DEFAULT 0"),
        ("reports", "warnings",                 "JSON"),
    ]

    with engine.connect() as conn:
        for table, col, col_def in NEW_COLUMNS:
            try:
                # Check existing columns via PRAGMA
                result = conn.execute(
                    __import__("sqlalchemy").text(f"PRAGMA table_info({table})")
                )
                existing = {row[1] for row in result}
                if col not in existing:
                    conn.execute(
                        __import__("sqlalchemy").text(
                            f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"
                        )
                    )
                    conn.commit()
            except Exception:
                pass  # Ignore — table may not exist yet (create_all will handle it)
