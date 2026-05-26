"""
LLM Service — Phase 6
OpenRouter API client for all 3-call orchestration LLM calls.

Provides:
  - Single LLM call with retry + exponential backoff
  - JSON-mode call (parses and validates JSON response)
  - Jinja2 prompt rendering from templates
  - Model selection: primary (Claude 3.5 Sonnet), fallback (Llama 3.1 70B)
  - Token usage tracking

OpenRouter docs: https://openrouter.ai/docs
"""

import json
import httpx
from pathlib import Path
from typing import Optional
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.config import settings
from app.utils.rate_limiter import RateLimiter, with_exponential_backoff

# ── Rate limiter — 10 concurrent LLM calls max ────────────────
_llm_limiter = RateLimiter(concurrency=10, calls_per_second=0)

# ── Jinja2 environment ────────────────────────────────────────
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_prompt(template_name: str, **context) -> str:
    """Render a Jinja2 prompt template with the given context variables."""
    template = _jinja_env.get_template(template_name)
    return template.render(**context)


def _build_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/Sucharita2006/Email-Outreach-Automation",
        "X-Title": "Email Outreach Automation",
    }


async def call_llm(
    prompt: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1000,
    use_fallback: bool = False,
) -> dict:
    """
    Make a single LLM call to OpenRouter.

    Returns:
        {
            "content": str,           # Raw response text
            "model": str,             # Model actually used
            "usage": {                # Token usage
                "prompt_tokens": int,
                "completion_tokens": int,
                "total_tokens": int,
            },
            "status": "ok" | "error",
            "error": str | None,
        }
    """
    if not settings.OPENROUTER_API_KEY:
        return {"status": "no_api_key", "content": "", "model": "", "usage": {}, "error": "OPENROUTER_API_KEY not set"}

    selected_model = model or (
        settings.OPENROUTER_FALLBACK_MODEL if use_fallback
        else settings.OPENROUTER_PRIMARY_MODEL
    )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": selected_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    async def _do_call():
        async with _llm_limiter:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                    json=payload,
                    headers=_build_headers(),
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return {
                    "status": "ok",
                    "content": content.strip(),
                    "model": selected_model,
                    "usage": {
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                    "error": None,
                }

    try:
        return await with_exponential_backoff(_do_call, max_retries=3, base_delay=2.0)
    except httpx.HTTPStatusError as e:
        # If primary model fails with rate limit / payment, try fallback
        if not use_fallback and e.response.status_code in (429, 503, 402):
            return await call_llm(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                use_fallback=True,
            )
        return {
            "status": "error",
            "content": "",
            "model": selected_model,
            "usage": {},
            "error": f"OpenRouter {e.response.status_code}: {e.response.text[:300]}",
        }
    except Exception as e:
        return {
            "status": "error",
            "content": "",
            "model": selected_model,
            "usage": {},
            "error": str(e),
        }


async def call_llm_json(
    prompt: str,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 800,
    required_keys: list[str] = None,
) -> dict:
    """
    Make an LLM call expecting a JSON response.
    Strips markdown code fences and parses the JSON.

    Returns:
        {
            "status": "ok" | "error" | "invalid_json" | "missing_keys",
            "data": dict | None,     # Parsed JSON
            "raw": str,              # Raw LLM output
            "model": str,
            "usage": dict,
            "error": str | None,
            "missing_keys": list,
        }
    """
    result = await call_llm(
        prompt=prompt,
        model=model,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if result["status"] != "ok":
        return {**result, "data": None, "raw": result.get("content", ""), "missing_keys": []}

    raw = result["content"]

    # Strip markdown code fences: ```json ... ``` or ``` ... ```
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        inner = lines[1:] if lines[0].startswith("```") else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        cleaned = "\n".join(inner).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return {
            "status": "invalid_json",
            "data": None,
            "raw": raw,
            "model": result["model"],
            "usage": result["usage"],
            "error": f"JSON parse error: {e}",
            "missing_keys": [],
        }

    # Validate required keys
    missing = [k for k in (required_keys or []) if k not in parsed]

    return {
        "status": "ok" if not missing else "missing_keys",
        "data": parsed,
        "raw": raw,
        "model": result["model"],
        "usage": result["usage"],
        "error": None if not missing else f"Missing keys: {missing}",
        "missing_keys": missing,
    }
