from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from hive_mind_os.cohort_journal import (
    CohortJournalError,
    CohortJournalEventKind,
    FileCohortJournalStore,
)
from hive_mind_os.cohort_policy import CohortExecutionPolicy
from hive_mind_os.cohort_runtime import (
    CohortRunStatus,
    CohortRuntime,
    ConvergenceResult,
    PackageRunResult,
    PackageRunState,
    VerificationResult,
)
from hive_mind_os.outcome_graph import OutcomeGraphSpec, OutcomeWorkPackage


def package(package_id: str, *dependencies: str) -> OutcomeWorkPackage:
    return OutcomeWorkPackage(
        package_id,
        (f"outcome-{package_id}",),
        dependencies=dependencies,
    )


class CohortJournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.graph = OutcomeGraphSpec(
            (package("foundation"), package("delivery", "foundation")),
            "sha256:" + "7" * 64,
            maximum_concurrent=2,
        )

    def runtime(self) -> CohortRuntime:
        return CohortRuntime(
            CohortExecutionPolicy(), FileCohortJournalStore(self.root)
        )

    def test_interrupted_run_resumes_completed_packages(self) -> None:
        executions: list[str] = []
        interrupted = True

        def execute(item: OutcomeWorkPackage, *_: Any) -> PackageRunResult:
            nonlocal interrupted
            executions.append(item.package_id)
            if item.package_id == "delivery" and interrupted:
                interrupted = False
                raise KeyboardInterrupt("simulated process interruption")
            return PackageRunResult(
                item.package_id,
                PackageRunState.SUCCEEDED,
                {"artifact": item.package_id},
            )

        with self.assertRaises(KeyboardInterrupt):
            self.runtime().execute(
                graph=self.graph,
                run_id="RUN-resume",
                kickoff_context={"objective": "durable delivery"},
                execute_package=execute,
                converge=lambda *_: ConvergenceResult(True, {}),
                verify=lambda *_: VerificationResult(True),
            )

        result = self.runtime().execute(
            graph=self.graph,
            run_id="RUN-resume",
            kickoff_context={"objective": "durable delivery"},
            execute_package=execute,
            converge=lambda *_: ConvergenceResult(True, {"merged": True}),
            verify=lambda *_: VerificationResult(True, ("focused-tests",)),
        )

        self.assertIs(result.status, CohortRunStatus.SUCCEEDED)
        self.assertEqual(1, executions.count("foundation"))
        self.assertEqual(2, executions.count("delivery"))
        self.assertEqual("foundation", result.package("foundation").output["artifact"])

    def test_digest_chain_detects_retained_event_tamper(self) -> None:
        self.runtime().execute(
            graph=OutcomeGraphSpec(
                (package("only"),), "sha256:" + "8" * 64
            ),
            run_id="RUN-tamper",
            kickoff_context={},
            execute_package=lambda item, *_: PackageRunResult(
                item.package_id, PackageRunState.SUCCEEDED, {"value": "original"}
            ),
            converge=lambda *_: ConvergenceResult(True, {}),
            verify=lambda *_: VerificationResult(True),
        )
        result_path = next(
            path
            for path in self.root.glob("*/event-*.json")
            if json.loads(path.read_text(encoding="utf-8"))["kind"]
            == CohortJournalEventKind.PACKAGE_RESULT.value
        )
        document = json.loads(result_path.read_text(encoding="utf-8"))
        document["payload"]["output"]["value"] = "tampered"
        result_path.write_text(
            json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(CohortJournalError, "digest chain mismatch"):
            FileCohortJournalStore(self.root).events("RUN-tamper")

    def test_completed_run_is_returned_exactly_once_without_callbacks(self) -> None:
        calls = {"package": 0, "converge": 0, "verify": 0}

        def execute(item: OutcomeWorkPackage, *_: Any) -> PackageRunResult:
            calls["package"] += 1
            return PackageRunResult(
                item.package_id,
                PackageRunState.SUCCEEDED,
                {"stable": True, "nested": [{"package": item.package_id}]},
            )

        def converge(*_: Any) -> ConvergenceResult:
            calls["converge"] += 1
            return ConvergenceResult(
                True, {"candidate": "sealed", "packages": ["foundation", "delivery"]}
            )

        def verify(*_: Any) -> VerificationResult:
            calls["verify"] += 1
            return VerificationResult(True, ("terminal",))

        arguments = {
            "graph": self.graph,
            "run_id": "RUN-once",
            "kickoff_context": {"items": [1, 2]},
            "execute_package": execute,
            "converge": converge,
            "verify": verify,
        }
        first = self.runtime().execute(**arguments)
        second = self.runtime().execute(**arguments)

        self.assertEqual(first, second)
        self.assertEqual({"package": 2, "converge": 1, "verify": 1}, calls)
        events = FileCohortJournalStore(self.root).events("RUN-once")
        self.assertEqual(
            1,
            sum(
                event.kind is CohortJournalEventKind.RUN_COMPLETED
                for event in events
            ),
        )
        self.assertEqual(
            2,
            sum(
                event.kind is CohortJournalEventKind.PACKAGE_RESULT
                for event in events
            ),
        )

    def test_resume_can_be_explicitly_disabled(self) -> None:
        graph = OutcomeGraphSpec((package("only"),), "sha256:" + "9" * 64)
        arguments = {
            "graph": graph,
            "run_id": "RUN-no-resume",
            "kickoff_context": {},
            "execute_package": lambda item, *_: PackageRunResult(
                item.package_id, PackageRunState.SUCCEEDED, {}
            ),
            "converge": lambda *_: ConvergenceResult(True, {}),
            "verify": lambda *_: VerificationResult(True),
        }
        self.runtime().execute(**arguments)
        with self.assertRaisesRegex(ValueError, "resume was disabled"):
            self.runtime().execute(**arguments, resume=False)


if __name__ == "__main__":
    unittest.main()
