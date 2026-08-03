from __future__ import annotations

import unittest
from copy import deepcopy

import hive_mind_os
import hive_mind_os.foundation as foundation
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.full_role_output_contracts import (
    OUTPUT_FIELDS_BY_ROLE,
    validate_full_role_envelope,
)
from hive_mind_os.foundation.full_role_outputs import (
    compile_integrator_full_outputs,
    compile_optimizer_full_outputs,
    compile_steward_full_outputs,
)


class FullRoleOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.compilers = {
            "integrator": compile_integrator_full_outputs,
            "steward": compile_steward_full_outputs,
            "optimizer": compile_optimizer_full_outputs,
        }

    def test_all_twenty_two_outputs_compile_deterministically(self) -> None:
        self.assertEqual(sum(map(len, OUTPUT_FIELDS_BY_ROLE.values())), 22)
        for role, compiler in self.compilers.items():
            first = compiler()
            self.assertEqual(first, compiler())
            validate_full_role_envelope(first)
            self.assertEqual(tuple(first["outputs"]), OUTPUT_FIELDS_BY_ROLE[role])

    def test_each_output_has_a_distinct_version_and_digest(self) -> None:
        versions: set[str] = set()
        for compiler in self.compilers.values():
            envelope = compiler()
            for output in envelope["outputs"].values():
                self.assertNotIn(output["schema_version"], versions)
                versions.add(output["schema_version"])
            self.assertEqual(len(envelope["output_digests"]), len(envelope["outputs"]))
        self.assertEqual(len(versions), 22)

    def test_outputs_remain_not_run_or_structural_without_authority(self) -> None:
        for compiler in self.compilers.values():
            envelope = compiler()
            self.assertTrue(
                all(value is False for value in envelope["claims"].values())
            )
            for output in envelope["outputs"].values():
                self.assertEqual(output["authority"]["authority"], "none")
                self.assertFalse(output["authority"]["execution_authorized"])
                self.assertFalse(output["authority"]["release_authorized"])

    def test_optimizer_holdout_and_results_remain_unobserved(self) -> None:
        envelope = compile_optimizer_full_outputs()
        source = envelope["source_intake"]
        serialized = repr(source).lower()
        self.assertNotIn("holdout result", serialized)
        self.assertEqual(
            envelope["outputs"]["outcome_metrics"]["payload"]["observations"], []
        )
        self.assertEqual(
            envelope["outputs"]["comparator_results"]["payload"]["results"], []
        )
        self.assertEqual(
            envelope["outputs"]["regression_results"]["payload"]["results"], []
        )
        self.assertFalse(
            envelope["outputs"]["experiment_design"]["payload"]["executed"]
        )

    def test_digest_and_semantic_resealing_fail_closed(self) -> None:
        envelope = compile_optimizer_full_outputs()
        hostile = deepcopy(envelope)
        hostile["outputs"]["comparator_results"]["payload"]["results"] = [
            {"winner": "challenger"}
        ]
        with self.assertRaisesRegex(ValueError, "digest"):
            validate_full_role_envelope(hostile)
        hostile = deepcopy(envelope)
        hostile["claims"]["superiority_established"] = True
        with self.assertRaisesRegex(ValueError, "claim escalated"):
            validate_full_role_envelope(hostile)
        hostile = deepcopy(envelope)
        hostile["scope_digest"] = "sha256:" + "0" * 64
        for field, output in hostile["outputs"].items():
            output["scope_digest"] = hostile["scope_digest"]
            output["output_id"] = f"phase5p:optimizer:{field}:{hostile['scope_digest']}"
            hostile["output_digests"][field] = digest(output)
        hostile["envelope_digest"] = digest(
            {key: value for key, value in hostile.items() if key != "envelope_digest"}
        )
        with self.assertRaisesRegex(ValueError, "scope digest drifted"):
            validate_full_role_envelope(hostile)

    def test_source_intakes_and_outputs_are_defensively_copied(self) -> None:
        first = compile_integrator_full_outputs()
        first["outputs"]["contract_inventory"]["payload"]["contract_families"].clear()
        self.assertTrue(
            compile_integrator_full_outputs()["outputs"]["contract_inventory"][
                "payload"
            ]["contract_families"]
        )

    def test_modules_remain_package_private(self) -> None:
        for name in (
            "compile_integrator_full_outputs",
            "compile_steward_full_outputs",
            "compile_optimizer_full_outputs",
        ):
            self.assertFalse(hasattr(hive_mind_os, name))
            self.assertFalse(hasattr(foundation, name))


if __name__ == "__main__":
    unittest.main()
