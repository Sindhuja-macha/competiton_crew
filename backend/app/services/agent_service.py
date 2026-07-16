"""
Agent Service — runs the LangGraph v2.1 workflow and persists all outputs to the DB.

v2.1 fixes:
  - Removed double tracker.complete() bug in _run_langgraph_with_tracking.
    The original code called tracker.complete(active_node) for the PREVIOUS node
    AND then immediately called tracker.complete(node_name) for the CURRENT node
    in the same loop iteration, meaning each node was completed twice.
    Fix: simplified the stream loop to start → update state → complete per event.
  - Uses run_graph(topic=...) via the workflow module
  - Persists all 3 briefing sections, governance stats, fact-check, peer-review
  - AGENT_PIPELINE updated to include fact_check and peer_review
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.logging_config import get_logger
from app.models.database import SessionLocal
from app.models.execution import Execution
from app.models.log import Log
from app.models.report import Report

logger = get_logger(__name__)

# Ordered agent steps in v2 pipeline (sequential, no parallel fan-in)
AGENT_PIPELINE: list[str] = [
    "planner",
    "research",
    "news",
    "analyst",
    "fact_check",
    "writer",
    "peer_review",
    "approval",
]


# ---------------------------------------------------------------------------
# Internal DB helpers
# ---------------------------------------------------------------------------

def _write_log(
    db,
    *,
    report_id: str,
    execution_id: str | None,
    level: str,
    agent_name: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    log = Log(
        id=str(uuid.uuid4()),
        report_id=report_id,
        execution_id=execution_id,
        level=level,
        agent_name=agent_name,
        message=message,
        details=details,
        created_at=datetime.now(timezone.utc),
    )
    db.add(log)
    db.commit()


def _create_execution(db, *, report_id: str, agent_name: str,
                       status: str = "queued", input_data: dict | None = None) -> Execution:
    ex = Execution(
        id=str(uuid.uuid4()),
        report_id=report_id,
        agent_name=agent_name,
        status=status,
        input_data=input_data,
        created_at=datetime.now(timezone.utc),
    )
    db.add(ex)
    db.commit()
    db.refresh(ex)
    return ex


def _start_execution(db, ex: Execution) -> None:
    ex.status = "running"
    ex.started_at = datetime.now(timezone.utc)
    db.commit()


def _finish_execution(
    db,
    ex: Execution,
    *,
    status: str,
    output_data: dict | None = None,
    error_message: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)

    ex.status = status
    ex.output_data = output_data
    ex.error_message = error_message
    ex.completed_at = now

    if ex.started_at:
        started = ex.started_at

        # Convert naive datetime to UTC-aware if necessary
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)

        ex.duration_seconds = (now - started).total_seconds()

    db.commit()

# ---------------------------------------------------------------------------
# Execution tracker
# ---------------------------------------------------------------------------

class _ExecutionTracker:
    def __init__(self, db, report_id: str):
        self.db = db
        self.report_id = report_id
        self._rows: dict[str, Execution] = {}
        for agent in AGENT_PIPELINE:
            ex = _create_execution(db, report_id=report_id, agent_name=agent)
            self._rows[agent] = ex

    def start(self, agent: str) -> None:
        ex = self._rows.get(agent)
        if ex and ex.status == "queued":
            _start_execution(self.db, ex)
            _write_log(self.db, report_id=self.report_id, execution_id=ex.id,
                       level="INFO", agent_name=agent,
                       message=f"{agent.capitalize()} agent started.")

    def complete(self, agent: str, output_data: dict | None = None) -> None:
        ex = self._rows.get(agent)
        if ex and ex.status == "running":
            _finish_execution(self.db, ex, status="completed", output_data=output_data)
            dur = ex.duration_seconds or 0
            _write_log(self.db, report_id=self.report_id, execution_id=ex.id,
                       level="INFO", agent_name=agent,
                       message=f"{agent.capitalize()} agent completed in {dur:.1f}s.")

    def fail(self, agent: str, error: str) -> None:
        ex = self._rows.get(agent)
        if ex and ex.status in ("queued", "running"):
            _finish_execution(self.db, ex, status="failed", error_message=error)
            _write_log(self.db, report_id=self.report_id, execution_id=ex.id,
                       level="ERROR", agent_name=agent,
                       message=f"{agent.capitalize()} agent failed: {error}")


# ---------------------------------------------------------------------------
# Output summaries for per-agent DB records
# ---------------------------------------------------------------------------

def _safe_output_summary(state: dict, agent: str) -> dict:
    """Compact summary of each agent's output for storage."""
    summaries = {
        "planner": lambda s: {"plan_steps": len(s.get("plan", []))},
        "research": lambda s: {
            "search_results": len(s.get("search_results", [])),
            "scraped_pages": len(s.get("scraped_pages", [])),
            "sources_attempted": s.get("sources_attempted", 0),
            "sources_succeeded": s.get("sources_succeeded", 0),
            "failed_sources": len(s.get("failed_sources", [])),
        },
        "news": lambda s: {"articles": len(s.get("latest_news", []))},
        "analyst": lambda s: {
            "cited_claims": len(s.get("cited_claims", [])),
            "uncited_dropped": len(s.get("uncited_claims_dropped", [])),
            "adversarial_flags": len(s.get("adversarial_flags", [])),
            "has_swot": bool(s.get("swot_analysis")),
        },
        "fact_check": lambda s: {
            "fact_check_passed": s.get("fact_check_passed", 0),
            "fact_check_failed": s.get("fact_check_failed", 0),
            "total_checked": len(s.get("fact_check_results", [])),
        },
        "writer": lambda s: {
            "report_length": len(s.get("final_report_markdown", "")),
            "sections": s.get("report_sections", []),
            "has_pricing_section": bool(s.get("briefing_section_pricing")),
            "has_market_section": bool(s.get("briefing_section_market")),
            "has_exec_section": bool(s.get("briefing_section_exec")),
        },
        "peer_review": lambda s: {
            "peer_review_passed": s.get("peer_review_passed", False),
            "issues": s.get("peer_review_issues", []),
        },
        "approval": lambda s: {
            "approved": s.get("approved", False),
            "note": s.get("approval_note", ""),
        },
    }
    fn = summaries.get(agent)
    if fn:
        try:
            return fn(state)
        except Exception:
            pass
    return {}


