from __future__ import annotations

import json
import os
import unittest
from collections.abc import Mapping
from unittest.mock import patch

from hive_mind_os.model_provider import (
    MAX_HTTP_RESPONSE_BYTES,
    AnthropicProvider,
    HttpTransport,
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

    def post(self, url, headers, body, timeout_s):
        self.calls.append((url, headers, body, timeout_s))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def config(kind: ProviderKind, retries: int = 2) -> ProviderConfig:
    return ProviderConfig(
        kind,
        "https://models.example/v1",
        "test-model",
        "TEST_MODEL_KEY",
        max_retries=retries,
    )


class ModelProviderTests(unittest.TestCase):
    def test_provider_config_rejects_plaintext_or_ambiguous_urls(self) -> None:
        for base_url in (
            "http://attacker.example/v1",
            "ftp://models.example/v1",
            "https://user:secret@models.example/v1",
            "https://models.example/v1?redirect=attacker",
        ):
            with self.subTest(base_url=base_url):
                with self.assertRaises(ValueError):
                    ProviderConfig(
                        ProviderKind.OPENAI_COMPATIBLE,
                        base_url,
                        "test-model",
                        "TEST_MODEL_KEY",
                    )

    def test_http_transport_caps_response_bytes_before_parsing(self) -> None:
        class OversizedResponse:
            headers = {"Content-Length": str(MAX_HTTP_RESPONSE_BYTES + 1)}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self, _size: int) -> bytes:
                self.fail("transport should reject Content-Length before reading")

            def fail(self, message: str) -> None:
                raise AssertionError(message)

        with patch("urllib.request.urlopen", return_value=OversizedResponse()):
            with self.assertRaisesRegex(ModelTransportError, "byte limit"):
                HttpTransport().post(
                    "https://models.example/v1/chat/completions",
                    {"Authorization": "Bearer sentinel-secret"},
                    b"{}",
                    1.0,
                )

    def test_openai_compatible_request_and_response(self) -> None:
        raw = json.dumps(
            {
                "choices": [{"message": {"content": '{"success":true}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            }
        ).encode()
        transport = FakeTransport([raw])
        provider = OpenAICompatibleProvider(
            config(ProviderKind.OPENAI_COMPATIBLE), transport
        )
        with patch.dict(os.environ, {"TEST_MODEL_KEY": "sentinel-secret"}):
            response = provider.complete(ModelRequest("system", "user"))
        body = json.loads(transport.calls[0][2])
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(response.content, '{"success":true}')
        self.assertEqual((response.prompt_tokens, response.completion_tokens), (12, 4))

    def test_anthropic_request_and_response(self) -> None:
        raw = json.dumps(
            {
                "content": [{"type": "text", "text": '{"success":true}'}],
                "usage": {"input_tokens": 9, "output_tokens": 3},
            }
        ).encode()
        transport = FakeTransport([raw])
        provider = AnthropicProvider(config(ProviderKind.ANTHROPIC), transport)
        with patch.dict(os.environ, {"TEST_MODEL_KEY": "sentinel-secret"}):
            response = provider.complete(ModelRequest("system", "user", "correct JSON"))
        body = json.loads(transport.calls[0][2])
        self.assertIn("correct JSON", body["messages"][0]["content"])
        self.assertEqual((response.prompt_tokens, response.completion_tokens), (9, 3))

    def test_missing_key_fails_before_transport(self) -> None:
        transport = FakeTransport([])
        provider = OpenAICompatibleProvider(
            config(ProviderKind.OPENAI_COMPATIBLE), transport
        )
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MissingModelCredential):
                provider.complete(ModelRequest("system", "user"))
        self.assertEqual(transport.calls, [])

    def test_api_key_redaction_and_no_body_leak(self) -> None:
        secret = "sentinel-never-log-key"
        transport = FakeTransport([TimeoutError(secret)] * 2)
        provider = OpenAICompatibleProvider(
            config(ProviderKind.OPENAI_COMPATIBLE, 1), transport
        )
        with patch.dict(os.environ, {"TEST_MODEL_KEY": secret}):
            with self.assertRaises(ModelTransportError) as captured:
                provider.complete(ModelRequest("system", "user"))
        self.assertNotIn(secret, str(captured.exception))
        self.assertTrue(all(secret.encode() not in call[2] for call in transport.calls))

    def test_transport_timeout_retries_are_bounded(self) -> None:
        transport = FakeTransport([TimeoutError("slow")] * 3)
        provider = OpenAICompatibleProvider(
            config(ProviderKind.OPENAI_COMPATIBLE, 2), transport
        )
        with patch.dict(os.environ, {"TEST_MODEL_KEY": "key"}):
            with self.assertRaisesRegex(ModelTransportError, "after 3 attempts"):
                provider.complete(ModelRequest("system", "user"))
        self.assertEqual(len(transport.calls), 3)


if __name__ == "__main__":
    unittest.main()
