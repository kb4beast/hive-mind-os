from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from dataclasses import fields
from importlib.resources import files
from pathlib import Path

import hive_mind_os
from hive_mind_os.contracts import validate_schema_catalog
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.mission_store import STORE_SCHEMA_VERSION, MissionStore
from hive_mind_os.model_backend import ModelBackend
from hive_mind_os.model_provider import (
    AnthropicProvider,
    ModelResponse,
    OpenAICompatibleProvider,
    ProviderConfig,
    ProviderKind,
)
from hive_mind_os.models import Objective, Role, WorkItem
from hive_mind_os.package_system.builtins import hive_core_catalog, hive_core_root
from hive_mind_os.prompt_registry import generation_zero_prompt, prompt_digest
from hive_mind_os.roles import DEFAULT_LIFECYCLE, ROLE_CONTRACTS
from hive_mind_os.scheduler import Scheduler
from hive_mind_os.source_docket import load_default_source_docket

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "phase1" / "generation_zero.json"
)


def _digest_json(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _database_shape(connection: sqlite3.Connection) -> dict[str, object]:
    table_names = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    objects = connection.execute(
        "SELECT type,name,sql FROM sqlite_master "
        "WHERE type IN ('table','index','trigger') "
        "ORDER BY type,name"
    ).fetchall()

    def sql_digest(value: str) -> str:
        normalized = " ".join(value.split())
        return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"

    object_sql = {
        (row[0], row[1]): row[2]
        for row in objects
        if isinstance(row[2], str)
    }
    indexes: dict[str, object] = {}
    for table in table_names:
        for row in connection.execute(
            f"PRAGMA index_list({table})"
        ).fetchall():
            name = row[1]
            sql = object_sql.get(("index", name))
            indexes[name] = {
                "columns": [
                    index_row[2]
                    for index_row in connection.execute(
                        f"PRAGMA index_info({name})"
                    ).fetchall()
                ],
                "origin": row[3],
                "partial": bool(row[4]),
                "sql_digest": sql_digest(sql) if sql is not None else None,
                "table": table,
                "unique": bool(row[2]),
            }
    return {
        "indexes": indexes,
        "tables": {
            table: {
                "columns": [
                    {
                        "name": row[1],
                        "type": row[2],
                        "not_null": bool(row[3]),
                        "default": row[4],
                        "primary_key_position": row[5],
                    }
                    for row in connection.execute(
                        f"PRAGMA table_info({table})"
                    ).fetchall()
                ],
                "foreign_keys": [
                    list(row)
                    for row in connection.execute(
                        f"PRAGMA foreign_key_list({table})"
                    ).fetchall()
                ],
                "sql_digest": sql_digest(object_sql[("table", table)]),
            }
            for table in table_names
        },
        "triggers": {
            row[1]: sql_digest(row[2])
            for row in objects
            if row[0] == "trigger" and isinstance(row[2], str)
        },
    }


def _stored_state_shape() -> dict[str, object]:
    ledger = EvidenceLedger()
    temporary = tempfile.TemporaryDirectory()
    mission_store = MissionStore(Path(temporary.name) / "mission")
    scheduler = Scheduler(Path(temporary.name) / "scheduler")
    try:
        ledger_shape = _database_shape(ledger._connection)
        mission_shape = _database_shape(mission_store._connection)
        scheduler_shape = _database_shape(scheduler._connection)
    finally:
        scheduler.close()
        mission_store.close()
        ledger.close()
        temporary.cleanup()

    def receipt(shape: dict[str, object]) -> dict[str, object]:
        tables = shape["tables"]
        assert isinstance(tables, dict)
        return {
            "indexes": shape["indexes"],
            "shape_digest": _digest_json(shape),
            "tables": sorted(tables),
            "triggers": shape["triggers"],
        }

    return {
        "evidence_ledger": receipt(ledger_shape),
        "mission_store": {
            **receipt(mission_shape),
            "schema_version": STORE_SCHEMA_VERSION,
        },
        "scheduler": receipt(scheduler_shape),
    }


def _provider_token_mapping() -> dict[str, object]:
    openai = OpenAICompatibleProvider(
        ProviderConfig(
            ProviderKind.OPENAI_COMPATIBLE,
            "https://example.invalid/v1",
            "generation-zero",
            "UNUSED_KEY",
        )
    )
    anthropic = AnthropicProvider(
        ProviderConfig(
            ProviderKind.ANTHROPIC,
            "https://example.invalid/v1",
            "generation-zero",
            "UNUSED_KEY",
        )
    )
    openai_response = openai._parse(
        b'{"choices":[{"message":{"content":"{}"}}],'
        b'"usage":{"prompt_tokens":11,"completion_tokens":7}}',
        "unused",
        0,
    )
    anthropic_response = anthropic._parse(
        b'{"content":[{"text":"{}"}],'
        b'"usage":{"input_tokens":13,"output_tokens":5}}',
        "unused",
        0,
    )
    return {
        "anthropic": [
            anthropic_response.prompt_tokens,
            anthropic_response.completion_tokens,
        ],
        "openai_compatible": [
            openai_response.prompt_tokens,
            openai_response.completion_tokens,
        ],
    }


def _model_call_shape() -> dict[str, object]:
    ledger = EvidenceLedger()
    provider = OpenAICompatibleProvider(
        ProviderConfig(
            ProviderKind.OPENAI_COMPATIBLE,
            "https://example.invalid/v1",
            "generation-zero",
            "UNUSED_KEY",
        )
    )
    backend = ModelBackend(provider, ledger=ledger)
    objective = Objective(
        "Characterize the model-call envelope.",
        id="objective:characterization",
        created_at="2026-07-28T00:00:00+00:00",
    )
    work_item = WorkItem(
        objective.id,
        Role.BUILDER,
        "Observe only.",
        id="work:characterization",
        created_at="2026-07-28T00:00:00+00:00",
    )
    context_manifest = backend._context_manifest(
        (),
        role=Role.BUILDER,
        provider=provider,
    )
    backend._record_call(
        objective,
        ROLE_CONTRACTS[Role.BUILDER],
        work_item,
        b'{"request":"fixture"}',
        ModelResponse("{}", b'{"response":"fixture"}', 11, 7),
        0,
        0.125,
        "succeeded",
        False,
        provider,
        context_manifest,
        prompt_digest(
            generation_zero_prompt(ROLE_CONTRACTS[Role.BUILDER])
        ),
    )
    try:
        event = ledger.events(objective.id)[0]
        payload = event["payload"]
        return {
            "context_manifest_fields": sorted(payload["context_manifest"]),
            "event_type": event["event_type"],
            "model_response_fields": [
                field.name for field in fields(ModelResponse)
            ],
            "payload_fields": sorted(payload),
            "provider_token_observations": _provider_token_mapping(),
            "request_fields": sorted(payload["request"]),
        }
    finally:
        ledger.close()


def _current_characterization() -> dict[str, object]:
    catalog = hive_core_catalog()
    package = catalog.package("hive-core")
    manifest = package.manifest
    snapshot = catalog.snapshot()
    raw_manifest_digest = (
        "sha256:"
        + hashlib.sha256(
            (hive_core_root() / "package.json").read_bytes()
        ).hexdigest()
    )
    resources = [
        {"path": item.path, "digest": item.digest} for item in manifest.files
    ]
    schema_root = files("hive_mind_os").joinpath("schemas")
    schemas = [
        {
            "path": item.name,
            "digest": f"sha256:{hashlib.sha256(item.read_bytes()).hexdigest()}",
        }
        for item in sorted(schema_root.iterdir(), key=lambda candidate: candidate.name)
        if item.name.endswith(".json")
    ]
    docket = load_default_source_docket()
    audit = docket.audit()
    return {
        "captured_from_commit": (
            "b032a9f32f48889e0889fae8d6dd04eb03f46b63"
        ),
        "captured_on_repair_head": (
            "0948f7ec385238f5825ce7c39dd25de2e9a1035d"
        ),
        "default_lifecycle": [role.value for role in DEFAULT_LIFECYCLE],
        "fixture_version": 1,
        "hive_core": {
            "catalog_fingerprint": snapshot.fingerprint,
            "component_contracts_digest": _digest_json(
                [
                    component.to_contract()
                    for component in package.components
                ]
            ),
            "component_ids": [
                component.component_id for component in manifest.components
            ],
            "manifest_digest": package.manifest_digest,
            "raw_manifest_digest": raw_manifest_digest,
            "resource_count": len(resources),
            "resource_inventory_digest": _digest_json(resources),
            "trust_state": manifest.trust_state.value,
            "version": manifest.version,
        },
        "model_call_event": _model_call_shape(),
        "package_version": hive_mind_os.__version__,
        "public_api": sorted(hive_mind_os.__all__),
        "roles": {
            role.value: {
                "default_capabilities": list(contract.default_capabilities),
                "generation_zero_prompt_digest": prompt_digest(
                    generation_zero_prompt(contract)
                ),
                "mission": contract.mission,
                "quality_gates": list(contract.quality_gates),
                "required_outputs": list(contract.required_outputs),
            }
            for role, contract in ROLE_CONTRACTS.items()
        },
        "schemas": {
            "resource_count": len(schemas),
            "resource_inventory_digest": _digest_json(schemas),
            "valid": validate_schema_catalog().valid,
        },
        "source_docket": {
            "audit_issues": len(audit.issues),
            "claims": len(docket.claims),
            "decisions": len(docket.decisions),
            "release_ready": audit.release_ready,
            "sources": len(docket.sources),
        },
        "stored_state": _stored_state_shape(),
    }


class GenerationZeroCharacterizationTests(unittest.TestCase):
    def test_generation_zero_fixture_matches_live_surfaces(self) -> None:
        expected = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(_current_characterization(), expected)

    def test_provider_token_mapping_is_not_inferred_from_field_names(self) -> None:
        self.assertEqual(
            _provider_token_mapping(),
            {
                "anthropic": [13, 5],
                "openai_compatible": [11, 7],
            },
        )

    def test_generation_zero_ledger_rejects_mutation(self) -> None:
        ledger = EvidenceLedger()
        try:
            event_sequence = ledger.append_event(
                "run:characterization",
                "phase1.fixture",
                Role.CURATOR.value,
                {"fixture": "generation-zero"},
            )
            ledger.append_lessons(
                "run:characterization",
                Role.CURATOR.value,
                ("retain the fixture",),
                event_sequence,
            )
            for table, verb, statement, message in (
                (
                    "events",
                    "update",
                    "UPDATE events SET actor = 'mutated'",
                    "events are append-only",
                ),
                (
                    "events",
                    "delete",
                    "DELETE FROM events",
                    "events are append-only",
                ),
                (
                    "lessons",
                    "update",
                    "UPDATE lessons SET lesson = 'mutated'",
                    "lessons are append-only",
                ),
                (
                    "lessons",
                    "delete",
                    "DELETE FROM lessons",
                    "lessons are append-only",
                ),
            ):
                with self.subTest(table=table, verb=verb):
                    with self.assertRaisesRegex(
                        sqlite3.DatabaseError,
                        message,
                    ):
                        with ledger._connection:
                            ledger._connection.execute(statement)
        finally:
            ledger.close()


if __name__ == "__main__":
    unittest.main()
