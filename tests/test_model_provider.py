from __future__ import annotations

import io
import json
import os
import subprocess
import unittest
import urllib.error
from collections.abc import Mapping
from pathlib import Path
from unittest.mock import patch

from hive_mind_os.model_provider import (
    MAX_HTTP_RESPONSE_BYTES,
    SUBSCRIPTION_BASE_URL,
    SUBSCRIPTION_DEFAULT_MODEL,
    AnthropicProvider,
    CodexSubscriptionProvider,
    HttpTransport,
    MissingModelCredential,
    ModelRequest,
    ModelTransportError,
    OpenAICompatibleProvider,
    ProviderConfig,
    ProviderKind,
    provider_from_env,
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
        kind, "https://models.example/v1", "test-model", "TEST_MODEL_KEY",
        max_retries=retries,
    )


class ModelProviderTests(unittest.TestCase):
    def test_provider_config_rejects_plaintext_or_ambiguous_urls(self) -> None:
        for base_url in (
            "http://attacker.example/v1",
            "ftp://models.example/v1",
            "https://user:secret@models.example/v1",
            "https://models.example/v1?redirect=attacker",
            "https://models.example/v1#fragment",
        ):
            with self.subTest(base_url=base_url):
                with self.assertRaises(ValueError):
                    ProviderConfig(
                        ProviderKind.OPENAI_COMPATIBLE,
                        base_url,
                        "test-model",
                        "TEST_MODEL_KEY",
                    )

    def test_http_transport_caps_response_bytes_before_reading(self) -> None:
        class OversizedResponse:
            headers = {"Content-Length": str(MAX_HTTP_RESPONSE_BYTES + 1)}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self, _size: int) -> bytes:
                self.fail("transport should reject Content-Length before reading")
                return b""

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

    def test_http_error_body_is_capped_before_parsing(self) -> None:
        error = urllib.error.HTTPError(
            "https://models.example/v1/chat/completions",
            413,
            "Payload Too Large",
            {},
            io.BytesIO(b"x" * (MAX_HTTP_RESPONSE_BYTES + 1)),
        )
        provider = OpenAICompatibleProvider(
            config(ProviderKind.OPENAI_COMPATIBLE, retries=0),
            FakeTransport([error]),
        )
        with patch.dict(os.environ, {"TEST_MODEL_KEY": "sentinel-secret"}):
            with self.assertRaisesRegex(ModelTransportError, "byte limit"):
                provider.complete(ModelRequest("system", "user"))

    def test_openai_compatible_request_and_response(self) -> None:
        raw = json.dumps({
            "choices": [{"message": {"content": "{\"success\":true}"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        }).encode()
        transport = FakeTransport([raw])
        provider = OpenAICompatibleProvider(config(ProviderKind.OPENAI_COMPATIBLE), transport)
        with patch.dict(os.environ, {"TEST_MODEL_KEY": "sentinel-secret"}):
            response = provider.complete(ModelRequest("system", "user"))
        body = json.loads(transport.calls[0][2])
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(response.content, '{"success":true}')
        self.assertEqual((response.prompt_tokens, response.completion_tokens), (12, 4))

    def test_anthropic_request_and_response(self) -> None:
        raw = json.dumps({
            "content": [{"type": "text", "text": "{\"success\":true}"}],
            "usage": {"input_tokens": 9, "output_tokens": 3},
        }).encode()
        transport = FakeTransport([raw])
        provider = AnthropicProvider(config(ProviderKind.ANTHROPIC), transport)
        with patch.dict(os.environ, {"TEST_MODEL_KEY": "sentinel-secret"}):
            response = provider.complete(ModelRequest("system", "user", "correct JSON"))
        body = json.loads(transport.calls[0][2])
        self.assertIn("correct JSON", body["messages"][0]["content"])
        self.assertEqual((response.prompt_tokens, response.completion_tokens), (9, 3))

    def test_missing_key_fails_before_transport(self) -> None:
        transport = FakeTransport([])
        provider = OpenAICompatibleProvider(config(ProviderKind.OPENAI_COMPATIBLE), transport)
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

    def test_subscription_provider_uses_a_scrubbed_read_only_ephemeral_codex_command(self) -> None:
        observed: dict[str, object] = {}

        def runner(command, workspace, environment, timeout_s):
            observed["command"] = command
            observed["workspace"] = workspace
            observed["environment"] = environment
            observed["timeout_s"] = timeout_s
            response = command[command.index("--output-last-message") + 1]
            Path(response).write_text(
                '{"model_turn_json":"{\\"success\\":true}"}', encoding="utf-8"
            )
            return subprocess.CompletedProcess(command, 0, b"unretained", b"unretained")

        config = ProviderConfig(
            ProviderKind.CODEX_SUBSCRIPTION,
            SUBSCRIPTION_BASE_URL,
            SUBSCRIPTION_DEFAULT_MODEL,
            "",
            timeout_s=12.5,
        )
        provider = CodexSubscriptionProvider(config, command_runner=runner)
        with patch("hive_mind_os.model_provider.shutil.which", return_value="codex"):
            with patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "must-not-reach-subprocess",
                    "OPENAI_ACCESS_KEY": "must-not-reach-subprocess",
                    "ANTHROPIC_API_KEY": "must-not-reach-subprocess",
                    "CODEX_API_KEY": "must-not-reach-subprocess",
                    "GITHUB_TOKEN": "must-not-reach-subprocess",
                    "MODEL_SECRET": "must-not-reach-subprocess",
                    "SAFE_VALUE": "preserved",
                },
                clear=True,
            ):
                response = provider.complete_once(
                    ModelRequest(
                        "outputs must contain exactly these keys: result. Quality gates: pass",
                        "user",
                    )
                )
        command = observed["command"]
        environment = observed["environment"]
        self.assertEqual(response.content, '{"success":true}')
        self.assertEqual(
            response.raw_body, b'{"model_turn_json":"{\\"success\\":true}"}'
        )
        self.assertEqual(provider.credential_reference, "chatgpt-subscription-session")
        self.assertIn("--sandbox", command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertIn("--ephemeral", command)
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--skip-git-repo-check", command)
        self.assertIn("INPUT_JSON.system is the trusted role contract", command[-1])
        self.assertIn('["result"]', command[-1])
        self.assertNotIn("--model", command)
        self.assertEqual(environment["SAFE_VALUE"], "preserved")
        for name in (
            "OPENAI_API_KEY",
            "OPENAI_ACCESS_KEY",
            "ANTHROPIC_API_KEY",
            "CODEX_API_KEY",
            "GITHUB_TOKEN",
            "MODEL_SECRET",
        ):
            self.assertNotIn(name, environment)

    def test_subscription_provider_fails_closed_for_missing_output_or_api_key_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "without an API-key environment"):
            ProviderConfig(
                ProviderKind.CODEX_SUBSCRIPTION,
                SUBSCRIPTION_BASE_URL,
                SUBSCRIPTION_DEFAULT_MODEL,
                "OPENAI_API_KEY",
            )

        def runner(command, _workspace, _environment, _timeout_s):
            return subprocess.CompletedProcess(command, 0, b"", b"")

        provider = CodexSubscriptionProvider(
            ProviderConfig(
                ProviderKind.CODEX_SUBSCRIPTION,
                SUBSCRIPTION_BASE_URL,
                SUBSCRIPTION_DEFAULT_MODEL,
                "",
            ),
            command_runner=runner,
        )
        with patch("hive_mind_os.model_provider.shutil.which", return_value="codex"):
            with self.assertRaisesRegex(ModelTransportError, "did not produce a response"):
                provider.complete_once(ModelRequest("system", "user"))

    def test_subscription_provider_factory_needs_no_api_key_or_model_id(self) -> None:
        with patch.dict(
            os.environ,
            {"HIVE_MIND_MODEL_PROVIDER": "codex_subscription"},
            clear=True,
        ):
            provider = provider_from_env()
        self.assertIsInstance(provider, CodexSubscriptionProvider)
        self.assertEqual(provider.config.base_url, SUBSCRIPTION_BASE_URL)
        self.assertEqual(provider.config.model, SUBSCRIPTION_DEFAULT_MODEL)


if __name__ == "__main__":
    unittest.main()
