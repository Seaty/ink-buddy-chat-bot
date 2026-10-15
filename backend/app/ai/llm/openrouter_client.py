"""OpenRouter HTTP client with the same ``chat()`` contract as :class:`OllamaClient`.

Takes Ollama-style messages (``images``: base64 JPEG strings) and options, calls
the OpenAI-compatible ``/chat/completions`` endpoint, and returns an
Ollama-shaped response (``message.content``, ``done_reason``,
``prompt_eval_count``, ``eval_count``), so ``QwenVision`` works unchanged.

Customer photos leave the machine on this path. Every request asks OpenRouter
to route only to providers that do not store or train on prompts
(``provider.data_collection = "deny"``) and that support every parameter sent
(``require_parameters``, so the JSON schema is never silently dropped).
``fallback_models`` are tried in order when the requested model fails — a model
served by a single provider goes down with it.
"""
from __future__ import annotations

import re
import time
from typing import Any, Sequence

import httpx

from app.ai.llm.errors import LLMError

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_S = 60.0
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRY_WAIT_S = 5.0

# OpenRouter finish_reason → Ollama done_reason (the rest pass through)
_DONE_REASON = {"length": "length", "stop": "stop", "tool_calls": "stop", "content_filter": "content_filter"}


class OpenRouterError(LLMError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class OpenRouterClient:
    def __init__(
        self,
        api_key: str | None,
        base_url: str | None = None,
        timeout_s: float | None = None,
        retries: int = 1,
        app_title: str = "Ink Buddy",
        fallback_models: Sequence[str] = (),
    ):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.retries = retries
        # Tried in order by OpenRouter when the requested model fails (down, rate-limited, no provider)
        self.fallback_models = [m for m in fallback_models if m]
        self._has_key = bool(api_key)
        timeout = timeout_s or DEFAULT_TIMEOUT_S
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=min(10.0, timeout)),
            headers={"Authorization": f"Bearer {api_key or ''}", "X-Title": app_title},
        )

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        format: str | dict | None = None,
        options: dict[str, Any] | None = None,
        think: bool | None = None,
        keep_alive: str | int | None = None,
    ) -> dict[str, Any]:
        """Non-streaming chat. ``think``, ``keep_alive`` and ``options.num_ctx`` are Ollama-only and ignored:
        use an instruct (non-thinking) model."""
        if not self._has_key:
            raise OpenRouterError("OPENROUTER_API_KEY is not set")
        body = self._request_body(model, messages, format, options or {})
        if fallbacks := [m for m in self.fallback_models if m != model]:
            body["models"] = [model, *fallbacks]
        r = self._post(body)
        data = r.json()
        if data.get("error"):  # some provider failures arrive as 200 + error object
            raise OpenRouterError(f"OpenRouter error from {model}: {_error_text(data)}")
        choices = data.get("choices") or []
        if not choices:
            raise OpenRouterError(f"OpenRouter returned no choices for {model}")
        choice = choices[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        finish = choice.get("finish_reason")
        return {
            "model": data.get("model", model),  # the fallback's id when one answered
            "message": {
                "role": "assistant",
                "content": message.get("content") or "",
                "thinking": message.get("reasoning") or "",
            },
            "done": True,
            "done_reason": _DONE_REASON.get(finish, finish),
            "prompt_eval_count": usage.get("prompt_tokens"),
            "eval_count": usage.get("completion_tokens"),
            "usage_cost": usage.get("cost"),
            "provider": data.get("provider"),
        }

    @staticmethod
    def _request_body(model: str, messages: list[dict], format, options: dict) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": [_to_openai_message(m) for m in messages],
            "provider": {"data_collection": "deny", "require_parameters": True},
        }
        if "temperature" in options:
            body["temperature"] = options["temperature"]
        if options.get("num_predict"):
            body["max_tokens"] = options["num_predict"]
        if isinstance(format, dict):
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": re.sub(r"[^A-Za-z0-9_-]", "_", format.get("title") or "response"),
                                "strict": False, "schema": format},
            }
        elif format == "json":
            body["response_format"] = {"type": "json_object"}
        return body

    def _post(self, body: dict) -> httpx.Response:
        model = body["model"]
        for attempt in range(self.retries + 1):
            try:
                r = self._http.post("/chat/completions", json=body)
            except httpx.TimeoutException as e:
                raise OpenRouterError(
                    f"{model} did not answer within {self._http.timeout.read:.0f}s (OPENROUTER_TIMEOUT_S)", 504
                ) from e
            except httpx.HTTPError as e:
                raise OpenRouterError(f"cannot reach OpenRouter at {self.base_url}: {type(e).__name__}") from e
            if r.status_code == 200:
                return r
            if r.status_code in RETRY_STATUSES and attempt < self.retries:
                time.sleep(_retry_after(r))
                continue
            raise OpenRouterError(_status_message(r, model), r.status_code)
        raise AssertionError("unreachable")

    def close(self) -> None:
        self._http.close()


def _to_openai_message(m: dict[str, Any]) -> dict[str, Any]:
    """Ollama message (``content`` str + ``images`` base64 JPEG) → OpenAI content parts."""
    images = m.get("images") or []
    if not images:
        return {"role": m["role"], "content": m.get("content", "")}
    parts: list[dict[str, Any]] = [{"type": "text", "text": m.get("content", "")}]
    parts += [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}} for b64 in images]
    return {"role": m["role"], "content": parts}


def _retry_after(r: httpx.Response) -> float:
    try:
        return min(float(r.headers.get("retry-after", 1)), MAX_RETRY_WAIT_S)
    except ValueError:
        return 1.0


def _error_text(data: dict) -> str:
    err = data.get("error") or {}
    if isinstance(err, dict):
        return f"{err.get('code', '')} {err.get('message', '')}".strip()[:300]
    return str(err)[:300]


def _status_message(r: httpx.Response, model: str) -> str:
    """Never echoes request headers (the API key); the body is OpenRouter's own error text."""
    hint = {
        401: "invalid OPENROUTER_API_KEY",
        402: "OpenRouter credit exhausted",
        403: "request blocked by OpenRouter moderation",
        404: f"no provider for {model} with the requested parameters (data_collection=deny, JSON schema)",
        408: "OpenRouter timed out",
        429: "OpenRouter rate limit",
    }.get(r.status_code, "OpenRouter request failed")
    try:
        detail = _error_text(r.json())
    except ValueError:
        detail = r.text[:200]
    return f"OpenRouter {r.status_code}: {hint}" + (f" ({detail})" if detail else "")
