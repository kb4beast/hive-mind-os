from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, Iterable, Mapping

from hive_mind_os.prompt_registry import generation_zero_prompt, prompt_digest
from hive_mind_os.roles import DEFAULT_LIFECYCLE, ROLE_CONTRACTS

from .canonical import canonical_bytes, digest

GENERATOR_VERSION = "phase2-foundation-generator-v1"


def compile_generation_zero_candidates() -> dict[str, bytes]:
    """Compile inert candidates from versioned canonical Phase 2 source."""

    definitions = _load_canonical_definitions()
    source = {
        "generator_version": GENERATOR_VERSION,
        "lifecycle": [role.value for role in DEFAULT_LIFECYCLE],
        "definitions": definitions,
    }
    source_digest = digest(source)
    outputs: dict[str, bytes] = {
        f"agents/{role}.json": canonical_bytes(document)
        for role, document in sorted(definitions.items())
    }
    manifest = {
        "record_type": "prompt-composition",
        "schema_version": 2,
        "generator_version": GENERATOR_VERSION,
        "source_digest": source_digest,
        "outputs": [
            {"path": path, "digest": digest_bytes(content)}
            for path, content in sorted(outputs.items())
        ],
        "activation": "inert",
    }
    outputs["manifest.json"] = canonical_bytes(manifest)
    return outputs


def _load_canonical_definitions() -> dict[str, dict[str, Any]]:
    root = files("hive_mind_os.foundation").joinpath("canonical", "agents")
    definitions: dict[str, dict[str, Any]] = {}
    for resource in sorted(root.iterdir(), key=lambda item: item.name):
        if not resource.name.endswith(".json"):
            continue
        document = json.loads(resource.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"canonical agent source is not an object: {resource.name}")
        role_id = document.get("role_id")
        if not isinstance(role_id, str) or resource.name != f"{role_id}.json":
            raise ValueError(f"canonical agent source identity mismatch: {resource.name}")
        definitions[role_id] = document
    expected_roles = [role.value for role in DEFAULT_LIFECYCLE]
    if sorted(definitions) != sorted(expected_roles):
        raise ValueError("canonical agent source does not cover the frozen lifecycle")
    for role in DEFAULT_LIFECYCLE:
        prompt_layers = definitions[role.value].get("prompt_layers")
        expected_prompt_digest = prompt_digest(
            generation_zero_prompt(ROLE_CONTRACTS[role])
        )
        if (
            not isinstance(prompt_layers, list)
            or len(prompt_layers) != 1
            or not isinstance(prompt_layers[0], dict)
            or prompt_layers[0].get("digest") != expected_prompt_digest
        ):
            raise ValueError(
                f"canonical agent source drifted from Generation Zero prompt: "
                f"{role.value}"
            )
    return definitions


def digest_bytes(content: bytes) -> str:
    from hashlib import sha256

    return f"sha256:{sha256(content).hexdigest()}"


def verify_generated_candidates(
    observed: Mapping[str, bytes],
    *,
    expected_paths: Iterable[str] | None = None,
) -> tuple[str, ...]:
    expected = compile_generation_zero_candidates()
    issues: list[str] = []
    paths = set(expected_paths) if expected_paths is not None else set(expected)
    for path in sorted(paths | set(observed) | set(expected)):
        if path not in expected:
            issues.append(f"unexpected generated artifact: {path}")
        elif path not in observed:
            issues.append(f"missing generated artifact: {path}")
        elif observed[path] != expected[path]:
            issues.append(f"generated artifact drift: {path}")
    return tuple(issues)
