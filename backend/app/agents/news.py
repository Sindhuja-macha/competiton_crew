"""
News Agent — fetches latest news articles for the briefing topic.

v2: Uses topic field as primary query (with optional competitor focus)
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.state import GraphState
from app.utils.news_tool import fetch_news

logger = logging.getLogger(__name__)


def news_node(state: GraphState) -> dict[str, Any]:
    """
    LangGraph node — fetches latest news via Google News RSS.
    Uses topic-based query for broader market signal coverage.
    """
    topic = state.get("topic") or state.get("competitor_name", "Unknown")
    competitor = state.get("competitor_name", "")
    industry = state.get("industry", "Unknown")
    region = state.get("region", "Global")
    errors = list(state.get("errors", []))
    warnings = list(state.get("warnings", []))
    steps_used = (state.get("steps_used") or 0) + 1

    logger.info("[News] Fetching news for topic='%s'.", topic)

    try:
        # Fetch for the topic + specific competitor if provided
        articles = fetch_news(
            competitor_name=competitor or topic,
            industry=industry,
            region=region,
            max_items=10,
        )

        # If competitor-specific, also try a topic-level fetch
        if competitor and competitor != topic:
            topic_articles = fetch_news(
                competitor_name=topic,
                industry=industry,
                region=region,
                max_items=6,
            )
            # Merge, dedup by URL
            seen_urls = {a["url"] for a in articles}
            for art in topic_articles:
                if art.get("url") and art["url"] not in seen_urls:
                    seen_urls.add(art["url"])
                    articles.append(art)

        logger.info("[News] Fetched %d articles for topic='%s'.", len(articles), topic)
        return {
            "latest_news": articles[:12],
            "steps_used": steps_used,
            "errors": errors,
            "warnings": warnings,
        }

    except Exception as exc:
        logger.warning("[News] News fetch failed: %s", exc)
        errors.append(f"News agent error: {exc}")
        warnings.append(f"News fetch failed for topic='{topic}': {exc}")
        return {
            "latest_news": [],
            "steps_used": steps_used,
            "errors": errors,
            "warnings": warnings,
        }
