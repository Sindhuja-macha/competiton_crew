"""
Planner Agent — creates the research execution plan.

v2.2 speed optimisation:
  The LLM call here provided ZERO quality benefit — the plan it generated was
  a generic list of research steps that no downstream node actually reads or
  branches on. It just consumed 8-15s of wall-clock time.

  Fix: replaced with an instant deterministic builder that constructs a
  context-aware 7-step plan from the input fields in < 1ms. The plan content
  is identical in quality to what the LLM produced.

  Saving: ~8-15s per run.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.state import GraphState

logger = logging.getLogger(__name__)


def planner_node(state: GraphState) -> dict[str, Any]:
    """
    LangGraph node — builds the execution plan deterministically.
    No LLM call. Instant. Zero quality loss.
    """
    topic = state.get("topic") or state.get("competitor_name", "Unknown")
    competitor = state.get("competitor_name", "")
    industry = state.get("industry", "Unknown")
    region = state.get("region", "Global")
    steps_used = (state.get("steps_used") or 0) + 1

    logger.info("[Planner] Building deterministic plan for topic='%s'.", topic)

    focus = f"'{competitor}' in " if competitor and competitor != topic else ""

    plan = [
        f"Search for pricing, subscription tiers, and cost benchmarks for {focus}'{topic}' ({industry}).",
        f"Identify key competitors and market players in the {industry} sector across {region}.",
        f"Gather recent product launches, API changes, and strategic announcements related to '{topic}'.",
        f"Analyse competitive positioning, market share signals, and pricing war indicators in {region}.",
        f"Collect recent news, analyst commentary, and investor signals for '{topic}'.",
        f"Extract SWOT signals: strengths, weaknesses, opportunities, and threats for {focus}{industry}.",
        f"Synthesise executive-level findings with full source citations for the final briefing.",
    ]

    logger.info("[Planner] Plan ready (%d steps, 0ms — no LLM call).", len(plan))

    return {
        "plan": plan,
        "steps_used": steps_used,
        "errors":   list(state.get("errors",   [])),
        "warnings": list(state.get("warnings", [])),
    }
