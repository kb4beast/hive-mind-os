from __future__ import annotations

import json
import re
from hashlib import sha256
from typing import Any, Mapping

_SPACE = re.compile(r"\s+")


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def digest(value: Any) -> str:
    return f"sha256:{sha256(canonical_bytes(value)).hexdigest()}"


def stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}:{sha256(canonical_bytes(value)).hexdigest()}"


def normalize_fingerprint_text(value: str) -> str:
    normalized = _SPACE.sub(" ", value.strip().casefold())
    if not normalized:
        raise ValueError("fingerprint text cannot be empty")
    return normalized


def reject_private_content(document: Mapping[str, Any]) -> None:
    prohibited = {
        "chain_of_thought",
        "context_body",
        "headers",
        "hidden_reasoning",
        "prompt",
        "prompt_body",
        "raw_body",
        "request_body",
        "response",
        "response_body",
        "secret",
        "tool_body",
    }

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key.casefold() in prohibited:
                    raise ValueError(f"private content field is prohibited: {path}.{key}")
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(document, "$")
