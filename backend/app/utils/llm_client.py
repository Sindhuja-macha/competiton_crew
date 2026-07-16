"""
LLM client — wraps OpenRouter via the OpenAI-compatible API.

Provides:
  - get_llm()          → ChatOpenAI instance for primary model
  - chat_with_fallback() → send a list of messages with automatic
                           primary → fallback retry using tenacity
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_openai import ChatOpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

# ── Retry decorator for transient errors ──────────────────────────────────
_retry_transient = retry(
    retry=retry_if_exception_type((Exception,)),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


def _build_client(model: str) -> ChatOpenAI:
    """Build a ChatOpenAI instance pointed at OpenRouter."""
    return ChatOpenAI(
        model=model,
        openai_api_key=_settings.openrouter_api_key,
        openai_api_base=_settings.openrouter_base_url,
        temperature=0.3,
        max_tokens=4096,
        default_headers={
            "HTTP-Referer": "https://competitive-intel.app",
            "X-Title": "Competitive Intelligence Briefing Crew",
        },
    )


def get_llm(model: str | None = None) -> ChatOpenAI:
    """Return a ChatOpenAI instance for the given (or primary) model."""
    return _build_client(model or _settings.primary_model)


def chat_with_fallback(messages: list[Any]) -> Any:
    """
    Invoke the LLM with an automatic fallback chain.

    Tries PRIMARY_MODEL first. If it raises any exception, retries once,
    then falls back to FALLBACK_MODEL and retries twice more.

    Parameters
    ----------
    messages : list
        LangChain message objects (HumanMessage, SystemMessage, …)

    Returns
    -------
    AIMessage
        The model response.
    """
    # ── Primary attempt ──────────────────────────────────────────────────
    try:
        primary = _build_client(_settings.primary_model)
        logger.debug("Invoking primary model: %s", _settings.primary_model)
        return _retry_on_primary(primary, messages)
    except Exception as primary_exc:
        logger.warning(
            "Primary model '%s' failed: %s — switching to fallback '%s'.",
            _settings.primary_model,
            primary_exc,
            _settings.fallback_model,
        )

    # ── Fallback attempt ─────────────────────────────────────────────────
    fallback = _build_client(_settings.fallback_model)
    logger.debug("Invoking fallback model: %s", _settings.fallback_model)
    return _retry_on_fallback(fallback, messages)


@retry(
    retry=retry_if_exception_type((Exception,)),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=2, max=8),
    reraise=True,
)
def _retry_on_primary(llm: ChatOpenAI, messages: list[Any]) -> Any:
    return llm.invoke(messages)


@retry(
    retry=retry_if_exception_type((Exception,)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=12),
    reraise=True,
)
def _retry_on_fallback(llm: ChatOpenAI, messages: list[Any]) -> Any:
    return llm.invoke(messages)
