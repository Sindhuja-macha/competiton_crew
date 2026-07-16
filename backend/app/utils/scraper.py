"""
Web scraper — BeautifulSoup + requests, with parallel fetching.

Speed optimisations:
  - Timeout reduced from 10s → 5s
  - scrape_multiple() uses ThreadPoolExecutor to fetch all URLs in parallel
  - MAX_CHARS reduced to 2000 (enough context, less LLM token cost)
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_TIMEOUT = 5          # reduced from 10s → 5s per request
_MAX_CHARS = 2000     # reduced from 5000 → 2000 (still plenty of context)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}
_STRIP_TAGS = {
    "script", "style", "nav", "footer", "header", "aside",
    "form", "button", "iframe", "noscript", "svg",
}


def scrape_page(url: str) -> str:
    """Fetch a URL and return clean extracted text. Returns '' on any error."""
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(_STRIP_TAGS):
            tag.decompose()

        text_parts: list[str] = []
        for selector in ["main", "article", "section", ".content", "#content", "body"]:
            container = soup.select_one(selector)
            if container:
                text_parts = container.get_text(separator="\n", strip=True).splitlines()
                break

        if not text_parts:
            text_parts = soup.get_text(separator="\n", strip=True).splitlines()

        lines = [line.strip() for line in text_parts if len(line.strip()) > 20]
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
        return text[:_MAX_CHARS]

    except Exception as exc:
        logger.warning("Scrape failed for '%s': %s", url, exc)
        return ""


def scrape_multiple(urls: list[str], max_pages: int = 3) -> list[dict[str, Any]]:
    """
    Scrape up to `max_pages` URLs in PARALLEL using a thread pool.
    Previously sequential (up to 50s); now all fire at once (max 5s total).
    """
    targets = urls[:max_pages]
    results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=min(len(targets), 5)) as pool:
        future_to_url = {pool.submit(scrape_page, url): url for url in targets}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                content = future.result()
                if content:
                    results.append({"url": url, "content": content})
            except Exception as exc:
                logger.warning("Parallel scrape failed for '%s': %s", url, exc)

    return results
