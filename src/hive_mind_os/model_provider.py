"""Provider-neutral, stdlib-only model transports.

HTTP response bodies are returned to the backend for digesting but are never logged here.
Credential values are read only at request time and are redacted from outward exceptions.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Iterable, Mapping, Protocol


class ProviderKind(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"


class ModelProviderError(RuntimeError):
    """Base error for provider configuration, transport, and response failures."""


class MissingModelCredential(ModelProviderError):
    """Raised before transport when the configured credential is absent."""


class ModelTransportError(ModelProviderError):
    """Raised after bounded transport attempts fail."""


class ModelResponseError(ModelProviderError):
    """Raised when a provider response cannot be interpreted."""

    def __init__(self, message: str, raw_body: bytes) -> None:
        super().__init__(message)
        self.raw_body = raw_body


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    kind: ProviderKind
    base_url: str
    model: str
    api_key_env: str
    timeout_s: float = 60.0
    max_output_tokens: int = 2048
    temperature: float = 0.0
    max_retries: int = 2

    def __post_init__(self) -> None:
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("model base URL must use http or https")
        if not self.model.strip() or not self.api_key_env.strip():
            raise ValueError("model and API-key environment name are required")
        if self.timeout_s <= 0 or self.max_output_tokens < 1 or self.max_retries < 0:
            raise ValueError("model timeout/tokens/retries are out of range")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("model temperature must be between 0 and 2")


@dataclass(frozen=True, slots=True)
class ModelRequest:
    system: str
    user: str
    corrective_message: str | None = None


@dataclass(frozen=True, slots=True)
class ModelResponse:
    content: str
    raw_body: bytes
    prompt_tokens: int | None
    completion_tokens: int | None
    transport_retry_index: int = 0


class TransportProtocol(Protocol):
    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_s: float,
    ) -> bytes: ...


class HttpTransport:
    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_s: float,
    ) -> bytes:
        request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return response.read()


class ModelProvider(Protocol):
    config: ProviderConfig
    kind: ProviderKind

    def build_request_body(self, request: ModelRequest) -> bytes: ...

    def complete_once(self, request: ModelRequest) -> ModelResponse: ...

    def complete(self, request: ModelRequest) -> ModelResponse: ...


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _read_api_key(config: ProviderConfig) -> str:
    value = os.environ.get(config.api_key_env, "")
    if not value:
        raise MissingModelCredential(
            f"required model credential environment variable is missing: {config.api_key_env}"
        )
    return value


def _decode_object(raw: bytes, secret: str) -> dict[str, object]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ModelResponseError(
            redact(f"provider returned invalid UTF-8 JSON: {error}", (secret,)),
            raw,
        ) from None
    if not isinstance(value, dict):
        raise ModelResponseError("provider response must be a JSON object", raw)
    return value


def _optional_int(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


class _BaseProvider:
    kind: ProviderKind

    def __init__(
        self,
        config: ProviderConfig,
        transport: TransportProtocol | None = None,
    ) -> None:
        if config.kind is not self.kind:
            raise ValueError(f"provider kind mismatch: expected {self.kind.value}")
        self.config = config
        self.transport = transport or HttpTransport()

    @property
    def endpoint(self) -> str:
        raise NotImplementedError

    def _headers(self, api_key: str) -> Mapping[str, str]:
        raise NotImplementedError

    def _parse(self, raw: bytes, api_key: str, retry_index: int) -> ModelResponse:
        raise NotImplementedError

    def build_request_body(self, request: ModelRequest) -> bytes:
        raise NotImplementedError

    def complete_once(self, request: ModelRequest) -> ModelResponse:
        api_key = _read_api_key(self.config)
        body = self.build_request_body(request)
        try:
            raw = self.transport.post(
                self.endpoint,
                self._headers(api_key),
                body,
                self.config.timeout_s,
            )
        except (TimeoutError, OSError, urllib.error.URLError) as error:
            message = redact(
                f"model transport failed: {type(error).__name__}: {error}",
                (api_key,),
            )
            raise ModelTransportError(message) from None
        return self._parse(raw, api_key, 0)

    def complete(self, request: ModelRequest) -> ModelResponse:
        last_error: BaseException | None = None
        for retry_index in range(self.config.max_retries + 1):
            try:
                return replace(
                    self.complete_once(request),
                    transport_retry_index=retry_index,
                )
            except ModelTransportError as error:
                last_error = error
        message = (
            f"model transport failed after {self.config.max_retries + 1} attempts: "
            f"{last_error}"
        )
        raise ModelTransportError(message) from None


class OpenAICompatibleProvider(_BaseProvider):
    kind = ProviderKind.OPENAI_COMPATIBLE

    @property
    def endpoint(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/chat/completions"

    def _headers(self, api_key: str) -> Mapping[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def build_request_body(self, request: ModelRequest) -> bytes:
        messages = [
            {"role": "system", "content": request.system},
            {"role": "user", "content": request.user},
        ]
        if request.corrective_message:
            messages.append({"role": "user", "content": request.corrective_message})
        payload = {
            "max_tokens": self.config.max_output_tokens,
            "messages": messages,
            "model": self.config.model,
            "response_format": {"type": "json_object"},
            "temperature": self.config.temperature,
        }
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def _parse(self, raw: bytes, api_key: str, retry_index: int) -> ModelResponse:
        value = _decode_object(raw, api_key)
        try:
            choices = value["choices"]
            first = choices[0]  # type: ignore[index]
            content = first["message"]["content"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError):
            raise ModelResponseError(
                "OpenAI-compatible response lacks message content", raw
            ) from None
        if not isinstance(content, str):
            raise ModelResponseError(
                "OpenAI-compatible message content must be a string", raw
            )
        usage = value.get("usage")
        usage_map = usage if isinstance(usage, dict) else {}
        return ModelResponse(
            content,
            raw,
            _optional_int(usage_map.get("prompt_tokens")),
            _optional_int(usage_map.get("completion_tokens")),
            retry_index,
        )


class AnthropicProvider(_BaseProvider):
    kind = ProviderKind.ANTHROPIC

    @property
    def endpoint(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/messages"

    def _headers(self, api_key: str) -> Mapping[str, str]:
        return {
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "x-api-key": api_key,
        }

    def build_request_body(self, request: ModelRequest) -> bytes:
        user_content = request.user
        if request.corrective_message:
            user_content += f"\n\n{request.corrective_message}"
        payload = {
            "max_tokens": self.config.max_output_tokens,
            "messages": [{"role": "user", "content": user_content}],
            "model": self.config.model,
            "system": request.system,
            "temperature": self.config.temperature,
        }
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def _parse(self, raw: bytes, api_key: str, retry_index: int) -> ModelResponse:
        value = _decode_object(raw, api_key)
        try:
            blocks = value["content"]
            content = blocks[0]["text"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError):
            raise ModelResponseError("Anthropic response lacks text content", raw) from None
        if not isinstance(content, str):
            raise ModelResponseError("Anthropic text content must be a string", raw)
        usage = value.get("usage")
        usage_map = usage if isinstance(usage, dict) else {}
        return ModelResponse(
            content,
            raw,
            _optional_int(usage_map.get("input_tokens")),
            _optional_int(usage_map.get("output_tokens")),
            retry_index,
        )


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return default if raw is None else int(raw)
    except ValueError:
        raise ModelProviderError(f"{name} must be an integer") from None


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return default if raw is None else float(raw)
    except ValueError:
        raise ModelProviderError(f"{name} must be numeric") from None


def provider_from_env(
    transport: TransportProtocol | None = None,
) -> OpenAICompatibleProvider | AnthropicProvider:
    raw_kind = os.environ.get("HIVE_MIND_MODEL_PROVIDER", "openai_compatible")
    try:
        kind = ProviderKind(raw_kind)
    except ValueError:
        raise ModelProviderError(
            "HIVE_MIND_MODEL_PROVIDER must be openai_compatible or anthropic"
        ) from None
    defaults = {
        ProviderKind.OPENAI_COMPATIBLE: (
            "https://api.openai.com/v1",
            "OPENAI_API_KEY",
        ),
        ProviderKind.ANTHROPIC: ("https://api.anthropic.com/v1", "ANTHROPIC_API_KEY"),
    }
    default_url, default_key_env = defaults[kind]
    config = ProviderConfig(
        kind=kind,
        base_url=os.environ.get("HIVE_MIND_MODEL_BASE_URL", default_url),
        model=os.environ.get("HIVE_MIND_MODEL_ID", "").strip(),
        api_key_env=os.environ.get("HIVE_MIND_MODEL_API_KEY_ENV", default_key_env),
        timeout_s=_env_float("HIVE_MIND_MODEL_TIMEOUT_S", 60.0),
        max_output_tokens=_env_int("HIVE_MIND_MODEL_MAX_OUTPUT_TOKENS", 2048),
        temperature=_env_float("HIVE_MIND_MODEL_TEMPERATURE", 0.0),
        max_retries=_env_int("HIVE_MIND_MODEL_MAX_RETRIES", 2),
    )
    _read_api_key(config)
    if kind is ProviderKind.OPENAI_COMPATIBLE:
        return OpenAICompatibleProvider(config, transport)
    return AnthropicProvider(config, transport)
