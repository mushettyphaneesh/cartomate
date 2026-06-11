"""
agent/ranker.py — LLM-Powered Product Variant Ranker

Given the user's original intent, the product being searched, and a list of
Blinkit search results, Claude picks the best match and explains why.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import anthropic
from dotenv import load_dotenv

from agent.searcher import SearchResult

load_dotenv()

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class RankedResult:
    """The LLM's pick from a list of search results."""
    selected_index: int
    reason: str
    product: SearchResult  # the resolved SearchResult object


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_prompt() -> str:
    prompt_path = Path(__file__).parent.parent / "prompts" / "ranker.txt"
    return prompt_path.read_text(encoding="utf-8")


def _format_results_for_llm(results: list[SearchResult]) -> str:
    lines = []
    for r in results:
        lines.append(f"[{r.index}] {r.name} | {r.unit} | {r.price}")
    return "\n".join(lines)


def _parse_response(content: str, results: list[SearchResult]) -> RankedResult:
    content = content.strip()
    data = json.loads(content)

    idx = int(data["selected_index"])
    reason = str(data.get("reason", "Best match for the intent."))

    # Guard against out-of-range index
    if idx < 0 or idx >= len(results):
        idx = 0

    return RankedResult(
        selected_index=idx,
        reason=reason,
        product=results[idx],
    )


# ── Main ranker function ──────────────────────────────────────────────────────

def rank_results(
    intent: str,
    product_name: str,
    results: list[SearchResult],
    client: Optional[anthropic.Anthropic] = None,
) -> RankedResult:
    """
    Use Claude to pick the best search result for the given product + intent.

    Args:
        intent:       The original user intent string
        product_name: The product being searched (e.g. "basmati rice")
        results:      List of SearchResult objects from the searcher
        client:       Optional pre-initialised Anthropic client

    Returns:
        RankedResult with the chosen product and a reason string

    Notes:
        Falls back to index 0 on any parse error (no crash).
    """
    if not results:
        raise ValueError("Cannot rank an empty result list.")

    if len(results) == 1:
        # Only one option — no need to call the LLM
        return RankedResult(
            selected_index=0,
            reason="Only one result available.",
            product=results[0],
        )

    system_prompt = _load_prompt()
    formatted_results = _format_results_for_llm(results)
    user_message = (
        f"User intent: {intent}\n"
        f"Product being searched: {product_name}\n\n"
        f"Search results:\n{formatted_results}"
    )

    def _call() -> str:
        if client is not None:
            model = os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")
            response = client.messages.create(
                model=model,
                max_tokens=256,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text  # type: ignore[index]
        else:
            from agent.llm import call_llm
            return call_llm(system_prompt, user_message, response_json=True)

    # First attempt
    try:
        raw = _call()
        return _parse_response(raw, results)
    except (json.JSONDecodeError, KeyError, ValueError, IndexError):
        pass  # Fall back to index 0

    # Silent fallback — never crash the agent loop
    return RankedResult(
        selected_index=0,
        reason="Auto-selected (ranker parse error).",
        product=results[0],
    )
