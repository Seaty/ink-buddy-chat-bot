"""OpenRouterClient: Ollama-style in → OpenAI-style request → Ollama-shaped response. No network."""

import json

import httpx
import pytest

from app.ai.llm import openrouter_client
from app.ai.llm.errors import LLMError
from app.ai.llm.openrouter_client import OpenRouterClient, OpenRouterError
from app.ai.llm.qwen_vision import QwenVision
from app.core.config import Settings
from app.core.errors import ApiError
from app.services.vision_service import VisionService, _vision_errors

KEY = "sk-or-v1-test-only-not-a-real-key"
SCHEMA = {"title": "OcrResult", "type": "object", "properties": {"segments": {"type": "array"}}}
OK = {
    "id": "gen-1",
    "model": "qwen/qwen3-vl-8b-instruct",
    "provider": "Parasail",
    "choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": '{"segments": []}'}}],
    "usage": {"prompt_tokens": 1066, "completion_tokens": 7, "total_tokens": 1073},
}


def client(*responses, fallback_models=(), retries=1, key=KEY):
    """Client whose transport answers with ``responses`` in order and records requests."""
    seen: list[httpx.Request] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    c = OpenRouterClient(key, "https://openrouter.test/api/v1", 30, retries=retries, fallback_models=fallback_models)
    c._http = httpx.Client(base_url=c.base_url, headers=c._http.headers, timeout=c._http.timeout,
                           transport=httpx.MockTransport(handler))
    return c, seen


def ok(body=OK, status=200, headers=None):
    return httpx.Response(status, json=body, headers=headers)


def sent(request: httpx.Request) -> dict:
    return json.loads(request.content)


# ---------------------------------------------------------------- request
def test_request_translation():
    c, seen = client(ok())
    c.chat("qwen/qwen3-vl-8b-instruct",
           [{"role": "system", "content": "be brief"},
            {"role": "user", "content": "read the text", "images": ["AAAA", "BBBB"]}],
           format=SCHEMA, options={"temperature": 0.0, "num_predict": 2048, "num_ctx": 16384},
           think=False, keep_alive="30m")
    req = seen[0]
    body = sent(req)
    assert req.url.path == "/api/v1/chat/completions"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert body["model"] == "qwen/qwen3-vl-8b-instruct"
    assert body["messages"][0] == {"role": "system", "content": "be brief"}
    assert body["messages"][1]["content"] == [
        {"type": "text", "text": "read the text"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA"}},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,BBBB"}},
    ]
    assert body["temperature"] == 0.0 and body["max_tokens"] == 2048
    assert body["response_format"] == {
        "type": "json_schema", "json_schema": {"name": "OcrResult", "strict": False, "schema": SCHEMA}}
    # privacy and no silent schema drop
    assert body["provider"] == {"data_collection": "deny", "require_parameters": True}
    # Ollama-only knobs are not sent
    assert not {"num_ctx", "keep_alive", "think", "options", "images", "models"} & set(body)


def test_json_mode_and_no_format():
    c, seen = client(ok(), ok())
    c.chat("m", [{"role": "user", "content": "x"}], format="json")
    c.chat("m", [{"role": "user", "content": "x"}])
    assert sent(seen[0])["response_format"] == {"type": "json_object"}
    assert "response_format" not in sent(seen[1])


def test_fallback_models_listed_after_requested_model():
    c, seen = client(ok(), fallback_models=["qwen/qwen3-vl-30b-a3b-instruct", "qwen/qwen3-vl-8b-instruct"])
    c.chat("qwen/qwen3-vl-8b-instruct", [{"role": "user", "content": "x"}])
    assert sent(seen[0])["models"] == ["qwen/qwen3-vl-8b-instruct", "qwen/qwen3-vl-30b-a3b-instruct"]


# ---------------------------------------------------------------- response
def test_response_is_ollama_shaped():
    c, _ = client(ok({**OK, "model": "qwen/qwen3-vl-30b-a3b-instruct", "choices": [
        {"finish_reason": "length", "message": {"content": "partial", "reasoning": "hmm"}}]}))
    r = c.chat("qwen/qwen3-vl-8b-instruct", [{"role": "user", "content": "x"}])
    assert r["message"] == {"role": "assistant", "content": "partial", "thinking": "hmm"}
    assert r["done_reason"] == "length"
    assert r["prompt_eval_count"] == 1066 and r["eval_count"] == 7
    assert r["model"] == "qwen/qwen3-vl-30b-a3b-instruct"  # which model actually answered


