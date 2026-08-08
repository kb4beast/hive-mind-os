from __future__ import annotations

import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from hive_mind_os.brain_kernel.local_assurance import (
    LocalAssuranceError,
    build_local_assurance_report,
    verify_local_assurance_artifact,
)


def digest(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


class LocalAssuranceArtifactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.commit = "a" * 40
        self.tree = "b" * 40

    def write(self, relative: str, contents: bytes) -> tuple[str, str]:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        return relative, digest(contents)

    def artifact(self) -> tuple[Path, Path]:
        receipts = []
        for index, name in enumerate(
            ("phase11-parity", "phase11-rollback", "security-regression", "recovery-regression"),
            start=1,
        ):
            path, receipt_digest = self.write(f"logs/{name}.log", f"{name}\n".encode())
            receipts.append(
                {
                    "name": name,
                    "status": "passed",
                    "digest": receipt_digest,
                    "command": ["python", "-m", "unittest", name],
                    "interpreter": "Python test fixture",
                    "transcript_path": path,
                }
            )
        summary = {
            "run_id": "p13-fixture",
            "code_digest": self.commit,
            "corpus_digest": digest(b"corpus"),
            "harness_digest": digest(b"harness"),
            "results_digest": digest(b"results"),
            "lane_digests": {"baseline": digest(b"baseline")},
            "verdict": {
                "disposition": "measurement-recorded",
                "judge_id": "judge",
                "lane_identities": ["lane"],
            },
        }
        summary_path, summary_digest = self.write(
            "benchmark/summary.json", json.dumps(summary, sort_keys=True).encode()
        )
        report = build_local_assurance_report(
            candidate_commit=self.commit,
            candidate_tree=self.tree,
            phase11_routes=(
                {
                    "route": "legacy-enqueue-v1",
                    "manifest_digest": digest(b"manifest"),
                    "parity_receipt_digest": receipts[0]["digest"],
                    "rollback_receipt_digest": receipts[1]["digest"],
                },
            ),
            benchmark_report=summary,
            test_receipts=receipts,
        )
        report_path = self.root / "assurance.json"
        report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
        manifest = {
            "schema_version": 1,
            "candidate_commit": self.commit,
            "candidate_tree": self.tree,
            "report_digest": report["report_digest"],
            "receipts": receipts,
            "benchmark_summary": {"path": summary_path, "digest": summary_digest},
        }
        manifest_path = self.root / "receipts.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
        return report_path, manifest_path

    def test_verifies_report_and_content_addressed_receipts(self) -> None:
        report, manifest = self.artifact()
        verified = verify_local_assurance_artifact(report, manifest)
        self.assertEqual(self.commit, verified["candidate_commit"])

    def test_rejects_mutated_transcript_and_unsafe_receipt_path(self) -> None:
        report, manifest = self.artifact()
        (self.root / "logs" / "phase11-parity.log").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(LocalAssuranceError, "digest"):
            verify_local_assurance_artifact(report, manifest)

        report, manifest = self.artifact()
        document = json.loads(manifest.read_text(encoding="utf-8"))
        document["receipts"][0]["transcript_path"] = "../outside.log"
        manifest.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(LocalAssuranceError, "relative"):
            verify_local_assurance_artifact(report, manifest)


if __name__ == "__main__":
    unittest.main()
