"""
Search tool — DuckDuckGo web search with parallel query execution.

Speed optimisations:
  - All queries run in parallel via ThreadPoolExecutor
  - max_results reduced from 8 → 4 per query (faster, still enough)
  - Dedup by URL across all parallel results
"""

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
            for r in ddgs.text(query, max_results=max_results, timelimit=None):
                results.append({
                    "title": r.get("title", ""),
                    "url":   r.get("href", ""),
                    "body":  r.get("body", ""),
                })
        logger.info("DDG search '%s' → %d results.", query, len(results))
        return results

    except Exception as exc:
        logger.warning("DDG search failed for '%s': %s", query, exc)
        return []


def search_competitor(
    competitor_name: str,
    industry: str,
    region: str,
) -> list[dict[str, Any]]:
    """
    Run multiple targeted searches IN PARALLEL and merge results.
    Previously sequential (~9s for 3 queries); now all fire at once (~3s).
    """
    queries = [
        f"{competitor_name} {industry} {region} company overview strategy",
        f"{competitor_name} pricing plans cost 2025",
        f"{competitor_name} new product launch features announcement",
    ]
    return _parallel_search(queries, max_results_each=4)


def _parallel_search(
    queries: list[str],
    max_results_each: int = 4,
) -> list[dict[str, Any]]:
    """Run multiple search queries in parallel and return deduped results."""
    all_results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    with ThreadPoolExecutor(max_workers=min(len(queries), 6)) as pool:
        futures = {pool.submit(search_web, q, max_results_each): q for q in queries}
        for future in as_completed(futures):
            try:
                for item in future.result():
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(item)
            except Exception as exc:
                logger.warning("Parallel search error: %s", exc)

    logger.info("Parallel search collected %d unique results.", len(all_results))
    return all_results
