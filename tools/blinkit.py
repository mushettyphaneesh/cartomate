"""
tools/blinkit.py — All Blinkit Interaction Logic

Central hub for all Blinkit-specific operations. Imports from agent.searcher
and agent.cart but provides clean, exception-typed public functions for the
LangGraph nodes to call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import Page

# ── Custom Exceptions ─────────────────────────────────────────────────────────

class BlinkitAuthError(Exception):
    """
    Raised when Blinkit redirects to a login page.

    To fix: run `python main.py --login` and log in through the browser window,
    then add your session cookies to .env or re-run the agent.
    """

class ProductNotFoundError(Exception):
    """Raised when a search query returns zero results."""

class OutOfStockError(Exception):
    """Raised when the selected product has no available Add button."""


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class CartItem:
    """Represents a product successfully added to the Blinkit cart."""
    name: str
    price: str
    unit: str
    reason: str  # Ranker's explanation for picking this variant


# ── Public API (thin wrappers used by LangGraph nodes) ───────────────────────

def search_products(page: Page, query: str) -> list:
    """
    Search Blinkit for a product. Returns a list of SearchResult objects.

    Raises:
        BlinkitAuthError: if login is required
        ProductNotFoundError: if zero results returned
    """
    # Deferred import to avoid circular dependency
    from agent.searcher import search_blinkit, SearchResult

    results: list[SearchResult] = search_blinkit(page, query)
    if not results:
        raise ProductNotFoundError(f"No results found for: '{query}'")
    return results


def add_to_cart(page: Page, result, product_name: str) -> CartItem:
    """
    Add a ranked product to the Blinkit cart.

    Args:
        page:         Active Playwright page (already on the search results page)
        result:       A RankedResult from agent.ranker
        product_name: Original product query string (for error messages)

    Returns:
        CartItem representing the successfully added product

    Raises:
        OutOfStockError: If the Add button cannot be found / clicked
        BlinkitAuthError: If clicking causes a login redirect
    """
    from agent.cart import add_product_to_cart
    return add_product_to_cart(page, result, product_name)
