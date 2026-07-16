"""
Planner Agent — creates the research execution plan.

v2: Topic-aware (uses state["topic"] as primary input, competitor_name is optional)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import GraphState
from app.utils.llm_client import chat_with_fallback

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Strategic Intelligence Planner.
Your task is to create a structured research plan for gathering competitive intelligence on a market topic.
Output ONLY a JSON object with a single key "plan" containing a list of 6-8 research steps as strings.
Example:
{"plan": ["Research pricing trends and benchmarks for the topic", "Identify key players and competitive moves", ...]}
Do NOT include any text outside the JSON."""


def planner_node(state: GraphState) -> dict[str, Any]:
    """
    LangGraph node — creates the execution plan.
    Uses topic-based input with optional competitor focus.
    """
    topic = state.get("topic") or state.get("competitor_name", "Unknown")
    competitor = state.get("competitor_name", "")
    industry = state.get("industry", "Unknown")
    region = state.get("region", "Global")
    steps_used = (state.get("steps_used") or 0) + 1

    logger.info("[Planner] Planning research for topic='%s'.", topic)

    try:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Create a research plan for this intelligence topic:\n"
                    f"- Topic: {topic}\n"
                    f"- Competitor Focus: {competitor or 'None — general market intelligence'}\n"
                    f"- Industry: {industry}\n"
                    f"- Region: {region}\n"
                    f"\nGenerate the JSON plan now."
                )
            ),
        ]
        response = chat_with_fallback(messages)
        raw = response.content.strip()

        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)
        plan = parsed.get("plan", [])
        if not plan:
            raise ValueError("Empty plan returned")

        logger.info("[Planner] Plan created with %d steps.", len(plan))
        return {
            "plan": plan,
            "steps_used": steps_used,
            "errors": state.get("errors", []),
            "warnings": state.get("warnings", []),
        }

    except Exception as exc:
        logger.warning("[Planner] LLM failed, using default plan: %s", exc)
        fallback_plan = [
            f"Research pricing and cost benchmarks for '{topic}' in {industry}",
            f"Identify key competitors and market players in {region}",
            f"Gather recent product launches and announcements related to '{topic}'",
            "Analyse competitive positioning and market share signals",
            "Collect relevant news and analyst commentary",
            "Extract strategic recommendations and market opportunities",
            "Summarise executive-level findings with source citations",
        ]
        errors = list(state.get("errors", []))
        errors.append(f"Planner LLM error: {exc}")
        return {
            "plan": fallback_plan,
            "steps_used": steps_used,
            "errors": errors,
            "warnings": list(state.get("warnings", [])),
        }
