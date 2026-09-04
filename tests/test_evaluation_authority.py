from __future__ import annotations

import dataclasses
import subprocess
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from hive_mind_os.brain_kernel.artifacts import ArtifactStore
from hive_mind_os.brain_kernel.canonical import canonical_bytes, canonical_digest
from hive_mind_os.brain_kernel.evaluation_authority import (
    CandidateAuthorityBinding,
    EvaluationAuthorityError,
    canonical_holdout_commitment,
    load_evaluation_authority_manifest,
    sealed_holdout_commitment,
    store_bound_surface_evidence,
    validate_bound_surface_evidence,
)
from hive_mind_os.brain_kernel.evaluation_runtime import (
    EvaluationRuntime,
    SealedHoldout,
    SurfaceKind,
    SurfaceResult,
)
from hive_mind_os.brain_kernel.qualification import EvidenceKind, ExecutionMode
from hive_mind_os.models import Role

NOW = "2030-01-02T00:00:00+00:00"
HEAD = "a" * 40
TREE = "b" * 40
HOLDOUT_CASES = {
    "case-a": {"expected": "repair"},
    "case-b": {"expected": "preserve"},
}


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _manifest_document(
    champions: dict[str, str], **overrides: object
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_id": "hive-mind-os/evaluation-authority",
        "schema_version": 1,
        "authority_id": "authority:offline-v2",
        "repository": {"head_commit": HEAD, "tree_oid": TREE},
        "role_champions": champions,
        "evaluation": {
            "contract_fingerprint": EvaluationRuntime().contract.fingerprint,
            "harness_fingerprint": canonical_digest({"harness": "v2"}),
        },
        "holdout": {
            "holdout_id": "holdout:offline-v2",
            "commitment": canonical_holdout_commitment(
                "holdout:offline-v2", HOLDOUT_CASES
            ),
        },
        "comparators": [
            {
                "comparator_id": "comparator:a",
                "pin": canonical_digest({"comparator": "a", "version": 1}),
                "license": "MIT",
            },
            {
                "comparator_id": "comparator:b",
                "pin": canonical_digest({"comparator": "b", "version": 1}),
                "license": "Apache-2.0",
            },
        ],
        "identities": {
            "proposer_id": "optimizer:proposal",
            "builder_id": "builder:isolated",
            "evaluator_id": "curator:evaluator",
            "judge_id": "judge:independent",
        },
        "budgets": {
            "max_generations": 2,
            "max_candidates": 4,
            "max_evaluations": 4,
            "max_surface_receipts": 8,
            "max_prompt_bytes": 100_000,
            "max_wall_seconds": 3_600,
        },
        "validity": {
            "not_before": "2030-01-01T00:00:00+00:00",
            "expires_at": "2030-01-03T00:00:00+00:00",
        },
    }
    document.update(overrides)
    document["manifest_digest"] = canonical_digest(document)
    return document


class EvaluationAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.repository = self.root / "repository"
        self.candidate = self.root / "candidate"
        self.run_root = self.root / "run"
        self.authority_root = self.root / "external-authority"
        for path in (
            self.repository,
            self.candidate,
            self.run_root,
            self.authority_root,
        ):
            path.mkdir()
        self.champions = {
            role.value: canonical_digest({"champion": role.value}) for role in Role
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_manifest(
        self, document: dict[str, object] | None = None, *, path: Path | None = None
    ) -> tuple[Path, str]:
        material = document or _manifest_document(self.champions)
        target = path or (self.authority_root / "authority.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(canonical_bytes(material) + b"\n")
        return target, str(material["manifest_digest"])

    def load(self, path: Path, digest: str, *, as_of: str = NOW):
        return load_evaluation_authority_manifest(
            path,
            expected_digest=digest,
            repository_root=self.repository,
            candidate_root=self.candidate,
            run_root=self.run_root,
            as_of=as_of,
        )

    def test_external_manifest_binds_every_authority_dimension(self) -> None:
        path, digest = self.write_manifest()
        manifest = self.load(path, digest)

        self.assertEqual(digest, manifest.manifest_digest)
        self.assertEqual(HEAD, manifest.repository_head)
        self.assertEqual(TREE, manifest.repository_tree)
        self.assertEqual(set(self.champions), set(manifest.champions))
        self.assertEqual(
            self.champions[Role.BUILDER.value], manifest.champion_digest(Role.BUILDER)
        )
        self.assertEqual(2, manifest.budget.max_generations)
        self.assertEqual(
            ["comparator:a", "comparator:b"],
            [item.comparator_id for item in manifest.comparators],
        )
        self.assertEqual("MIT", manifest.comparator("comparator:a").license_id)
        self.assertEqual(
            {"holdout_id", "commitment"}, set(manifest.to_document()["holdout"])
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            manifest.authority_id = "rewritten"  # type: ignore[misc]

    def test_holdout_commitment_is_canonical_and_content_sensitive(self) -> None:
        reordered = {
            "case-b": {"expected": "preserve"},
            "case-a": {"expected": "repair"},
        }
        expected = canonical_holdout_commitment("holdout:offline-v2", HOLDOUT_CASES)
        self.assertEqual(
            expected,
            canonical_holdout_commitment("holdout:offline-v2", reordered),
        )
        self.assertEqual(
            expected,
            sealed_holdout_commitment(
                SealedHoldout("holdout:offline-v2", HOLDOUT_CASES)
            ),
        )
        self.assertNotEqual(
            expected,
            canonical_holdout_commitment(
                "holdout:offline-v2",
                {**HOLDOUT_CASES, "case-a": {"expected": "substituted"}},
            ),
        )
        self.assertNotEqual(
            expected,
            canonical_holdout_commitment("holdout:other", HOLDOUT_CASES),
        )

    def test_path_digest_validity_and_holdout_disclosure_fail_closed(self) -> None:
        path, digest = self.write_manifest()
        with self.assertRaisesRegex(EvaluationAuthorityError, "caller-authenticated"):
            self.load(path, canonical_digest({"wrong": True}))
        with self.assertRaisesRegex(EvaluationAuthorityError, "not yet valid"):
            self.load(path, digest, as_of="2029-12-31T23:59:59+00:00")
        with self.assertRaisesRegex(EvaluationAuthorityError, "expired"):
            self.load(path, digest, as_of="2030-01-03T00:00:00+00:00")

        internal_path, internal_digest = self.write_manifest(
            path=self.repository / "authority.json"
        )
        with self.assertRaisesRegex(EvaluationAuthorityError, "outside the repository"):
            self.load(internal_path, internal_digest)

        disclosed = _manifest_document(self.champions)
        disclosed["holdout"] = {
            **disclosed["holdout"],  # type: ignore[arg-type]
            "answers": {"case": "secret"},
        }
        disclosed.pop("manifest_digest")
        disclosed["manifest_digest"] = canonical_digest(disclosed)
        disclosed_path, disclosed_digest = self.write_manifest(disclosed)
        with self.assertRaisesRegex(EvaluationAuthorityError, "unknown answers"):
            self.load(disclosed_path, disclosed_digest)

    def test_duplicate_keys_and_incomplete_role_or_identity_bindings_are_rejected(
        self,
    ) -> None:
        duplicate = self.authority_root / "duplicate.json"
        duplicate.write_text('{"schema_id":"x","schema_id":"y"}', encoding="utf-8")
        with self.assertRaisesRegex(EvaluationAuthorityError, "duplicate key"):
            self.load(duplicate, canonical_digest({"irrelevant": True}))

        incomplete = _manifest_document(
            {key: value for key, value in self.champions.items() if key != "builder"}
        )
        path, digest = self.write_manifest(incomplete)
        with self.assertRaisesRegex(EvaluationAuthorityError, "every kernel role"):
            self.load(path, digest)

        collision = _manifest_document(self.champions)
        collision["identities"] = {
            **collision["identities"],  # type: ignore[arg-type]
            "judge_id": "curator:evaluator",
        }
        collision.pop("manifest_digest")
        collision["manifest_digest"] = canonical_digest(collision)
        path, digest = self.write_manifest(collision)
        with self.assertRaisesRegex(EvaluationAuthorityError, "must be unique"):
            self.load(path, digest)

    def test_candidate_parent_current_identity_and_holdout_access_are_checked(
        self,
    ) -> None:
        path, digest = self.write_manifest()
        manifest = self.load(path, digest)
        candidate_digest = canonical_digest({"candidate": 1})
        fields = {
            "candidate_id": "candidate:1",
            "candidate_digest": candidate_digest,
            "role": "builder",
            "parent_champion_digest": self.champions["builder"],
            "authority_manifest_digest": digest,
            "generation": 1,
        }
        candidate = CandidateAuthorityBinding(**fields)
        manifest.validate_candidate(
            candidate, current_champion_digest=self.champions["builder"]
        )

        wrong_parent = CandidateAuthorityBinding(
            **{**fields, "parent_champion_digest": canonical_digest({"wrong": 1})}
        )
        with self.assertRaisesRegex(EvaluationAuthorityError, "parent"):
            manifest.validate_candidate(
                wrong_parent, current_champion_digest=self.champions["builder"]
            )
        with self.assertRaisesRegex(
            EvaluationAuthorityError, "current champion changed"
        ):
            manifest.validate_candidate(
                candidate, current_champion_digest=canonical_digest({"changed": 1})
            )
        accessed = CandidateAuthorityBinding(**{**fields, "accessed_holdout": True})
        with self.assertRaisesRegex(
            EvaluationAuthorityError, "accessed protected holdout"
        ):
            manifest.validate_candidate(
                accessed, current_champion_digest=self.champions["builder"]
            )

    def test_artifact_store_receipt_binds_surface_to_exact_candidate_and_comparator(
        self,
    ) -> None:
        path, digest = self.write_manifest()
        manifest = self.load(path, digest)
        store = ArtifactStore(self.run_root / "evidence-store")
        raw = self.run_root / "surface.log"
        raw.write_text("measured by evaluator\n", encoding="utf-8")
        raw_ref = f"{raw.as_posix()}#sha256:{sha256(raw.read_bytes()).hexdigest()}"
        surface = SurfaceResult(
            SurfaceKind.COMPARATOR,
            "pinned-comparator",
            (0.7, 0.7, 0.7),
            (0.8, 0.8, 0.8),
            (raw_ref,),
        )
        candidate = CandidateAuthorityBinding(
            candidate_id="candidate:1",
            candidate_digest=canonical_digest({"candidate": 1}),
            role="builder",
            parent_champion_digest=self.champions["builder"],
            authority_manifest_digest=digest,
            generation=1,
        )
        plan_digest = canonical_digest({"plan": 1})
        comparator = manifest.comparator("comparator:a")
        bound = store_bound_surface_evidence(
            store,
            surface=surface,
            receipt_id="receipt:comparator",
            claim_id="claim:1",
            candidate_digest=candidate.candidate_digest,
            parent_champion_digest=candidate.parent_champion_digest,
            authority_manifest_digest=digest,
            evaluation_plan_digest=plan_digest,
            generation=1,
            evaluator_id=manifest.identities.evaluator_id,
            evaluator_trust_domain="independent-curator",
            repository_head=HEAD,
            repository_tree=TREE,
            contract_fingerprint=manifest.contract_fingerprint,
            harness_fingerprint=manifest.harness_fingerprint,
            holdout_commitment=manifest.holdout_commitment,
            observed_at=NOW,
            expires_at="2030-01-03T00:00:00+00:00",
            evidence_kind=EvidenceKind.STRUCTURAL,
            execution_mode=ExecutionMode.LOCAL,
            comparator_id=comparator.comparator_id,
            comparator_pin=comparator.pin,
        )
        validate_bound_surface_evidence(
            bound,
            store=store,
            manifest=manifest,
            candidate=candidate,
            evaluation_plan_digest=plan_digest,
            prior_outcome_digest=None,
        )
        forged_candidate = CandidateAuthorityBinding(
            **{
                **fields_from_candidate(candidate),
                "candidate_id": "candidate:forged",
                "candidate_digest": canonical_digest({"candidate": "forged"}),
            }
        )
        with self.assertRaisesRegex(EvaluationAuthorityError, "wrong candidate"):
            validate_bound_surface_evidence(
                bound,
                store=store,
                manifest=manifest,
                candidate=forged_candidate,
                evaluation_plan_digest=plan_digest,
                prior_outcome_digest=None,
            )


def fields_from_candidate(candidate: CandidateAuthorityBinding) -> dict[str, object]:
    return {
        field.name: getattr(candidate, field.name)
        for field in dataclasses.fields(CandidateAuthorityBinding)
    }


if __name__ == "__main__":
    unittest.main()
