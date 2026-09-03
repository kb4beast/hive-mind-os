from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from hive_mind_os.activation_bundle import AuthorizedOneRun
from hive_mind_os.dag_standard import compile_plan
from hive_mind_os.host_adapter import (
    HOST_DEADLINE_CAPABILITY,
    HostExecutionReceipt,
    HostIdentity,
    HostLease,
    HostObservation,
    HostReceiptState,
    canonical_checkpoint_digest,
)
from hive_mind_os.host_runtime import (
    HostOperationJournal,
    HostOperationRecord,
    HostOperationState,
    HostRecoveryRequired,
    HostRuntime,
    HostRuntimeError,
)
from hive_mind_os.portable_plan import NonRepositorySubject, SubjectBinding
from hive_mind_os.runtime_contracts import canonical_digest, canonical_json_bytes
from tests.test_dag_standard_product import ROLES, STAGES, STANDARD, compiler_plan
from tests.test_generic_dag_v4_activation import authorized_one_run_fixture


def digest(character: str) -> str:
    return "sha256:" + character * 64


NOW = datetime(2026, 9, 2, 12, 5, tzinfo=UTC)
NOW_TEXT = "2026-09-02T12:05:00Z"
LEASE_END = "2026-09-02T12:10:00Z"
RUN_END = "2026-09-02T12:15:00Z"
_HOST_PLAN_BASE = compiler_plan()
_HOST_PLAN = replace(
    _HOST_PLAN_BASE,
    nodes=(
        replace(
            _HOST_PLAN_BASE.nodes[0],
            node_id="node-1",
            dependencies=(),
            roles=ROLES,
            lifecycle_stages=STAGES,
        ),
    ),
)
HOST_PLAN_BYTES = _HOST_PLAN.canonical_bytes()
HOST_STANDARD_BYTES = STANDARD
HOST_COMPILATION_RECEIPT = compile_plan(
    HOST_PLAN_BYTES,
    expected_plan_digest=_HOST_PLAN.digest(),
    standard_bytes=HOST_STANDARD_BYTES,
).to_document()
PLAN = _HOST_PLAN.digest()
SUBJECT = _HOST_PLAN.subject.subject_id
GENERATION = digest("3")
AUTHORITY = canonical_digest(
    [item.to_document() for item in _HOST_PLAN.authority]
)
ADAPTER_INVENTORY = canonical_digest(
    [item.to_document() for item in _HOST_PLAN.adapters]
)
BOUND_CAPABILITIES = (HOST_DEADLINE_CAPABILITY, "read")


class FakeHost:
    def __init__(self) -> None:
        self.identity = HostIdentity(
            "host-1",
            "windows",
            "amd64",
            "3.14",
            digest("6"),
            ADAPTER_INVENTORY,
        )
        self.clean = True
        self.prepare_calls = 0
        self.observe_calls = 0
        self.execute_calls = 0
        self.completed_calls = 0
        self.cancel_calls = 0
        self.delay = 0.0
        self.last_authorization: AuthorizedOneRun | None = None
        self.last_prepare_values: dict[str, object] | None = None
        self.capabilities: tuple[str, ...] = (
            "execute",
            "read",
            "checkpoint",
            "cancel",
            HOST_DEADLINE_CAPABILITY,
        )
        self.trust_evidence_digest = digest("8")
        self.observed_at = NOW_TEXT
        self.lease_issued_at = NOW_TEXT
        self.receipt_observed_at = NOW_TEXT

    def observe(self, *, subject_id: str) -> HostObservation:
        self.observe_calls += 1
        return HostObservation(
            self.identity,
            subject_id,
            self.observed_at,
            self.capabilities,
            self.trust_evidence_digest,
            self.clean,
        )

    def prepare(self, **values) -> HostLease:
        self.prepare_calls += 1
        self.last_prepare_values = dict(values)
        authorization = values["authorization"]
        self.last_authorization = authorization
        return HostLease(
            "lease-1",
            self.identity.host_id,
            values["subject_id"],
            values["generation_id"],
            values["authority_digest"],
            values["adapter_inventory_digest"],
            values["external_effects_required"],
            canonical_digest(dict(values["compilation_receipt"])),
            authorization.activation_digest,
            authorization.proof_digest,
            authorization.candidate_commit,
            authorization.candidate_tree,
            authorization.candidate_content_sha256,
            authorization.candidate_parent_commit,
            authorization.candidate_parent_tree,
            authorization.manifest_sha256,
            authorization.repository_id,
            authorization.request_sha256,
            authorization.target_branch,
            authorization.execution_client_sha256,
            authorization.issued_at.astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            authorization.protected_merge_authorized,
            self.identity.digest,
            self.trust_evidence_digest,
            values["required_capabilities"],
            self.lease_issued_at,
            values["lease_deadline"],
            values["node_ids"],
            values["nonce_digest"],
        )

    def execute(self, *, node_id: str, input_bytes: bytes, lease: HostLease):
        self.execute_calls += 1
        if self.delay:
            time.sleep(self.delay)
        self.completed_calls += 1
        return HostExecutionReceipt(
            f"receipt-{self.execute_calls}",
            lease.lease_id,
            node_id,
            HostReceiptState.SUCCEEDED,
            "sha256:" + sha256(input_bytes).hexdigest(),
            digest("9"),
            digest("a"),
            self.receipt_observed_at,
        )

    def cancel(self, *, lease: HostLease, reason: str):
        self.cancel_calls += 1
        return HostExecutionReceipt(
            "receipt-cancel",
            lease.lease_id,
            lease.allowed_node_ids[0],
            HostReceiptState.CANCELLED,
            canonical_digest({"reason": reason}),
            None,
            digest("b"),
            self.receipt_observed_at,
        )


class HostRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.host = FakeHost()
        self.journal = HostOperationJournal()
        self.addCleanup(self.journal.close)
        self.runtime = HostRuntime(
            self.host,
            self.journal,
            one_run_deadline=RUN_END,
            clock=lambda: NOW,
            adoption_verifier=lambda **_: True,
        )
        self.authorization = authorized_one_run_fixture(
            HOST_PLAN_BYTES, nonce_seed=self.id()
        )

    def create(self, key: str = "create-1") -> HostLease:
        return self.runtime.create(
            plan_bytes=HOST_PLAN_BYTES,
            standard_bytes=HOST_STANDARD_BYTES,
            generation_id=GENERATION,
            lease_deadline=LEASE_END,
            authorization=self.authorization,
            idempotency_key=key,
        )

    def test_create_poll_message_checkpoint_cancel_and_resume_are_idempotent(
        self,
    ) -> None:
        lease = self.create()
        self.assertEqual(self.create(), lease)
        self.assertEqual(self.host.prepare_calls, 1)
        self.assertEqual(self.authorization.activation_digest, lease.activation_digest)
        self.assertEqual(self.authorization.proof_digest, lease.activation_proof_digest)
        self.assertEqual(
            self.authorization.candidate_content_sha256,
            lease.candidate_content_sha256,
        )
        self.assertEqual(self.authorization.manifest_sha256, lease.manifest_sha256)
        self.assertEqual(self.authorization.repository_id, lease.repository_id)
        self.assertEqual(
            self.authorization.execution_client_sha256,
            lease.execution_client_sha256,
        )
        self.assertIs(lease.protected_merge_authorized, False)
        prepared = self.host.last_authorization
        self.assertIsNotNone(prepared)
        assert prepared is not None
        principals = prepared.proof_document()["principals"]
        self.assertIsInstance(principals, dict)
        assert isinstance(principals, dict)
        issuer = principals["issuer"]
        self.assertIsInstance(issuer, dict)
        assert isinstance(issuer, dict)
        self.assertEqual("principal:issuer", issuer["principal_id"])
        receipt = self.runtime.message(
            lease=lease,
            node_id="node-1",
            input_bytes=b"exact-node-delta",
            idempotency_key="message-1",
        )
        again = self.runtime.execute(
            lease=lease,
            node_id="node-1",
            input_bytes=b"exact-node-delta",
            idempotency_key="message-1",
        )
        self.assertEqual(again, receipt)
        self.assertEqual(self.host.execute_calls, 1)
        with self.assertRaisesRegex(HostRuntimeError, "authenticated host output"):
            self.runtime.checkpoint(
                lease=lease,
                receipt=receipt,
                checkpoint_digest=digest("b"),
                candidate_digest=digest("d"),
                idempotency_key="checkpoint-substituted-candidate",
            )
        checkpoint = self.runtime.checkpoint(
            lease=lease,
            receipt=receipt,
            checkpoint_digest=canonical_checkpoint_digest(lease, receipt),
            candidate_digest=receipt.output_digest,
            idempotency_key="checkpoint-1",
        )
        self.assertEqual(checkpoint.node_id, "node-1")
        resumed = self.runtime.resume(
            create_idempotency_key="create-1",
            poll_idempotency_key="poll-resume",
        )
        self.assertEqual(resumed, lease)
        cancelled = self.runtime.cancel(
            lease=lease,
            reason="bounded test cancellation",
            idempotency_key="cancel-1",
        )
        self.assertEqual(cancelled.state, HostReceiptState.CANCELLED)
        self.assertEqual(self.host.cancel_calls, 1)

    def test_create_derives_effect_scope_from_exact_signed_plan_bytes(self) -> None:
        lease = self.create("derived-create")
        values = self.host.last_prepare_values
        self.assertIsNotNone(values)
        assert values is not None
        self.assertEqual(PLAN, values["plan_digest"])
        self.assertEqual(SUBJECT, values["subject_id"])
        self.assertEqual(AUTHORITY, values["authority_digest"])
        self.assertEqual(
            ADAPTER_INVENTORY, values["adapter_inventory_digest"]
        )
        self.assertEqual(("node-1",), values["node_ids"])
        self.assertEqual(BOUND_CAPABILITIES, values["required_capabilities"])
        self.assertEqual(("node-1",), lease.allowed_node_ids)

        changed = replace(
            _HOST_PLAN,
            nodes=(replace(_HOST_PLAN.nodes[0], objective="caller substitution"),),
        )
        prepare_calls = self.host.prepare_calls
        with self.assertRaisesRegex(HostRuntimeError, "another plan"):
            self.runtime.create(
                plan_bytes=changed.canonical_bytes(),
                standard_bytes=HOST_STANDARD_BYTES,
                generation_id=GENERATION,
                lease_deadline=LEASE_END,
                authorization=self.authorization,
                idempotency_key="substituted-plan-create",
            )
        self.assertEqual(prepare_calls, self.host.prepare_calls)

        with self.assertRaises(TypeError):
            self.runtime.create(
                plan_bytes=HOST_PLAN_BYTES,
                standard_bytes=HOST_STANDARD_BYTES,
                generation_id=GENERATION,
                subject_id=digest("f"),  # pyright: ignore[reportCallIssue]
                lease_deadline=LEASE_END,
                authorization=self.authorization,
                idempotency_key="caller-controlled-subject-create",
            )
        self.assertEqual(prepare_calls, self.host.prepare_calls)

    def test_create_rejects_adapter_id_configuration_or_aggregate_drift(
        self,
    ) -> None:
        renamed_adapter = replace(
            _HOST_PLAN.adapters[0], adapter_id="other-subject-adapter"
        )
        renamed_plan = replace(
            _HOST_PLAN,
            adapters=(renamed_adapter,),
            capabilities=tuple(
                replace(item, adapter_id=renamed_adapter.adapter_id)
                for item in _HOST_PLAN.capabilities
            ),
            nodes=tuple(
                replace(item, adapter_ids=(renamed_adapter.adapter_id,))
                for item in _HOST_PLAN.nodes
            ),
        )
        reconfigured_plan = replace(
            _HOST_PLAN,
            adapters=(
                replace(
                    _HOST_PLAN.adapters[0],
                    configuration_digest=digest("f"),
                ),
            ),
        )
        cases = (
            ("adapter-id", renamed_plan, ADAPTER_INVENTORY),
            ("adapter-configuration", reconfigured_plan, ADAPTER_INVENTORY),
            ("adapter-aggregate", _HOST_PLAN, digest("e")),
        )
        for label, plan, observed_inventory_digest in cases:
            with self.subTest(label=label):
                host = FakeHost()
                host.identity = replace(
                    host.identity, adapter_digest=observed_inventory_digest
                )
                journal = HostOperationJournal()
                self.addCleanup(journal.close)
                runtime = HostRuntime(
                    host,
                    journal,
                    one_run_deadline=RUN_END,
                    clock=lambda: NOW,
                )
                authorization = authorized_one_run_fixture(
                    plan.canonical_bytes(), nonce_seed=self.id() + label
                )
                with self.assertRaisesRegex(
                    HostRuntimeError, "adapter inventory"
                ):
                    runtime.create(
                        plan_bytes=plan.canonical_bytes(),
                        standard_bytes=HOST_STANDARD_BYTES,
                        generation_id=GENERATION,
                        lease_deadline=LEASE_END,
                        authorization=authorization,
                        idempotency_key=f"{label}-create",
                    )
                self.assertEqual(0, host.prepare_calls)
                self.assertEqual(0, host.execute_calls)

    def test_direct_create_denies_external_effect_without_external_authority(
        self,
    ) -> None:
        external_capability = replace(
            _HOST_PLAN.capabilities[0], effect_class="external-reversible"
        )
        denied_plan = replace(
            _HOST_PLAN,
            capabilities=(external_capability,),
            authority=(replace(_HOST_PLAN.authority[0], external_effects=False),),
        )
        denied_authorization = authorized_one_run_fixture(
            denied_plan.canonical_bytes(), nonce_seed=self.id() + "-denied"
        )
        with self.assertRaisesRegex(
            HostRuntimeError, "lacks external-effect authority"
        ):
            self.runtime.create(
                plan_bytes=denied_plan.canonical_bytes(),
                standard_bytes=HOST_STANDARD_BYTES,
                generation_id=GENERATION,
                lease_deadline=LEASE_END,
                authorization=denied_authorization,
                idempotency_key="direct-external-denied",
            )
        self.assertEqual(0, self.host.observe_calls)
        self.assertEqual(0, self.host.prepare_calls)

        permitted_plan = replace(
            denied_plan,
            authority=(replace(_HOST_PLAN.authority[0], external_effects=True),),
        )
        permitted_authorization = authorized_one_run_fixture(
            permitted_plan.canonical_bytes(), nonce_seed=self.id() + "-permitted"
        )
        lease = self.runtime.create(
            plan_bytes=permitted_plan.canonical_bytes(),
            standard_bytes=HOST_STANDARD_BYTES,
            generation_id=GENERATION,
            lease_deadline=LEASE_END,
            authorization=permitted_authorization,
            idempotency_key="direct-external-permitted",
        )
        self.assertIs(lease.external_effects_required, True)
        assert self.host.last_prepare_values is not None
        self.assertIs(
            self.host.last_prepare_values["external_effects_required"], True
        )

    def test_direct_create_applies_shared_authority_and_budget_admission(self) -> None:
        short_authority = replace(
            _HOST_PLAN,
            authority=(
                replace(
                    _HOST_PLAN.authority[0],
                    expires_at="2026-09-02T12:09:59Z",
                ),
            ),
        )
        undersized_budget = replace(
            _HOST_PLAN,
            budgets=(
                replace(
                    _HOST_PLAN.budgets[0],
                    policy=replace(_HOST_PLAN.budgets[0].policy, tool_calls=0),
                ),
            ),
        )
        for label, plan in (
            ("authority-expiry", short_authority),
            ("tool-budget", undersized_budget),
        ):
            with self.subTest(label=label):
                authorization = authorized_one_run_fixture(
                    plan.canonical_bytes(), nonce_seed=self.id() + label
                )
                with self.assertRaisesRegex(
                    HostRuntimeError, "authority or static budget"
                ):
                    self.runtime.create(
                        plan_bytes=plan.canonical_bytes(),
                        standard_bytes=HOST_STANDARD_BYTES,
                        generation_id=GENERATION,
                        lease_deadline=LEASE_END,
                        authorization=authorization,
                        idempotency_key=f"direct-admission-{label}",
                    )
        self.assertEqual(0, self.host.observe_calls)
        self.assertEqual(0, self.host.prepare_calls)
        self.assertEqual(0, self.host.execute_calls)

    def test_direct_create_requires_canonical_compiler_standard_and_governance(
        self,
    ) -> None:
        compiler_mismatch = replace(
            _HOST_PLAN,
            standard=replace(_HOST_PLAN.standard, package_digest=digest("f")),
        )
        missing_role = replace(
            _HOST_PLAN,
            nodes=(
                replace(
                    _HOST_PLAN.nodes[0],
                    roles=tuple(item for item in ROLES if item != "optimizer"),
                ),
            ),
        )
        missing_stage = replace(
            _HOST_PLAN,
            nodes=(
                replace(
                    _HOST_PLAN.nodes[0],
                    lifecycle_stages=tuple(
                        item for item in STAGES if item != "integrate"
                    ),
                ),
            ),
        )
        missing_evidence = replace(
            _HOST_PLAN,
            nodes=(replace(_HOST_PLAN.nodes[0], evidence_ids=()),),
        )
        noncanonical = HOST_PLAN_BYTES.replace(b"{", b"{ ", 1)
        cases = (
            ("noncanonical-plan", noncanonical, HOST_STANDARD_BYTES),
            ("substituted-standard", HOST_PLAN_BYTES, b"substituted standard"),
            (
                "compiler-package",
                compiler_mismatch.canonical_bytes(),
                HOST_STANDARD_BYTES,
            ),
            ("missing-role", missing_role.canonical_bytes(), HOST_STANDARD_BYTES),
            (
                "missing-stage",
                missing_stage.canonical_bytes(),
                HOST_STANDARD_BYTES,
            ),
            (
                "missing-evidence",
                missing_evidence.canonical_bytes(),
                HOST_STANDARD_BYTES,
            ),
        )
        for label, plan_bytes, standard_bytes in cases:
            with self.subTest(label=label):
                authorization = authorized_one_run_fixture(
                    plan_bytes, nonce_seed=self.id() + label
                )
                with self.assertRaisesRegex(
                    HostRuntimeError, "plan, standard, or activation binding"
                ):
                    self.runtime.create(
                        plan_bytes=plan_bytes,
                        standard_bytes=standard_bytes,
                        generation_id=GENERATION,
                        lease_deadline=LEASE_END,
                        authorization=authorization,
                        idempotency_key=f"qualification-{label}",
                    )
        self.assertEqual(0, self.host.observe_calls)
        self.assertEqual(0, self.host.prepare_calls)
        self.assertEqual(0, self.host.execute_calls)

    def test_direct_create_cross_binds_request_repository_base_and_target(
        self,
    ) -> None:
        repository = _HOST_PLAN.subject.repository
        assert repository is not None
        variants = (
            ("request", replace(_HOST_PLAN, request_id=digest("f"))),
            (
                "repository",
                replace(
                    _HOST_PLAN,
                    subject=SubjectBinding.for_repository(
                        replace(repository, repository_id=digest("e"))
                    ),
                ),
            ),
            (
                "base-commit",
                replace(
                    _HOST_PLAN,
                    subject=SubjectBinding.for_repository(
                        replace(repository, commit="e" * 40)
                    ),
                ),
            ),
            (
                "base-tree",
                replace(
                    _HOST_PLAN,
                    subject=SubjectBinding.for_repository(
                        replace(repository, tree="e" * 40)
                    ),
                ),
            ),
            (
                "target",
                replace(
                    _HOST_PLAN,
                    subject=SubjectBinding.for_repository(
                        replace(repository, target_branch="other")
                    ),
                ),
            ),
            (
                "non-repository",
                replace(
                    _HOST_PLAN,
                    subject=SubjectBinding.for_non_repository(
                        NonRepositorySubject("artifact", digest("d"), digest("c"))
                    ),
                ),
            ),
        )
        for label, plan in variants:
            with self.subTest(label=label):
                plan_bytes = plan.canonical_bytes()
                authorization = authorized_one_run_fixture(
                    plan_bytes, nonce_seed=self.id() + label
                )
                with self.assertRaisesRegex(
                    HostRuntimeError, "activation binding"
                ):
                    self.runtime.create(
                        plan_bytes=plan_bytes,
                        standard_bytes=HOST_STANDARD_BYTES,
                        generation_id=GENERATION,
                        lease_deadline=LEASE_END,
                        authorization=authorization,
                        idempotency_key=f"binding-{label}",
                    )
        self.assertEqual(0, self.host.observe_calls)
        self.assertEqual(0, self.host.prepare_calls)
        self.assertEqual(0, self.host.execute_calls)

    def test_resume_reobserves_and_rejects_identity_trust_or_capability_drift(
        self,
    ) -> None:
        lease = self.create("drift-create")
        identity = self.host.identity
        starting_observations = self.host.observe_calls
        for field, value in (
            ("executable_digest", digest("a")),
            ("adapter_digest", digest("b")),
        ):
            with self.subTest(field=field):
                self.host.identity = replace(identity, **{field: value})
                with self.assertRaisesRegex(HostRecoveryRequired, "identity drifted"):
                    self.runtime.resume(
                        create_idempotency_key="drift-create",
                        poll_idempotency_key="stable-resume-poll",
                    )
                self.host.identity = identity

        self.host.trust_evidence_digest = digest("c")
        with self.assertRaisesRegex(HostRecoveryRequired, "identity drifted"):
            self.runtime.resume(
                create_idempotency_key="drift-create",
                poll_idempotency_key="stable-resume-poll",
            )
        self.host.trust_evidence_digest = digest("8")

        self.host.capabilities = tuple(
            item for item in self.host.capabilities if item != "read"
        )
        with self.assertRaisesRegex(HostRecoveryRequired, "identity drifted"):
            self.runtime.resume(
                create_idempotency_key="drift-create",
                poll_idempotency_key="stable-resume-poll",
            )
        self.host.capabilities = (
            "execute",
            "read",
            "checkpoint",
            "cancel",
            HOST_DEADLINE_CAPABILITY,
        )

        self.assertEqual(
            lease,
            self.runtime.resume(
                create_idempotency_key="drift-create",
                poll_idempotency_key="stable-resume-poll",
            ),
        )
        self.assertEqual(starting_observations + 5, self.host.observe_calls)

    def test_host_without_external_deadline_enforcement_is_denied(self) -> None:
        self.host.capabilities = tuple(
            item
            for item in self.host.capabilities
            if item != HOST_DEADLINE_CAPABILITY
        )
        with self.assertRaisesRegex(HostRuntimeError, "host lacks required"):
            self.create("missing-deadline-enforcement")
        self.assertEqual(0, self.host.prepare_calls)

    def test_idempotency_key_cannot_be_rebound_to_different_input(self) -> None:
        lease = self.create()
        self.runtime.message(
            lease=lease,
            node_id="node-1",
            input_bytes=b"one",
            idempotency_key="message-same",
        )
        with self.assertRaisesRegex(HostRuntimeError, "another request"):
            self.runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=b"two",
                idempotency_key="message-same",
            )
        self.assertEqual(self.host.execute_calls, 1)

    def test_message_aliases_converge_and_node_input_cannot_change(self) -> None:
        lease = self.create("message-alias-create")
        first = self.runtime.message(
            lease=lease,
            node_id="node-1",
            input_bytes=b"one semantic message",
            idempotency_key="message-alias-first",
        )
        alias = self.runtime.message(
            lease=lease,
            node_id="node-1",
            input_bytes=b"one semantic message",
            idempotency_key="message-alias-second",
        )
        self.assertEqual(first, alias)
        self.assertEqual(
            self.journal.latest("message-alias-first"),
            self.journal.latest("message-alias-second"),
        )
        with self.assertRaisesRegex(HostRuntimeError, "semantic operation"):
            self.runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=b"different input for the same node",
                idempotency_key="message-alias-different-input",
            )
        self.assertEqual(1, self.host.execute_calls)

    def test_concurrent_message_aliases_have_one_adapter_owner(self) -> None:
        lease = self.create("concurrent-alias-create")
        self.host.delay = 0.05
        keys = ("concurrent-alias-a", "concurrent-alias-b")
        outcomes: list[HostExecutionReceipt | HostRecoveryRequired] = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    self.runtime.message,
                    lease=lease,
                    node_id="node-1",
                    input_bytes=b"one concurrently aliased message",
                    idempotency_key=key,
                )
                for key in keys
            ]
            for future in futures:
                try:
                    outcomes.append(future.result())
                except HostRecoveryRequired as error:
                    outcomes.append(error)
        self.assertEqual(1, self.host.execute_calls)
        receipts = [
            item for item in outcomes if isinstance(item, HostExecutionReceipt)
        ]
        self.assertEqual(2, len(receipts))
        self.assertEqual(receipts[0], receipts[1])
        converged = self.runtime.message(
            lease=lease,
            node_id="node-1",
            input_bytes=b"one concurrently aliased message",
            idempotency_key=keys[1],
        )
        self.assertEqual(receipts[0], converged)
        self.assertEqual(1, self.host.execute_calls)

    def test_cross_handle_create_alias_waits_for_durable_owner(self) -> None:
        owner_in_prepare = threading.Event()
        alias_waiting = threading.Event()
        release_owner = threading.Event()

        class WaitingJournal(HostOperationJournal):
            def wait_for_terminal(
                self,
                key: str,
                *,
                timeout_seconds: float,
                monotonic: Callable[[], float],
            ) -> HostOperationRecord:
                alias_waiting.set()
                return super().wait_for_terminal(
                    key,
                    timeout_seconds=timeout_seconds,
                    monotonic=monotonic,
                )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cross-handle-create.sqlite3"
            with HostOperationJournal(path) as owner_journal:
                owner_journal.connection.execute("PRAGMA journal_mode=WAL").fetchone()
                with WaitingJournal(path) as alias_journal:
                    host = FakeHost()
                    original_prepare = host.prepare

                    def paused_prepare(**values: object) -> HostLease:
                        owner_in_prepare.set()
                        if not release_owner.wait(timeout=3):
                            raise RuntimeError("create owner was not released")
                        return original_prepare(**values)

                    host.prepare = paused_prepare  # type: ignore[method-assign]
                    owner_runtime = HostRuntime(
                        host,
                        owner_journal,
                        one_run_deadline=RUN_END,
                        clock=lambda: NOW,
                    )
                    alias_runtime = HostRuntime(
                        host,
                        alias_journal,
                        one_run_deadline=RUN_END,
                        clock=lambda: NOW,
                    )
                    authorization = authorized_one_run_fixture(
                        HOST_PLAN_BYTES,
                        nonce_seed=self.id() + "-cross-handle-create",
                    )

                    def create(runtime: HostRuntime, key: str) -> HostLease:
                        return runtime.create(
                            plan_bytes=HOST_PLAN_BYTES,
                            standard_bytes=HOST_STANDARD_BYTES,
                            generation_id=GENERATION,
                            lease_deadline=LEASE_END,
                            authorization=authorization,
                            idempotency_key=key,
                            timeout_seconds=1,
                        )

                    with ThreadPoolExecutor(max_workers=2) as pool:
                        owner = pool.submit(create, owner_runtime, "handle-create-owner")
                        self.assertTrue(owner_in_prepare.wait(timeout=3))
                        alias = pool.submit(create, alias_runtime, "handle-create-alias")
                        self.assertTrue(alias_waiting.wait(timeout=3))
                        release_owner.set()
                        owner_lease = owner.result(timeout=3)
                        alias_lease = alias.result(timeout=3)

                    self.assertEqual(owner_lease, alias_lease)
                    self.assertEqual(1, host.prepare_calls)
                    self.assertEqual(
                        owner_journal.latest("handle-create-owner"),
                        alias_journal.latest("handle-create-alias"),
                    )

    def test_cross_handle_message_alias_waits_for_durable_owner(self) -> None:
        owner_in_execute = threading.Event()
        alias_waiting = threading.Event()
        release_owner = threading.Event()

        class WaitingJournal(HostOperationJournal):
            def wait_for_terminal(
                self,
                key: str,
                *,
                timeout_seconds: float,
                monotonic: Callable[[], float],
            ) -> HostOperationRecord:
                alias_waiting.set()
                return super().wait_for_terminal(
                    key,
                    timeout_seconds=timeout_seconds,
                    monotonic=monotonic,
                )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cross-handle-message.sqlite3"
            with HostOperationJournal(path) as owner_journal:
                owner_journal.connection.execute("PRAGMA journal_mode=WAL").fetchone()
                host = FakeHost()
                owner_runtime = HostRuntime(
                    host,
                    owner_journal,
                    one_run_deadline=RUN_END,
                    clock=lambda: NOW,
                )
                authorization = authorized_one_run_fixture(
                    HOST_PLAN_BYTES,
                    nonce_seed=self.id() + "-cross-handle-message",
                )
                lease = owner_runtime.create(
                    plan_bytes=HOST_PLAN_BYTES,
                    standard_bytes=HOST_STANDARD_BYTES,
                    generation_id=GENERATION,
                    lease_deadline=LEASE_END,
                    authorization=authorization,
                    idempotency_key="handle-message-create",
                )
                with WaitingJournal(path) as alias_journal:
                    alias_runtime = HostRuntime(
                        host,
                        alias_journal,
                        one_run_deadline=RUN_END,
                        clock=lambda: NOW,
                    )
                    original_execute = host.execute

                    def paused_execute(
                        *, node_id: str, input_bytes: bytes, lease: HostLease
                    ) -> HostExecutionReceipt:
                        owner_in_execute.set()
                        if not release_owner.wait(timeout=3):
                            raise RuntimeError("message owner was not released")
                        return original_execute(
                            node_id=node_id,
                            input_bytes=input_bytes,
                            lease=lease,
                        )

                    host.execute = paused_execute  # type: ignore[method-assign]
                    payload = b"one cross-handle semantic message"

                    def message(runtime: HostRuntime, key: str) -> HostExecutionReceipt:
                        return runtime.message(
                            lease=lease,
                            node_id="node-1",
                            input_bytes=payload,
                            idempotency_key=key,
                            timeout_seconds=1,
                        )

                    with ThreadPoolExecutor(max_workers=2) as pool:
                        owner = pool.submit(
                            message, owner_runtime, "handle-message-owner"
                        )
                        self.assertTrue(owner_in_execute.wait(timeout=3))
                        alias = pool.submit(
                            message, alias_runtime, "handle-message-alias"
                        )
                        self.assertTrue(alias_waiting.wait(timeout=3))
                        release_owner.set()
                        owner_receipt = owner.result(timeout=3)
                        alias_receipt = alias.result(timeout=3)

                    self.assertEqual(owner_receipt, alias_receipt)
                    self.assertEqual(1, host.execute_calls)
                    self.assertEqual(
                        owner_journal.latest("handle-message-owner"),
                        alias_journal.latest("handle-message-alias"),
                    )

    def test_create_cancel_and_checkpoint_aliases_converge(self) -> None:
        lease = self.create("semantic-create-first")
        self.assertEqual(lease, self.create("semantic-create-alias"))
        self.assertEqual(1, self.host.prepare_calls)

        receipt = self.runtime.message(
            lease=lease,
            node_id="node-1",
            input_bytes=b"checkpoint aliases",
            idempotency_key="checkpoint-alias-message",
        )
        checkpoint_digest = canonical_checkpoint_digest(lease, receipt)
        first_checkpoint = self.runtime.checkpoint(
            lease=lease,
            receipt=receipt,
            checkpoint_digest=checkpoint_digest,
            candidate_digest=receipt.output_digest,
            idempotency_key="checkpoint-alias-first",
        )
        second_checkpoint = self.runtime.checkpoint(
            lease=lease,
            receipt=receipt,
            checkpoint_digest=checkpoint_digest,
            candidate_digest=receipt.output_digest,
            idempotency_key="checkpoint-alias-second",
        )
        self.assertEqual(first_checkpoint, second_checkpoint)

        first_cancel = self.runtime.cancel(
            lease=lease,
            reason="one semantic cancellation",
            idempotency_key="cancel-alias-first",
        )
        second_cancel = self.runtime.cancel(
            lease=lease,
            reason="one semantic cancellation",
            idempotency_key="cancel-alias-second",
        )
        self.assertEqual(first_cancel, second_cancel)
        with self.assertRaisesRegex(HostRuntimeError, "semantic operation"):
            self.runtime.cancel(
                lease=lease,
                reason="conflicting cancellation reason",
                idempotency_key="cancel-alias-conflict",
            )
        self.assertEqual(1, self.host.cancel_calls)

    def test_checkpoint_wrong_digest_cannot_poison_later_exact_recovery(self) -> None:
        lease = self.create("checkpoint-poison-create")
        receipt = self.runtime.message(
            lease=lease,
            node_id="node-1",
            input_bytes=b"checkpoint poison defense",
            idempotency_key="checkpoint-poison-message",
        )
        expected = canonical_checkpoint_digest(lease, receipt)
        with self.assertRaisesRegex(HostRuntimeError, "canonical host result"):
            self.runtime.checkpoint(
                lease=lease,
                receipt=receipt,
                checkpoint_digest=digest("0"),
                candidate_digest=receipt.output_digest,
                idempotency_key="checkpoint-poison-wrong",
            )
        self.assertIsNone(self.journal.latest("checkpoint-poison-wrong"))
        exact = self.runtime.checkpoint(
            lease=lease,
            receipt=receipt,
            checkpoint_digest=expected,
            candidate_digest=receipt.output_digest,
            idempotency_key="checkpoint-poison-exact",
        )
        self.assertEqual(
            exact,
            self.runtime.historical_checkpoint(
                lease=lease,
                receipt=receipt,
                checkpoint_digest=expected,
                candidate_digest=receipt.output_digest,
            ),
        )

    def test_concurrent_checkpoint_aliases_converge_on_one_journal_fact(self) -> None:
        lease = self.create("concurrent-checkpoint-create")
        receipt = self.runtime.message(
            lease=lease,
            node_id="node-1",
            input_bytes=b"concurrent checkpoint aliases",
            idempotency_key="concurrent-checkpoint-message",
        )
        expected = canonical_checkpoint_digest(lease, receipt)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    self.runtime.checkpoint,
                    lease=lease,
                    receipt=receipt,
                    checkpoint_digest=expected,
                    candidate_digest=receipt.output_digest,
                    idempotency_key=key,
                )
                for key in ("concurrent-checkpoint-a", "concurrent-checkpoint-b")
            ]
            checkpoints = [future.result() for future in futures]
        self.assertEqual(checkpoints[0], checkpoints[1])
        checkpoint_records = tuple(
            record
            for record in self.journal.records()
            if record.action == "checkpoint"
        )
        self.assertEqual(2, len(checkpoint_records))

    def test_create_rechecks_effective_deadline_before_prepare(self) -> None:
        now = [NOW]
        runtime = HostRuntime(
            self.host,
            self.journal,
            one_run_deadline=RUN_END,
            clock=lambda: now[0],
        )
        observe = self.host.observe

        def observe_then_expire(*, subject_id: str) -> HostObservation:
            result = observe(subject_id=subject_id)
            now[0] = datetime(2026, 9, 2, 12, 10, tzinfo=UTC)
            return result

        self.host.observe = observe_then_expire  # type: ignore[method-assign]
        with self.assertRaisesRegex(HostRuntimeError, "deadline has expired"):
            runtime.create(
                plan_bytes=HOST_PLAN_BYTES,
                standard_bytes=HOST_STANDARD_BYTES,
                generation_id=GENERATION,
                lease_deadline=LEASE_END,
                authorization=self.authorization,
                idempotency_key="advance-before-prepare",
            )
        self.assertEqual(1, self.host.observe_calls)
        self.assertEqual(0, self.host.prepare_calls)
        self.assertEqual(0, self.host.execute_calls)

    def test_create_rechecks_activation_lower_bound_before_prepare(self) -> None:
        now = [NOW]
        runtime = HostRuntime(
            self.host,
            self.journal,
            one_run_deadline=RUN_END,
            clock=lambda: now[0],
        )
        claim_activation = self.journal.claim_activation

        def claim_then_roll_back(**values) -> None:
            claim_activation(**values)
            now[0] = datetime(2026, 9, 2, 11, 59, tzinfo=UTC)

        self.journal.claim_activation = claim_then_roll_back  # type: ignore[method-assign]
        with self.assertRaisesRegex(HostRuntimeError, "not yet valid"):
            runtime.create(
                plan_bytes=HOST_PLAN_BYTES,
                standard_bytes=HOST_STANDARD_BYTES,
                generation_id=GENERATION,
                lease_deadline=LEASE_END,
                authorization=self.authorization,
                idempotency_key="rollback-before-prepare",
            )
        self.assertEqual(1, self.host.observe_calls)
        self.assertEqual(0, self.host.prepare_calls)
        latest = self.journal.latest("rollback-before-prepare")
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertIs(latest.state, HostOperationState.DENIED)

    def test_message_rechecks_lease_deadline_immediately_before_execute(self) -> None:
        lease = self.create("advance-before-message-create")
        now = [NOW]
        runtime = HostRuntime(
            self.host,
            self.journal,
            one_run_deadline=RUN_END,
            clock=lambda: now[0],
        )
        begin = runtime._begin  # noqa: SLF001

        def begin_then_expire(**values):
            result = begin(**values)
            now[0] = datetime(2026, 9, 2, 12, 10, tzinfo=UTC)
            return result

        runtime._begin = begin_then_expire  # type: ignore[method-assign]  # noqa: SLF001
        with self.assertRaises(HostRecoveryRequired):
            runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=b"deadline advanced before execute",
                idempotency_key="advance-before-message",
            )
        self.assertEqual(0, self.host.execute_calls)

    def test_cancel_rechecks_lease_deadline_immediately_before_adapter(self) -> None:
        lease = self.create("advance-before-cancel-create")
        now = [NOW]
        runtime = HostRuntime(
            self.host,
            self.journal,
            one_run_deadline=RUN_END,
            clock=lambda: now[0],
        )
        begin = runtime._begin  # noqa: SLF001

        def begin_then_expire(**values):
            result = begin(**values)
            now[0] = datetime(2026, 9, 2, 12, 10, tzinfo=UTC)
            return result

        runtime._begin = begin_then_expire  # type: ignore[method-assign]  # noqa: SLF001
        with self.assertRaises(HostRecoveryRequired):
            runtime.cancel(
                lease=lease,
                reason="deadline advanced before cancel",
                idempotency_key="advance-before-cancel",
            )
        self.assertEqual(0, self.host.cancel_calls)

    def test_legacy_conflicting_message_receipts_fail_journal_verification(
        self,
    ) -> None:
        lease = self.create("legacy-conflict-create")
        receipt = self.runtime.message(
            lease=lease,
            node_id="node-1",
            input_bytes=b"legacy conflict",
            idempotency_key="legacy-conflict-first",
        )
        first = self.journal.history("legacy-conflict-first")[0]
        conflicting = replace(
            receipt,
            receipt_id="legacy-conflicting-receipt",
            output_digest=digest("f"),
        )
        key = "legacy-conflict-second"
        intent = HostOperationRecord(
            key,
            "message",
            first.request_digest,
            HostOperationState.INTENT_RECORDED,
            1,
            None,
            None,
            None,
            None,
        )
        succeeded = HostOperationRecord(
            key,
            "message",
            first.request_digest,
            HostOperationState.SUCCEEDED,
            2,
            "execution-receipt",
            conflicting.to_document(),
            self.runtime.usage(),
            None,
        )
        previous: str | None = None
        self.journal.connection.execute(
            "INSERT INTO host_operation_aliases VALUES(?,?,?,?)",
            (key, key, "message", first.request_digest),
        )
        for record in (intent, succeeded):
            event_digest = canonical_digest(
                {"previous_digest": previous, "record": record.to_document()}
            )
            self.journal.connection.execute(
                """
                INSERT INTO host_operation_events(
                    idempotency_key, operation_sequence, action, request_digest,
                    payload_json, previous_digest, event_digest
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    key,
                    record.sequence,
                    record.action,
                    record.request_digest,
                    canonical_json_bytes(record.to_document()).decode(),
                    previous,
                    event_digest,
                ),
            )
            previous = event_digest
        self.journal.connection.commit()
        with self.assertRaisesRegex(HostRuntimeError, "unique semantic claim"):
            self.runtime.historical_message_success(
                lease=lease,
                node_id="node-1",
                input_digest=receipt.input_digest,
            )

    def test_concurrent_identical_effects_have_one_adapter_owner(self) -> None:
        def race(call):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(call) for _ in range(2)]
                results = []
                for future in futures:
                    try:
                        results.append(future.result())
                    except HostRecoveryRequired as error:
                        results.append(error)
                return results

        create_results = race(lambda: self.create("concurrent-create"))
        self.assertEqual(1, self.host.prepare_calls)
        leases = [item for item in create_results if isinstance(item, HostLease)]
        self.assertTrue(leases)
        lease = leases[0]

        self.host.delay = 0.05
        message_results = race(
            lambda: self.runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=b"concurrent exact message",
                idempotency_key="concurrent-message",
            )
        )
        self.assertEqual(1, self.host.execute_calls)
        self.assertTrue(
            any(isinstance(item, HostExecutionReceipt) for item in message_results)
        )
        self.host.delay = 0

        cancel_results = race(
            lambda: self.runtime.cancel(
                lease=lease,
                reason="concurrent exact cancel",
                idempotency_key="concurrent-cancel",
            )
        )
        self.assertEqual(1, self.host.cancel_calls)
        self.assertTrue(
            any(isinstance(item, HostExecutionReceipt) for item in cancel_results)
        )

    def test_cancel_claim_blocks_sequential_message_resume_and_cached_create(
        self,
    ) -> None:
        lease = self.create("lease-wide-cancel-create")
        cancelled = self.runtime.cancel(
            lease=lease,
            reason="lease-wide durable stop",
            idempotency_key="lease-wide-cancel",
        )
        self.assertIs(cancelled.state, HostReceiptState.CANCELLED)
        self.assertTrue(self.journal.cancellation_claimed(lease))
        with self.assertRaisesRegex(HostRuntimeError, "cancellation"):
            self.runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=b"must not execute after cancellation",
                idempotency_key="post-cancel-message",
            )
        with self.assertRaisesRegex(HostRuntimeError, "cancellation"):
            self.runtime.resume(
                create_idempotency_key="lease-wide-cancel-create",
                poll_idempotency_key="post-cancel-resume",
            )
        with self.assertRaisesRegex(HostRuntimeError, "cancellation"):
            self.create("lease-wide-cancel-create")
        self.assertEqual(0, self.host.execute_calls)
        self.assertEqual(1, self.host.prepare_calls)

    def test_cancel_claim_wins_race_before_any_later_message_admission(
        self,
    ) -> None:
        lease = self.create("cancel-race-create")
        cancel_entered = threading.Event()
        release_cancel = threading.Event()
        original_cancel = self.host.cancel

        def blocked_cancel(
            *, lease: HostLease, reason: str
        ) -> HostExecutionReceipt:
            cancel_entered.set()
            if not release_cancel.wait(timeout=3):
                raise RuntimeError("test did not release cancellation")
            return original_cancel(lease=lease, reason=reason)

        self.host.cancel = blocked_cancel  # type: ignore[method-assign]
        with ThreadPoolExecutor(max_workers=2) as pool:
            cancellation = pool.submit(
                self.runtime.cancel,
                lease=lease,
                reason="concurrent durable stop",
                idempotency_key="cancel-race-stop",
            )
            self.assertTrue(cancel_entered.wait(timeout=3))
            with self.assertRaisesRegex(HostRuntimeError, "cancellation"):
                self.runtime.message(
                    lease=lease,
                    node_id="node-1",
                    input_bytes=b"arrived after cancellation claim",
                    idempotency_key="cancel-race-message",
                )
            release_cancel.set()
            self.assertIs(
                cancellation.result(timeout=3).state,
                HostReceiptState.CANCELLED,
            )
        with self.assertRaisesRegex(HostRuntimeError, "cancellation"):
            self.runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=b"arrived after cancellation commit",
                idempotency_key="cancel-race-post-commit-message",
            )
        self.assertEqual(0, self.host.execute_calls)
        self.assertEqual(1, self.host.cancel_calls)

    def test_completion_seal_blocks_later_cancel_before_adapter_effect(self) -> None:
        lease = self.create("completion-before-cancel-create")
        receipt = self.runtime.message(
            lease=lease,
            node_id="node-1",
            input_bytes=b"completed before cancellation",
            idempotency_key="completion-before-cancel-message",
        )
        checkpoint_digest = canonical_checkpoint_digest(lease, receipt)
        self.runtime.checkpoint(
            lease=lease,
            receipt=receipt,
            checkpoint_digest=checkpoint_digest,
            candidate_digest=receipt.output_digest,
            idempotency_key="completion-before-cancel-checkpoint",
        )

        self.assertIsNone(self.runtime.seal_completion(lease))
        with self.assertRaisesRegex(HostRuntimeError, "completion"):
            self.runtime.cancel(
                lease=lease,
                reason="too late",
                idempotency_key="completion-before-cancel-stop",
            )
        self.assertEqual(0, self.host.cancel_calls)

    def test_completion_and_cancellation_have_one_atomic_terminal_winner(
        self,
    ) -> None:
        lease = self.create("completion-cancel-race-create")
        receipt = self.runtime.message(
            lease=lease,
            node_id="node-1",
            input_bytes=b"terminal race",
            idempotency_key="completion-cancel-race-message",
        )
        self.runtime.checkpoint(
            lease=lease,
            receipt=receipt,
            checkpoint_digest=canonical_checkpoint_digest(lease, receipt),
            candidate_digest=receipt.output_digest,
            idempotency_key="completion-cancel-race-checkpoint",
        )
        barrier = threading.Barrier(2)

        def complete() -> str | None:
            barrier.wait(timeout=3)
            return self.runtime.seal_completion(lease)

        def cancel() -> HostExecutionReceipt:
            barrier.wait(timeout=3)
            return self.runtime.cancel(
                lease=lease,
                reason="terminal race cancellation",
                idempotency_key="completion-cancel-race-stop",
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            complete_future = pool.submit(complete)
            cancel_future = pool.submit(cancel)
            try:
                completion_result: str | None | BaseException = (
                    complete_future.result(timeout=3)
                )
            except BaseException as error:
                completion_result = error
            try:
                cancellation_result: HostExecutionReceipt | BaseException = (
                    cancel_future.result(timeout=3)
                )
            except BaseException as error:
                cancellation_result = error

        if isinstance(cancellation_result, HostExecutionReceipt):
            self.assertEqual(
                "terminal race cancellation",
                self.runtime.seal_completion(lease),
            )
            self.assertEqual(1, self.host.cancel_calls)
            self.assertTrue(
                completion_result == "terminal race cancellation"
                or isinstance(completion_result, HostRecoveryRequired)
            )
        else:
            self.assertIsInstance(cancellation_result, HostRuntimeError)
            self.assertIsNone(completion_result)
            self.assertIsNone(self.runtime.seal_completion(lease))
            self.assertEqual(0, self.host.cancel_calls)

    def test_verify_uses_one_snapshot_during_cross_connection_cancel_commit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cross-connection-verify.sqlite3"
            with HostOperationJournal(path) as writer:
                writer.connection.execute("PRAGMA journal_mode=WAL").fetchone()
                host = FakeHost()
                authorization = authorized_one_run_fixture(
                    HOST_PLAN_BYTES, nonce_seed=self.id() + "-snapshot"
                )
                runtime = HostRuntime(
                    host,
                    writer,
                    one_run_deadline=RUN_END,
                    clock=lambda: NOW,
                )
                lease = runtime.create(
                    plan_bytes=HOST_PLAN_BYTES,
                    standard_bytes=HOST_STANDARD_BYTES,
                    generation_id=GENERATION,
                    lease_deadline=LEASE_END,
                    authorization=authorization,
                    idempotency_key="snapshot-create",
                )
                with HostOperationJournal(path) as reader:
                    snapshot_read = threading.Event()
                    release_reader = threading.Event()
                    cancel_intent_committed = threading.Event()
                    release_cancel = threading.Event()
                    original_rows = reader._rows  # noqa: SLF001
                    pause_once = [True]

                    def paused_rows(key: str | None = None):
                        rows = original_rows(key)
                        if key is None and pause_once[0]:
                            pause_once[0] = False
                            snapshot_read.set()
                            if not release_reader.wait(timeout=3):
                                raise RuntimeError("reader snapshot was not released")
                        return rows

                    reader._rows = paused_rows  # type: ignore[method-assign]  # noqa: SLF001
                    original_cancel = host.cancel

                    def cancel_after_commit(
                        *, lease: HostLease, reason: str
                    ) -> HostExecutionReceipt:
                        cancel_intent_committed.set()
                        if not release_cancel.wait(timeout=3):
                            raise RuntimeError("cancel adapter was not released")
                        return original_cancel(lease=lease, reason=reason)

                    host.cancel = cancel_after_commit  # type: ignore[method-assign]
                    with ThreadPoolExecutor(max_workers=2) as pool:
                        verification = pool.submit(reader.verify)
                        self.assertTrue(snapshot_read.wait(timeout=3))
                        cancellation = pool.submit(
                            runtime.cancel,
                            lease=lease,
                            reason="cross-connection snapshot cancellation",
                            idempotency_key="snapshot-cancel",
                        )
                        self.assertTrue(cancel_intent_committed.wait(timeout=3))
                        release_reader.set()
                        verification.result(timeout=3)
                        release_cancel.set()
                        receipt = cancellation.result(timeout=3)
                    self.assertIs(receipt.state, HostReceiptState.CANCELLED)
                    reader.verify()
                    self.assertEqual(
                        ("cross-connection snapshot cancellation", receipt),
                        runtime.committed_cancellation(lease),
                    )

    def test_repeated_cross_connection_cancel_and_completion_are_consistent(
        self,
    ) -> None:
        for iteration in range(8):
            with self.subTest(iteration=iteration), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "cross-connection-terminal.sqlite3"
                with HostOperationJournal(path) as primary:
                    primary.connection.execute("PRAGMA journal_mode=WAL").fetchone()
                    host = FakeHost()
                    authorization = authorized_one_run_fixture(
                        HOST_PLAN_BYTES,
                        nonce_seed=f"{self.id()}-terminal-{iteration}",
                    )
                    primary_runtime = HostRuntime(
                        host,
                        primary,
                        one_run_deadline=RUN_END,
                        clock=lambda: NOW,
                    )
                    lease = primary_runtime.create(
                        plan_bytes=HOST_PLAN_BYTES,
                        standard_bytes=HOST_STANDARD_BYTES,
                        generation_id=GENERATION,
                        lease_deadline=LEASE_END,
                        authorization=authorization,
                        idempotency_key=f"terminal-create-{iteration}",
                    )
                    receipt = primary_runtime.message(
                        lease=lease,
                        node_id="node-1",
                        input_bytes=f"terminal-{iteration}".encode(),
                        idempotency_key=f"terminal-message-{iteration}",
                    )
                    primary_runtime.checkpoint(
                        lease=lease,
                        receipt=receipt,
                        checkpoint_digest=canonical_checkpoint_digest(lease, receipt),
                        candidate_digest=receipt.output_digest,
                        idempotency_key=f"terminal-checkpoint-{iteration}",
                    )
                    with HostOperationJournal(path) as secondary:
                        secondary_runtime = HostRuntime(
                            host,
                            secondary,
                            one_run_deadline=RUN_END,
                            clock=lambda: NOW,
                        )
                        barrier = threading.Barrier(2)
                        reason = f"terminal cancellation {iteration}"

                        def complete() -> str | None:
                            barrier.wait(timeout=3)
                            return primary_runtime.seal_completion(lease)

                        def cancel() -> HostExecutionReceipt:
                            barrier.wait(timeout=3)
                            return secondary_runtime.cancel(
                                lease=lease,
                                reason=reason,
                                idempotency_key=f"terminal-cancel-{iteration}",
                            )

                        with ThreadPoolExecutor(max_workers=2) as pool:
                            complete_future = pool.submit(complete)
                            cancel_future = pool.submit(cancel)
                            try:
                                completion: str | None | BaseException = (
                                    complete_future.result(timeout=3)
                                )
                            except BaseException as error:
                                completion = error
                            try:
                                cancellation: HostExecutionReceipt | BaseException = (
                                    cancel_future.result(timeout=3)
                                )
                            except BaseException as error:
                                cancellation = error

                        primary.verify()
                        secondary.verify()
                        terminal = primary_runtime.seal_completion(lease)
                        if isinstance(cancellation, HostExecutionReceipt):
                            self.assertEqual(reason, terminal)
                            self.assertTrue(
                                completion == reason
                                or isinstance(completion, HostRecoveryRequired)
                            )
                        else:
                            self.assertIsInstance(cancellation, HostRuntimeError)
                            self.assertIn("completion", str(cancellation))
                            self.assertIsNone(completion)
                            self.assertIsNone(terminal)

    def test_create_key_cannot_be_rebound_to_another_activation(self) -> None:
        self.create("same-create")
        replacement = authorized_one_run_fixture(
            HOST_PLAN_BYTES, nonce_seed=self.id() + "-replacement"
        )
        with self.assertRaisesRegex(HostRuntimeError, "another request"):
            self.runtime.create(
                plan_bytes=HOST_PLAN_BYTES,
                standard_bytes=HOST_STANDARD_BYTES,
                generation_id=GENERATION,
                lease_deadline=LEASE_END,
                authorization=replacement,
                idempotency_key="same-create",
            )
        self.assertEqual(1, self.host.prepare_calls)

    def test_one_authorization_create_alias_converges_after_restart(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "host-claim.sqlite3"
            first_journal = HostOperationJournal(path)
            first_runtime = HostRuntime(
                self.host,
                first_journal,
                one_run_deadline=RUN_END,
                clock=lambda: NOW,
            )
            first_runtime.create(
                plan_bytes=HOST_PLAN_BYTES,
                standard_bytes=HOST_STANDARD_BYTES,
                generation_id=GENERATION,
                lease_deadline=LEASE_END,
                authorization=self.authorization,
                idempotency_key="durable-create-1",
            )
            first_journal.close()

            with HostOperationJournal(path) as reopened:
                restarted = HostRuntime(
                    self.host,
                    reopened,
                    one_run_deadline=RUN_END,
                    clock=lambda: NOW,
                )
                aliased = restarted.create(
                    plan_bytes=HOST_PLAN_BYTES,
                    standard_bytes=HOST_STANDARD_BYTES,
                    generation_id=GENERATION,
                    lease_deadline=LEASE_END,
                    authorization=self.authorization,
                    idempotency_key="durable-create-2",
                )
                self.assertEqual("lease-1", aliased.lease_id)
                self.assertEqual(1, self.host.prepare_calls)
                latest = reopened.latest("durable-create-2")
                self.assertIsNotNone(latest)
                assert latest is not None
                self.assertEqual(HostOperationState.SUCCEEDED, latest.state)

    def test_forged_one_run_is_denied_before_host_prepare(self) -> None:
        forged = object.__new__(AuthorizedOneRun)
        with self.assertRaisesRegex(HostRuntimeError, "sealed one-run"):
            self.runtime.create(
                plan_bytes=HOST_PLAN_BYTES,
                standard_bytes=HOST_STANDARD_BYTES,
                generation_id=GENERATION,
                lease_deadline=LEASE_END,
                authorization=forged,
                idempotency_key="forged-create",
            )
        self.assertEqual(0, self.host.prepare_calls)

    def test_forged_field_valid_lease_never_crosses_message_or_cancel_boundary(
        self,
    ) -> None:
        lease = self.create("forged-lease-create")
        substitutions = (
            ("lease_id", "lease-forged"),
            ("activation_digest", digest("a")),
            ("activation_proof_digest", digest("b")),
            ("nonce_digest", digest("c")),
            ("subject_id", digest("d")),
            ("host_identity_digest", digest("e")),
        )
        for field, value in substitutions:
            forged = replace(lease, **{field: value})
            with self.subTest(operation="message", field=field):
                with self.assertRaisesRegex(
                    HostRuntimeError, "journal-authenticated lease"
                ):
                    self.runtime.message(
                        lease=forged,
                        node_id="node-1",
                        input_bytes=b"forged-lease-input",
                        idempotency_key=f"forged-lease-message-{field}",
                    )
        forged = replace(lease, lease_id="lease-forged-cancel")
        with self.assertRaisesRegex(HostRuntimeError, "journal-authenticated lease"):
            self.runtime.cancel(
                lease=forged,
                reason="forged lease",
                idempotency_key="forged-lease-cancel",
            )
        self.assertEqual(0, self.host.execute_calls)
        self.assertEqual(0, self.host.cancel_calls)

    def test_public_journal_cannot_forge_authority_or_host_effect_provenance(
        self,
    ) -> None:
        forged_lease = HostLease(
            "lease-forged-without-authorization",
            self.host.identity.host_id,
            SUBJECT,
            GENERATION,
            AUTHORITY,
            ADAPTER_INVENTORY,
            False,
            digest("9"),
            digest("a"),
            digest("b"),
            "a" * 40,
            "b" * 40,
            digest("c"),
            "c" * 40,
            "d" * 40,
            digest("d"),
            digest("e"),
            digest("f"),
            "main",
            digest("0"),
            NOW_TEXT,
            False,
            self.host.identity.digest,
            self.host.trust_evidence_digest,
            BOUND_CAPABILITIES,
            NOW_TEXT,
            LEASE_END,
            ("node-1",),
            digest("1"),
        )
        request = {
            "lease": forged_lease.to_document(),
            "node_id": "node-1",
            "input_digest": digest("2"),
        }
        intent = HostOperationRecord(
            idempotency_key="forged-create-history",
            action="create",
            request_digest=canonical_digest(request),
            state=HostOperationState.INTENT_RECORDED,
            sequence=1,
            response_type=None,
            response=None,
            usage=None,
            reason=None,
        )
        succeeded = HostOperationRecord(
            idempotency_key="forged-create-history",
            action="create",
            request_digest=intent.request_digest,
            state=HostOperationState.SUCCEEDED,
            sequence=2,
            response_type="lease",
            response=forged_lease.to_document(),
            usage=self.runtime.usage(),
            reason=None,
        )
        for record in (intent, succeeded):
            with self.assertRaisesRegex(HostRuntimeError, "runtime-owned"):
                self.journal.append(record)
        with self.assertRaisesRegex(HostRuntimeError, "runtime-owned"):
            self.journal.bind_semantic_alias(
                alias_key="forged-alias",
                kind="message",
                scope_digest=digest("6"),
                request=request,
            )
        with self.assertRaisesRegex(HostRuntimeError, "runtime-owned"):
            self.journal.claim_activation(
                authorization=object.__new__(AuthorizedOneRun),
                create_idempotency_key="forged-create-history",
                create_request=request,
                host_identity_digest=self.host.identity.digest,
                claimed_at=NOW_TEXT,
            )
        with self.assertRaisesRegex(HostRuntimeError, "runtime-owned"):
            self.journal.claim_completion(
                forged_lease,
                claimed_at=NOW_TEXT,
            )

        forged_receipt = HostExecutionReceipt(
            "receipt-forged-without-authorization",
            forged_lease.lease_id,
            "node-1",
            HostReceiptState.SUCCEEDED,
            digest("2"),
            digest("3"),
            digest("4"),
            NOW_TEXT,
        )
        with self.assertRaisesRegex(HostRuntimeError, "journal-authenticated lease"):
            self.runtime.message(
                lease=forged_lease,
                node_id="node-1",
                input_bytes=b"never execute",
                idempotency_key="forged-no-auth-message",
            )
        with self.assertRaisesRegex(HostRuntimeError, "journal-authenticated lease"):
            self.runtime.cancel(
                lease=forged_lease,
                reason="never cancel",
                idempotency_key="forged-no-auth-cancel",
            )
        with self.assertRaisesRegex(HostRuntimeError, "journal-authenticated lease"):
            self.runtime.checkpoint(
                lease=forged_lease,
                receipt=forged_receipt,
                checkpoint_digest=digest("5"),
                candidate_digest=forged_receipt.output_digest,
                idempotency_key="forged-no-auth-checkpoint",
            )
        self.assertEqual(0, self.host.execute_calls)
        self.assertEqual(0, self.host.cancel_calls)
        self.assertEqual((), self.journal.history("forged-create-history"))

    def test_checkpoint_rejects_a_substituted_lease_even_for_a_real_receipt(
        self,
    ) -> None:
        lease = self.create("checkpoint-lease-create")
        receipt = self.runtime.message(
            lease=lease,
            node_id="node-1",
            input_bytes=b"real-message",
            idempotency_key="checkpoint-lease-message",
        )
        forged_lease = replace(lease, candidate_tree="f" * 40)
        with self.assertRaisesRegex(HostRuntimeError, "journal-authenticated lease"):
            self.runtime.checkpoint(
                lease=forged_lease,
                receipt=receipt,
                checkpoint_digest=digest("d"),
                candidate_digest=receipt.output_digest,
                idempotency_key="checkpoint-forged-lease",
            )
        self.assertIsNone(self.journal.latest("checkpoint-forged-lease"))

    def test_create_adoption_requires_exact_activation_and_candidate(self) -> None:
        proof = self.authorization.proof_document()
        request = {
            "plan_digest": PLAN,
            "generation_id": GENERATION,
            "authority_digest": AUTHORITY,
            "adapter_inventory_digest": ADAPTER_INVENTORY,
            "external_effects_required": False,
            "compilation_receipt": HOST_COMPILATION_RECEIPT,
            "subject_id": SUBJECT,
            "node_ids": ["node-1"],
            "nonce_digest": "sha256:"
            + sha256(self.authorization.nonce.encode("utf-8")).hexdigest(),
            "lease_deadline": LEASE_END,
            "activation_proof": proof,
            "required_capabilities": list(BOUND_CAPABILITIES),
        }
        original_prepare = self.host.prepare
        prepared: list[HostLease] = []

        def lose_prepare_result(**values) -> HostLease:
            prepared.append(original_prepare(**values))
            raise RuntimeError("host lease response was lost")

        self.host.prepare = lose_prepare_result  # type: ignore[method-assign]
        with self.assertRaises(HostRecoveryRequired):
            self.create("adopt-create")
        self.host.prepare = original_prepare  # type: ignore[method-assign]
        lease = prepared[0]
        for field, value in (
            ("activation_digest", digest("a")),
            ("activation_proof_digest", digest("b")),
            ("candidate_commit", "c" * 40),
            ("candidate_tree", "d" * 40),
            ("candidate_content_sha256", digest("e")),
            ("candidate_parent_commit", "e" * 40),
            ("candidate_parent_tree", "f" * 40),
            ("manifest_sha256", digest("0")),
            ("repository_id", digest("1")),
            ("request_sha256", digest("2")),
            ("target_branch", "other"),
            ("execution_client_sha256", digest("3")),
            ("activation_issued_at", "2026-09-02T12:00:01Z"),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(HostRuntimeError, "not bound"):
                    self.runtime.adopt(
                        operation_idempotency_key="adopt-create",
                        request=request,
                        response_type="lease",
                        response=replace(lease, **{field: value}),
                        evidence_digest=digest("f"),
                    )
        adopted = self.runtime.adopt(
            operation_idempotency_key="adopt-create",
            request=request,
            response_type="lease",
            response=lease,
            evidence_digest=digest("f"),
        )
        self.assertEqual(lease, adopted)

    def test_message_rejects_a_receipt_not_bound_to_the_exact_request(self) -> None:
        lease = self.create()

        def wrong_node_receipt(
            *, node_id: str, input_bytes: bytes, lease: HostLease
        ) -> HostExecutionReceipt:
            del node_id
            return HostExecutionReceipt(
                "receipt-wrong-node",
                lease.lease_id,
                "node-other",
                HostReceiptState.SUCCEEDED,
                "sha256:" + sha256(input_bytes).hexdigest(),
                digest("9"),
                digest("a"),
                NOW_TEXT,
            )

        self.host.execute = wrong_node_receipt  # type: ignore[method-assign]
        with self.assertRaisesRegex(HostRecoveryRequired, "requires adoption"):
            self.runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=b"exact-node-delta",
                idempotency_key="message-wrong-node",
            )
        latest = self.journal.latest("message-wrong-node")
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(HostOperationState.RECOVERABLE, latest.state)

    def test_receipt_observed_after_lease_expiry_is_recoverable(self) -> None:
        lease = self.create()

        def late_receipt(
            *, node_id: str, input_bytes: bytes, lease: HostLease
        ) -> HostExecutionReceipt:
            return HostExecutionReceipt(
                "receipt-late",
                lease.lease_id,
                node_id,
                HostReceiptState.SUCCEEDED,
                "sha256:" + sha256(input_bytes).hexdigest(),
                digest("9"),
                digest("a"),
                "2026-09-02T12:10:01Z",
            )

        self.host.execute = late_receipt  # type: ignore[method-assign]
        with self.assertRaisesRegex(HostRecoveryRequired, "requires adoption"):
            self.runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=b"late-result",
                idempotency_key="message-late",
            )

    def test_message_receipt_at_exclusive_lease_boundary_is_recoverable(self) -> None:
        now = [NOW]
        boundary_runtime = HostRuntime(
            self.host,
            self.journal,
            one_run_deadline=RUN_END,
            clock=lambda: now[0],
            adoption_verifier=lambda **_: True,
        )
        lease = boundary_runtime.create(
            plan_bytes=HOST_PLAN_BYTES,
            standard_bytes=HOST_STANDARD_BYTES,
            generation_id=GENERATION,
            lease_deadline=LEASE_END,
            authorization=self.authorization,
            idempotency_key="exclusive-message-create",
        )

        def boundary_receipt(
            *, node_id: str, input_bytes: bytes, lease: HostLease
        ) -> HostExecutionReceipt:
            now[0] = datetime(2026, 9, 2, 12, 10, tzinfo=UTC)
            return HostExecutionReceipt(
                "receipt-at-exclusive-boundary",
                lease.lease_id,
                node_id,
                HostReceiptState.SUCCEEDED,
                "sha256:" + sha256(input_bytes).hexdigest(),
                digest("9"),
                digest("a"),
                LEASE_END,
            )

        self.host.execute = boundary_receipt  # type: ignore[method-assign]
        with self.assertRaisesRegex(HostRecoveryRequired, "requires adoption"):
            boundary_runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=b"boundary-result",
                idempotency_key="exclusive-boundary-message",
            )

    def test_cancel_receipt_at_exclusive_lease_boundary_is_recoverable(self) -> None:
        now = [NOW]
        boundary_runtime = HostRuntime(
            self.host,
            self.journal,
            one_run_deadline=RUN_END,
            clock=lambda: now[0],
            adoption_verifier=lambda **_: True,
        )
        lease = boundary_runtime.create(
            plan_bytes=HOST_PLAN_BYTES,
            standard_bytes=HOST_STANDARD_BYTES,
            generation_id=GENERATION,
            lease_deadline=LEASE_END,
            authorization=self.authorization,
            idempotency_key="exclusive-cancel-create",
        )

        def boundary_cancel(*, lease: HostLease, reason: str) -> HostExecutionReceipt:
            now[0] = datetime(2026, 9, 2, 12, 10, tzinfo=UTC)
            return HostExecutionReceipt(
                "cancel-at-exclusive-boundary",
                lease.lease_id,
                lease.allowed_node_ids[0],
                HostReceiptState.CANCELLED,
                canonical_digest({"reason": reason}),
                None,
                digest("b"),
                LEASE_END,
            )

        self.host.cancel = boundary_cancel  # type: ignore[method-assign]
        with self.assertRaisesRegex(HostRecoveryRequired, "requires adoption"):
            boundary_runtime.cancel(
                lease=lease,
                reason="exclusive boundary",
                idempotency_key="exclusive-boundary-cancel",
            )

    def test_adoption_rejects_receipt_at_exclusive_lease_boundary(self) -> None:
        lease = self.create("exclusive-adopt-create")
        payload = b"ambiguous-boundary"

        def ambiguous(**_values):
            raise RuntimeError("lost result")

        self.host.execute = ambiguous  # type: ignore[method-assign]
        with self.assertRaises(HostRecoveryRequired):
            self.runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=payload,
                idempotency_key="exclusive-boundary-adopt",
            )
        request = {
            "lease": lease.to_document(),
            "node_id": "node-1",
            "input_digest": "sha256:" + sha256(payload).hexdigest(),
        }
        receipt = HostExecutionReceipt(
            "adopted-at-exclusive-boundary",
            lease.lease_id,
            "node-1",
            HostReceiptState.SUCCEEDED,
            request["input_digest"],
            digest("e"),
            digest("f"),
            LEASE_END,
        )
        with self.assertRaisesRegex(HostRuntimeError, "not bound"):
            self.runtime.adopt(
                operation_idempotency_key="exclusive-boundary-adopt",
                request=request,
                response_type="execution-receipt",
                response=receipt,
                evidence_digest=digest("0"),
            )

        runtime_boundary = HostRuntime(
            self.host,
            self.journal,
            one_run_deadline=RUN_END,
            clock=lambda: datetime(2026, 9, 2, 12, 15, tzinfo=UTC),
        )
        runtime_receipt = replace(
            receipt,
            observed_at=RUN_END,
        )
        self.assertFalse(
            runtime_boundary._receipt_time_is_bound(  # noqa: SLF001
                runtime_receipt,
                replace(lease, expires_at="2026-09-02T12:20:00Z"),
            )
        )

    def test_authenticated_historical_receipts_survive_clock_rollback(self) -> None:
        live = datetime(2026, 9, 2, 12, 6, tzinfo=UTC)
        rolled_back = datetime(2026, 9, 2, 12, 5, 30, tzinfo=UTC)
        now = [live]
        evidence_time = "2026-09-02T12:06:00Z"
        self.host.observed_at = evidence_time
        self.host.lease_issued_at = evidence_time
        self.host.receipt_observed_at = evidence_time
        runtime = HostRuntime(
            self.host,
            self.journal,
            one_run_deadline=RUN_END,
            clock=lambda: now[0],
            adoption_verifier=lambda **_: True,
        )

        message_authorization = authorized_one_run_fixture(
            HOST_PLAN_BYTES, nonce_seed=self.id() + "-historical-message"
        )
        message_lease = runtime.create(
            plan_bytes=HOST_PLAN_BYTES,
            standard_bytes=HOST_STANDARD_BYTES,
            generation_id=GENERATION,
            lease_deadline=LEASE_END,
            authorization=message_authorization,
            idempotency_key="historical-rollback-message-create",
        )
        payload = b"historical receipt survives rollback"
        message_receipt = runtime.message(
            lease=message_lease,
            node_id="node-1",
            input_bytes=payload,
            idempotency_key="historical-rollback-message",
        )
        runtime.checkpoint(
            lease=message_lease,
            receipt=message_receipt,
            checkpoint_digest=canonical_checkpoint_digest(
                message_lease, message_receipt
            ),
            candidate_digest=message_receipt.output_digest,
            idempotency_key="historical-rollback-checkpoint",
        )
        now[0] = rolled_back
        self.assertEqual(
            message_receipt,
            runtime.historical_message_success(
                lease=message_lease,
                node_id="node-1",
                input_digest=message_receipt.input_digest,
            ),
        )
        self.assertIsNone(runtime.seal_completion(message_lease))

        now[0] = live
        cancel_authorization = authorized_one_run_fixture(
            HOST_PLAN_BYTES, nonce_seed=self.id() + "-historical-cancel"
        )
        cancel_lease = runtime.create(
            plan_bytes=HOST_PLAN_BYTES,
            standard_bytes=HOST_STANDARD_BYTES,
            generation_id=GENERATION,
            lease_deadline=LEASE_END,
            authorization=cancel_authorization,
            idempotency_key="historical-rollback-cancel-create",
        )
        cancel_receipt = runtime.cancel(
            lease=cancel_lease,
            reason="historical rollback cancellation",
            idempotency_key="historical-rollback-cancel",
        )
        now[0] = rolled_back
        self.assertEqual(
            ("historical rollback cancellation", cancel_receipt),
            runtime.committed_cancellation(cancel_lease),
        )

        now[0] = live
        adoption_authorization = authorized_one_run_fixture(
            HOST_PLAN_BYTES, nonce_seed=self.id() + "-historical-adoption"
        )
        adoption_lease = runtime.create(
            plan_bytes=HOST_PLAN_BYTES,
            standard_bytes=HOST_STANDARD_BYTES,
            generation_id=GENERATION,
            lease_deadline=LEASE_END,
            authorization=adoption_authorization,
            idempotency_key="historical-rollback-adoption-create",
        )
        adoption_payload = b"adopt after clock rollback"

        def ambiguous(**_values):
            raise RuntimeError("host result was lost")

        self.host.execute = ambiguous  # type: ignore[method-assign]
        with self.assertRaises(HostRecoveryRequired):
            runtime.message(
                lease=adoption_lease,
                node_id="node-1",
                input_bytes=adoption_payload,
                idempotency_key="historical-rollback-adoption",
            )
        adoption_request = {
            "lease": adoption_lease.to_document(),
            "node_id": "node-1",
            "input_digest": "sha256:" + sha256(adoption_payload).hexdigest(),
        }
        adopted_receipt = HostExecutionReceipt(
            "historical-rollback-adopted-receipt",
            adoption_lease.lease_id,
            "node-1",
            HostReceiptState.SUCCEEDED,
            adoption_request["input_digest"],
            digest("e"),
            digest("f"),
            evidence_time,
        )
        now[0] = rolled_back
        self.assertEqual(
            adopted_receipt,
            runtime.adopt(
                operation_idempotency_key="historical-rollback-adoption",
                request=adoption_request,
                response_type="execution-receipt",
                response=adopted_receipt,
                evidence_digest=digest("0"),
            ),
        )

    def test_stale_or_future_observations_and_future_receipts_fail_closed(self) -> None:
        for label, observed_at in (
            ("stale", "2026-09-02T12:04:59Z"),
            ("future", "2026-09-02T12:05:01Z"),
        ):
            with self.subTest(operation="create", label=label):
                self.host.observed_at = observed_at
                with self.assertRaisesRegex(HostRuntimeError, label):
                    authorization = authorized_one_run_fixture(
                        HOST_PLAN_BYTES,
                        nonce_seed=self.id() + f"-{label}-observation-create",
                    )
                    self.runtime.create(
                        plan_bytes=HOST_PLAN_BYTES,
                        standard_bytes=HOST_STANDARD_BYTES,
                        generation_id=GENERATION,
                        lease_deadline=LEASE_END,
                        authorization=authorization,
                        idempotency_key=f"{label}-observation-create",
                    )
            with self.subTest(operation="poll", label=label):
                with self.assertRaisesRegex(HostRecoveryRequired, "new observation"):
                    self.runtime.poll(
                        subject_id=SUBJECT,
                        idempotency_key=f"{label}-observation-poll",
                    )
        self.host.observed_at = NOW_TEXT
        future_receipt_authorization = authorized_one_run_fixture(
            HOST_PLAN_BYTES,
            nonce_seed=self.id() + "-future-receipt-create",
        )
        lease = self.runtime.create(
            plan_bytes=HOST_PLAN_BYTES,
            standard_bytes=HOST_STANDARD_BYTES,
            generation_id=GENERATION,
            lease_deadline=LEASE_END,
            authorization=future_receipt_authorization,
            idempotency_key="future-receipt-create",
        )
        for label, observed_at in (
            ("stale", "2026-09-02T12:04:59Z"),
            ("future", "2026-09-02T12:05:01Z"),
        ):
            with self.subTest(operation="resume", label=label):
                self.host.observed_at = observed_at
                with self.assertRaises(HostRecoveryRequired):
                    self.runtime.resume(
                        create_idempotency_key="future-receipt-create",
                        poll_idempotency_key="resume-freshness",
                    )
        self.host.observed_at = NOW_TEXT

        def future_receipt(
            *, node_id: str, input_bytes: bytes, lease: HostLease
        ) -> HostExecutionReceipt:
            return HostExecutionReceipt(
                "receipt-future",
                lease.lease_id,
                node_id,
                HostReceiptState.SUCCEEDED,
                "sha256:" + sha256(input_bytes).hexdigest(),
                digest("9"),
                digest("a"),
                "2026-09-02T12:05:01Z",
            )

        self.host.execute = future_receipt  # type: ignore[method-assign]
        with self.assertRaisesRegex(HostRecoveryRequired, "requires adoption"):
            self.runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=b"future-result",
                idempotency_key="message-future",
            )

    def test_timeout_is_recoverable_and_never_automatically_reexecuted(self) -> None:
        lease = self.create()
        self.host.delay = 0.1
        with self.assertRaises(HostRecoveryRequired):
            self.runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=b"slow",
                idempotency_key="message-timeout",
                timeout_seconds=0.01,
            )
        self.assertEqual(0, self.host.completed_calls)
        with self.assertRaises(HostRecoveryRequired):
            self.runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=b"slow",
                idempotency_key="message-timeout",
                timeout_seconds=0.01,
            )
        time.sleep(0.12)
        self.assertEqual(self.host.execute_calls, 1)
        self.assertEqual(
            1,
            self.host.completed_calls,
            "the in-process timeout is detection, not thread containment",
        )
        latest = self.journal.latest("message-timeout")
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(
            latest.state,
            HostOperationState.RECOVERABLE,
        )

    def test_ambiguous_execution_can_be_adopted_only_for_exact_request(self) -> None:
        lease = self.create()
        payload = b"slow"
        self.host.delay = 0.1
        with self.assertRaises(HostRecoveryRequired):
            self.runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=payload,
                idempotency_key="message-adopt",
                timeout_seconds=0.01,
            )
        request = {
            "lease": lease.to_document(),
            "node_id": "node-1",
            "input_digest": "sha256:" + sha256(payload).hexdigest(),
        }
        adopted = HostExecutionReceipt(
            "receipt-adopted",
            lease.lease_id,
            "node-1",
            HostReceiptState.SUCCEEDED,
            request["input_digest"],
            digest("e"),
            digest("f"),
            NOW_TEXT,
        )
        with self.assertRaisesRegex(HostRuntimeError, "differs"):
            self.runtime.adopt(
                operation_idempotency_key="message-adopt",
                request={**request, "node_id": "node-other"},
                response_type="execution-receipt",
                response=adopted,
                evidence_digest=digest("0"),
            )
        self.runtime.adoption_verifier = lambda **_: False
        with self.assertRaisesRegex(HostRuntimeError, "not authenticated"):
            self.runtime.adopt(
                operation_idempotency_key="message-adopt",
                request=request,
                response_type="execution-receipt",
                response=adopted,
                evidence_digest=digest("0"),
            )
        self.runtime.adoption_verifier = lambda **_: True
        result = self.runtime.adopt(
            operation_idempotency_key="message-adopt",
            request=request,
            response_type="execution-receipt",
            response=adopted,
            evidence_digest=digest("0"),
        )
        self.assertEqual(result, adopted)
        retry = self.runtime.message(
            lease=lease,
            node_id="node-1",
            input_bytes=payload,
            idempotency_key="message-adopt",
        )
        self.assertEqual(retry, adopted)
        self.assertEqual(self.host.execute_calls, 1)

    def test_adoption_alias_is_durable_and_exact_retry_converges(self) -> None:
        lease = self.create("adoption-alias-create")
        payload = b"adoption alias payload"

        def ambiguous(**_values):
            raise RuntimeError("lost host result")

        self.host.execute = ambiguous  # type: ignore[method-assign]
        with self.assertRaises(HostRecoveryRequired):
            self.runtime.message(
                lease=lease,
                node_id="node-1",
                input_bytes=payload,
                idempotency_key="adoption-canonical-message",
            )
        request = {
            "lease": lease.to_document(),
            "node_id": "node-1",
            "input_digest": "sha256:" + sha256(payload).hexdigest(),
        }
        receipt = HostExecutionReceipt(
            "adoption-alias-receipt",
            lease.lease_id,
            "node-1",
            HostReceiptState.SUCCEEDED,
            request["input_digest"],
            digest("d"),
            digest("e"),
            NOW_TEXT,
        )
        first = self.runtime.adopt(
            operation_idempotency_key="adoption-public-alias",
            request=request,
            response_type="execution-receipt",
            response=receipt,
            evidence_digest=digest("f"),
        )
        again = self.runtime.adopt(
            operation_idempotency_key="adoption-public-alias",
            request=request,
            response_type="execution-receipt",
            response=receipt,
            evidence_digest=digest("f"),
        )
        self.assertEqual(first, again)
        with self.assertRaisesRegex(HostRuntimeError, "exact durable evidence"):
            self.runtime.adopt(
                operation_idempotency_key="adoption-public-alias",
                request=request,
                response_type="execution-receipt",
                response=receipt,
                evidence_digest=digest("0"),
            )
        self.assertEqual(
            self.journal.latest("adoption-public-alias"),
            self.journal.latest("adoption-canonical-message"),
        )

    def test_concurrent_conflicting_adoption_alias_can_bind_only_one_intent(
        self,
    ) -> None:
        def ambiguous(**_values):
            raise RuntimeError("lost host result")

        self.host.execute = ambiguous  # type: ignore[method-assign]
        cases = []
        for index in range(2):
            authorization = authorized_one_run_fixture(
                HOST_PLAN_BYTES,
                nonce_seed=self.id() + f"-activation-{index}",
            )
            lease = self.runtime.create(
                plan_bytes=HOST_PLAN_BYTES,
                standard_bytes=HOST_STANDARD_BYTES,
                generation_id=GENERATION,
                lease_deadline=LEASE_END,
                authorization=authorization,
                idempotency_key=f"conflicting-adoption-create-{index}",
            )
            payload = f"conflicting adoption {index}".encode()
            with self.assertRaises(HostRecoveryRequired):
                self.runtime.message(
                    lease=lease,
                    node_id="node-1",
                    input_bytes=payload,
                    idempotency_key=f"conflicting-adoption-message-{index}",
                )
            request = {
                "lease": lease.to_document(),
                "node_id": "node-1",
                "input_digest": "sha256:" + sha256(payload).hexdigest(),
            }
            receipt = HostExecutionReceipt(
                f"conflicting-adoption-receipt-{index}",
                lease.lease_id,
                "node-1",
                HostReceiptState.SUCCEEDED,
                request["input_digest"],
                digest(str(index + 1)),
                digest(str(index + 3)),
                NOW_TEXT,
            )
            cases.append((request, receipt))

        def adopt_case(index: int) -> HostExecutionReceipt:
            request, receipt = cases[index]
            adopted = self.runtime.adopt(
                operation_idempotency_key="one-shared-adoption-alias",
                request=request,
                response_type="execution-receipt",
                response=receipt,
                evidence_digest=digest("f"),
            )
            assert isinstance(adopted, HostExecutionReceipt)
            return adopted

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(adopt_case, index) for index in range(2)]
            outcomes: list[HostExecutionReceipt | HostRuntimeError] = []
            for future in futures:
                try:
                    outcomes.append(future.result())
                except HostRuntimeError as error:
                    outcomes.append(error)
        self.assertEqual(
            1,
            sum(isinstance(item, HostExecutionReceipt) for item in outcomes),
        )
        self.assertEqual(1, sum(isinstance(item, HostRuntimeError) for item in outcomes))
        bound = self.journal.latest("one-shared-adoption-alias")
        self.assertIsNotNone(bound)
        assert bound is not None
        loser_index = next(
            index
            for index, (_request, receipt) in enumerate(cases)
            if bound.response != receipt.to_document()
        )
        with self.assertRaisesRegex(HostRuntimeError, "rebound|another request"):
            adopt_case(loser_index)

    def test_cancel_adoption_requires_exact_cancelled_receipt(self) -> None:
        lease = self.create()
        reason = "bounded cancellation"

        def ambiguous_cancel(*, lease: HostLease, reason: str):
            del lease, reason
            raise RuntimeError("host result was lost")

        self.host.cancel = ambiguous_cancel  # type: ignore[method-assign]
        with self.assertRaises(HostRecoveryRequired):
            self.runtime.cancel(
                lease=lease,
                reason=reason,
                idempotency_key="cancel-adopt",
            )
        request = {"lease": lease.to_document(), "reason": reason}
        input_digest = canonical_digest({"reason": reason})
        for state in (HostReceiptState.FAILED, HostReceiptState.SUCCEEDED):
            with self.subTest(state=state):
                receipt = HostExecutionReceipt(
                    f"receipt-{state.value.lower()}",
                    lease.lease_id,
                    "node-1",
                    state,
                    input_digest,
                    digest("e")
                    if state is HostReceiptState.SUCCEEDED
                    else None,
                    digest("f"),
                    NOW_TEXT,
                )
                with self.assertRaisesRegex(HostRuntimeError, "not bound"):
                    self.runtime.adopt(
                        operation_idempotency_key="cancel-adopt",
                        request=request,
                        response_type="execution-receipt",
                        response=receipt,
                        evidence_digest=digest("0"),
                    )
        latest = self.journal.latest("cancel-adopt")
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(HostOperationState.RECOVERABLE, latest.state)

    def test_expired_lease_never_crosses_cancel_boundary(self) -> None:
        lease = self.create("expired-cancel-create")
        expired_runtime = HostRuntime(
            self.host,
            self.journal,
            one_run_deadline=RUN_END,
            clock=lambda: datetime(2026, 9, 2, 12, 10, 1, tzinfo=UTC),
        )
        with self.assertRaisesRegex(HostRuntimeError, "lease has expired"):
            expired_runtime.cancel(
                lease=lease,
                reason="too late",
                idempotency_key="expired-cancel",
            )
        self.assertEqual(0, self.host.cancel_calls)

    def test_clock_rollback_before_lease_issue_never_crosses_message_boundary(
        self,
    ) -> None:
        lease = self.create("rollback-message-create")
        rollback = HostRuntime(
            self.host,
            self.journal,
            one_run_deadline=RUN_END,
            clock=lambda: datetime(2026, 9, 2, 11, 59, tzinfo=UTC),
        )
        with self.assertRaisesRegex(HostRuntimeError, "not yet valid"):
            rollback.message(
                lease=lease,
                node_id="node-1",
                input_bytes=b"must not execute before issuance",
                idempotency_key="rollback-before-message",
            )
        self.assertEqual(0, self.host.execute_calls)
        self.assertIsNone(self.journal.latest("rollback-before-message"))

    def test_clock_rollback_before_lease_issue_never_crosses_cancel_boundary(
        self,
    ) -> None:
        lease = self.create("rollback-cancel-create")
        rollback = HostRuntime(
            self.host,
            self.journal,
            one_run_deadline=RUN_END,
            clock=lambda: datetime(2026, 9, 2, 11, 59, tzinfo=UTC),
        )
        with self.assertRaisesRegex(HostRuntimeError, "not yet valid"):
            rollback.cancel(
                lease=lease,
                reason="must not cancel before issuance",
                idempotency_key="rollback-before-cancel",
            )
        self.assertEqual(0, self.host.cancel_calls)
        self.assertIsNone(self.journal.latest("rollback-before-cancel"))

    def test_checkpoint_requires_a_journal_authenticated_message_receipt(
        self,
    ) -> None:
        lease = self.create("forged-checkpoint-create")
        forged = HostExecutionReceipt(
            "forged-receipt",
            lease.lease_id,
            "node-1",
            HostReceiptState.SUCCEEDED,
            digest("a"),
            digest("b"),
            digest("c"),
            NOW_TEXT,
        )
        with self.assertRaisesRegex(HostRuntimeError, "journal-authenticated"):
            self.runtime.checkpoint(
                lease=lease,
                receipt=forged,
                checkpoint_digest=digest("d"),
                candidate_digest=forged.output_digest,
                idempotency_key="forged-checkpoint",
            )
        self.assertIsNone(self.journal.latest("forged-checkpoint"))

    def test_checkpoint_binds_receipt_to_full_lease_not_reused_lease_id(
        self,
    ) -> None:
        first_lease = self.create("same-id-first-create")
        receipt = self.runtime.message(
            lease=first_lease,
            node_id="node-1",
            input_bytes=b"first activation input",
            idempotency_key="same-id-first-message",
        )
        second_authorization = authorized_one_run_fixture(
            HOST_PLAN_BYTES, nonce_seed=self.id() + "-second-activation"
        )
        second_lease = self.runtime.create(
            plan_bytes=HOST_PLAN_BYTES,
            standard_bytes=HOST_STANDARD_BYTES,
            generation_id=GENERATION,
            lease_deadline=LEASE_END,
            authorization=second_authorization,
            idempotency_key="same-id-second-create",
        )
        self.assertEqual(first_lease.lease_id, second_lease.lease_id)
        self.assertNotEqual(
            first_lease.activation_digest, second_lease.activation_digest
        )
        with self.assertRaisesRegex(HostRuntimeError, "message receipt"):
            self.runtime.checkpoint(
                lease=second_lease,
                receipt=receipt,
                checkpoint_digest=digest("d"),
                candidate_digest=receipt.output_digest,
                idempotency_key="same-id-replayed-checkpoint",
            )
        self.assertIsNone(self.journal.latest("same-id-replayed-checkpoint"))

    def test_dirty_host_and_authority_expansion_fail_before_prepare(self) -> None:
        self.host.clean = False
        with self.assertRaisesRegex(HostRuntimeError, "dirty"):
            self.create("dirty-create")
        self.assertEqual(self.host.prepare_calls, 0)
        with self.assertRaises(HostRuntimeError):
            self.runtime.create(
                plan_bytes=HOST_PLAN_BYTES,
                standard_bytes=HOST_STANDARD_BYTES,
                generation_id=GENERATION,
                lease_deadline="2026-09-02T17:00:00Z",
                authorization=self.authorization,
                idempotency_key="too-long",
            )

    def test_intent_only_restart_requires_recovery_and_usage_is_honest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "host.sqlite3"
            journal = HostOperationJournal(path)
            seed_runtime = HostRuntime(
                self.host,
                journal,
                one_run_deadline=RUN_END,
                clock=lambda: NOW,
            )
            seed_runtime._begin(  # noqa: SLF001 - emulate crash after runtime intent
                key="poll-crashed",
                action="poll",
                request={"subject_id": SUBJECT},
            )
            journal.close()
            with HostOperationJournal(path) as resumed_journal:
                resumed = HostRuntime(
                    self.host,
                    resumed_journal,
                    one_run_deadline=RUN_END,
                    clock=lambda: NOW,
                )
                started = time.monotonic()
                with self.assertRaisesRegex(
                    HostRecoveryRequired, "owner has not published"
                ):
                    resumed.poll(
                        subject_id=SUBJECT,
                        idempotency_key="poll-crashed",
                        timeout_seconds=0.02,
                    )
                self.assertGreaterEqual(time.monotonic() - started, 0.015)
            self.create("usage-create")
            usage = self.runtime.usage()
            self.assertIsNone(usage.model_input_tokens)
            self.assertIsNone(usage.model_output_tokens)

    def test_journal_rejects_boolean_schema_version(self) -> None:
        self.runtime.poll(subject_id=SUBJECT, idempotency_key="schema-version-poll")
        row = self.journal.connection.execute(
            "SELECT payload_json FROM host_operation_events WHERE global_sequence=1"
        ).fetchone()
        payload = json.loads(str(row[0]))
        payload["schema_version"] = True
        self.journal.connection.execute(
            "DROP TRIGGER host_operation_events_no_update"
        )
        self.journal.connection.execute(
            "UPDATE host_operation_events SET payload_json=? WHERE global_sequence=1",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")),),
        )
        self.journal.connection.commit()
        with self.assertRaisesRegex(HostRuntimeError, "unknown shape"):
            self.journal.verify()

    def test_boolean_timeout_is_rejected_before_adapter_or_journal(self) -> None:
        with self.assertRaisesRegex(HostRuntimeError, "timeout must be positive"):
            self.runtime.poll(
                subject_id=SUBJECT,
                idempotency_key="boolean-timeout-poll",
                timeout_seconds=True,  # type: ignore[arg-type]
            )
        self.assertEqual(0, self.host.observe_calls)
        self.assertIsNone(self.journal.latest("boolean-timeout-poll"))


if __name__ == "__main__":
    unittest.main()
