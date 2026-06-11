"""
tools/browser.py — Playwright Browser Setup & Teardown Helpers

Manages a persistent Chromium browser profile so the user only needs to log
in to Blinkit once. Subsequent runs reuse the saved session cookies.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import Browser, BrowserContext, Page, Playwright

load_dotenv()

# ── Constants ─────────────────────────────────────────────────────────────────

BLINKIT_BASE = "https://blinkit.com"

# Browser viewport — matches a typical laptop screen
VIEWPORT = {"width": 1280, "height": 800}

# User-Agent mimicking a real Chrome browser
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ── Public API ────────────────────────────────────────────────────────────────

def get_browser_context(playwright: Playwright) -> BrowserContext:
    """
    Launch a persistent Chromium browser context backed by a profile directory.

    The profile dir (default: ./browser_profile) stores cookies and local
    storage so that Blinkit sessions survive between agent runs.

    Args:
        playwright: The Playwright instance (from sync_playwright())

    Returns:
        A persistent BrowserContext with geolocation and UA configured.
    """
    profile_dir = Path(
        os.environ.get("BLINKIT_PROFILE_DIR", "./browser_profile")
    ).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    lat = float(os.environ.get("BLINKIT_LAT", "12.9116"))
    lng = float(os.environ.get("BLINKIT_LNG", "77.6370"))

    context: BrowserContext = playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=False,  # Visible so user can log in on first run
        viewport=VIEWPORT,
        user_agent=USER_AGENT,
        geolocation={"latitude": lat, "longitude": lng},
        permissions=["geolocation"],
        locale="en-IN",
        timezone_id="Asia/Kolkata",
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )
    return context


def get_page(context: BrowserContext) -> Page:
    """
    Get or create the first page in a browser context.

    Args:
        context: An active BrowserContext

    Returns:
        A configured Playwright Page object
    """
    pages = context.pages
    page = pages[0] if pages else context.new_page()

    # Mask Playwright's automation fingerprint
    page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return page


def teardown_browser(context: BrowserContext) -> None:
    """
    Gracefully close the browser context.

    Args:
        context: The BrowserContext to close
    """
    try:
        context.close()
    except Exception:
        pass  # Already closed or crashed — ignore


def ensure_logged_in(page: Page) -> bool:
    """
    Check if the user is logged in by navigating to a search page.
    If Blinkit redirects us to /login or /phone, the session is inactive.
    """
    test_url = f"{BLINKIT_BASE}/s/?q=sugar"
    print(f"[Debug] Checking login session by navigating to: {test_url}")
    
    try:
        page.goto(test_url, wait_until="domcontentloaded", timeout=30_000)
    except Exception as e:
        print(f"[Debug] Navigation failed: {e}")
        return False

    current_url = page.url
    print(f"[Debug] Current URL after navigation: {current_url}")
    print(f"[Debug] Page Title: '{page.title()}'")
    
    if "/login" in current_url or "/phone" in current_url or "/signup" in current_url:
        print("[Debug] Redirected to login/phone URL. Session is inactive.")
        return False

    print("[Debug] Session is active (no login redirect detected)!")
    return True
