"""
agent/cart.py — Add Selected Product to Blinkit Cart

Finds the "Add" button for the ranked product on the current search results
page and clicks it. Handles out-of-stock, login redirects, and already-in-cart
states.
"""

from __future__ import annotations

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from tools.blinkit import BlinkitAuthError, CartItem, OutOfStockError

# ── Selectors for Add buttons ─────────────────────────────────────────────────

# Blinkit renders an "Add" button per product card. We try multiple selectors.
ADD_BUTTON_SELECTORS = [
    'button[data-test-id="add-to-cart"]',
    'button[class*="AddToCart"]',
    'button[class*="add-to-cart"]',
    'button:has-text("Add")',
]

OUT_OF_STOCK_SELECTORS = [
    '[class*="OutOfStock"]',
    '[data-test-id="out-of-stock"]',
    'button:has-text("Notify")',
]

LOGIN_INDICATORS = ["/login", "/phone", "signup"]

CLICK_TIMEOUT_MS = 10_000


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_login_redirect(page: Page) -> bool:
    url = page.url.lower()
    return any(indicator in url for indicator in LOGIN_INDICATORS)


def _find_add_button(page: Page, card_index: int):
    """
    Locate the Add button for the product at `card_index` on the page.

    Strategy: collect ALL Add buttons visible on the page (one per product
    card), then index into the list.
    """
    for selector in ADD_BUTTON_SELECTORS:
        try:
            buttons = page.query_selector_all(selector)
            if buttons and card_index < len(buttons):
                return buttons[card_index]
        except Exception:
            continue
    return None


def _is_out_of_stock(page: Page, card_index: int) -> bool:
    """Check if the product card shows an out-of-stock indicator."""
    for selector in OUT_OF_STOCK_SELECTORS:
        try:
            indicators = page.query_selector_all(selector)
            if indicators and card_index < len(indicators):
                return True
        except Exception:
            continue
    return False


# ── Main cart function ────────────────────────────────────────────────────────

def add_product_to_cart(
    page: Page,
    ranked_result,         # RankedResult from agent.ranker
    product_name: str,
) -> CartItem:
    """
    Click the Add button for the ranked product on the current results page.

    Args:
        page:          Active Playwright page (on the search results page)
        ranked_result: RankedResult with selected_index, reason, product
        product_name:  Original search query string

    Returns:
        CartItem with the added product details

    Raises:
        OutOfStockError:  The selected variant is out of stock
        BlinkitAuthError: Clicking caused a login redirect
    """
    card_index = ranked_result.selected_index
    product = ranked_result.product

    # Check for out-of-stock first
    if _is_out_of_stock(page, card_index):
        raise OutOfStockError(
            f"'{product.name}' is out of stock on Blinkit."
        )

    # Find and click the Add button
    button = _find_add_button(page, card_index)
    if button is None:
        raise OutOfStockError(
            f"Could not find an Add button for '{product.name}' "
            f"(card index {card_index}). It may be out of stock or unlisted."
        )

    try:
        button.scroll_into_view_if_needed()
        button.click(timeout=CLICK_TIMEOUT_MS)
    except PlaywrightTimeout as exc:
        raise OutOfStockError(
            f"Timed out trying to click Add for '{product.name}'."
        ) from exc

    # Check for login redirect after click
    if _is_login_redirect(page):
        raise BlinkitAuthError(
            "Blinkit requires login to add items to cart. "
            "Run `python main.py --login` to authenticate."
        )

    # Brief wait for cart animation to settle (using selector, not sleep)
    try:
        # Wait for the button to change state (e.g. show quantity controls)
        page.wait_for_function(
            f"""() => {{
                const buttons = document.querySelectorAll('button');
                const btn = Array.from(buttons).find(b => b.textContent.trim() === 'Add');
                return btn === undefined || btn.textContent.trim() !== 'Add';
            }}""",
            timeout=5_000,
        )
    except Exception:
        pass  # Timeout here is not fatal — the click probably worked

    return CartItem(
        name=product.name,
        price=product.price,
        unit=product.unit,
        reason=ranked_result.reason,
    )
