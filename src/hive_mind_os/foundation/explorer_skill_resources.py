from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

EXPLORER_SKILL_DOCUMENTS: tuple[Mapping[str, Any], ...] = (
    MappingProxyType({
        "activation": "inert",
        "input_schema": "explorer-context-selection-v1",
        "output_schema": "explorer-shadow-run-v1",
        "purpose": "Capture scope-bound evidence while treating repository content as untrusted data.",
        "record_type": "skill-definition",
        "requested_capabilities": ("read_repository",),
        "rollback": "remove the explicit Explorer shadow caller",
        "schema_version": 2,
        "side_effects": (),
        "skill_id": "explorer:evidence-capture",
        "version": "1",
    }),
    MappingProxyType({
        "activation": "inert",
        "input_schema": "explorer-context-selection-v1",
        "output_schema": "explorer-shadow-run-v1",
        "purpose": "Require counterargument, causal mechanism, break point, and falsifiable acceptance evidence.",
        "record_type": "skill-definition",
        "requested_capabilities": (),
        "rollback": "remove the explicit Explorer shadow caller",
        "schema_version": 2,
        "side_effects": (),
        "skill_id": "explorer:counterargument-bridge",
        "version": "1",
    }),
    MappingProxyType({
        "activation": "inert",
        "input_schema": "explorer-context-selection-v1",
        "output_schema": "explorer-shadow-run-v1",
        "purpose": "Stop on declared bounds while preserving omissions, critical coverage, and unknowns.",
        "record_type": "skill-definition",
        "requested_capabilities": (),
        "rollback": "remove the explicit Explorer shadow caller",
        "schema_version": 2,
        "side_effects": (),
        "skill_id": "explorer:honest-stopping",
        "version": "1",
    }),
)

EXPLORER_SKILL_BUNDLE_DIGEST = (
    "sha256:f0c149f6ae3a738cc0324ecb3311e0a3ff93cdfd4923be3709e3c9e5e5b05985"
)
