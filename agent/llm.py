"""
agent/llm.py — Unified LLM Interface (Nvidia API, Gemini, & Anthropic)

Uses the Nvidia API with the google/gemma-3n-e2b-it model as requested,
with fallbacks to Google Gemini or Anthropic Claude if configured.
"""

from __future__ import annotations

import os
from typing import Optional
import requests

from dotenv import load_dotenv

load_dotenv()

def call_llm(
    system_prompt: str,
    user_prompt: str,
    response_json: bool = False,
    override_model: Optional[str] = None,
) -> str:
    """
    Call the configured LLM provider. Defaults to the Nvidia API (google/gemma-3n-e2b-it).
    """
    # ── 1. Nvidia API (Primary Choice) ────────────────────────────────────────
    # Try loading key from environment
    nvidia_key = os.environ.get("NVIDIA_API_KEY")
    
    if nvidia_key:
        invoke_url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {nvidia_key}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        model_name = override_model or os.environ.get("LLM_MODEL", "google/gemma-3n-e2b-it")
        
        # If model name was set to something else but we are using Nvidia, force Gemma model
        if "gemini" in model_name or "claude" in model_name:
            model_name = "google/gemma-3n-e2b-it"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": 1024 if response_json else 256,
            "temperature": 0.20,
            "top_p": 0.70,
            "frequency_penalty": 0.00,
            "presence_penalty": 0.00,
            "stream": False
        }

        try:
            response = requests.post(invoke_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            response_data = response.json()
            content = response_data["choices"][0]["message"]["content"]
            return content.strip()
        except Exception as e:
            print(f"[Debug] Nvidia API call failed: {e}. Trying fallback LLM...")

    # ── 2. Google Gemini Fallback ────────────────────────────────────────────
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            # pyrefly: ignore [missing-import]
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            
            model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                system_instruction=system_prompt,
            )
            
            generation_config = {}
            if response_json:
                generation_config["response_mime_type"] = "application/json"
                
            response = model.generate_content(
                user_prompt,
                generation_config=generation_config,
            )
            return response.text.strip()
        except Exception as e:
            print(f"[Debug] Gemini fallback failed: {e}")

    # ── 3. Anthropic Claude Fallback ──────────────────────────────────────────
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            
            max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "2048"))
            if not response_json:
                max_tokens = min(max_tokens, 256)
                
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            print(f"[Debug] Anthropic fallback failed: {e}")

    raise RuntimeError(
        "All configured LLM providers failed or no API keys are configured."
    )
