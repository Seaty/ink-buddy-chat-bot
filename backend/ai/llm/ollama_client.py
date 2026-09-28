"""Minimal Ollama HTTP client: connection, timeout, model call.

Talks to /api/chat directly (not LangChain) so callers get the full response,
including the separate ``thinking`` field and ``done_reason``.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://localhost:11434"
# qwen3-vl:latest thinks before answering (~2 min per image call on an RTX 3050).
DEFAULT_TIMEOUT_S = 300.0


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str | None = None, timeout_s: float | None = None):
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        timeout = timeout_s or float(os.getenv("OLLAMA_TIMEOUT_S", DEFAULT_TIMEOUT_S))
        self._http = httpx.Client(base_url=self.base_url, timeout=httpx.Timeout(timeout, connect=5.0))

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
        """Non-streaming /api/chat. Messages may carry ``images`` (base64 strings)."""
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if format is not None:
            body["format"] = format
        if options:
            body["options"] = options
        if think is not None:
            body["think"] = think
        if keep_alive is not None:
            body["keep_alive"] = keep_alive
        try:
            r = self._http.post("/api/chat", json=body)
        except httpx.TimeoutException as e:
            raise OllamaError(
                f"{model} did not answer within {self._http.timeout.read:.0f}s "
                "(thinking models are slow; raise OLLAMA_TIMEOUT_S or use an instruct model)"
            ) from e
        except httpx.HTTPError as e:
            raise OllamaError(f"cannot reach Ollama at {self.base_url}: {e}") from e
        if r.status_code != 200:
            raise OllamaError(f"Ollama {r.status_code}: {r.text[:300]}")
        return r.json()

    def close(self) -> None:
        self._http.close()
