"""
main.py — CartoMate Smart Cart Agent Entry Point

Usage:
    python main.py "I want to make biryani"
    python main.py --login       # Open browser to log in to Blinkit first
    python main.py --yes "..."   # Skip confirmation prompt (auto-confirm)
    python main.py --dry-run "..." # Plan + search without adding to cart
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

load_dotenv()

console = Console()


# ── Helpers ───────────────────────────────────────────────────────────────────

def print_banner():
    console.print(
        Panel.fit(
            "[bold cyan]🛒  CartoMate — Smart Cart Agent[/bold cyan]\n"
            "[dim]Powered by Claude + LangGraph + Playwright[/dim]",
            border_style="cyan",
        )
    )


def print_product_plan(product_list: list):
    table = Table(title="📋 Shopping Plan", box=box.ROUNDED, border_style="blue")
    table.add_column("#", style="dim", width=3)
    table.add_column("Product", style="bold")
    table.add_column("Quantity", style="cyan")
    table.add_column("Priority", style="yellow")

    for i, p in enumerate(product_list, 1):
        priority_style = "green" if p.priority == "essential" else "dim"
        table.add_row(
            str(i),
            p.name,
            p.quantity,
            f"[{priority_style}]{p.priority}[/{priority_style}]",
        )
    console.print(table)


def print_search_result(product_name: str, results: list, ranked):
    if not results:
        console.print(f"  [yellow]⚠  '{product_name}' — no results found, skipping[/yellow]")
        return

    console.print(f"\n  [bold]🔍 Searching:[/bold] {product_name}")
    for r in results:
        marker = "→" if r.index == (ranked.selected_index if ranked else -1) else " "
        console.print(f"     {marker} [{r.index}] {r.name} | {r.unit} | {r.price}")

    if ranked:
        console.print(
            f"  [green]✓  Selected:[/green] {ranked.product.name} "
            f"[dim]({ranked.reason})[/dim]"
        )


def print_summary(cart_items: list, skipped_items: list):
    console.print()

    # Cart table
    if cart_items:
        table = Table(
            title="🛒  Cart Summary",
            box=box.ROUNDED,
            border_style="green",
        )
        table.add_column("Status", width=4)
        table.add_column("Product", style="bold")
        table.add_column("Unit", style="cyan")
        table.add_column("Price", style="green", justify="right")
        table.add_column("Reason", style="dim")

        for item in cart_items:
            table.add_row("✅", item.name, item.unit, item.price, item.reason)

        for skip in skipped_items:
            table.add_row(
                "⚠️",
                skip["name"],
                "—",
                "—",
                f"[yellow]{skip['reason']}[/yellow]",
            )

        console.print(table)
    else:
        console.print("[yellow]No items were added to the cart.[/yellow]")
        for skip in skipped_items:
            console.print(f"  ⚠  [yellow]{skip['name']}[/yellow] — {skip['reason']}")

    # Totals
    total_items = len(cart_items)
    total_skipped = len(skipped_items)

    # Parse prices for sum (best-effort)
    total_price = 0
    for item in cart_items:
        try:
            digits = "".join(c for c in item.price if c.isdigit())
            total_price += int(digits) if digits else 0
        except Exception:
            pass

    console.print(
        f"\n[bold]Total:[/bold] {total_items} item(s) added"
        + (f", {total_skipped} skipped" if total_skipped else "")
        + (f" | [green]Estimated: ₹{total_price}[/green]" if total_price else "")
    )
    console.print(
        "[dim]Cart URL:[/dim] [link=https://blinkit.com/cart]https://blinkit.com/cart[/link]"
    )


def login_mode(page):
    """Open Blinkit and wait for the user to log in manually."""
    console.print("[cyan]Opening Blinkit in browser — please log in...[/cyan]")
    page.goto("https://blinkit.com", wait_until="domcontentloaded")
    console.print("[dim]Press Enter once you are logged in and can see the homepage.[/dim]")
    input()
    console.print("[green]✓ Session saved. You can now run the agent normally.[/green]")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args:
        console.print(
            "[red]Usage:[/red] python main.py \"I want to make biryani\"\n"
            "       python main.py --login"
        )
        sys.exit(1)

    # Flag parsing
    auto_confirm = "--yes" in args or os.environ.get("AUTO_CONFIRM", "").lower() == "true"
    dry_run = "--dry-run" in args
    do_login = "--login" in args

    # Extract the intent (first non-flag argument)
    intent_args = [a for a in args if not a.startswith("--")]
    intent: Optional[str] = intent_args[0] if intent_args else None

    print_banner()

    with sync_playwright() as playwright:
        from tools.browser import get_browser_context, get_page, ensure_logged_in, teardown_browser

        console.print("[dim]Starting browser...[/dim]")
        context = get_browser_context(playwright)
        page = get_page(context)

        # ── Login mode ────────────────────────────────────────────────────
        if do_login:
            login_mode(page)
            teardown_browser(context)
            return

        if not intent:
            console.print("[red]Error:[/red] Please provide a grocery intent string.")
            teardown_browser(context)
            sys.exit(1)

        # ── Check login status ────────────────────────────────────────────
        console.print("[dim]Checking Blinkit session...[/dim]")
        logged_in = ensure_logged_in(page)
        if not logged_in:
            console.print(
                "[yellow]⚠  Not logged in to Blinkit.[/yellow]\n"
                "   Run [bold]python main.py --login[/bold] first, then retry."
            )
            teardown_browser(context)
            sys.exit(1)

        console.print(f"[green]✓[/green] Session active\n")
        console.print(f"[bold]Intent:[/bold] {intent}\n")

        # ── Build and run the agent graph ─────────────────────────────────
        from agent.graph import build_graph

        app = build_graph(page)

        initial_state = {
            "intent": intent,
            "product_list": [],
            "current_index": 0,
            "search_results": [],
            "ranked_result": None,
            "cart_items": [],
            "skipped_items": [],
            "error": None,
        }

        # Stream events so we can show progress in real time
        final_state = None

        with console.status("[cyan]Planning your grocery list...[/cyan]"):
            # Run plan node separately to show the list before continuing
            plan_result = None
            for event in app.stream(initial_state, stream_mode="values"):
                final_state = event

                # After plan node — show the product list
                if (
                    plan_result is None
                    and event.get("product_list")
                    and event["current_index"] == 0
                ):
                    plan_result = event

        # ── Handle fatal errors (e.g. clarification needed) ───────────────
        if final_state and final_state.get("error"):
            err = final_state["error"]
            if err.startswith("CLARIFICATION_NEEDED:"):
                question = err.replace("CLARIFICATION_NEEDED:", "", 1)
                console.print(
                    Panel(
                        f"[yellow]🤔 {question}[/yellow]",
                        title="Clarification Needed",
                        border_style="yellow",
                    )
                )
            else:
                console.print(f"[red]Error:[/red] {err}")
            teardown_browser(context)
            sys.exit(1)

        if not final_state or not final_state.get("product_list"):
            console.print("[red]Could not generate a product list. Please try again.[/red]")
            teardown_browser(context)
            sys.exit(1)

        # Show the plan
        print_product_plan(final_state["product_list"])

        # ── Dry run — stop before cart ────────────────────────────────────
        if dry_run:
            console.print(
                "\n[dim]Dry run complete — no items were added to the cart.[/dim]"
            )
            teardown_browser(context)
            return

        # ── Confirmation gate ─────────────────────────────────────────────
        if not auto_confirm:
            confirmed = Confirm.ask(
                "\n[bold]Add these items to your Blinkit cart?[/bold]"
            )
            if not confirmed:
                console.print("[dim]Aborted. Nothing was added to the cart.[/dim]")
                teardown_browser(context)
                return

        # ── Run the full graph (search + rank + add_to_cart) ─────────────
        console.print()
        cart_items = []
        skipped_items = []

        for event in app.stream(initial_state, stream_mode="values"):
            # Show search progress as it happens
            if event.get("search_results") is not None and event.get("product_list"):
                idx = event.get("current_index", 0)
                if idx > 0 and idx <= len(event["product_list"]):
                    pname = event["product_list"][idx - 1].name
                    results = event.get("search_results", [])
                    ranked = event.get("ranked_result")
                    print_search_result(pname, results, ranked)

            cart_items = event.get("cart_items", cart_items)
            skipped_items = event.get("skipped_items", skipped_items)
            final_state = event

        # ── Print final summary ───────────────────────────────────────────
        print_summary(
            final_state.get("cart_items", []),
            final_state.get("skipped_items", []),
        )

        teardown_browser(context)


if __name__ == "__main__":
    main()
