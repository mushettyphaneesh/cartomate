"""
tests/test_searcher.py — Unit tests for agent/searcher.py

Uses mocked Playwright Page objects — no real browser is launched.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from agent.searcher import (
    SearchResult,
    _clean_price,
    _try_inner_text,
    search_blinkit,
)
from tools.blinkit import BlinkitAuthError


# ── Helper factories ──────────────────────────────────────────────────────────

def _make_card(name: str, price: str, unit: str, product_id: str = "pid-1") -> MagicMock:
    """Create a mock product card ElementHandle."""
    card = MagicMock()
    card.get_attribute.side_effect = lambda attr: (
        product_id if attr == "data-product-id" else None
    )

    def query_selector(selector: str):
        child = MagicMock()
        if "Name" in selector or "h3" in selector:
            child.inner_text.return_value = name
        elif "Price" in selector or "price" in selector:
            child.inner_text.return_value = price
        elif "Weight" in selector or "weight" in selector or "quantity" in selector:
            child.inner_text.return_value = unit
        else:
            return None
        return child

    card.query_selector.side_effect = query_selector
    return card


def _make_page(url: str = "https://blinkit.com/s/?q=rice", cards: list = None) -> MagicMock:
    """Create a mock Playwright Page."""
    page = MagicMock()
    type(page).url = PropertyMock(return_value=url)
    page.goto.return_value = None
    page.wait_for_selector.return_value = None
    page.query_selector_all.return_value = cards or []
    return page


# ── _clean_price tests ────────────────────────────────────────────────────────

class TestCleanPrice:
    def test_standard_rupee_symbol(self):
        assert _clean_price("₹129") == "₹129"

    def test_price_with_spaces(self):
        assert _clean_price("₹ 129") == "₹129"

    def test_price_with_commas(self):
        assert _clean_price("₹1,299") == "₹1299"

    def test_price_with_prefix_text(self):
        result = _clean_price("MRP ₹55")
        assert "55" in result

    def test_empty_returns_na(self):
        assert _clean_price("") == "N/A"


# ── search_blinkit tests (mocked page) ───────────────────────────────────────

class TestSearchBlinkit:
    def test_returns_results_when_products_found(self):
        cards = [
            _make_card("Daawat Basmati Rice 1kg", "₹129", "1 kg", "p1"),
            _make_card("India Gate Basmati 1kg", "₹149", "1 kg", "p2"),
            _make_card("Kohinoor Basmati 500g", "₹75", "500 g", "p3"),
        ]
        page = _make_page(cards=cards)

        results = search_blinkit(page, "basmati rice")

        assert len(results) == 3
        assert all(isinstance(r, SearchResult) for r in results)
        assert results[0].index == 0
        assert results[1].index == 1

    def test_returns_empty_list_when_no_products(self):
        page = _make_page(cards=[])
        # wait_for_selector raises PlaywrightTimeout for empty pages
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        page.wait_for_selector.side_effect = PlaywrightTimeout("timeout")

        results = search_blinkit(page, "some obscure product xyz")
        assert results == []

    def test_raises_auth_error_on_login_redirect(self):
        page = _make_page(url="https://blinkit.com/login?redirect=/s/?q=rice")

        with pytest.raises(BlinkitAuthError):
            search_blinkit(page, "rice")

    def test_caps_results_at_max_results(self):
        # Create 10 cards — should only get back 5
        cards = [
            _make_card(f"Product {i}", f"₹{10 * i}", f"{i} kg", f"p{i}")
            for i in range(1, 11)
        ]
        page = _make_page(cards=cards)

        results = search_blinkit(page, "rice")
        assert len(results) <= 5

    def test_result_indices_are_sequential(self):
        cards = [
            _make_card("Rice A", "₹100", "1 kg"),
            _make_card("Rice B", "₹120", "1 kg"),
        ]
        page = _make_page(cards=cards)

        results = search_blinkit(page, "rice")
        indices = [r.index for r in results]
        assert indices == list(range(len(results)))

    def test_malformed_card_is_skipped_gracefully(self):
        good_card = _make_card("Good Rice", "₹100", "1 kg")
        bad_card = MagicMock()
        bad_card.query_selector.side_effect = Exception("DOM error")
        bad_card.get_attribute.side_effect = Exception("DOM error")

        page = _make_page(cards=[good_card, bad_card])

        results = search_blinkit(page, "rice")
        # Bad card should be skipped, good card should be returned
        assert len(results) >= 1
        assert results[0].name == "Good Rice"
