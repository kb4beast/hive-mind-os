from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.brain_kernel.dag_runtime import (
    ISOLATION_ASSURANCE,
    SPECIALIST_ROLES,
    ArtifactRequirement,
    ArtifactType,
    DagNode,
    DagPlan,
    DagValidationError,
    ExecutableDagRuntime,
    NodeStatus,
    SpecialistContext,
    SpecialistHandler,
    SpecialistResult,
)

CANDIDATE = canonical_digest({"candidate": "dag-runtime-tests"})


def artifact_type(role: str) -> ArtifactType:
    schema_id = f"test/{role}"
    return ArtifactType(
        schema_id,
        "1",
        canonical_digest({"schema_id": schema_id, "version": 1}),
    )


def plan(*, nodes: tuple[DagNode, ...] | None = None) -> DagPlan:
    if nodes is not None:
        return DagPlan("test-eight-specialists", nodes)
    types = {role: artifact_type(role) for role in SPECIALIST_ROLES}

    def node(
        node_id: str,
        role: str,
        dependencies: tuple[tuple[str, str], ...] = (),
        *,
        scope: tuple[str, ...] = (),
    ) -> DagNode:
        return DagNode(
            node_id,
            role,
            f"executor:{role}",
            tuple(value[0] for value in dependencies),
            tuple(
                ArtifactRequirement(
                    source,
                    types[source_role].schema_id,
                    types[source_role].schema_version,
                )
                for source, source_role in dependencies
            ),
            types[role],
            write_scope=scope,
            native_symbol=f"native:{role}",
        )

    return DagPlan(
        "test-eight-specialists",
        (
            node("01-orchestrator", "orchestrator"),
            node("02-explorer", "explorer", (("01-orchestrator", "orchestrator"),)),
            node("03-architect", "architect", (("02-explorer", "explorer"),)),
            node(
                "04-builder",
                "builder",
                (("03-architect", "architect"),),
                scope=("output.txt",),
            ),
            node("05-curator", "curator", (("04-builder", "builder"),)),
            node("06-integrator", "integrator", (("03-architect", "architect"),)),
            node("07-steward", "steward", (("02-explorer", "explorer"),)),
            node(
                "08-optimizer",
                "optimizer",
                (
                    ("05-curator", "curator"),
                    ("06-integrator", "integrator"),
                    ("07-steward", "steward"),
                ),
            ),
        ),
    )


def handlers(
    *,
    delays: dict[str, float] | None = None,
    failures: frozenset[str] = frozenset(),
    counters: dict[str, int] | None = None,
    intervals: dict[str, tuple[float, float]] | None = None,
) -> dict[str, SpecialistHandler]:
    result: dict[str, SpecialistHandler] = {}
    for role in SPECIALIST_ROLES:

        async def execute(
            context: SpecialistContext, *, role: str = role
        ) -> SpecialistResult:
            if counters is not None:
                counters[role] = counters.get(role, 0) + 1
            started = time.monotonic()
            await asyncio.sleep((delays or {}).get(role, 0.001))
            if intervals is not None:
                intervals[role] = (started, time.monotonic())
            if role in failures:
                raise RuntimeError(f"retained adverse evidence for {role}")
            if role == "builder":
                context.write_text("output.txt", "bounded output\n")
            return SpecialistResult(
                {"role": role, "input_count": len(context.artifacts)},
                True,
                f"native:{role}",
            )

        result[role] = execute
    return result


