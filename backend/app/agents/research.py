"""
Research Agent — gathers intelligence sources for a given topic.

v2 — key changes:
  - Topic-based input: uses state["topic"] (with optional competitor_name focus)
  - Source/step cap: respects max_sources and max_steps budget
  - Per-source partial-failure: each source gets a SourceResult with status
  - Failed sources are noted and skipped; run still completes
  - Produces structured source_results list consumed downstream
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import (
    DEFAULT_MAX_SOURCES,
    DEFAULT_MAX_STEPS,
    GraphState,
    SourceResult,
)
from app.utils.llm_client import chat_with_fallback
from app.utils.scraper import scrape_multiple, scrape_page
from app.utils.search_tool import search_web

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a Competitive Intelligence Research Analyst.
You will receive raw search results and scraped web content about a market topic.
Your task is to synthesise this information into structured output.

Output ONLY a valid JSON object with these keys:
{
  "competitor_overview": "2-3 paragraph summary of the competitive landscape and key players",
  "pricing_summary": "Summary of pricing data, tiers, cost benchmarks found in sources",
  "key_products": ["product/service 1", "product/service 2"],
  "sources_used": [
    {"title": "...", "url": "...", "source": "Web", "content_snippet": "key excerpt..."}
  ]
}

CRITICAL RULES:
- Only include facts directly supported by the sources provided. 
- If information is unavailable, say "Not found in sources."
- Do NOT invent data, prices, or company claims.
- Every fact must trace back to a URL in sources_used.
Output ONLY the JSON, no other text."""


def _build_search_queries(topic: str, competitor_name: str, industry: str, region: str) -> list[str]:
    """Build targeted search queries from topic and optional competitor."""
    queries: list[str] = []

    if competitor_name:
        queries += [
            f"{competitor_name} {industry} pricing strategy 2024 2025",
            f"{competitor_name} product launches announcements {region}",
            f"{competitor_name} market share competitive position {industry}",
        ]

    # Topic-level queries (always included)
    queries += [
        f"{topic} pricing trends 2025",
        f"{topic} market analysis competitive intelligence",
        f"{topic} recent news announcements {region}",
    ]
    return queries


