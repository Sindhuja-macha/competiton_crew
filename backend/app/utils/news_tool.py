"""
News tool — Google News RSS feed via feedparser.

Fetches the latest news articles for a competitor/industry.
Errors are caught so the workflow never stops because of this tool.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def _parse_published(entry: Any) -> str:
    """Return ISO 8601 string from feedparser entry, or now()."""
    try:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            import time
            ts = time.mktime(entry.published_parsed)
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        pass
    return datetime.now(timezone.utc).isoformat()


def fetch_news(
    competitor_name: str,
    industry: str,
    region: str,
    max_items: int = 10,
) -> list[dict[str, Any]]:
    """
    Fetch recent news articles from Google News RSS.

    Returns
    -------
    list[dict]  — each dict has keys: title, url, source, published_at, summary
    """
    try:
        import feedparser  # noqa: PLC0415

        query = quote_plus(f"{competitor_name} {industry}")
        url = GOOGLE_NEWS_RSS.format(query=query)
        feed = feedparser.parse(url)

        articles: list[dict[str, Any]] = []
        for entry in feed.entries[:max_items]:
            title = getattr(entry, "title", "No title")
            link = getattr(entry, "link", "")
            source = getattr(entry, "source", {})
            source_name = source.get("title", "Google News") if isinstance(source, dict) else "Google News"
            summary = getattr(entry, "summary", "")

            # Strip HTML tags from summary
            try:
                from bs4 import BeautifulSoup  # noqa: PLC0415
                summary = BeautifulSoup(summary, "html.parser").get_text(separator=" ").strip()
            except Exception:
                pass

            articles.append(
                {
                    "title": title,
                    "url": link,
                    "source": source_name,
                    "published_at": _parse_published(entry),
                    "summary": summary[:300] if summary else "",
                }
            )

        logger.info(
            "Google News RSS fetched %d articles for '%s'.",
            len(articles),
            competitor_name,
        )
        return articles

    except Exception as exc:
        logger.warning("News fetch failed for '%s': %s", competitor_name, exc)
        return []