class DagPlanValidationTests(unittest.TestCase):
    def test_requires_all_eight_roles_once_and_unique_executors(self) -> None:
        valid = plan()
        self.assertEqual(set(SPECIALIST_ROLES), {node.role for node in valid.nodes})
        with self.assertRaisesRegex(
            DagValidationError, "every specialist role exactly once"
        ):
            plan(nodes=valid.nodes[:-1])
        duplicated = (*valid.nodes[:-1], replace(valid.nodes[-1], role="steward"))
        with self.assertRaisesRegex(DagValidationError, "duplicates"):
            plan(nodes=duplicated)
        same_identity = tuple(
            replace(node, executor_id="executor:shared")
            if node.role == "curator"
            else node
            for node in valid.nodes
        )
        same_identity = tuple(
            replace(node, executor_id="executor:shared")
            if node.role == "builder"
            else node
            for node in same_identity
        )
        with self.assertRaisesRegex(DagValidationError, "unique executor"):
            plan(nodes=same_identity)

    def test_typed_edges_must_exactly_match_the_producer(self) -> None:
        valid = plan()
        explorer = valid.nodes[1]
        wrong = replace(
            explorer,
            required_artifacts=(
                ArtifactRequirement("01-orchestrator", "wrong/schema", "1"),
            ),
        )
        with self.assertRaisesRegex(DagValidationError, "does not produce"):
            plan(nodes=(valid.nodes[0], wrong, *valid.nodes[2:]))
        with self.assertRaisesRegex(DagValidationError, "type every dependency"):
            plan(
                nodes=(
                    valid.nodes[0],
                    replace(explorer, required_artifacts=()),
                    *valid.nodes[2:],
                )
            )

    def test_overlapping_write_scopes_require_a_dependency_path(self) -> None:
        valid = plan()
        architect = replace(valid.nodes[2], write_scope=("shared",))
        steward = replace(valid.nodes[6], write_scope=("shared/result.json",))
        nodes = tuple(
            architect
            if node.role == "architect"
            else steward
            if node.role == "steward"
            else node
            for node in valid.nodes
        )
        with self.assertRaisesRegex(DagValidationError, "overlapping write scopes"):
            plan(nodes=nodes)


class ExecutableDagRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_dependency_ready_nodes_genuinely_overlap(self) -> None:
        intervals: dict[str, tuple[float, float]] = {}
        with tempfile.TemporaryDirectory() as temporary:
            result = await ExecutableDagRuntime(
                temporary, candidate_digest=CANDIDATE
            ).run(
                plan(),
                handlers(
                    delays={"architect": 0.08, "steward": 0.08},
                    intervals=intervals,
                ),
            )
        architect = intervals["architect"]
        steward = intervals["steward"]
        explorer = intervals["explorer"]
        self.assertLess(max(architect[0], steward[0]), min(architect[1], steward[1]))
        self.assertLessEqual(explorer[1], architect[0])
        self.assertLessEqual(explorer[1], steward[0])
        self.assertGreaterEqual(result.max_observed_parallelism, 2)
        self.assertTrue(
            all(value.status is NodeStatus.SUCCEEDED for value in result.receipts)
        )

    async def test_receipt_and_event_order_ignore_completion_timing(self) -> None:
        first_delays = {
            role: index * 0.002 for index, role in enumerate(SPECIALIST_ROLES)
        }
        second_delays = {
            role: index * 0.002 for index, role in enumerate(reversed(SPECIALIST_ROLES))
        }
        with (
            tempfile.TemporaryDirectory() as first,
            tempfile.TemporaryDirectory() as second,
        ):
            one = await ExecutableDagRuntime(first, candidate_digest=CANDIDATE).run(
                plan(), handlers(delays=first_delays)
            )
            two = await ExecutableDagRuntime(second, candidate_digest=CANDIDATE).run(
                plan(), handlers(delays=second_delays)
            )
        self.assertEqual(one.logical_digest, two.logical_digest)
        self.assertEqual(
            [value.receipt_digest for value in one.receipts],
            [value.receipt_digest for value in two.receipts],
        )
        self.assertEqual(list(range(1, 9)), [value.sequence for value in one.events])
        self.assertEqual(
            tuple(value.node_id for value in one.receipts), plan().topological_order
        )

    async def test_failure_blocks_only_descendants_and_preserves_peer_evidence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = await ExecutableDagRuntime(
                temporary, candidate_digest=CANDIDATE
            ).run(plan(), handlers(failures=frozenset({"architect"})))
        self.assertIs(NodeStatus.FAILED, result.receipt_for("03-architect").status)
        self.assertIn(
            "retained adverse evidence",
            result.receipt_for("03-architect").error_message or "",
        )
        self.assertIs(NodeStatus.SUCCEEDED, result.receipt_for("07-steward").status)
        for node_id in ("04-builder", "05-curator", "06-integrator", "08-optimizer"):
            self.assertIs(NodeStatus.BLOCKED, result.receipt_for(node_id).status)

    async def test_completed_nodes_are_idempotent_on_resume(self) -> None:
        counters: dict[str, int] = {}
        with tempfile.TemporaryDirectory() as temporary:
            runtime = ExecutableDagRuntime(temporary, candidate_digest=CANDIDATE)
            first = await runtime.run(plan(), handlers(counters=counters))
            second = await runtime.run(plan(), handlers(counters=counters))
        self.assertEqual({role: 1 for role in SPECIALIST_ROLES}, counters)
        self.assertEqual(first.logical_digest, second.logical_digest)
        self.assertEqual(0, second.max_observed_parallelism)

    async def test_external_resume_is_dependency_closed_and_does_not_repeat_effects(
        self,
    ) -> None:
        first_counters: dict[str, int] = {}
        resumed_counters: dict[str, int] = {}
        with tempfile.TemporaryDirectory() as temporary:
            first = await ExecutableDagRuntime(
                temporary, candidate_digest=CANDIDATE
            ).run(plan(), handlers(counters=first_counters))
            resumed = await ExecutableDagRuntime(
                temporary, candidate_digest=CANDIDATE
            ).run(
                plan(),
                handlers(counters=resumed_counters),
                resume_receipts=first.receipts,
            )
            with self.assertRaisesRegex(DagValidationError, "dependency-closed"):
                await ExecutableDagRuntime(temporary, candidate_digest=CANDIDATE).run(
                    plan(),
                    handlers(),
                    resume_receipts=(first.receipt_for("02-explorer"),),
                )
            forged = (
                replace(
                    first.receipts[0],
                    native_evidence=False,
                    invoked_symbol="generic-fallback",
                ),
                *first.receipts[1:],
            )
            with self.assertRaisesRegex(DagValidationError, "lacks native evidence"):
                await ExecutableDagRuntime(temporary, candidate_digest=CANDIDATE).run(
                    plan(), handlers(), resume_receipts=forged
                )
        self.assertEqual({role: 1 for role in SPECIALIST_ROLES}, first_counters)
        self.assertEqual({}, resumed_counters)
        self.assertEqual(first.logical_digest, resumed.logical_digest)

    async def test_generic_fallback_cannot_claim_native_evidence(self) -> None:
        registry = handlers()

        async def generic(_: SpecialistContext) -> SpecialistResult:
            return SpecialistResult({"claim": "generic"}, False, "generic-fallback")

        registry["builder"] = generic
        with tempfile.TemporaryDirectory() as temporary:
            result = await ExecutableDagRuntime(
                temporary, candidate_digest=CANDIDATE
            ).run(plan(), registry)
        builder = result.receipt_for("04-builder")
        self.assertIs(NodeStatus.FAILED, builder.status)
        self.assertEqual("NativeEvidenceRequired", builder.error_type)
        self.assertFalse(builder.native_evidence)

    async def test_scope_and_path_escape_fail_closed_with_honest_sandbox_label(
        self,
    ) -> None:
        registry = handlers()

        async def out_of_scope(context: SpecialistContext) -> SpecialistResult:
            context.write_text("undeclared.txt", "escape\n")
            return SpecialistResult({"role": "builder"}, True, "native:builder")

        registry["builder"] = out_of_scope
        with tempfile.TemporaryDirectory() as temporary:
            result = await ExecutableDagRuntime(
                temporary, candidate_digest=CANDIDATE
            ).run(plan(), registry)
        receipt = result.receipt_for("04-builder")
        self.assertIs(NodeStatus.FAILED, receipt.status)
        self.assertEqual("WorkspaceViolation", receipt.error_type)
        self.assertIn("undeclared.txt", receipt.error_message or "")
        self.assertEqual(ISOLATION_ASSURANCE, receipt.isolation_assurance)
        self.assertIn("not-an-os-sandbox", receipt.isolation_assurance)

    async def test_parent_path_escape_is_observed_and_unrelated_peer_can_finish(
        self,
    ) -> None:
        registry = handlers()

        def escape(context: SpecialistContext) -> SpecialistResult:
            (context.workspace.parent / "escape.txt").write_text(
                "outside node workspace\n", encoding="utf-8"
            )
            return SpecialistResult({"role": "builder"}, True, "native:builder")

        registry["builder"] = escape
        with tempfile.TemporaryDirectory() as temporary:
            result = await ExecutableDagRuntime(
                temporary, candidate_digest=CANDIDATE, max_concurrency=1
            ).run(plan(), registry)
            self.assertTrue((Path(temporary) / "workspaces" / "escape.txt").is_file())
        self.assertEqual(
            "WorkspaceViolation", result.receipt_for("04-builder").error_type
        )
        self.assertIs(NodeStatus.SUCCEEDED, result.receipt_for("06-integrator").status)


if __name__ == "__main__":
    unittest.main()
