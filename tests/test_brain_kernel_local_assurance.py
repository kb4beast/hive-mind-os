from __future__ import annotations

import unittest

from hive_mind_os.brain_kernel.local_assurance import (
    LocalAssuranceError,
    build_local_assurance_report,
)


def digest(character: str) -> str:
    return "sha256:" + character * 64


class LocalAssuranceTests(unittest.TestCase):
    candidate_commit = "a" * 40
    candidate_tree = "b" * 40

    def benchmark(self) -> dict[str, object]:
        return {
            "run_id": "p13-local-fixture",
            "code_digest": self.candidate_commit,
            "corpus_digest": digest("c"),
            "harness_digest": digest("d"),
            "results_digest": digest("e"),
            "lane_digests": {"hive-mind": digest("f"), "baseline": digest("0")},
            "verdict": {
                "disposition": "measurement-recorded",
                "judge_id": "local-measurement-judge",
                "lane_identities": ["hive-lane", "baseline-lane"],
            },
        }

    @staticmethod
    def receipt(name: str, character: str) -> dict[str, str]:
        return {"name": name, "status": "passed", "digest": digest(character)}

    @staticmethod
    def route() -> dict[str, str]:
        return {
            "route": "legacy-enqueue-v1",
            "manifest_digest": digest("1"),
            "parity_receipt_digest": digest("2"),
            "rollback_receipt_digest": digest("3"),
        }

    def receipts(self) -> tuple[dict[str, str], ...]:
        return (
            self.receipt("phase11-parity", "4"),
            self.receipt("phase11-rollback", "5"),
            self.receipt("security-regression", "6"),
            self.receipt("recovery-regression", "7"),
        )

    def report(self) -> dict[str, object]:
        return build_local_assurance_report(
            candidate_commit=self.candidate_commit,
            candidate_tree=self.candidate_tree,
            phase11_routes=(self.route(),),
            benchmark_report=self.benchmark(),
            test_receipts=self.receipts(),
        )

    def test_report_is_deterministic_and_cannot_promote(self) -> None:
        first = self.report()
        second = self.report()

        self.assertEqual(first, second)
        self.assertEqual(self.candidate_commit, first["candidate_commit"])
        self.assertEqual(self.candidate_tree, first["candidate_tree"])
        self.assertFalse(first["release_ready"])
        self.assertFalse(first["production_ready"])
        self.assertFalse(first["comparative_claim_authorized"])
        self.assertFalse(first["signed_attestation_present"])
        self.assertFalse(first["real_provider_used"])
        self.assertTrue(str(first["report_digest"]).startswith("sha256:"))

    def test_mismatched_candidate_or_non_measurement_verdict_fails_closed(self) -> None:
        benchmark = self.benchmark()
        benchmark["code_digest"] = "c" * 40
        with self.assertRaisesRegex(LocalAssuranceError, "candidate"):
            build_local_assurance_report(
                candidate_commit=self.candidate_commit,
                candidate_tree=self.candidate_tree,
                phase11_routes=(self.route(),),
                benchmark_report=benchmark,
                test_receipts=self.receipts(),
            )

        benchmark = self.benchmark()
        benchmark["verdict"] = {"disposition": "adopt", "judge_id": "judge", "lane_identities": []}
        with self.assertRaisesRegex(LocalAssuranceError, "measurement"):
            build_local_assurance_report(
                candidate_commit=self.candidate_commit,
                candidate_tree=self.candidate_tree,
                phase11_routes=(self.route(),),
                benchmark_report=benchmark,
                test_receipts=self.receipts(),
            )

    def test_missing_route_or_security_recovery_receipts_fails_closed(self) -> None:
        with self.assertRaisesRegex(LocalAssuranceError, "Phase 11"):
            build_local_assurance_report(
                candidate_commit=self.candidate_commit,
                candidate_tree=self.candidate_tree,
                phase11_routes=(),
                benchmark_report=self.benchmark(),
                test_receipts=(),
            )

        with self.assertRaisesRegex(LocalAssuranceError, "security-regression"):
            build_local_assurance_report(
                candidate_commit=self.candidate_commit,
                candidate_tree=self.candidate_tree,
                phase11_routes=(self.route(),),
                benchmark_report=self.benchmark(),
                test_receipts=(
                    self.receipt("phase11-parity", "4"),
                    self.receipt("phase11-rollback", "5"),
                    self.receipt("recovery-regression", "7"),
                ),
            )


if __name__ == "__main__":
    unittest.main()
