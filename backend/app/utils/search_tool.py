from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger(__name__)

def search_web(query: str, max_results: int = 4) -> list[dict[str, Any]]:
    """Run a single DuckDuckGo text search and return structured results."""
    try:
        from duckduckgo_search import DDGS

        results: list[dict[str, Any]] = []
        with DDGS() as ddgs:
            # list() makes this perfectly safe across all package versions
            raw_results = list(ddgs.text(query, max_results=max_results))

            if raw_results:
                for r in raw_results:
                    results.append({
                        "title": r.get("title", ""),
                        "url":   r.get("href", ""),  # Using 'href' per library specification
                        "body":  r.get("body", ""),
                    })

        logger.info("DDG search '%s' → %d results.", query, len(results))
        return results

    except Exception as exc:
        logger.warning("DDG search failed for '%s': %s", query, exc)
        return []
