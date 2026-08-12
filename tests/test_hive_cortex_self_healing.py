from __future__ import annotations

import unittest

from hive_mind_os.brain_kernel.reconciler import (
    ReconciliationPolicy,
    RepairAction,
    RepairKind,
)
from hive_mind_os.brain_kernel.self_healing import (
    FailoverExhaustedError,
    HealingReceipt,
    ProgressLedger,
    ProgressUpdate,
    ProviderFailoverChain,
    RepairHandlerRegistry,
    SelfHealingError,
    SelfHealingRuntime,
    request_identity,
)
from hive_mind_os.brain_kernel.store import KernelIntegrityError, KernelStore
from hive_mind_os.model_provider import (
    MissingModelCredential,
    ModelRequest,
    ModelResponse,
    ModelResponseError,
    ModelTransportError,
)

_SECRET_BODY = b'{"authorization":"sk-do-not-log"}'


class _RecordingProvider:
    """In-memory provider fake; no configuration, transport, or credential."""

    def __init__(self, reference: str, error: Exception | None = None) -> None:
        self._reference = reference
        self._error = error
        self.calls = 0

    @property
    def credential_reference(self) -> str:
        return self._reference

    def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        self.last_request = request
        if self._error is not None:
            raise self._error
        return ModelResponse("healed", _SECRET_BODY, 11, 7)


def _fault_matrix_document() -> dict[str, object]:
    """One snapshot holding every simultaneously recoverable fault class."""

    return {
        "mission_id": "MISSION-heal",
        "mission_status": "RUNNING",
        "authority_scope": ["src/heal.py"],
        "work": {
            "WORK-alpha": {
                "status": "RUNNING",
                "attempts": 1,
                "authority_scope": ["src/heal.py"],
            },
            "WORK-beta": {
                "status": "AWAITING_VERIFICATION",
                "verification_attempts": 1,
                "authority_scope": ["src/heal.py"],
            },
        },
        "leases": [
            {"lease_id": "LEASE-alpha", "work_id": "WORK-alpha", "expires_at": 5}
        ],
        "intents": [{"intent_id": "INTENT-alpha", "work_id": "WORK-alpha"}],
        "workspaces": [
            {
                "workspace_id": "WS-alpha",
                "work_id": "WORK-alpha",
                "exists": False,
                "rebuild_attempts": 1,
            }
        ],
        "provider_failures": [
            {
                "failure_id": "FAIL-alpha",
                "work_id": "WORK-alpha",
                "attempts": 1,
                "retryable": True,
            }
        ],
        "verifications": [
            {
                "verification_id": "VERIFY-beta",
                "work_id": "WORK-beta",
                "status": "INTERRUPTED",
                "attempts": 1,
            }
        ],
    }


