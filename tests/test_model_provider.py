from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from hive_mind_os.model_provider import (
    AnthropicProvider,
    MissingModelCredential,
    ModelRequest,
    ModelTransportError,
    OpenAICompatibleProvider,
    ProviderConfig,
    ProviderKind,
)


class FakeTransport:
    def __init__(self, responses: list[bytes | BaseException]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, Mapping[str, str], bytes, float]] = []

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_s: float,
    ) -> bytes:
        self.calls.append((url, headers, body, timeout_s))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def config(kind: ProviderKind, *, retries: int = 2) -> ProviderConfig:
    return ProviderConfig(
        kind=kind,
        base_url="https://models.example/v1",
        model="test-model",
        api_key_env="TEST_MODEL_KEY",
        max_retries=retries,
    )


def test_openai_compatible_request_and_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_MODEL_KEY", "sentinel-secret")
    raw = json.dumps(
        {
            "choices": [{"message": {"content": "{\"success\":true}"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        }
    ).encode()
    transport = FakeTransport([raw])
    provider = OpenAICompatibleProvider(
        config(ProviderKind.OPENAI_COMPATIBLE), transport
    )
    response = provider.complete(ModelRequest("system", "user"))
    body = json.loads(transport.calls[0][2])
    assert body["model"] == "test-model"
    assert body["response_format"] == {"type": "json_object"}
    assert response.content == '{"success":true}'
    assert (response.prompt_tokens, response.completion_tokens) == (12, 4)


def test_anthropic_request_and_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_MODEL_KEY", "sentinel-secret")
    raw = json.dumps(
        {
            "content": [{"type": "text", "text": "{\"success\":true}"}],
            "usage": {"input_tokens": 9, "output_tokens": 3},
        }
    ).encode()
    transport = FakeTransport([raw])
    provider = AnthropicProvider(config(ProviderKind.ANTHROPIC), transport)
    response = provider.complete(ModelRequest("system", "user", "correct JSON"))
    body = json.loads(transport.calls[0][2])
    assert body["system"] == "system"
    assert "correct JSON" in body["messages"][0]["content"]
    assert (response.prompt_tokens, response.completion_tokens) == (9, 3)


def test_missing_key_fails_before_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_MODEL_KEY", raising=False)
    transport = FakeTransport([])
    provider = OpenAICompatibleProvider(
        config(ProviderKind.OPENAI_COMPATIBLE), transport
    )
    with pytest.raises(MissingModelCredential, match="TEST_MODEL_KEY"):
        provider.complete(ModelRequest("system", "user"))
    assert transport.calls == []


def test_api_key_does_not_leak_in_errors_or_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sentinel-never-log-key"
    monkeypatch.setenv("TEST_MODEL_KEY", secret)
    transport = FakeTransport([TimeoutError(secret)] * 2)
    provider = OpenAICompatibleProvider(
        config(ProviderKind.OPENAI_COMPATIBLE, retries=1), transport
    )
    with pytest.raises(ModelTransportError) as captured:
        provider.complete(ModelRequest("system", "user"))
    assert secret not in str(captured.value)
    assert all(secret.encode() not in call[2] for call in transport.calls)


def test_transport_timeout_retries_are_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_MODEL_KEY", "key")
    transport = FakeTransport([TimeoutError("slow")] * 3)
    provider = OpenAICompatibleProvider(
        config(ProviderKind.OPENAI_COMPATIBLE, retries=2), transport
    )
    with pytest.raises(ModelTransportError, match="after 3 attempts"):
        provider.complete(ModelRequest("system", "user"))
    assert len(transport.calls) == 3
