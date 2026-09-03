from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INTAKE_PATH = ROOT / "evidence/audits/v4-successor-recovery/SOURCE-INTAKE.json"
ARCHIVE_PATH = ROOT / "evidence/sources/v4-successor-recovery/SOURCE-ARCHIVE.json"
COURT_PATH = ROOT / "evidence/courts/CASE-V4-SUCCESSOR-RECOVERY-2026-09-02.json"
C77_RECEIPT_PATH = ROOT / "evidence/audits/v4-successor-recovery/REMOTE-CI-PUSH-ATTEMPT-3.json"
C78_RECEIPT_PATH = ROOT / "evidence/audits/v4-successor-recovery/REMOTE-CI-PULL-REQUEST-ATTEMPT-3.json"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class V4SourceProvenanceTests(unittest.TestCase):
    def assert_artifact(
        self,
        record: dict[str, Any],
        *,
        path_field: str = "path",
        bytes_field: str = "bytes",
        digest_field: str = "sha256",
    ) -> Path:
        path = ROOT / record[path_field]
        self.assertTrue(path.is_file(), record[path_field])
        self.assertEqual(record[bytes_field], path.stat().st_size)
        self.assertEqual(record[digest_field], digest(path))
        return path

    def test_every_registered_source_has_digest_bound_local_bytes(self) -> None:
        intake = json.loads(INTAKE_PATH.read_text(encoding="utf-8"))
        archive = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
        archive_binding = intake["source_archive"]
        self.assertEqual(archive_binding["bytes"], ARCHIVE_PATH.stat().st_size)
        self.assertEqual(archive_binding["sha256"], digest(ARCHIVE_PATH))

        sources = {item["source_id"]: item for item in intake["sources"]}
        archived = {item["source_id"]: item for item in archive["sources"]}
        expected_ids = {f"SRC-V4-{number:03d}" for number in range(1, 14)}
        self.assertEqual(expected_ids, set(sources))
        self.assertEqual(expected_ids, set(archived))
        self.assertEqual(list(sources), archive_binding["source_ids"])
        self.assertEqual([], intake["unavailable_sources"])
        self.assertEqual([], archive["unavailable_sources"])
        for source_id, source in sources.items():
            self.assertEqual(source_id, source["archive_binding"]["entry"])

        local_draft = archived["SRC-V4-001"]
        self.assert_artifact(local_draft)
        self.assert_artifact(
            local_draft,
            path_field="provenance_path",
            bytes_field="provenance_bytes",
            digest_field="provenance_sha256",
        )

        pull_set = archived["SRC-V4-002"]
        self.assert_artifact(pull_set["derived_assessment"])
        self.assertEqual(list(range(157, 165)), [item["number"] for item in pull_set["pull_requests"]])
        for pull in pull_set["pull_requests"]:
            for role in ("pull", "files", "reviews"):
                self.assert_artifact(pull[role])

        reused_intake = ROOT / archived["SRC-V4-003"]["source_intake_path"]
        reused_archive = ROOT / archived["SRC-V4-003"]["archive_path"]
        self.assertEqual(archived["SRC-V4-003"]["source_intake_sha256"], digest(reused_intake))
        self.assertEqual(archived["SRC-V4-003"]["archive_sha256"], digest(reused_archive))
        with tarfile.open(reused_archive, "r:") as source_tar:
            for source_id in ("SRC-V4-003", "SRC-V4-004", "SRC-V4-005"):
                record = archived[source_id]
                member = source_tar.getmember(record["member"])
                self.assertEqual(record["member_bytes"], member.size)
                stream = source_tar.extractfile(member)
                self.assertIsNotNone(stream)
                assert stream is not None
                self.assertEqual(
                    record["member_sha256"],
                    "sha256:" + hashlib.sha256(stream.read()).hexdigest(),
                )

        for artifact in archived["SRC-V4-006"]["files"]:
            self.assert_artifact(artifact)
        for source_id in ("SRC-V4-007", "SRC-V4-008", "SRC-V4-009", "SRC-V4-010"):
            record = archived[source_id]
            self.assert_artifact(record)
            self.assertEqual(record["license_sha256"], digest(ROOT / record["license_path"]))
        predecessor = archived["SRC-V4-011"]
        self.assert_artifact(predecessor)
        self.assert_artifact(
            predecessor,
            path_field="provenance_path",
            bytes_field="provenance_bytes",
            digest_field="provenance_sha256",
        )

        for source_id in ("SRC-V4-012", "SRC-V4-013"):
            record = archived[source_id]
            for artifact in record["artifacts"]:
                self.assert_artifact(artifact)
            self.assertEqual(record["license_sha256"], digest(ROOT / record["license_path"]))

        validator = archived["SRC-V4-013"]
        wheel = next(
            ROOT / artifact["path"]
            for artifact in validator["artifacts"]
            if artifact["role"] == "wheel"
        )
        with zipfile.ZipFile(wheel) as archive_file:
            metadata = archive_file.read("spdx_tools-0.8.5.dist-info/METADATA").decode(
                "utf-8"
            )
        self.assertIn("Name: spdx-tools", metadata)
        self.assertIn("Version: 0.8.5", metadata)
        self.assertIn("License-Expression: Apache-2.0", metadata)

    def test_source_claims_are_atomic_bidirectional_and_time_bound(self) -> None:
        intake = json.loads(INTAKE_PATH.read_text(encoding="utf-8"))
        archive = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
        court = json.loads(COURT_PATH.read_text(encoding="utf-8"))
        sources = {item["source_id"]: item for item in intake["sources"]}
        claims = {item["claim_id"]: item for item in intake["atomic_claims"]}
        counterclaims = {
            item["counterclaim_id"]: item for item in intake["counterclaims"]
        }
        court_claim_ids = {item["claim_id"] for item in court["claims"]}

        self.assertEqual(
            [f"CLM-V4-{number:03d}" for number in range(1, 25)],
            list(claims),
        )
        self.assertEqual(
            [f"CTR-V4-{number:03d}" for number in range(1, 10)],
            list(counterclaims),
        )
        self.assertLessEqual(
            datetime.fromisoformat(intake["intake_started_at_utc"].replace("Z", "+00:00")),
            datetime.fromisoformat(
                intake["last_archive_capture_at_utc"].replace("Z", "+00:00")
            ),
        )
        self.assertEqual(
            intake["last_archive_capture_at_utc"], archive["captured_at_utc"]
        )
        archive_finalized = datetime.fromisoformat(
            archive["captured_at_utc"].replace("Z", "+00:00")
        )
        archived = {item["source_id"]: item for item in archive["sources"]}
        for source_id, source in sources.items():
            observed = source["observed_or_retrieved_at_utc"]
            self.assertTrue(observed.endswith("Z"))
            self.assertIsNotNone(
                datetime.fromisoformat(observed.replace("Z", "+00:00")).tzinfo
            )
            archive_time = archived[source_id].get(
                "captured_at_utc", archived[source_id].get("retrieved_at_utc")
            )
            self.assertIsInstance(archive_time, str)
            self.assertLessEqual(
                datetime.fromisoformat(archive_time.replace("Z", "+00:00")),
                archive_finalized,
            )
            for claim_id in source["supports_claim_ids"]:
                self.assertIn(source_id, claims[claim_id]["source_ids"])
            for counterclaim_id in source["supports_counterclaim_ids"]:
                self.assertIn(source_id, counterclaims[counterclaim_id]["source_ids"])

        for source_id in ("SRC-V4-007", "SRC-V4-008", "SRC-V4-009"):
            self.assertIn(
                "no commit-signature verification evidence was retained",
                sources[source_id]["provenance"],
            )

        for claim_id, claim in claims.items():
            self.assertTrue(claim["statement"])
            self.assertTrue(claim["intake_status"])
            self.assertTrue(set(claim["source_ids"]).issubset(sources))
            self.assertTrue(set(claim["counterclaim_ids"]).issubset(counterclaims))
            self.assertTrue(set(claim["court_claim_ids"]).issubset(court_claim_ids))
            for source_id in claim["source_ids"]:
                self.assertIn(claim_id, sources[source_id]["supports_claim_ids"])
        for counterclaim_id, counterclaim in counterclaims.items():
            self.assertTrue(counterclaim["statement"])
            self.assertTrue(set(counterclaim["source_ids"]).issubset(sources))
            self.assertTrue(
                set(counterclaim["court_claim_ids"]).issubset(court_claim_ids)
            )
            for source_id in counterclaim["source_ids"]:
                self.assertIn(
                    counterclaim_id, sources[source_id]["supports_counterclaim_ids"]
                )

    def test_open_pr_record_is_explicitly_a_limited_scout_assessment(self) -> None:
        assessment = json.loads(
            (
                ROOT
                / "evidence/audits/v4-successor-recovery/OPEN-PR-DISPOSITIONS.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual("hive-mind-open-pr-scout-assessment-v2", assessment["kind"])
        self.assertFalse(assessment["court_disposition"])
        self.assertIn("no complete-list response was archived", assessment["scope"])
        self.assertEqual(
            list(range(157, 165)),
            [item["number"] for item in assessment["pull_requests"]],
        )
        self.assertTrue(
            all("scout_recommendation" in item for item in assessment["pull_requests"])
        )

    def test_local_draft_bundle_is_complete_and_reproduces_the_exact_source_tip(self) -> None:
        archive = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
        record = next(
            item for item in archive["sources"] if item["source_id"] == "SRC-V4-001"
        )
        bundle = self.assert_artifact(record)
        environment = {
            name: value
            for name, value in os.environ.items()
            if not name.upper().startswith("GIT_")
        }
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(
                ["git", "init", "--quiet", str(repository)],
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            verified = subprocess.run(
                ["git", "-C", str(repository), "bundle", "verify", str(bundle)],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, verified.returncode, verified.stderr + verified.stdout)
            self.assertIn("complete history", verified.stderr + verified.stdout)
            heads = subprocess.run(
                ["git", "bundle", "list-heads", str(bundle)],
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            self.assertEqual(
                [
                    "540bd310f2f58d7c335897c40f3ac8b44d4de712 "
                    "refs/heads/codex/generic-v4-main-activation"
                ],
                heads,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "fetch",
                    "--quiet",
                    str(bundle),
                    "refs/heads/codex/generic-v4-main-activation:refs/heads/source-v4",
                ],
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            observed = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repository),
                    "show",
                    "-s",
                    "--format=%H%n%T%n%P",
                    "refs/heads/source-v4",
                ],
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.splitlines()
            self.assertEqual(
                [
                    "540bd310f2f58d7c335897c40f3ac8b44d4de712",
                    "abb7ecd6d2c2f2e149dbdf1faeb89618d837c284",
                    "04ba84f663a0fd67aebb5ab562fbdce7a321b104",
                ],
                observed,
            )

    def test_provider_snapshots_match_the_claimed_pr_and_r4_run_identities(self) -> None:
        archive = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
        archived = {item["source_id"]: item for item in archive["sources"]}
        pull_set = archived["SRC-V4-002"]
        for pull in pull_set["pull_requests"]:
            document = json.loads((ROOT / pull["pull"]["path"]).read_text(encoding="utf-8"))
            reviews = json.loads((ROOT / pull["reviews"]["path"]).read_text(encoding="utf-8"))
            files = json.loads((ROOT / pull["files"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(pull["number"], document["number"])
            self.assertEqual(pull["head"], document["head"]["sha"])
            self.assertEqual("59a5364501c5e49ceb28574aad7a4ac1512291b9", document["base"]["sha"])
            self.assertEqual([], reviews)
            self.assertTrue(files)

        r4_files = {
            item["role"]: ROOT / item["path"] for item in archived["SRC-V4-006"]["files"]
        }
        run = json.loads(r4_files["run"].read_text(encoding="utf-8"))
        jobs = json.loads(r4_files["jobs"].read_text(encoding="utf-8"))
        artifacts = json.loads(r4_files["artifacts"].read_text(encoding="utf-8"))
        self.assertEqual(33694910734, run["id"])
        self.assertEqual("ce692c0145d9c7611b34383974fde1c78903c5ef", run["head_sha"])
        self.assertEqual("success", run["conclusion"])
        self.assertTrue(any(job["name"] == "unit-tests (Python 3.14)" for job in jobs["jobs"]))
        self.assertTrue(any(item["id"] == 9871406573 for item in artifacts["artifacts"]))

    def test_c77_attested_invalid_sbom_and_validator_receipts_are_preserved(self) -> None:
        receipt = json.loads(C77_RECEIPT_PATH.read_text(encoding="utf-8"))
        self.assertEqual("V4-SBOM-P2-002", receipt["finding"]["finding_id"])
        self.assertEqual(33749585546, receipt["run"]["run_id"])
        self.assertEqual("3743ad1e2bafaac2efd2b19d91510086ce48d478", receipt["candidate"]["commit"])
        self.assert_artifact(receipt["artifact"]["sbom"])
        self.assert_artifact(receipt["attestation"]["verification_transcript"])
        self.assert_artifact(receipt["attestation"]["statement"])
        self.assert_artifact(receipt["finding"]["validator_transcript"])
        self.assertEqual(
            receipt["artifact"]["sbom"]["sha256"],
            receipt["local_repair_replay"]["input_sha256"],
        )
        self.assertEqual(
            "sha256:803004a2e6fb30e336b67d79deebcd7e06fda817838d4520a07991dd62cc1bea",
            receipt["local_repair_replay"]["normalized_sha256"],
        )
        self.assertEqual(0, receipt["local_repair_replay"]["validator_exit_code"])

    def test_c78_pr_merge_checkout_failure_is_preserved_without_relaxing_the_collector(
        self,
    ) -> None:
        receipt = json.loads(C78_RECEIPT_PATH.read_text(encoding="utf-8"))
        self.assertEqual("V4-CI-P2-003", receipt["finding"]["finding_id"])
        self.assertEqual(33749590483, receipt["run"]["run_id"])
        self.assertEqual("pull_request", receipt["run"]["event"])
        self.assertEqual(
            "3743ad1e2bafaac2efd2b19d91510086ce48d478",
            receipt["candidate"]["commit"],
        )
        failed_job = receipt["failed_job"]
        self.assertEqual(100629827595, failed_job["job_id"])
        self.assertEqual(1, failed_job["exit_code"])
        self.assertIn("FAILED (failures=3, skipped=1)", failed_job["unittest_summary"])
        self.assertIn("one direct-child", failed_job["shared_observed_error"])
        self.assertEqual(200, failed_job["provider_log_observation"]["http_status"])
        self.assertEqual(
            "REJECT_3743AD1_AS_FINAL_CANDIDATE_AND_ADAPT_WITH_A_WINDOWS_DIRECT_HEAD_COLLECTOR_LANE_PLUS_FRESH_GATES",
            receipt["disposition"],
        )


if __name__ == "__main__":
    unittest.main()