class HiveCortexSelfHealingTests(unittest.TestCase):
    def _registry(
        self, applied: list[RepairAction], kinds: tuple[RepairKind, ...]
    ) -> RepairHandlerRegistry:
        registry = RepairHandlerRegistry()
        for kind in kinds:
            registry.register(kind, applied.append)
        return registry

    # --- self-healing-fault-matrix ---------------------------------------

    def test_self_healing_fault_matrix_tests(self) -> None:
        applied: list[RepairAction] = []
        registry = self._registry(applied, tuple(RepairKind))
        runtime = SelfHealingRuntime(registry)
        receipt = runtime.heal(
            _fault_matrix_document(), now=10, granted_authority=("src/heal.py",)
        )

        expected_order = [
            "release-stale-lease:LEASE-alpha",
            "rebuild-workspace:WS-alpha",
            "remand:WORK-alpha",
            "remand:WORK-beta",
            "retry:WORK-alpha",
        ]
        self.assertEqual(
            [outcome.action_id for outcome in receipt.outcomes], expected_order
        )
        self.assertEqual([action.action_id for action in applied], expected_order)
        self.assertEqual(
            {outcome.status for outcome in receipt.outcomes}, {"applied"}
        )
        self.assertEqual(
            [outcome.kind for outcome in receipt.outcomes],
            [
                RepairKind.RELEASE_STALE_LEASE.value,
                RepairKind.REBUILD_WORKSPACE.value,
                RepairKind.REMAND.value,
                RepairKind.REMAND.value,
                RepairKind.RETRY.value,
            ],
        )
        # Every applied repair stayed inside a declared, bounded attempt budget.
        for action in applied:
            self.assertLessEqual(action.attempt, action.max_attempts)
            self.assertGreaterEqual(action.max_attempts, 1)
        self.assertFalse(receipt.quarantined)
        self.assertEqual(receipt.escalations, ())
        self.assertEqual(receipt.mission_id, "MISSION-heal")

        # Determinism: an identical pass reproduces the identical receipt digest.
        second_applied: list[RepairAction] = []
        second = SelfHealingRuntime(
            self._registry(second_applied, tuple(RepairKind))
        ).heal(_fault_matrix_document(), now=10, granted_authority=("src/heal.py",))
        self.assertEqual(receipt.digest, second.digest)
        self.assertEqual(receipt.to_document(), second.to_document())

        # An unregistered kind is retained as a proposal, never invented.
        partial_applied: list[RepairAction] = []
        partial = SelfHealingRuntime(
            self._registry(
                partial_applied,
                (
                    RepairKind.RELEASE_STALE_LEASE,
                    RepairKind.REBUILD_WORKSPACE,
                    RepairKind.REMAND,
                ),
            )
        ).heal(_fault_matrix_document(), now=10, granted_authority=("src/heal.py",))
        statuses = {
            outcome.action_id: outcome.status for outcome in partial.outcomes
        }
        self.assertEqual(statuses["retry:WORK-alpha"], "skipped-no-handler")
        self.assertEqual(statuses["remand:WORK-beta"], "applied")
        self.assertNotIn(
            "retry:WORK-alpha", [action.action_id for action in partial_applied]
        )

        # A failing handler surfaces; the pass never continues past a bad repair.
        exploding = RepairHandlerRegistry()
        exploding.register(
            RepairKind.RELEASE_STALE_LEASE,
            self._raiser(RuntimeError("lease release failed")),
        )
        with self.assertRaises(SelfHealingError) as caught:
            SelfHealingRuntime(exploding).heal(
                _fault_matrix_document(), now=10, granted_authority=("src/heal.py",)
            )
        self.assertIn("release-stale-lease:LEASE-alpha", str(caught.exception))
        self.assertIsInstance(caught.exception.__cause__, RuntimeError)

        # Re-registering a kind is refused rather than silently overwritten.
        duplicate = RepairHandlerRegistry()
        duplicate.register(RepairKind.RETRY, applied.append)
        with self.assertRaises(ValueError):
            duplicate.register(RepairKind.RETRY, applied.append)

    @staticmethod
    def _raiser(error: Exception):
        def handler(action: RepairAction) -> None:
            raise error

        return handler

    # --- provider-failover-tests -----------------------------------------

    def test_provider_failover_tests(self) -> None:
        request = ModelRequest("system-contract", "user-body", "corrective")
        transport = _RecordingProvider(
            "environment:PROVIDER_A", ModelTransportError("model transport failed: A")
        )
        credential = _RecordingProvider(
            "environment:PROVIDER_B",
            MissingModelCredential("required model credential is missing: PROVIDER_B"),
        )
        healthy = _RecordingProvider("environment:PROVIDER_C")

        response, receipt = ProviderFailoverChain(
            [transport, credential, healthy]
        ).complete(request)

        self.assertEqual(response.content, "healed")
        self.assertEqual(receipt.served_by, 2)
        self.assertEqual(receipt.request_digest, request_identity(request))

        # AC2: contract identity is invariant across chain shape.
        _, single = ProviderFailoverChain(
            [_RecordingProvider("environment:PROVIDER_C")]
        ).complete(request)
        self.assertEqual(single.request_digest, receipt.request_digest)
        self.assertEqual(single.response_digest, receipt.response_digest)
        self.assertNotEqual(single.digest, receipt.digest)

        # A different contract must not collapse onto the same identity.
        self.assertNotEqual(
            receipt.request_digest,
            request_identity(ModelRequest("system-contract", "user-body", None)),
        )

        # Every provider saw the byte-identical request object.
        self.assertIs(transport.last_request, request)
        self.assertIs(credential.last_request, request)
        self.assertIs(healthy.last_request, request)

        self.assertEqual(
            [attempt.outcome for attempt in receipt.attempts],
            ["transport-error", "missing-credential", "success"],
        )
        self.assertEqual(
            [attempt.provider_index for attempt in receipt.attempts], [0, 1, 2]
        )
        self.assertEqual(
            [attempt.credential_reference for attempt in receipt.attempts],
            ["environment:PROVIDER_A", "environment:PROVIDER_B", "environment:PROVIDER_C"],
        )
        self.assertEqual(receipt.attempts[2].detail, "")

        # No secret material leaks into the receipt.
        document = receipt.to_document()
        self.assertNotIn("raw_body", document)
        rendered = repr(document)
        self.assertNotIn("sk-do-not-log", rendered)
        self.assertNotIn(_SECRET_BODY.decode("utf-8"), rendered)

        with self.assertRaises(ValueError):
            ProviderFailoverChain([])

    def test_provider_failover_exhaustion_tests(self) -> None:
        request = ModelRequest("system-contract", "user-body")
        providers = [
            _RecordingProvider("environment:A", ModelTransportError("down")),
            _RecordingProvider("environment:B", MissingModelCredential("absent")),
            _RecordingProvider("environment:C", ModelTransportError("down")),
        ]
        with self.assertRaises(FailoverExhaustedError) as caught:
            ProviderFailoverChain(providers).complete(request)
        self.assertEqual(len(caught.exception.attempts), len(providers))
        self.assertEqual(
            [attempt.outcome for attempt in caught.exception.attempts],
            ["transport-error", "missing-credential", "transport-error"],
        )
        self.assertEqual([provider.calls for provider in providers], [1, 1, 1])

    def test_provider_semantic_error_does_not_failover_tests(self) -> None:
        request = ModelRequest("system-contract", "user-body")
        semantic = _RecordingProvider(
            "environment:A", ModelResponseError("bad", b"{}")
        )
        healthy = _RecordingProvider("environment:B")
        with self.assertRaises(ModelResponseError) as caught:
            ProviderFailoverChain([semantic, healthy]).complete(request)
        self.assertEqual(caught.exception.raw_body, b"{}")
        self.assertEqual(semantic.calls, 1)
        self.assertEqual(healthy.calls, 0)

    # --- rollback-tests ---------------------------------------------------

    @staticmethod
    def _rollback_document() -> dict[str, object]:
        return {
            "mission_id": "MISSION-rollback",
            "mission_status": "RUNNING",
            "work": {
                "WORK-roll": {
                    "status": "INTEGRATING",
                    "rollback_required": True,
                    "authority_scope": ["src/a.py"],
                }
            },
        }

    def test_rollback_inside_authority_tests(self) -> None:
        applied: list[RepairAction] = []
        registry = self._registry(applied, (RepairKind.ROLLBACK,))
        receipt = SelfHealingRuntime(registry).heal(
            self._rollback_document(), now=1, granted_authority=("src/a.py",)
        )
        self.assertEqual([action.action_id for action in applied], ["rollback:WORK-roll"])
        self.assertEqual(applied[0].authority_scope, ("src/a.py",))
        self.assertEqual(len(receipt.outcomes), 1)
        self.assertEqual(receipt.outcomes[0].status, "applied")
        self.assertEqual(receipt.outcomes[0].kind, RepairKind.ROLLBACK.value)
        self.assertEqual(receipt.escalations, ())

    def test_rollback_outside_authority_escalates_tests(self) -> None:
        applied: list[RepairAction] = []
        registry = self._registry(applied, (RepairKind.ROLLBACK,))
        receipt = SelfHealingRuntime(registry).heal(
            self._rollback_document(), now=1, granted_authority=()
        )
        self.assertEqual(applied, [])
        self.assertEqual(len(receipt.outcomes), 1)
        self.assertEqual(receipt.outcomes[0].status, "escalated-authority")
        self.assertEqual(receipt.outcomes[0].action_id, "rollback:WORK-roll")
        self.assertEqual(receipt.escalations, ("rollback:WORK-roll",))
        self.assertIn("rollback:WORK-roll", receipt.to_document()["escalations"])

        # A strictly narrower grant is still outside the required scope.
        narrower: list[RepairAction] = []
        partial = SelfHealingRuntime(
            self._registry(narrower, (RepairKind.ROLLBACK,))
        ).heal(
            self._rollback_document(), now=1, granted_authority=("src/other.py",)
        )
        self.assertEqual(narrower, [])
        self.assertEqual(partial.escalations, ("rollback:WORK-roll",))

    # --- quarantine-tests -------------------------------------------------

    def test_no_progress_quarantine_tests(self) -> None:
        applied: list[RepairAction] = []
        registry = self._registry(applied, (RepairKind.QUARANTINE,))
        policy = ReconciliationPolicy()
        receipt = SelfHealingRuntime(registry, policy=policy).heal(
            {
                "mission_id": "MISSION-stall",
                "mission_status": "RUNNING",
                "no_progress_count": policy.no_progress_limit,
                "progress_signature": "same-observation",
            },
            now=1,
        )
        self.assertTrue(receipt.quarantined)
        self.assertEqual(
            [outcome.action_id for outcome in receipt.outcomes],
            ["quarantine:MISSION-stall"],
        )
        self.assertEqual(receipt.outcomes[0].status, "applied")
        self.assertEqual([action.target_id for action in applied], ["MISSION-stall"])
        self.assertEqual(applied[0].kind, RepairKind.QUARANTINE)
        self.assertEqual(applied[0].attempt, policy.no_progress_limit)
        self.assertTrue(receipt.to_document()["quarantined"])

        # Under the bound the same mission is not quarantined.
        below: list[RepairAction] = []
        healthy = SelfHealingRuntime(
            self._registry(below, (RepairKind.QUARANTINE,)), policy=policy
        ).heal(
            {
                "mission_id": "MISSION-stall",
                "mission_status": "RUNNING",
                "no_progress_count": policy.no_progress_limit - 1,
                "progress_signature": "same-observation",
            },
            now=1,
        )
        self.assertFalse(healthy.quarantined)
        self.assertEqual(below, [])
        # A pass proposing nothing keeps the signature so stalls accumulate.
        self.assertEqual(healthy.progress.signature, "same-observation")
        self.assertEqual(
            healthy.progress.no_progress_count, policy.no_progress_limit
        )

    def test_progress_ledger_reset_tests(self) -> None:
        ledger = ProgressLedger()
        first = ledger.advance(ProgressUpdate("sig-a", 0), "sig-a")
        self.assertEqual(first, ProgressUpdate("sig-a", 1))
        second = ledger.advance(first, "sig-a")
        self.assertEqual(second, ProgressUpdate("sig-a", 2))
        reset = ledger.advance(second, "sig-b")
        self.assertEqual(reset, ProgressUpdate("sig-b", 0))
        self.assertEqual(
            ledger.advance(reset, None), ProgressUpdate(None, 0)
        )
        self.assertEqual(
            ledger.advance(ProgressUpdate(None, 4), None), ProgressUpdate(None, 0)
        )

        # A pass that proposes repairs establishes a new signature.
        applied: list[RepairAction] = []
        receipt = SelfHealingRuntime(
            self._registry(applied, (RepairKind.ROLLBACK,))
        ).heal(
            self._rollback_document(), now=1, granted_authority=("src/a.py",)
        )
        self.assertEqual(receipt.progress.signature, receipt.desired_digest)
        self.assertEqual(receipt.progress.no_progress_count, 0)

    # --- durable healing-pass event ---------------------------------------

    def test_store_pass_event_is_rejected_by_the_reducer_tests(self) -> None:
        """The mandated durable append is unsatisfiable against current source.

        ``projection.reduce_event`` (projection.py:271-272) fails closed on any
        unknown ``event_type`` and ``KernelStore.append_batch`` rebuilds
        projections inside the same transaction (store.py:320), so a
        ``self_healing.pass`` event cannot be appended until the reducer learns
        the type.  Teaching it lives in ``projection.py``, outside this node's
        write scope, so the real invariant asserted here is that the failure is
        closed and leaves no partial write.
        """

        store = KernelStore(":memory:")
        try:
            applied: list[RepairAction] = []
            runtime = SelfHealingRuntime(
                self._registry(applied, (RepairKind.ROLLBACK,)), store=store
            )
            with self.assertRaises(KernelIntegrityError) as caught:
                runtime.heal(
                    self._rollback_document(),
                    now=1,
                    granted_authority=("src/a.py",),
                )
            self.assertIsInstance(caught.exception.__cause__, ValueError)
            self.assertEqual(
                str(caught.exception.__cause__),
                "unknown kernel event type: self_healing.pass",
            )
            self.assertEqual(store.events(), [])
        finally:
            store.close()

    def test_healing_receipt_document_is_deterministic_tests(self) -> None:
        applied: list[RepairAction] = []
        receipt = SelfHealingRuntime(
            self._registry(applied, (RepairKind.ROLLBACK,))
        ).heal(self._rollback_document(), now=1, granted_authority=("src/a.py",))
        self.assertIsInstance(receipt, HealingReceipt)
        document = receipt.to_document()
        self.assertEqual(
            sorted(document),
            [
                "desired_digest",
                "escalations",
                "mission_id",
                "observed_digest",
                "outcomes",
                "progress",
                "quarantined",
            ],
        )
        self.assertTrue(document["observed_digest"].startswith("sha256:"))
        self.assertTrue(receipt.digest.startswith("sha256:"))
        # No wall-clock, absolute path, or platform separator reached the receipt.
        rendered = repr(document)
        self.assertNotIn("\\", rendered)
        self.assertNotIn("C:/", rendered)


if __name__ == "__main__":
    unittest.main()
