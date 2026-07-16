"""
LangGraph Workflow — Competitive Intelligence Briefing Crew v2.

Pipeline topology (sequential — compatible with LangGraph 0.1.19):
  START
    └── planner_node
          └── research_node
                └── news_node
                      └── analyst_node
                            └── fact_check_node
                                  └── writer_node
                                        └── peer_review_node
                                              └── approval_node
                                                    └── END

NOTE ON PARALLELISM:
  LangGraph 0.1.19 does NOT guarantee correct fan-in semantics when two edges
  point to the same target node (both research→analyst AND news→analyst).
  In practice this causes analyst_node to execute TWICE — once per incoming
  edge — producing duplicate DB records and corrupted state merges.

  Fix: Run research → news sequentially. The news_node is lightweight (RSS
  fetch only, ≈1s) so the latency impact is negligible while avoiding the
  double-execution bug entirely.

  If you later upgrade to langgraph >= 0.2.x you may re-introduce parallel
  fan-out by wrapping the two nodes in a proper Send / join pattern.

Key features:
  - Topic-based input (topic + optional competitor_name)
  - Run/step budget wired in initial_state
  - fact_check and peer_review nodes fully integrated
  - run_graph() updated to accept topic parameter
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from langgraph.graph import END, START, StateGraph

from app.agents.analyst import analyst_node
from app.agents.approval import approval_node
from app.agents.fact_check import fact_check_node
from app.agents.news import news_node
from app.agents.peer_review import peer_review_node
from app.agents.planner import planner_node
from app.agents.research import research_node
from app.agents.state import DEFAULT_MAX_SOURCES, DEFAULT_MAX_STEPS, GraphState
from app.agents.writer import writer_node

logger = logging.getLogger(__name__)


def build_workflow() -> StateGraph:
    """
    Build and return the compiled LangGraph StateGraph.

    Pipeline (fully sequential, LangGraph 0.1.19-safe):
      planner → research → news → analyst → fact_check → writer → peer_review → approval
    """
    builder = StateGraph(GraphState)

    # ── Register all nodes ────────────────────────────────────────────────
    builder.add_node("planner",     planner_node)
    builder.add_node("research",    research_node)
    builder.add_node("news",        news_node)
    builder.add_node("analyst",     analyst_node)
    builder.add_node("fact_check",  fact_check_node)
    builder.add_node("writer",      writer_node)
    builder.add_node("peer_review", peer_review_node)
    builder.add_node("approval",    approval_node)

    # ── Edges — strictly sequential ───────────────────────────────────────
    builder.add_edge(START,         "planner")
    builder.add_edge("planner",     "research")
    builder.add_edge("research",    "news")
    builder.add_edge("news",        "analyst")
    builder.add_edge("analyst",     "fact_check")
    builder.add_edge("fact_check",  "writer")
    builder.add_edge("writer",      "peer_review")
    builder.add_edge("peer_review", "approval")
    builder.add_edge("approval",    END)

    return builder


# ── Compile once at import time ───────────────────────────────────────────
_compiled_graph = None


def get_compiled_graph():
    """Return the compiled graph, building it on first call."""
    global _compiled_graph
    if _compiled_graph is None:
        logger.info("Compiling LangGraph workflow (sequential, v2.1)…")
        _compiled_graph = build_workflow().compile()
        logger.info("LangGraph workflow compiled successfully.")
    return _compiled_graph


def run_graph(
    topic: str,
    competitor_name: str = "",
    industry: str = "Unknown",
    region: str = "Global",
    report_id: str = "",
    max_sources: int = DEFAULT_MAX_SOURCES,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> GraphState:
    """
    Execute the full LangGraph workflow synchronously.

    Parameters
    ----------
    topic : str
        The intelligence topic (e.g. "EV pricing 2025", "cloud AI market")
    competitor_name : str, optional
        Optional specific competitor to focus on
    industry, region : str
        Market context
    report_id : str
        Unique run identifier
    max_sources : int
        Hard cap on number of sources to gather
    max_steps : int
        Hard cap on total workflow steps

    Returns
    -------
    GraphState
        The final merged state after all nodes have executed.
    """
    graph = get_compiled_graph()

    initial_state: GraphState = {
        # Topic-based input
        "topic": topic,
        "competitor_name": competitor_name or topic,
        "industry": industry,
        "region": region,
        "report_id": report_id,
        # Budget
        "max_sources": max_sources,
        "max_steps": max_steps,
        "steps_used": 0,
        "sources_attempted": 0,
        "sources_succeeded": 0,
        # Governance
        "cited_claims": [],
        "uncited_claims_dropped": [],
        "adversarial_flags": [],
        # Tracking
        "errors": [],
        "warnings": [],
    }

    started_at = datetime.now(timezone.utc)
    logger.info(
        "Starting LangGraph workflow v2.1 | report_id=%s | topic='%s' | "
        "max_sources=%d max_steps=%d",
        report_id, topic, max_sources, max_steps,
    )

    final_state: GraphState = graph.invoke(initial_state)

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

    # ── Build run_metadata ────────────────────────────────────────────────
    run_metadata = {
        "report_id": report_id,
        "topic": topic,
        "competitor_name": competitor_name,
        "industry": industry,
        "region": region,
        "started_at": started_at.isoformat(),
        "duration_seconds": elapsed,
        "budget": {
            "max_sources": max_sources,
            "max_steps": max_steps,
            "steps_used": final_state.get("steps_used", 0),
            "sources_attempted": final_state.get("sources_attempted", 0),
            "sources_succeeded": final_state.get("sources_succeeded", 0),
        },
        "governance": {
            "cited_claims_kept": len(final_state.get("cited_claims", [])),
            "uncited_claims_dropped": len(final_state.get("uncited_claims_dropped", [])),
            "adversarial_flags": len(final_state.get("adversarial_flags", [])),
            "fact_check_passed": final_state.get("fact_check_passed", 0),
            "fact_check_failed": final_state.get("fact_check_failed", 0),
        },
        "quality": {
            "peer_review_passed": final_state.get("peer_review_passed", False),
            "peer_review_issues": final_state.get("peer_review_issues", []),
            "approved": final_state.get("approved", False),
        },
        "errors": final_state.get("errors", []),
        "warnings": final_state.get("warnings", []),
        "failed_sources": final_state.get("failed_sources", []),
    }

    final_state["run_metadata"] = run_metadata

    logger.info(
        "LangGraph workflow v2.1 completed | report_id=%s | %.1fs | "
        "claims=%d | dropped=%d | peer_review=%s",
        report_id,
        elapsed,
        len(final_state.get("cited_claims", [])),
        len(final_state.get("uncited_claims_dropped", [])),
        final_state.get("peer_review_passed", False),
    )

    return final_state
