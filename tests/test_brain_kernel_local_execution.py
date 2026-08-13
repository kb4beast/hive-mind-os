from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hive_mind_os.brain_kernel.authority import (
    AuthorityDenied,
    AuthorityRegistry,
    CapabilityToken,
)
from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.contracts import EffectIntent
from hive_mind_os.brain_kernel.effects import EffectGateway, intent_seal, sealed_intent
from hive_mind_os.cortex.repository import local_execution
from hive_mind_os.cortex.repository.local_execution import (
    LocalWorkspaceAdapter,
    run_sealed_builder_curator_fixture,
)

REFUSED_TARGET = "base/app.txt"
AUTH_TIME = "2029-01-01T00:00:00Z"


def _forged_token(envelope_digest: str, action: str, target: str) -> CapabilityToken:
    """The A5-F10 forgery, written past the constructor's issuance check.

    Re-declared locally on purpose; sibling test modules are never imported.
    """

    forged = object.__new__(CapabilityToken)
    values = (
        envelope_digest,
        action,
        target,
        canonical_digest(
            {"envelope": envelope_digest, "action": action, "target": target}
        ),
        "",
    )
    for name, value in zip(CapabilityToken.__slots__, values):
        object.__setattr__(forged, name, value)
    return forged


class _RecordingGateway(EffectGateway):
    """Records how the production module constructed and used its gateway."""

    constructed: list[AuthorityRegistry | None] = []
    executed: list[EffectIntent] = []

    def __init__(self, store=None, *, authority=None, **keywords) -> None:
        _RecordingGateway.constructed.append(authority)
        super().__init__(store, authority=authority, **keywords)

    def execute(self, intent, token):
        _RecordingGateway.executed.append(intent)
        return super().execute(intent, token)


class LocalKernelExecutionTests(unittest.TestCase):
    def test_builder_uses_an_isolated_gateway_write_and_curator_verifies_after_seal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_sealed_builder_curator_fixture(root)
            self.assertEqual("adopt", result.verdict)
            self.assertLess(result.seal_sequence, result.candidate_access_sequence)
            self.assertNotEqual(result.builder.executor_id, result.curator.executor_id)
            self.assertTrue(result.builder.effect_receipt_refs)
            self.assertEqual("before\n", (root / "base" / "app.txt").read_text())
            self.assertEqual("after\n", (root / "candidate" / "app.txt").read_text())

    def test_workspace_adapter_refuses_path_escape_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter = LocalWorkspaceAdapter(root)
            with self.assertRaises(AuthorityDenied):
                adapter.write("../outside.txt", b"no")
            self.assertFalse((root.parent / "outside.txt").exists())


class ProductionGatewayBindingTests(unittest.TestCase):
    """BIND-1030 / A5-F10: the fixture's own gateway consults live authority."""

    def setUp(self) -> None:
        _RecordingGateway.constructed.clear()
        _RecordingGateway.executed.clear()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        with patch.object(local_execution, "EffectGateway", _RecordingGateway):
            self.result = run_sealed_builder_curator_fixture(self.root)
        self.registry = _RecordingGateway.constructed[0]
        self.intent = _RecordingGateway.executed[0]

    def test_the_fixture_builds_an_authority_bound_gateway_over_a_sealed_intent(
        self,
    ) -> None:
        self.assertEqual("adopt", self.result.verdict)
        self.assertEqual(1, len(_RecordingGateway.constructed))
        self.assertIsInstance(self.registry, AuthorityRegistry)
        self.assertEqual(1, len(_RecordingGateway.executed))
        self.assertEqual(intent_seal(self.intent), self.intent.intent_digest)

    def test_the_registry_the_fixture_built_refuses_a_forged_token(self) -> None:
        assert isinstance(self.registry, AuthorityRegistry)
        # Cheat: spend a hand-built token on the sealed base workspace the
        # envelope's write scope deliberately excludes.
        escape = sealed_intent(replace(self.intent, target=REFUSED_TARGET))
        forged = _forged_token(
            self.intent.authority_envelope_digest, "write", REFUSED_TARGET
        )
        adapter = LocalWorkspaceAdapter(self.root)
        adapter.register_payload(b"escaped\n")
        gateway = EffectGateway(authority=self.registry, clock=lambda: AUTH_TIME)
        gateway.register_adapter("isolated-write", adapter.apply)

        with self.assertRaisesRegex(AuthorityDenied, "outside write scope"):
            gateway.execute(escape, forged)
        self.assertEqual("before\n", (self.root / "base" / "app.txt").read_text())