def test_null_content_becomes_empty_string():
    c, _ = client(ok({**OK, "choices": [{"finish_reason": "stop", "message": {"content": None}}]}))
    assert c.chat("m", [{"role": "user", "content": "x"}])["message"]["content"] == ""


def test_works_inside_qwen_vision():
    c, _ = client(ok())
    vision = QwenVision(client=c, model="qwen/qwen3-vl-8b-instruct")
    from PIL import Image
    assert vision.ocr(Image.new("RGB", (64, 64), "white")) == []


# ---------------------------------------------------------------- errors
def test_error_in_200_body():
    c, _ = client(ok({"error": {"code": 502, "message": "upstream died"}}))
    with pytest.raises(OpenRouterError, match="upstream died"):
        c.chat("m", [{"role": "user", "content": "x"}])


def test_no_choices():
    c, _ = client(ok({"id": "x", "choices": []}))
    with pytest.raises(OpenRouterError, match="no choices"):
        c.chat("m", [{"role": "user", "content": "x"}])


def test_retries_rate_limit_once(monkeypatch):
    waits = []
    monkeypatch.setattr(openrouter_client.time, "sleep", waits.append)
    c, seen = client(ok({"error": {"code": 429, "message": "slow down"}}, 429, {"retry-after": "30"}), ok())
    assert c.chat("m", [{"role": "user", "content": "x"}])["done_reason"] == "stop"
    assert len(seen) == 2
    assert waits == [openrouter_client.MAX_RETRY_WAIT_S]  # Retry-After capped


def test_gives_up_after_retries(monkeypatch):
    monkeypatch.setattr(openrouter_client.time, "sleep", lambda s: None)
    c, seen = client(ok({}, 503), ok({}, 503))
    with pytest.raises(OpenRouterError, match="503"):
        c.chat("m", [{"role": "user", "content": "x"}])
    assert len(seen) == 2


@pytest.mark.parametrize("status,hint", [(401, "invalid OPENROUTER_API_KEY"), (402, "credit exhausted")])
def test_client_errors_are_not_retried_and_hide_key(status, hint):
    c, seen = client(ok({"error": {"code": status, "message": "nope"}}, status))
    with pytest.raises(OpenRouterError) as e:
        c.chat("m", [{"role": "user", "content": "x"}])
    assert hint in str(e.value) and KEY not in str(e.value)
    assert len(seen) == 1


def test_timeout_and_unreachable():
    c, _ = client(httpx.ReadTimeout("slow"), httpx.ConnectError("refused"))
    with pytest.raises(OpenRouterError, match="did not answer within 30s"):
        c.chat("m", [{"role": "user", "content": "x"}])
    with pytest.raises(OpenRouterError, match="cannot reach OpenRouter"):
        c.chat("m", [{"role": "user", "content": "x"}])


def test_missing_key_fails_without_request():
    c, seen = client(key=None)
    with pytest.raises(OpenRouterError, match="OPENROUTER_API_KEY"):
        c.chat("m", [{"role": "user", "content": "x"}])
    assert seen == []


def test_errors_share_the_llm_base():
    assert issubclass(OpenRouterError, LLMError)


# ---------------------------------------------------------------- service wiring
def test_service_picks_client_by_provider():
    s = Settings(vision_provider="openrouter", openrouter_api_key=KEY,
                 openrouter_fallback_models=["qwen/qwen3-vl-30b-a3b-instruct"])
    c = VisionService(s, pipeline=object())._llm_client()
    assert isinstance(c, OpenRouterClient) and c.fallback_models == ["qwen/qwen3-vl-30b-a3b-instruct"]
    from app.ai.llm.ollama_client import OllamaClient
    assert isinstance(VisionService(Settings(vision_provider="ollama"), pipeline=object())._llm_client(), OllamaClient)


def test_provider_failure_is_503():
    with pytest.raises(ApiError) as e:
        with _vision_errors():
            raise OpenRouterError("OpenRouter 402: OpenRouter credit exhausted")
    assert e.value.status == 503 and e.value.code == "VISION_UNAVAILABLE"
