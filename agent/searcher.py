"""
agent/searcher.py — Blinkit Product Search via Playwright

Navigates to Blinkit's search page for a given query, waits for results to
load, and extracts the top 5 product cards from the DOM.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from tools.blinkit import BlinkitAuthError

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class SearchResult:
    """A single product from Blinkit search results."""
    index: int
    name: str
    price: str          # e.g. "₹129"
    unit: str           # e.g. "1 kg" or "500 ml"
    product_id: str     # DOM data-product-id or URL slug (best-effort)
    add_button_index: int = 0   # positional index of the Add button on the page

    def display(self) -> str:
        return f"[{self.index}] {self.name} | {self.unit} | {self.price}"


# ── Selectors (tried in order; first match wins) ──────────────────────────────

# Blinkit uses React; selectors are subject to change. We try multiple fallbacks.
PRODUCT_CARD_SELECTORS = [
    '[data-test-id="plp-product"]',
    '[class*="ProductCard"]',
    '.product-container',
]

NAME_SELECTORS = [
    '[class*="ProductName"]',
    '[data-test-id="product-name"]',
    'h3',
]

PRICE_SELECTORS = [
    '[class*="Price"]',
    '[data-test-id="product-price"]',
    '[class*="price"]',
]

UNIT_SELECTORS = [
    '[class*="Weight"]',
    '[data-test-id="product-weight"]',
    '[class*="weight"]',
    '[class*="quantity"]',
]

SEARCH_URL_TEMPLATE = "https://blinkit.com/s/?q={query}"

MAX_RESULTS = 5
SEARCH_TIMEOUT_MS = 20_000   # 20 s for the product grid to appear
LOGIN_INDICATORS = ["/login", "/phone", "signup"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_login_redirect(page: Page) -> bool:
    """Return True if Blinkit redirected us to the login flow."""
    url = page.url.lower()
    return any(indicator in url for indicator in LOGIN_INDICATORS)


def _try_inner_text(element, selectors: list[str]) -> str:
    """Try each selector, return the first non-empty inner text found."""
    for sel in selectors:
        try:
            child = element.query_selector(sel)
            if child:
                text = (child.inner_text() or "").strip()
                if text:
                    return text
        except Exception:
            continue
    return ""


def _clean_price(raw: str) -> str:
    """Normalise price string to ₹NNN format."""
    raw = raw.strip()
    # Keep only digits and ₹ symbol
    match = re.search(r"[\u20b9₹]?\s*\d[\d,]*", raw)
    if match:
        return "₹" + match.group().replace("₹", "").replace("\u20b9", "").replace(",", "").strip()
    return raw or "N/A"


def _wait_for_products(page: Page) -> Optional[list]:
    """
    Try each product-card selector in sequence.
    Returns a list of ElementHandle or None if no products found.
    """
    for selector in PRODUCT_CARD_SELECTORS:
        try:
            page.wait_for_selector(selector, timeout=SEARCH_TIMEOUT_MS)
            cards = page.query_selector_all(selector)
            if cards:
                return cards
        except PlaywrightTimeout:
            continue
    return None


# ── Main search function ──────────────────────────────────────────────────────

def search_blinkit(page: Page, query: str) -> list[SearchResult]:
    """
    Search Blinkit for a product and return up to MAX_RESULTS results.

    Args:
        page:  An active Playwright Page (must already be on blinkit.com)
        query: Product search query, e.g. "basmati rice"

    Returns:
        List of SearchResult objects (may be empty if no products found)

    Raises:
        BlinkitAuthError: If Blinkit redirects to the login page
    """
    encoded = urllib.parse.quote(query)
    url = SEARCH_URL_TEMPLATE.format(query=encoded)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except Exception as exc:
        raise RuntimeError(f"Failed to navigate to Blinkit search page: {exc}") from exc

    if _is_login_redirect(page):
        raise BlinkitAuthError(
            "Blinkit requires login. Run `python main.py --login` to open the "
            "browser and log in, then retry."
        )

    cards = _wait_for_products(page)
    if not cards:
        return []  # Product not found — caller handles gracefully

    results: list[SearchResult] = []
    for idx, card in enumerate(cards[:MAX_RESULTS]):
        try:
            name = _try_inner_text(card, NAME_SELECTORS) or "Unknown Product"
            raw_price = _try_inner_text(card, PRICE_SELECTORS)
            unit = _try_inner_text(card, UNIT_SELECTORS) or "N/A"
            price = _clean_price(raw_price)

            # Best-effort product ID from data attributes
            product_id = (
                card.get_attribute("data-product-id")
                or card.get_attribute("data-id")
                or f"idx-{idx}"
            )

            results.append(
                SearchResult(
                    index=idx,
                    name=name,
                    price=price,
                    unit=unit,
                    product_id=str(product_id),
                    add_button_index=idx,
                )
            )
        except Exception:
            continue  # Skip malformed cards silently

    return results
