"""
Writer Agent — produces the 5 required structured briefing sections.

Speed optimisation v2:
  - Single LLM call for all 3 core sections (was 3 separate calls = 3x slower)
  - Reduced context size passed to LLM
  - Fallback template if LLM fails

Bug fixes v2.1:
  - JSON sanitization: strips markdown fences, escapes lone backslashes, and
    uses a multi-stage repair strategy to handle unterminated strings produced
    by truncated LLM output.
  - sources state preserved: writer_node now explicitly passes `sources` back
    so LangGraph state merging never drops the accumulated source list.
  - SWOT Analysis section: reads `swot_analysis` from analyst_node output and
    renders it as a full markdown section in the final report.
  - Pricing Analysis section: extracted as a dedicated Section 4 from the
    writer LLM output (was only embedded inside section_pricing prose).
  - swot_analysis and pricing_analysis are included in the return dict so
    they are available to downstream nodes (peer_review, approval).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import BriefingSection, CitedClaim, GraphState
from app.utils.llm_client import chat_with_fallback

logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a Senior Intelligence Report Writer for a Strategy team.

Write ALL THREE sections of a competitive intelligence briefing in ONE response.

Output ONLY a valid JSON object — no markdown fences, no trailing commas:
{
  "section_pricing": "Markdown content for Section 1: Competitor Pricing & Product Moves",
  "section_market": "Markdown content for Section 2: Market Signals & Trends",
  "section_exec": "Markdown content for Section 3: Executive Summary & Strategic Recommendation"
}

═══════════════════════════════════════════════════
CRITICAL JSON ENCODING RULES — THE PARSER IS STRICT
═══════════════════════════════════════════════════
1. NEVER place a real (literal) newline character inside a JSON string value.
   Instead, write the two-character escape sequence \\n wherever a line break
   is needed within a string. Violating this rule breaks the JSON parser.
2. NEVER place a raw, unescaped double-quote character (") inside a JSON
   string value. Always escape it as \\". Example:
     WRONG : "The company said "prices will rise"."
     CORRECT: "The company said \\"prices will rise\\"."
3. No trailing comma after the last key-value pair.
4. No markdown code fences (``` or ```json) around the output.
5. Output ONLY the JSON object. No preamble, no explanation, nothing else.
═══════════════════════════════════════════════════

CONTENT RULES for every section:
1. Every factual statement MUST end with a NAMED ANCHOR MARKDOWN LINK — never a raw URL.
   Format: [Read Source Title](https://full-url.com)
   Example: "AWS expanded its Asia-Pacific footprint in Q1 2025. [Read Reuters Report](https://reuters.com/article/aws)"
   You are STRICTLY FORBIDDEN from printing raw unformatted URL strings inline.
   Raw URL format WRONG : "...as reported at https://reuters.com/article"
   Named anchor CORRECT: "...as reported. [Read Reuters](https://reuters.com/article)"
2. Verified claims (2+ sources) stated directly. Single-source claims hedged with "According to [Source], ..."
3. 3-5 concise bullet points per section — one bullet per factual claim.
4. Professional executive tone. No filler phrases.
5. Section 3 must end with ONE clear, actionable recommendation."""


# ── JSON sanitization helpers ─────────────────────────────────────────────

