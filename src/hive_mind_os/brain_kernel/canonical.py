"""Deterministic, fail-closed JSON encoding for kernel contracts."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from hashlib import sha256
from typing import Any


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _plain(asdict(value))
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def canonical_bytes(value: Any) -> bytes:
    """Return the one UTF-8 JSON representation accepted by the kernel."""

    return json.dumps(
        _plain(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    return f"sha256:{sha256(canonical_bytes(value)).hexdigest()}"


def canonical_document(value: Any) -> dict[str, Any]:
    """Convert a contract to a JSON object, rejecting non-object values."""

    document = _plain(value)
    if not isinstance(document, dict):
        raise ValueError("kernel contract must serialize to a JSON object")
    canonical_bytes(document)
    return document
