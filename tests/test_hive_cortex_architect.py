from __future__ import annotations

import unittest

from hive_mind_os.brain_kernel.architect import (
    AcceptanceMapping,
    Architect,
    ArchitectureArtifact,
    ArchitectureValidationError,
    DesignOption,
    InterfaceContract,
)


def artifact(*, mappings: tuple[AcceptanceMapping, ...] | None = None, **changes: object) -> ArchitectureArtifact:
    values: dict[str, object] = {
        "objective": "Make role design handoffs operational and independently checkable.",
        "options": (
            DesignOption("typed-artifact", "Use an immutable typed artifact.", ("requires explicit schema maintenance",)),
            DesignOption("free-form-text", "Use narrative-only output.", ("cannot be deterministically checked",)),
        ),
        "selected_option": "typed-artifact",
        "interfaces": (
            InterfaceContract("architect-to-builder", "architect", "builder", "immutable design artifact", "additive only"),
        ),
        "invariants": ("Architect output cannot approve or execute an effect.",),
        "threats": ("Unmapped acceptance criteria could conceal an incomplete design.",),
        "data_classification": ("repository metadata",),
        "compatibility_impact": "Additive module with no persisted-state migration.",
        "migration_plan": "Adopt the artifact at new Architect call sites.",
        "rollback_plan": "Revert the isolated candidate while retaining evidence.",
        "acceptance_mappings": mappings
        or (
            AcceptanceMapping("alternatives", ("options",), ("test_alternatives_are_explicit",)),
            AcceptanceMapping("rollback", ("rollback_plan",), ("test_rollback_is_required",)),
        ),
    }
    values.update(changes)
    return ArchitectureArtifact(**values)  # type: ignore[arg-type]


class ArchitectureArtifactTests(unittest.TestCase):
    def test_architect_produces_complete_deterministic_handoff(self) -> None:
        result = Architect().produce(artifact(), sealed_criteria=("alternatives", "rollback"))
        self.assertEqual("typed-artifact", result.selected_option)
        self.assertEqual(result.digest, Architect().produce(result, sealed_criteria=("rollback", "alternatives")).digest)
        mapping = result.to_document()["acceptance_mappings"]
        self.assertEqual("alternatives", mapping[0]["criterion_id"])  # type: ignore[index]
        self.assertTrue(mapping[0]["design_refs"])  # type: ignore[index]
        self.assertTrue(mapping[0]["verification_refs"])  # type: ignore[index]

    def test_requires_explicit_competing_options_and_tradeoffs(self) -> None:
        with self.assertRaisesRegex(ArchitectureValidationError, "at least two options"):
            artifact(options=(DesignOption("only", "Only choice", ("unsafe",)),))
        with self.assertRaisesRegex(ArchitectureValidationError, "option tradeoffs"):
            DesignOption("missing", "Missing tradeoff", ())

    def test_rejects_selected_option_outside_the_comparison(self) -> None:
        with self.assertRaisesRegex(ArchitectureValidationError, "selected option"):
            artifact(selected_option="invented")

    def test_requires_exact_design_and_verification_acceptance_coverage(self) -> None:
        with self.assertRaisesRegex(ArchitectureValidationError, "missing: rollback"):
            artifact(mappings=(AcceptanceMapping("alternatives", ("options",), ("test",)),)).validate_against(("alternatives", "rollback"))
        with self.assertRaisesRegex(ArchitectureValidationError, "acceptance verification references"):
            AcceptanceMapping("alternatives", ("options",), ())

    def test_rejects_missing_mandatory_risk_and_recovery_details(self) -> None:
        with self.assertRaisesRegex(ArchitectureValidationError, "threats"):
            artifact(threats=())
        with self.assertRaisesRegex(ArchitectureValidationError, "migration plan"):
            artifact(migration_plan="")
        with self.assertRaisesRegex(ArchitectureValidationError, "rollback plan"):
            artifact(rollback_plan="")


if __name__ == "__main__":
    unittest.main()
