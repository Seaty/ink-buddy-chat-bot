"""Errors shared by the model clients (Ollama, OpenRouter)."""


class LLMError(RuntimeError):
    """The model provider could not produce an answer (unreachable, timeout, rejected, out of credit)."""