def research_node(state: GraphState) -> dict[str, Any]:
    """
    LangGraph node — gathers intelligence data via search and scraping.

    Respects max_sources and max_steps budget caps.
    Records per-source status (ok / failed / timeout / skipped).
    Partial failures are noted; the run always continues.
    """
    topic = state.get("topic") or state.get("competitor_name", "Unknown Topic")
    competitor = state.get("competitor_name", "")
    industry = state.get("industry", "Unknown")
    region = state.get("region", "Global")
    report_id = state.get("report_id", "")

    max_sources: int = state.get("max_sources") or DEFAULT_MAX_SOURCES
    max_steps: int = state.get("max_steps") or DEFAULT_MAX_STEPS
    steps_used: int = (state.get("steps_used") or 0) + 1  # count this node entry

    logger.info("[Research] topic='%s' competitor='%s' max_sources=%d max_steps=%d",
                topic, competitor, max_sources, max_steps)

    errors = list(state.get("errors", []))
    warnings = list(state.get("warnings", []))

    # ── Budget guard ──────────────────────────────────────────────────────
    if steps_used >= max_steps:
        msg = f"Research skipped: step budget exhausted ({steps_used}/{max_steps})"
        logger.warning("[Research] %s", msg)
        warnings.append(msg)
        return {
            "steps_used": steps_used,
            "search_results": [],
            "scraped_pages": [],
            "source_results": [],
            "failed_sources": [],
            "competitor_overview": "Research budget exhausted — no data gathered.",
            "pricing_summary": "No pricing data (budget exhausted).",
            "sources": [],
            "sources_attempted": 0,
            "sources_succeeded": 0,
            "errors": errors,
            "warnings": warnings,
        }

    # ── Step 1: Build and execute searches ───────────────────────────────
    queries = _build_search_queries(topic, competitor, industry, region)
    steps_used += 1

    all_search_results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for q in queries:
        if len(seen_urls) >= max_sources:
            warnings.append(f"Source cap ({max_sources}) reached during search phase.")
            break
        results = search_web(q, max_results=6)
        for r in results:
            url = r.get("url", "")
            if url and url not in seen_urls and len(seen_urls) < max_sources:
                seen_urls.add(url)
                all_search_results.append(r)

    logger.info("[Research] Collected %d unique search results.", len(all_search_results))

    # ── Step 2: Scrape pages with per-source error handling ──────────────
    steps_used += 1
    source_results: list[SourceResult] = []
    scraped_pages: list[dict[str, Any]] = []
    failed_sources: list[str] = []
    sources_attempted = 0
    sources_succeeded = 0

    # Limit scraping to cap
    urls_to_scrape = [r["url"] for r in all_search_results[:min(5, max_sources)] if r.get("url")]

    for url in urls_to_scrape:
        if sources_attempted >= max_sources:
            break
        sources_attempted += 1

        try:
            content = scrape_page(url)
            if content and len(content.strip()) > 100:
                sources_succeeded += 1
                scraped_pages.append({"url": url, "content": content})
                source_results.append(SourceResult(
                    title=next((r["title"] for r in all_search_results if r.get("url") == url), url),
                    url=url,
                    source="Scraped",
                    content_snippet=content[:400],
                    status="ok",
                    failure_reason=None,
                ))
            else:
                failed_sources.append(url)
                source_results.append(SourceResult(
                    title=url,
                    url=url,
                    source="Scraped",
                    content_snippet="",
                    status="failed",
                    failure_reason="Empty or too-short content returned",
                ))
                warnings.append(f"Source returned empty content: {url}")
        except TimeoutError:
            failed_sources.append(url)
            source_results.append(SourceResult(
                title=url, url=url, source="Scraped", content_snippet="",
                status="timeout", failure_reason="Request timed out",
            ))
            warnings.append(f"Source timed out (skipped): {url}")
        except Exception as exc:
            failed_sources.append(url)
            source_results.append(SourceResult(
                title=url, url=url, source="Scraped", content_snippet="",
                status="failed", failure_reason=str(exc),
            ))
            warnings.append(f"Source failed (skipped): {url} — {exc}")

    # Also add search results (not scraped) as sources for the source ledger
    for r in all_search_results:
        url = r.get("url", "")
        if url and not any(s["url"] == url for s in source_results):
            source_results.append(SourceResult(
                title=r.get("title", url),
                url=url,
                source="DuckDuckGo",
                content_snippet=r.get("body", "")[:400],
                status="ok",
                failure_reason=None,
            ))
            sources_succeeded += 1

    if failed_sources:
        logger.info("[Research] %d sources failed/skipped: %s", len(failed_sources), failed_sources)

    # ── Step 3: LLM synthesis ────────────────────────────────────────────
    steps_used += 1

    search_snippets = "\n\n".join(
        f"[{i+1}] {r['title']}\n{r['url']}\n{r.get('body', '')[:400]}"
        for i, r in enumerate(all_search_results[:8])
    )
    scraped_snippets = "\n\n".join(
        f"[Scraped: {p['url']}]\n{p['content'][:600]}"
        for p in scraped_pages[:3]
    )
    raw_data = f"SEARCH RESULTS:\n{search_snippets}\n\nSCRAPED PAGES:\n{scraped_snippets}"

    try:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=(
                f"Topic: {topic}\n"
                f"Competitor Focus: {competitor or 'None specified'}\n"
                f"Industry: {industry}\nRegion: {region}\n\n"
                f"RAW DATA:\n{raw_data[:6000]}\n\n"
                f"Synthesise into the required JSON. Only use facts found in the sources."
            )),
        ]
        response = chat_with_fallback(messages)
        raw = response.content.strip()

        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)

        # Build final source list — merge LLM-identified sources + search hits
        llm_sources: list[dict[str, str]] = parsed.get("sources_used", [])
        final_sources: list[dict[str, str]] = []
        final_urls: set[str] = set()

        for s in llm_sources:
            url = s.get("url", "")
            if url and url not in final_urls:
                final_urls.add(url)
                final_sources.append({
                    "title": s.get("title", url),
                    "url": url,
                    "source": s.get("source", "Web"),
                    "content_snippet": s.get("content_snippet", ""),
                })

        for sr in all_search_results[:10]:
            url = sr.get("url", "")
            if url and url not in final_urls:
                final_urls.add(url)
                final_sources.append({
                    "title": sr.get("title", url),
                    "url": url,
                    "source": "DuckDuckGo",
                    "content_snippet": sr.get("body", "")[:200],
                })

        logger.info("[Research] Synthesis complete. sources=%d scraped_ok=%d failed=%d",
                    len(final_sources), sources_succeeded, len(failed_sources))

        return {
            "search_results": all_search_results,
            "scraped_pages": scraped_pages,
            "source_results": source_results,
            "failed_sources": failed_sources,
            "competitor_overview": parsed.get(
                "competitor_overview",
                f"Competitive landscape for '{topic}' in the {industry} industry.",
            ),
            "pricing_summary": parsed.get(
                "pricing_summary",
                "Pricing information not found in available sources.",
            ),
            "sources": final_sources[:max_sources],
            "steps_used": steps_used,
            "sources_attempted": sources_attempted,
            "sources_succeeded": sources_succeeded,
            "errors": errors,
            "warnings": warnings,
        }

    except Exception as exc:
        logger.warning("[Research] LLM synthesis failed: %s", exc)
        errors.append(f"Research LLM synthesis error: {exc}")

        # Fallback: build sources purely from search results
        fallback_sources = [
            {
                "title": r.get("title", r["url"]),
                "url": r["url"],
                "source": "DuckDuckGo",
                "content_snippet": r.get("body", "")[:200],
            }
            for r in all_search_results[:10]
            if r.get("url")
        ]
        return {
            "search_results": all_search_results,
            "scraped_pages": scraped_pages,
            "source_results": source_results,
            "failed_sources": failed_sources,
            "competitor_overview": (
                f"Research gathered {sources_succeeded} sources for '{topic}' "
                f"({industry}, {region}). "
                f"LLM synthesis failed — raw data preserved. "
                + (f"Note: {len(failed_sources)} sources were unreachable." if failed_sources else "")
            ),
            "pricing_summary": "Pricing data requires manual review (synthesis failed).",
            "sources": fallback_sources,
            "steps_used": steps_used,
            "sources_attempted": sources_attempted,
            "sources_succeeded": sources_succeeded,
            "errors": errors,
            "warnings": warnings,
        }
