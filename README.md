# 🛒 CartoMate — Smart Cart Agent

CartoMate is an AI-powered grocery agent that converts a natural language intent
(like *"I'm cooking biryani"* or *"I'm going on a trek"*) into a filled Blinkit
cart. It uses Claude for reasoning and Playwright for browser automation — no
manual searching required.

> ⚠️ **Research / Demo Project** — This project is intended as a portfolio
> demonstration of agentic LLM reasoning combined with browser automation.
> It is not intended for production use at scale and must be used in compliance
> with Blinkit's Terms of Service.

---

## Architecture

```
User Intent (CLI)
       │
       ▼
┌──────────────┐      ┌─────────────────────────────────────┐
│   main.py    │─────▶│          LangGraph StateGraph        │
│  (Rich UI)   │      │                                      │
└──────────────┘      │  ┌───────┐   ┌────────┐             │
                      │  │ plan  │──▶│ search │◀──────┐     │
                      │  └───────┘   └────────┘       │     │
                      │   Claude        Playwright      │     │
                      │                    │            │     │
                      │               ┌────────┐       │     │
                      │               │  rank  │       │     │
                      │               └────────┘       │     │
                      │                Claude           │     │
                      │                    │            │     │
                      │            ┌──────────────┐    │     │
                      │            │ add_to_cart  │────┘     │
                      │            └──────────────┘ (loop)   │
                      │               Playwright              │
                      │                    │ (all done)       │
                      │            ┌───────────────┐          │
                      │            │   summarise   │          │
                      │            └───────────────┘          │
                      └─────────────────────────────────────┘
                                         │
                                    Rich Terminal
                                      Summary
```

### Key Components

| Component | File | Description |
|-----------|------|-------------|
| Intent Planner | `agent/planner.py` | Claude converts user intent → JSON product list |
| Product Searcher | `agent/searcher.py` | Playwright searches Blinkit, extracts product cards |
| Result Ranker | `agent/ranker.py` | Claude picks best variant from search results |
| Cart Manager | `agent/cart.py` | Playwright clicks the Add button on Blinkit |
| Agent Graph | `agent/graph.py` | LangGraph StateGraph orchestrating the full loop |
| Browser Helpers | `tools/browser.py` | Persistent Chromium profile for session reuse |
| Blinkit Tools | `tools/blinkit.py` | Typed exceptions + public tool API |
| Entry Point | `main.py` | CLI with Rich UI, flags, and confirmation gate |

---

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Playwright's Chromium browser

```bash
playwright install chromium
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set:

```env
ANTHROPIC_API_KEY=sk-ant-api03-...   # Your Anthropic API key
BLINKIT_LAT=12.9116                  # Your delivery lat (default: Bangalore)
BLINKIT_LNG=77.6370                  # Your delivery lng
BLINKIT_PROFILE_DIR=./browser_profile
```

To get your delivery location coordinates, open blinkit.com, set your address,
then check the URL or use Google Maps to find the lat/lng.

### 4. Log in to Blinkit (one-time setup)

```bash
python main.py --login
```

This opens a Chromium window. Log in to blinkit.com with your phone number/OTP.
Your session is saved to `./browser_profile` and reused on all future runs.

---

## Usage

### Basic run

```bash
python main.py "I want to make biryani"
```

### Dry run (plan + search, no cart)

```bash
python main.py --dry-run "I am hosting a dinner party"
```

### Skip confirmation prompt

```bash
python main.py --yes "I'm going on a trek to Kedarkantha"
```

---

## Example Output

```
╭───────────────────────────────────────────╮
│  🛒  CartoMate — Smart Cart Agent         │
│  Powered by Claude + LangGraph + Playwright│
╰───────────────────────────────────────────╯

Intent: I want to make biryani

╭──────────────────────────────────────────────────────────────╮
│                     📋 Shopping Plan                         │
├───┬──────────────────┬──────────┬────────────────────────────┤
│ # │ Product          │ Quantity │ Priority                   │
├───┼──────────────────┼──────────┼────────────────────────────┤
│ 1 │ basmati rice     │ 1 kg     │ essential                  │
│ 2 │ biryani masala   │ 1 pack   │ essential                  │
│ 3 │ ghee             │ 500 ml   │ essential                  │
│ 4 │ onions           │ 500 g    │ essential                  │
│ 5 │ yogurt           │ 500 g    │ essential                  │
│ 6 │ mint leaves      │ 1 bunch  │ optional                   │
│ 7 │ saffron          │ 1 pack   │ optional                   │
╰───┴──────────────────┴──────────┴────────────────────────────╯

