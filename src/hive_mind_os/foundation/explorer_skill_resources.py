from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

_DOCUMENTS = (
    {
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
    },
    {
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
    },
    {
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
    },
)

EXPLORER_SKILL_DOCUMENTS: tuple[Mapping[str, Any], ...] = tuple(
    MappingProxyType(document) for document in _DOCUMENTS
)
