"""
agent/graph.py — LangGraph StateGraph for the Smart Cart Agent

Defines the CartState TypedDict and assembles the full agent pipeline:

    plan → search → rank → add_to_cart ↺ (loop until all products processed)
                                    ↓
                               summarise → END

Each node function receives the full CartState and returns a dict of state
updates. The Playwright page is passed via a shared context object injected
at build time.
"""

from __future__ import annotations

import os
from typing import Any, Optional, TypedDict

import anthropic
from dotenv import load_dotenv
from langgraph.graph import END, StateGraph
from playwright.sync_api import Page

from agent.cart import add_product_to_cart
from agent.planner import ClarificationNeeded, ProductItem, plan_products
from agent.ranker import RankedResult, rank_results
from agent.searcher import SearchResult, search_blinkit
from tools.blinkit import (
    BlinkitAuthError,
    CartItem,
    OutOfStockError,
    ProductNotFoundError,
)

load_dotenv()


# ── State Schema ─────────────────────────────────────────────────────────────

class CartState(TypedDict):
    """Shared mutable state passed between all LangGraph nodes."""
    intent: str                             # Raw user input
    product_list: list[ProductItem]         # Planner output
    current_index: int                      # Which product we're processing
    search_results: list[SearchResult]      # Searcher output for current product
    ranked_result: Optional[RankedResult]   # Ranker output for current product
    cart_items: list[CartItem]              # Successfully added products
    skipped_items: list[dict]               # Products skipped (not found / OOS)
    error: Optional[str]                    # Fatal error message (stops graph)


# ── Context object (injected into nodes via closure) ─────────────────────────

class AgentContext:
    """Holds live objects (Playwright page, Anthropic client) shared across nodes."""
    def __init__(self, page: Page, anthropic_client: Optional[anthropic.Anthropic]):
        self.page = page
        self.client = anthropic_client


# ── Node implementations ─────────────────────────────────────────────────────

def make_plan_node(ctx: AgentContext):
    def plan_node(state: CartState) -> dict:
        try:
            products = plan_products(state["intent"], client=ctx.client)
            return {
                "product_list": products,
                "current_index": 0,
                "cart_items": [],
                "skipped_items": [],
                "error": None,
            }
        except ClarificationNeeded as e:
            return {"error": f"CLARIFICATION_NEEDED:{e.question}"}
        except Exception as e:
            return {"error": f"Planner failed: {e}"}
    return plan_node


def make_search_node(ctx: AgentContext):
    def search_node(state: CartState) -> dict:
        idx = state["current_index"]
        product = state["product_list"][idx]
        try:
            results = search_blinkit(ctx.page, product.name)
            return {"search_results": results}
        except BlinkitAuthError as e:
            return {"error": str(e)}
        except Exception:
            # Treat unexpected errors as "not found" — agent continues
            return {"search_results": []}
    return search_node


def make_rank_node(ctx: AgentContext):
    def rank_node(state: CartState) -> dict:
        results = state["search_results"]
        if not results:
            return {"ranked_result": None}

        idx = state["current_index"]
        product = state["product_list"][idx]
        try:
            ranked = rank_results(
                intent=state["intent"],
                product_name=product.name,
                results=results,
                client=ctx.client,
            )
            return {"ranked_result": ranked}
        except Exception:
            # Fallback: pick first result
            from agent.ranker import RankedResult as RR
            return {
                "ranked_result": RR(
                    selected_index=0,
                    reason="Auto-selected (ranker error).",
                    product=results[0],
                )
            }
    return rank_node


def make_add_to_cart_node(ctx: AgentContext):
    def add_to_cart_node(state: CartState) -> dict:
        idx = state["current_index"]
        product = state["product_list"][idx]
        ranked = state.get("ranked_result")

        skipped = list(state.get("skipped_items", []))
        cart = list(state.get("cart_items", []))

        # No results from search — skip gracefully
        if ranked is None:
            skipped.append({
                "name": product.name,
                "reason": "Not found on Blinkit",
            })
            return {
                "cart_items": cart,
                "skipped_items": skipped,
                "current_index": idx + 1,
            }

        try:
            cart_item = add_product_to_cart(ctx.page, ranked, product.name)
            cart.append(cart_item)
        except OutOfStockError as e:
            skipped.append({"name": product.name, "reason": str(e)})
        except BlinkitAuthError as e:
            return {"error": str(e)}
        except Exception as e:
            skipped.append({"name": product.name, "reason": f"Error: {e}"})

        return {
            "cart_items": cart,
            "skipped_items": skipped,
            "current_index": idx + 1,
        }
    return add_to_cart_node


def summarise_node(state: CartState) -> dict:
    """Terminal node — just returns the state as-is; printing is done in main.py."""
    return {}


# ── Routing functions ─────────────────────────────────────────────────────────

def route_after_plan(state: CartState) -> str:
    if state.get("error"):
        return "summarise"
    if not state.get("product_list"):
        return "summarise"
    return "search"


def route_after_add(state: CartState) -> str:
    if state.get("error"):
        return "summarise"
    idx = state["current_index"]
    total = len(state.get("product_list", []))
    if idx >= total:
        return "summarise"
    return "search"


# ── Graph builder ─────────────────────────────────────────────────────────────

def build_graph(page: Page, anthropic_client: Optional[anthropic.Anthropic] = None):
    """
    Construct and compile the LangGraph StateGraph.

    Args:
        page:             Active Playwright page
        anthropic_client: Optional pre-built Anthropic client (for testing)

    Returns:
        A compiled LangGraph app (callable with invoke())
    """
    if anthropic_client is None:
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_key:
            anthropic_client = anthropic.Anthropic(api_key=anthropic_key)

    ctx = AgentContext(page=page, anthropic_client=anthropic_client)

    graph = StateGraph(CartState)

    # Add nodes
    graph.add_node("plan", make_plan_node(ctx))
    graph.add_node("search", make_search_node(ctx))
    graph.add_node("rank", make_rank_node(ctx))
    graph.add_node("add_to_cart", make_add_to_cart_node(ctx))
    graph.add_node("summarise", summarise_node)

    # Entry
    graph.set_entry_point("plan")

    # Edges
    graph.add_conditional_edges("plan", route_after_plan, {
        "search": "search",
        "summarise": "summarise",
    })
    graph.add_edge("search", "rank")
    graph.add_edge("rank", "add_to_cart")
    graph.add_conditional_edges("add_to_cart", route_after_add, {
        "search": "search",      # Loop: next product
        "summarise": "summarise",
    })
    graph.add_edge("summarise", END)

    return graph.compile()