Add these items to your Blinkit cart? [y/n]: y

  🔍 Searching: basmati rice
      [0] India Gate Basmati Rice | 1 kg | ₹189
   →  [1] Daawat Extra Long Basmati | 1 kg | ₹179
      [2] Fortune Biryani Basmati | 1 kg | ₹159
  ✓  Selected: Daawat Extra Long Basmati (Best brand for biryani cooking.)

  🔍 Searching: biryani masala
   →  [0] Everest Shahi Biryani Masala | 50 g | ₹55
      [1] MDH Biryani Masala | 50 g | ₹49
  ✓  Selected: Everest Shahi Biryani Masala (Everest is preferred for biryani.)

  ...

╭──────────────────────────────────────────────────────────────────────╮
│                        🛒  Cart Summary                              │
├───────┬──────────────────────────────┬────────┬───────┬─────────────┤
│ Status│ Product                      │ Unit   │ Price │ Reason      │
├───────┼──────────────────────────────┼────────┼───────┼─────────────┤
│ ✅    │ Daawat Extra Long Basmati    │ 1 kg   │ ₹179  │ Best brand..│
│ ✅    │ Everest Shahi Biryani Masala │ 50 g   │ ₹55   │ Preferred...│
│ ✅    │ Amul Ghee                    │ 500 ml │ ₹310  │ Amul is...  │
│ ✅    │ Fresh Onions                 │ 500 g  │ ₹25   │ Local...    │
│ ✅    │ Nestle A+ Curd               │ 400 g  │ ₹45   │ Good value  │
│ ⚠️    │ saffron                      │ —      │ —     │ Not found   │
╰───────┴──────────────────────────────┴────────┴───────┴─────────────╯

Total: 5 item(s) added, 1 skipped | Estimated: ₹614
Cart URL: https://blinkit.com/cart
```

---

## Running Tests

Tests use mocked Playwright and Anthropic clients — no real browser or API key needed:

```bash
python -m pytest tests/ -v
```

---

## Project Structure

```
cartomate/
├── agent/
│   ├── __init__.py
│   ├── planner.py        # LLM: intent → product list
│   ├── searcher.py       # Blinkit product search (Playwright)
│   ├── ranker.py         # LLM: pick best product variant
│   ├── cart.py           # Add selected product to cart (Playwright)
│   └── graph.py          # LangGraph StateGraph agent loop
├── tools/
│   ├── __init__.py
│   ├── blinkit.py        # Public API + custom exceptions
│   └── browser.py        # Playwright setup/teardown helpers
├── prompts/
│   ├── planner.txt       # System prompt for the planner LLM
│   └── ranker.txt        # System prompt for the ranker LLM
├── tests/
│   ├── __init__.py
│   ├── test_planner.py
│   └── test_searcher.py
├── main.py               # Entry point
├── requirements.txt
├── .env.example
└── README.md
```

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Product not found on Blinkit | Logged as "⚠️ Skipped", agent continues |
| Out of stock | Logged as "⚠️ Skipped", agent continues |
| Not logged in to Blinkit | Clear error message + instructions to run `--login` |
| LLM returns malformed JSON | Automatic retry with stricter prompt |
| Intent too vague | Claude asks a clarification question; no search starts |
| Any single product failure | Never crashes — rest of the list is processed |

---

## Limitations

- Blinkit's DOM selectors may change without notice; this agent implements
  multi-selector fallbacks but may need updates if Blinkit redesigns its UI.
- The agent adds 1 unit of each product (increment logic for specific quantities
  is not implemented in this version).
- Location-based pricing means results vary by delivery address.

---

## Disclaimer

This is a research and portfolio demonstration project. Automated interaction
with Blinkit's website may be subject to their Terms of Service. Use responsibly
and only for personal grocery planning.