# ---------------------------------------------------------------------------
# LangGraph wrapper with per-node DB hooks
# ---------------------------------------------------------------------------

def _run_langgraph_with_tracking(report: Report, tracker: _ExecutionTracker, db) -> dict[str, Any]:
    """
    Stream the LangGraph graph, recording start/complete for each node.

    BUG FIX v2.1:
      The original code maintained an `active_node` variable and called
      tracker.complete(active_node) when it saw a NEW node start, THEN
      immediately called tracker.complete(node_name) again. This meant
      every node was completed twice in the DB.

      Fix: simplified to start → accumulate state → complete inside a single
      block, with a guard in tracker.complete() that only fires when status
      is still "running".
    """
    from app.agents.workflow import get_compiled_graph

    graph = get_compiled_graph()

    initial_state = {
        "topic": report.topic or report.competitor_name,
        "competitor_name": report.competitor_name or report.topic,
        "industry": report.industry,
        "region": report.region,
        "report_id": report.id,
        "max_sources": report.max_sources or 15,
        "max_steps": report.max_steps or 50,
        "steps_used": 0,
        "sources_attempted": 0,
        "sources_succeeded": 0,
        "cited_claims": [],
        "uncited_claims_dropped": [],
        "adversarial_flags": [],
        "errors": [],
        "warnings": [],
    }

    final_state: dict[str, Any] = dict(initial_state)

    # graph.stream with stream_mode="updates" yields {node_name: node_output_delta}
    for event in graph.stream(initial_state, stream_mode="updates"):
        for node_name, node_output in event.items():
            if node_name in ("__start__", "__end__"):
                continue

            # Mark as started (guard: only if still queued)
            tracker.start(node_name)

            # Merge node output into accumulated state
            if isinstance(node_output, dict):
                final_state.update(node_output)

            # Mark as completed (guard: only if still running)
            tracker.complete(
                node_name,
                output_data=_safe_output_summary(final_state, node_name),
            )

            # Write governance audit log after key governance agents
            if node_name == "analyst":
                _write_log(
                    db, report_id=report.id, execution_id=None,
                    level="INFO", agent_name="governance",
                    message=(
                        f"Analyst governance: "
                        f"{len(final_state.get('cited_claims', []))} claims kept, "
                        f"{len(final_state.get('uncited_claims_dropped', []))} dropped, "
                        f"{len(final_state.get('adversarial_flags', []))} adversarial flags."
                    ),
                    details={
                        "cited_claims_kept": len(final_state.get("cited_claims", [])),
                        "uncited_dropped": len(final_state.get("uncited_claims_dropped", [])),
                        "adversarial_flags": final_state.get("adversarial_flags", []),
                    },
                )
            elif node_name == "fact_check":
                _write_log(
                    db, report_id=report.id, execution_id=None,
                    level="INFO", agent_name="governance",
                    message=(
                        f"Fact-check: "
                        f"{final_state.get('fact_check_passed', 0)} verified (2+ sources), "
                        f"{final_state.get('fact_check_failed', 0)} single-source."
                    ),
                )
            elif node_name == "peer_review":
                passed = final_state.get("peer_review_passed", False)
                _write_log(
                    db, report_id=report.id, execution_id=None,
                    level="INFO" if passed else "WARNING",
                    agent_name="governance",
                    message=f"Peer review: {'PASSED' if passed else 'FAILED'} — "
                            f"{final_state.get('peer_review_note', '')}",
                    details={"issues": final_state.get("peer_review_issues", [])},
                )

    return final_state


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_workflow_background(report_id: str) -> None:
    """
    Synchronous function executed by FastAPI's BackgroundTasks.
    Runs the full LangGraph v2.1 workflow and persists all outputs.
    """
    db = SessionLocal()
    try:
        report: Report | None = db.query(Report).filter(Report.id == report_id).first()
        if not report:
            logger.error("run_workflow_background: report %s not found.", report_id)
            return

        report.status = "running"
        report.updated_at = datetime.now(timezone.utc)
        db.commit()

        _write_log(db, report_id=report_id, execution_id=None, level="INFO",
                   agent_name="orchestrator",
                   message=(
                       f"LangGraph v2.1 workflow started. "
                       f"topic='{report.topic}' competitor='{report.competitor_name}' "
                       f"({report.industry} / {report.region}). "
                       f"Budget: max_sources={report.max_sources} max_steps={report.max_steps}."
                   ))

        workflow_start = datetime.now(timezone.utc)
        tracker = _ExecutionTracker(db, report_id)

        try:
            final_state = _run_langgraph_with_tracking(report, tracker, db)
        except Exception as workflow_exc:
            logger.exception("LangGraph workflow error for report %s.", report_id)
            for agent in AGENT_PIPELINE:
                ex = tracker._rows.get(agent)
                if ex and ex.status in ("queued", "running"):
                    tracker.fail(agent, str(workflow_exc))
            raise

        # ── Persist all results ─────────────────────────────────────────
        now = datetime.now(timezone.utc)
        duration = (now - workflow_start).total_seconds()

        report.status = "completed"
        report.updated_at = now
        report.duration_seconds = duration

        # Standard section fields (legacy compat)
        report.competitor_overview = final_state.get("competitor_overview") or ""
        report.pricing_summary = final_state.get("pricing_summary") or ""
        report.sources = final_state.get("sources") or []
        report.latest_news = final_state.get("latest_news") or []
        report.executive_summary = final_state.get("executive_summary") or ""
        report.swot_analysis = final_state.get("swot_analysis") or {}
        report.recommendations = final_state.get("recommendations") or []

        # 3 required briefing sections
        report.briefing_section_pricing = final_state.get("briefing_section_pricing") or {}
        report.briefing_section_market = final_state.get("briefing_section_market") or {}
        report.briefing_section_exec = final_state.get("briefing_section_exec") or {}
        report.final_report_markdown = final_state.get("final_report_markdown") or ""
        report.report_sections = final_state.get("report_sections") or []

        # Governance
        cited_claims = final_state.get("cited_claims") or []
        # Serialize CitedClaim TypedDicts to plain dicts for JSON storage
        report.cited_claims = [dict(c) for c in cited_claims]
        report.uncited_claims_dropped = final_state.get("uncited_claims_dropped") or []
        report.adversarial_flags = final_state.get("adversarial_flags") or []

        # Fact-check
        report.fact_check_results = final_state.get("fact_check_results") or []
        report.fact_check_passed = final_state.get("fact_check_passed") or 0
        report.fact_check_failed = final_state.get("fact_check_failed") or 0

        # Peer review
        report.peer_review_passed = final_state.get("peer_review_passed")
        report.peer_review_issues = final_state.get("peer_review_issues") or []
        report.peer_review_note = final_state.get("peer_review_note") or ""

        # Budget tracking
        report.sources_attempted = final_state.get("sources_attempted") or 0
        report.sources_succeeded = final_state.get("sources_succeeded") or 0
        report.warnings = final_state.get("warnings") or []

        # Run metadata
        report.run_metadata = final_state.get("run_metadata") or {}

        db.commit()

        # Write final governance audit trail to logs
        _write_log(
            db, report_id=report_id, execution_id=None, level="INFO",
            agent_name="orchestrator",
            message=(
                f"Workflow v2.1 completed for topic='{report.topic}' in {duration:.1f}s. "
                f"Claims: {len(cited_claims)} kept, "
                f"{len(report.uncited_claims_dropped)} dropped, "
                f"{len(report.adversarial_flags)} adversarial. "
                f"Fact-check: {report.fact_check_passed} verified. "
                f"Peer review: {'passed' if report.peer_review_passed else 'failed/not run'}."
            ),
            details={
                "duration_seconds": duration,
                "governance": {
                    "cited_claims_kept": len(cited_claims),
                    "uncited_dropped": len(report.uncited_claims_dropped),
                    "adversarial_flags": report.adversarial_flags,
                    "fact_check_passed": report.fact_check_passed,
                    "fact_check_failed": report.fact_check_failed,
                },
                "quality": {
                    "peer_review_passed": report.peer_review_passed,
                    "peer_review_issues": report.peer_review_issues,
                    "approved": final_state.get("approved", True),
                },
                "budget": {
                    "sources_attempted": report.sources_attempted,
                    "sources_succeeded": report.sources_succeeded,
                    "max_sources": report.max_sources,
                    "max_steps": report.max_steps,
                },
                "errors": final_state.get("errors", []),
                "warnings": report.warnings,
            },
        )
        logger.info("Workflow v2.1 finished for report %s in %.1fs.", report_id, duration)

    except Exception as exc:
        logger.exception("Fatal workflow error for report %s.", report_id)
        try:
            report = db.query(Report).filter(Report.id == report_id).first()
            if report:
                report.status = "failed"
                report.error_message = str(exc)
                report.updated_at = datetime.now(timezone.utc)
                db.commit()
            _write_log(db, report_id=report_id, execution_id=None, level="CRITICAL",
                       agent_name="orchestrator", message=f"Workflow failed: {exc}")
        except Exception:
            pass
    finally:
        db.close()
