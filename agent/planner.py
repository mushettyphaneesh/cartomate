"""
agent/planner.py — Intent → Structured Product List

Uses Claude to convert a raw user intent string into a list of grocery/essential
products with name, quantity, and priority fields.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()

# ── Data models ──────────────────────────────────────────────────────────────

@dataclass
class ProductItem:
    """A single product to search for on Blinkit."""
    name: str
    quantity: str
    priority: str  # "essential" | "optional"

    def to_dict(self) -> dict:
        return {"name": self.name, "quantity": self.quantity, "priority": self.priority}


# ── Custom exceptions ─────────────────────────────────────────────────────────

class ClarificationNeeded(Exception):
    """Raised when the LLM determines the user intent is too vague."""
    def __init__(self, question: str):
        self.question = question
        super().__init__(question)


class PlannerError(Exception):
    """Raised on unrecoverable planner failures."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_prompt() -> str:
    prompt_path = Path(__file__).parent.parent / "prompts" / "planner.txt"
    return prompt_path.read_text(encoding="utf-8")


def _parse_response(content: str) -> list[ProductItem]:
    """
    Parse the LLM response into a list of ProductItems.
    Raises ClarificationNeeded or ValueError on bad output.
    """
    content = content.strip()
    data = json.loads(content)

    # Ambiguous intent — LLM returned a clarification request
    if isinstance(data, dict) and "clarification_needed" in data:
        raise ClarificationNeeded(data["clarification_needed"])

    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array, got: {type(data).__name__}")

    products: list[ProductItem] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        products.append(
            ProductItem(
                name=str(item.get("name", "")).strip(),
                quantity=str(item.get("quantity", "1 unit")).strip(),
                priority=str(item.get("priority", "essential")).strip(),
            )
        )

    if not products:
        raise ValueError("Planner returned an empty product list.")

    return products


# ── Main planner function ─────────────────────────────────────────────────────

def plan_products(
    intent: str,
    client: Optional[anthropic.Anthropic] = None,
) -> list[ProductItem]:
    """
    Convert a natural language user intent into a list of ProductItems.

    Args:
        intent: Raw user string, e.g. "I want to make biryani"
        client: Optional pre-initialised Anthropic client (for testing / DI)

    Returns:
        List of ProductItem objects

    Raises:
        ClarificationNeeded: If the LLM deems the intent too vague
        PlannerError: If the LLM returns malformed JSON twice
    """
    system_prompt = _load_prompt()

    def _call(user_message: str) -> str:
        if client is not None:
            model = os.environ.get("LLM_MODEL", "claude-sonnet-4-20250514")
            max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "2048"))
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text  # type: ignore[index]
        else:
            from agent.llm import call_llm
            return call_llm(system_prompt, user_message, response_json=True)

    # First attempt
    try:
        raw = _call(intent)
        return _parse_response(raw)
    except ClarificationNeeded:
        raise  # propagate directly — don't retry
    except (json.JSONDecodeError, ValueError):
        pass  # fall through to retry

    # Retry with a stricter prompt
    strict_suffix = (
        "\n\nCRITICAL: Your previous response was not valid JSON. "
        "Return ONLY a raw JSON array. No prose, no markdown, no code blocks."
    )
    try:
        raw = _call(intent + strict_suffix)
        return _parse_response(raw)
    except ClarificationNeeded:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise PlannerError(
            f"Planner failed after 2 attempts. Last error: {exc}"
        ) from exc
