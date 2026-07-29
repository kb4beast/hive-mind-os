from __future__ import annotations

from typing import Any, Iterable, Mapping

from hive_mind_os.prompt_registry import generation_zero_prompt, prompt_digest
from hive_mind_os.roles import DEFAULT_LIFECYCLE, ROLE_CONTRACTS

from .canonical import canonical_bytes, digest

GENERATOR_VERSION = "phase2-foundation-generator-v1"


def compile_generation_zero_candidates() -> dict[str, bytes]:
    """Compile inert v2 candidates deterministically from frozen v1 authorities."""

    definitions: dict[str, dict[str, Any]] = {}
    for role in DEFAULT_LIFECYCLE:
        contract = ROLE_CONTRACTS[role]
        prompt = generation_zero_prompt(contract)
        definitions[role.value] = {
            "record_type": "agent-definition",
            "schema_version": 2,
            "agent_id": f"hive-agent:{role.value}:v2-candidate",
            "role_id": role.value,
            "mission": contract.mission,
            "required_outputs": list(contract.required_outputs),
            "requested_capabilities": list(contract.default_capabilities),
            "quality_gates": list(contract.quality_gates),
            "prompt_layers": [
                {
                    "layer_id": f"generation-zero:{role.value}",
                    "version": "1",
                    "digest": prompt_digest(prompt),
                    "trust": "generation-zero",
                    "sensitivity": "internal",
                }
            ],
            "activation": "inert",
            "authority": "none",
        }
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