def _strip_markdown_fences(raw: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrappers if present."""
    stripped = raw.strip()
    # Pattern: optional language tag after opening fence
    fence_re = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)
    m = fence_re.match(stripped)
    if m:
        return m.group(1).strip()
    # Fallback: split on ``` and take what is inside
    if "```" in stripped:
        parts = stripped.split("```")
        # parts[1] is the first fenced block
        if len(parts) >= 3:
            inner = parts[1]
            if inner.lower().startswith("json"):
                inner = inner[4:]
            return inner.strip()
    return stripped


def _sanitize_json_string(raw: str) -> str:
    """
    Best-effort repair of common JSON issues from LLM output.

    Steps applied in order:
    1. Strip markdown fences.
    2. Remove BOM / zero-width characters.
    3. Replace smart-quotes with straight quotes.
    4. Normalize lone carriage returns.
    5. Replace literal newlines that appear INSIDE JSON string values
       (between an opening quote and the matching close quote) with \\n.
       This is the primary fix for "Unterminated string" errors caused by
       an LLM emitting real line breaks inside a string value.
    """
    text = _strip_markdown_fences(raw)

    # Step 2: remove invisible / BOM characters
    text = text.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "")

    # Step 3: replace curly/smart quotes with straight equivalents
    text = (
        text
        .replace("\u201c", '"').replace("\u201d", '"')  # " "
        .replace("\u2018", "'").replace("\u2019", "'")  # ' '
    )

    # Step 4: normalise lone \r
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Step 5: replace literal newlines inside JSON string values.
    # Walk character-by-character tracking whether we are inside a string.
    # When a newline is encountered inside a string, replace it with \n.
    result = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and in_string:
            # Consume the escape sequence as-is (don't flip in_string)
            result.append(ch)
            i += 1
            if i < len(text):
                result.append(text[i])
                i += 1
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
        elif ch == "\n" and in_string:
            # Replace literal newline inside a string with the escape sequence
            result.append("\\n")
        elif ch == "\t" and in_string:
            result.append("\\t")
        else:
            result.append(ch)
        i += 1

    return "".join(result)


def _try_parse_json(text: str) -> dict | None:
    """
    Multi-stage JSON parse with progressive repair.
    Returns the parsed dict on success, or None on total failure.

    Stages:
      1. Direct json.loads
      2. Extract outermost {...}
      3. Truncation repair via last-good key-value pattern
      4. Strip last broken key entirely
      5. Regex partial-recovery — extract whatever named keys are present
         and assemble a partial dict so the writer never returns completely
         empty even if the JSON is severely malformed.
    """
    # Stage 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Stage 2: extract outermost {...}
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Stage 3: truncation repair — find last complete key-value pair
    if start != -1:
        inner = text[start:]
        last_good = re.search(
            r',\s*"[^"]+"\s*:\s*"[^"]*"(?=\s*[,}])',
            inner,
        )
        if last_good:
            truncated = inner[: last_good.end()] + "\n}"
            try:
                return json.loads(truncated)
            except json.JSONDecodeError:
                pass

        # Stage 4: strip the last broken key entirely
        all_keys = list(re.finditer(r'"(section_[a-z]+)"\s*:\s*"', inner))
        if len(all_keys) >= 2:
            cut_pos = all_keys[-1].start()
            truncated = inner[:cut_pos].rstrip().rstrip(",") + "\n}"
            try:
                return json.loads(truncated)
            except json.JSONDecodeError:
                pass

    # Stage 5: regex partial-recovery.
    # Extract whatever section_* values are present using a regex that
    # captures text between the opening quote and either the closing
    # quote-comma-quote pattern or end-of-string. Assembles a partial dict
    # so the writer can still render something meaningful.
    partial: dict[str, str] = {}
    pattern = re.compile(
        r'"(section_(?:pricing|market|exec))"\s*:\s*"((?:[^"\\]|\\.)*)"',
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        key = m.group(1)
        # Un-escape the captured value
        try:
            val = json.loads(f'"{m.group(2)}"')
        except json.JSONDecodeError:
            val = m.group(2).replace('\\"', '"').replace("\\n", "\n")
        partial[key] = val

    if partial:
        logger.warning(
            "[Writer] Stages 1-4 failed; partial-recovery extracted %d section(s): %s",
            len(partial), list(partial.keys()),
        )
        return partial

    logger.warning("[Writer] All JSON repair strategies exhausted — falling back to template.")
    return None


# ── Context formatters ────────────────────────────────────────────────────

def _format_claims_block(claims: list[CitedClaim], max_claims: int = 12) -> str:
    """Format claims for the LLM context block with named anchor citations."""
    lines = []
    for c in claims[:max_claims]:
        tag = "✓" if c.get("verified") else "⚠"
        url = c.get("source_url", "#")
        title = c.get("source_title") or "Source"
        claim_text = c.get("claim", "")
        # Append named anchor if not already present in claim text
        anchor = f"[Read {title}]({url})"
        if url and url != "#" and url not in claim_text:
            claim_text = f"{claim_text} {anchor}"
        lines.append(f"[{tag}] {claim_text}")
    return "\n".join(lines) if lines else "No verified claims available."


def _build_citation_footer(sources: list[dict]) -> str:
    """Build a numbered markdown reference list from the sources list."""
    if not sources:
        return "_No sources were collected for this run._"
    lines = []
    for i, s in enumerate(sources[:20], 1):
        title = s.get("title") or s.get("url") or "Unknown"
        url = s.get("url") or "#"
        origin = s.get("source", "Web")
        lines.append(f"{i}. [{title}]({url}) — *{origin}*")
    return "\n".join(lines)


def _render_swot(swot: dict) -> str:
    """
    Render a SWOT dict into a clean markdown bullet block.
    Analyst items already contain bare URLs like [https://...] — preserve them.
    """
    if not swot:
        return "_SWOT analysis not available for this run._"

    sections = [
        ("Strengths 💪", swot.get("strengths", [])),
        ("Weaknesses ⚠", swot.get("weaknesses", [])),
        ("Opportunities 🚀", swot.get("opportunities", [])),
        ("Threats 🔴", swot.get("threats", [])),
    ]
    lines = []
    for header, items in sections:
        lines.append(f"**{header}**")
        if items:
            for item in items:
                # item may already contain [https://...] from analyst — keep as-is
                lines.append(f"- {item}")
        else:
            lines.append("- _(none identified)_")
        lines.append("")
    return "\n".join(lines).strip()


# ── Main node ─────────────────────────────────────────────────────────────

def writer_node(state: GraphState) -> dict[str, Any]:
    """
    LangGraph node — single LLM call produces all 3 briefing sections.

    Fix summary (v2.1):
    - JSON is sanitized through a multi-stage repair pipeline before parsing.
    - `sources` is explicitly included in the return dict so the LangGraph
      state merge never silently drops it.
    - SWOT Analysis (from analyst_node) is rendered as a dedicated section.
    - The return dict includes `swot_analysis` so peer_review/approval see it.
    """
    topic = state.get("topic") or state.get("competitor_name", "Unknown")
    industry = state.get("industry", "Unknown")
    region = state.get("region", "Global")
    errors = list(state.get("errors", []))
    warnings = list(state.get("warnings", []))
    steps_used = (state.get("steps_used") or 0) + 1

    logger.info("[Writer] Generating 3-section briefing (single LLM call) for '%s'.", topic)

    now = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    cited_claims: list[CitedClaim] = list(state.get("cited_claims", []))

    # ── Preserve sources from state ───────────────────────────────────────
    # CRITICAL: reading here ensures we always return it, preventing LangGraph
    # from silently zeroing the key when it merges the writer node's output.
    sources: list[dict] = list(state.get("sources") or [])

    latest_news = state.get("latest_news", [])
    recommendations = state.get("recommendations", [])
    fact_check_passed = state.get("fact_check_passed", 0)
    fact_check_failed = state.get("fact_check_failed", 0)
    uncited_dropped = state.get("uncited_claims_dropped", [])
    adversarial_flags = state.get("adversarial_flags", [])
    failed_sources = state.get("failed_sources", [])
    swot_analysis: dict = state.get("swot_analysis") or {}

    # Partition claims by section tag
    pricing_claims = [c for c in cited_claims if c.get("section") == "pricing"] or cited_claims[:6]
    market_claims  = [c for c in cited_claims if c.get("section") == "market"]  or cited_claims[:6]
    exec_claims    = (
        [c for c in cited_claims if c.get("section") == "exec"]
        or sorted(cited_claims, key=lambda c: 0 if c.get("confidence") == "high" else 1)[:6]
    )

    news_lines = "\n".join(
        f"- {item['title']} [{item.get('source', '?')}] ({item.get('url', '#')})"
        for item in latest_news[:5]
    ) or "No recent news."

    rec_lines = "\n".join(f"- {r}" for r in recommendations[:5]) or "No recommendations."

    context = (
        f"Topic: {topic} | Industry: {industry} | Region: {region} | Date: {now}\n\n"
        f"PRICING/OVERVIEW:\n{state.get('pricing_summary', '')[:500]}\n\n"
        f"PRICING CLAIMS:\n{_format_claims_block(pricing_claims)}\n\n"
        f"MARKET TRENDS:\n{state.get('market_trends', '')[:400]}\n\n"
        f"MARKET CLAIMS:\n{_format_claims_block(market_claims)}\n\n"
        f"RECENT NEWS:\n{news_lines}\n\n"
        f"EXEC CLAIMS:\n{_format_claims_block(exec_claims)}\n\n"
        f"RECOMMENDATIONS:\n{rec_lines}"
    )

    # ── Single LLM call for all 3 sections ───────────────────────────────
    section_pricing_content = ""
    section_market_content  = ""
    section_exec_content    = ""
    llm_ok = False

    try:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Write all 3 briefing sections for:\n\n{context[:4500]}"),
        ]
        response = chat_with_fallback(messages)
        raw = response.content.strip()

        # ── Multi-stage JSON sanitization (fix for unterminated string error) ──
        sanitized = _sanitize_json_string(raw)
        parsed = _try_parse_json(sanitized)

        if parsed is None:
            raise ValueError(
                "JSON repair failed after all stages — "
                f"raw snippet: {raw[:200]!r}"
            )

        section_pricing_content = parsed.get("section_pricing", "")
        section_market_content  = parsed.get("section_market", "")
        section_exec_content    = parsed.get("section_exec", "")
        llm_ok = True
        logger.info("[Writer] All 3 sections generated and parsed successfully.")

    except Exception as exc:
        logger.warning("[Writer] LLM call or JSON parse failed, using fallback template: %s", exc)
        errors.append(f"Writer LLM/JSON error: {exc}")

    # ── Fallback: build sections from raw state data ──────────────────────
    if not llm_ok:
        section_pricing_content = (
            f"{state.get('pricing_summary', 'Pricing data not available.')}\n\n"
            + "\n".join(
                f"- {c.get('claim', '')} [Read Source]({c.get('source_url', '#')})"
                for c in pricing_claims[:5]
            )
        )
        section_market_content = (
            f"{state.get('market_trends', 'Market data not available.')}\n\n"
            f"**Recent News:**\n{news_lines}"
        )
        section_exec_content = (
            f"{state.get('executive_summary', f'Intelligence briefing for {topic}.')}\n\n"
            f"**Recommendation:**\n{rec_lines}"
        )

    # ── Build BriefingSection objects ─────────────────────────────────────
    section_pricing = BriefingSection(
        title="Competitor Pricing & Product Moves",
        content=section_pricing_content,
        cited_claims=pricing_claims,
    )
    section_market = BriefingSection(
        title="Market Signals & Trends",
        content=section_market_content,
        cited_claims=market_claims,
    )
    section_exec = BriefingSection(
        title="Executive Summary & Strategic Recommendation",
        content=section_exec_content,
        cited_claims=exec_claims,
    )

    # ── SWOT render ───────────────────────────────────────────────────────
    swot_markdown = _render_swot(swot_analysis)

    # ── Sources footer ────────────────────────────────────────────────────
    sources_footer = _build_citation_footer(sources)

    # ── Failed-source note ────────────────────────────────────────────────
    failed_note = ""
    if failed_sources:
        failed_note = (
            f"\n\n> **⚠ Data Gaps:** {len(failed_sources)} source(s) unreachable and skipped:\n"
            + "\n".join(f"> - {u}" for u in failed_sources[:5])
        )

    # ── Governance note ───────────────────────────────────────────────────
    governance_note = ""
    if uncited_dropped or adversarial_flags or fact_check_passed:
        governance_note = (
            f"\n\n---\n### Governance\n"
            f"- Uncited claims dropped: **{len(uncited_dropped)}**\n"
            f"- Adversarial flags suppressed: **{len(adversarial_flags)}**\n"
            f"- Claims verified (2+ sources): **{fact_check_passed}**\n"
            f"- Claims single-source (hedged): **{fact_check_failed}**\n"
        )

    # ── Assemble full Markdown ────────────────────────────────────────────
    final_report_markdown = f"""# Competitive Intelligence Briefing: {topic}
**Industry:** {industry} | **Region:** {region} | **Generated:** {now}

---

## 1. Competitor Pricing & Product Moves

{section_pricing_content}

---

## 2. Market Signals & Trends

{section_market_content}

---

## 3. Executive Summary & Strategic Recommendation

{section_exec_content}

---

## 4. SWOT Analysis

{swot_markdown}

---

## 5. Pricing Analysis

{state.get('pricing_summary', '_Pricing data not available for this run._')}
{failed_note}

---

## Sources & References

{sources_footer}
{governance_note}

---
*Competitive Intelligence Briefing Crew | {now}*
*Verified claims: {fact_check_passed} | Single-source (hedged): {fact_check_failed} | Sources collected: {len(sources)}*
"""

    logger.info(
        "[Writer] Briefing assembled: %d chars | sources=%d | swot=%s.",
        len(final_report_markdown),
        len(sources),
        "yes" if swot_analysis else "no",
    )

    return {
        # ── Primary writer outputs ────────────────────────────────────────
        "briefing_section_pricing": section_pricing,
        "briefing_section_market":  section_market,
        "briefing_section_exec":    section_exec,
        "final_report_markdown":    final_report_markdown,
        "report_sections": [
            "Competitor Pricing & Product Moves",
            "Market Signals & Trends",
            "Executive Summary & Strategic Recommendation",
            "SWOT Analysis",
            "Pricing Analysis",
            "Sources & References",
        ],
        # ── Pass-through state keys — MUST be returned so LangGraph merge
        #    never zeros them when this node's output dict is applied. ─────
        "sources":       sources,
        "swot_analysis": swot_analysis,
        # ── Bookkeeping ───────────────────────────────────────────────────
        "steps_used": steps_used,
        "errors":     errors,
        "warnings":   warnings,
    }
