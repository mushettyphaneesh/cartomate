"""
tests/test_planner.py — Unit tests for agent/planner.py

All tests use mocked Anthropic clients — no real API calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from agent.planner import (
    ClarificationNeeded,
    PlannerError,
    ProductItem,
    _parse_response,
    plan_products,
)


# ── _parse_response unit tests ────────────────────────────────────────────────

class TestParseResponse:
    def test_valid_product_list(self):
        raw = json.dumps([
            {"name": "basmati rice", "quantity": "1 kg", "priority": "essential"},
            {"name": "ghee", "quantity": "500 ml", "priority": "optional"},
        ])
        result = _parse_response(raw)
        assert len(result) == 2
        assert isinstance(result[0], ProductItem)
        assert result[0].name == "basmati rice"
        assert result[1].priority == "optional"

    def test_clarification_needed(self):
        raw = json.dumps({"clarification_needed": "What dish are you making?"})
        with pytest.raises(ClarificationNeeded) as exc_info:
            _parse_response(raw)
        assert "What dish" in exc_info.value.question

    def test_invalid_json_raises_value_error(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            _parse_response("this is not json")

    def test_empty_list_raises_value_error(self):
        with pytest.raises(ValueError, match="empty"):
            _parse_response("[]")

    def test_non_list_raises_value_error(self):
        with pytest.raises(ValueError, match="Expected a JSON array"):
            _parse_response(json.dumps({"some": "dict"}))

    def test_malformed_items_are_skipped(self):
        raw = json.dumps([
            {"name": "rice", "quantity": "1 kg", "priority": "essential"},
            "not a dict",  # This should be silently skipped
            {"name": "ghee", "quantity": "500 ml", "priority": "optional"},
        ])
        result = _parse_response(raw)
        assert len(result) == 2

    def test_missing_fields_get_defaults(self):
        raw = json.dumps([{"name": "rice"}])
        result = _parse_response(raw)
        assert result[0].quantity == "1 unit"
        assert result[0].priority == "essential"


# ── plan_products integration tests (mocked LLM) ─────────────────────────────

def _make_mock_client(response_text: str) -> MagicMock:
    """Create a mock Anthropic client that returns response_text."""
    mock_content = MagicMock()
    mock_content.text = response_text

    mock_response = MagicMock()
    mock_response.content = [mock_content]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    return mock_client


class TestPlanProducts:
    def test_valid_intent_returns_product_list(self):
        mock_response = json.dumps([
            {"name": "basmati rice", "quantity": "1 kg", "priority": "essential"},
            {"name": "biryani masala", "quantity": "1 pack", "priority": "essential"},
        ])
        client = _make_mock_client(mock_response)

        result = plan_products("I want to make biryani", client=client)

        assert len(result) == 2
        assert result[0].name == "basmati rice"
        # LLM was called exactly once (valid response on first attempt)
        assert client.messages.create.call_count == 1

    def test_ambiguous_intent_raises_clarification_needed(self):
        mock_response = json.dumps(
            {"clarification_needed": "What dish are you planning to cook?"}
        )
        client = _make_mock_client(mock_response)

        with pytest.raises(ClarificationNeeded) as exc_info:
            plan_products("food", client=client)

        assert "dish" in exc_info.value.question.lower()

    def test_malformed_json_triggers_retry(self):
        # First call: bad JSON. Second call: valid JSON.
        bad_response = "Here are the products: rice, ghee"
        good_response = json.dumps([
            {"name": "rice", "quantity": "1 kg", "priority": "essential"},
        ])

        mock_content_bad = MagicMock()
        mock_content_bad.text = bad_response

        mock_content_good = MagicMock()
        mock_content_good.text = good_response

        mock_response_bad = MagicMock()
        mock_response_bad.content = [mock_content_bad]

        mock_response_good = MagicMock()
        mock_response_good.content = [mock_content_good]

        client = MagicMock()
        client.messages.create.side_effect = [mock_response_bad, mock_response_good]

        result = plan_products("make me something", client=client)

        assert len(result) == 1
        assert result[0].name == "rice"
        assert client.messages.create.call_count == 2  # retry happened

    def test_two_malformed_responses_raise_planner_error(self):
        client = _make_mock_client("definitely not json")

        with pytest.raises(PlannerError):
            plan_products("something vague", client=client)

        assert client.messages.create.call_count == 2
