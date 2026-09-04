from __future__ import annotations

import base64
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path

from hive_mind_os.brain_kernel.artifacts import (
    ArtifactEnvelope,
    ArtifactIntegrityError,
    ArtifactStore,
)


def digest(number: int) -> str:
    return f"sha256:{number:064x}"


MEDIA_TYPE = "application/json"
CANDIDATE_DIGEST = digest(1)
DEPENDENCY_DIGESTS = (digest(2), digest(3))
SCHEMA_ID = "hive.evidence/test-result"
SCHEMA_VERSION = "1.0.0"
SCHEMA_DIGEST = digest(4)
PRODUCER_ID = "curator-one"


class ArtifactStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = ArtifactStore(Path(self.temporary.name))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def put(
        self,
        content: bytes,
        *,
        store: ArtifactStore | None = None,
        media_type: str = MEDIA_TYPE,
        candidate_digest: str = CANDIDATE_DIGEST,
        dependency_digests: tuple[str, ...] = DEPENDENCY_DIGESTS,
        schema_id: str = SCHEMA_ID,
        schema_version: str = SCHEMA_VERSION,
        schema_digest: str = SCHEMA_DIGEST,
        producer_id: str = PRODUCER_ID,
    ) -> ArtifactEnvelope:
        return (store or self.store).put(
            content,
            media_type=media_type,
            candidate_digest=candidate_digest,
            dependency_digests=dependency_digests,
            schema_id=schema_id,
            schema_version=schema_version,
            schema_digest=schema_digest,
            producer_id=producer_id,
        )

    def test_round_trip_is_deterministic_immutable_and_provenance_bound(self) -> None:
        first = self.put(b'{"passed":true}')
        second = self.put(b'{"passed":true}')
        stored = self.store.read(first.artifact_digest)

        self.assertEqual(first, second)
        self.assertEqual(first, stored.envelope)
        self.assertEqual(first, ArtifactEnvelope.from_document(first.to_document()))
        self.assertEqual(b'{"passed":true}', stored.content)
        self.assertEqual(stored.content, self.store.get(first.artifact_digest))
        self.assertEqual((digest(2), digest(3)), first.dependency_digests)
        with self.assertRaises(FrozenInstanceError):
            first.producer_id = "rewriter"  # type: ignore[misc]

    def test_address_changes_for_candidate_dependency_or_schema_provenance(self) -> None:
        baseline = self.put(b"same bytes")
        changed_envelopes = (
            self.put(b"same bytes", candidate_digest=digest(11)),
            self.put(b"same bytes", dependency_digests=(digest(12),)),
            self.put(b"same bytes", schema_id="hive.evidence/other"),
            self.put(b"same bytes", schema_version="2.0.0"),
            self.put(b"same bytes", schema_digest=digest(13)),
        )
        for changed in changed_envelopes:
            with self.subTest(artifact_digest=changed.artifact_digest):
                self.assertNotEqual(
                    baseline.artifact_digest, changed.artifact_digest
                )

    def test_dependency_order_and_duplicates_have_one_canonical_identity(self) -> None:
        first = self.put(
            b"payload",
            dependency_digests=(
                digest(3),
                digest(2),
                digest(2),
            ),
        )
        second = self.put(b"payload")
        self.assertEqual(first, second)

    def test_parallel_store_instances_publish_one_complete_bundle(self) -> None:
        root = Path(self.temporary.name)

        def publish(_: int) -> ArtifactEnvelope:
            return self.put(b"parallel payload", store=ArtifactStore(root))

        with ThreadPoolExecutor(max_workers=8) as executor:
            envelopes = tuple(executor.map(publish, range(32)))
        self.assertEqual(1, len(set(envelopes)))
        self.assertEqual(
            b"parallel payload", self.store.get(envelopes[0].artifact_digest)
        )
        artifact_directory = self.store._path(envelopes[0].artifact_digest).parent
        self.assertEqual([], list(artifact_directory.glob(".artifact-pending-*")))

    def test_payload_mutation_is_detected_and_never_repaired_by_put(self) -> None:
        envelope = self.put(b"original")
        path = self.store._path(envelope.artifact_digest)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["content_base64"] = base64.b64encode(b"mutated").decode("ascii")
        path.write_text(json.dumps(document), encoding="utf-8")

        with self.assertRaisesRegex(ArtifactIntegrityError, "content digest"):
            self.store.read(envelope.artifact_digest)
        with self.assertRaises(ArtifactIntegrityError):
            self.put(b"original")
        self.assertEqual(b"mutated", base64.b64decode(document["content_base64"]))

    def test_envelope_provenance_mutation_is_detected(self) -> None:
        envelope = self.put(b"original")
        path = self.store._path(envelope.artifact_digest)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["envelope"]["candidate_digest"] = digest(99)
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaisesRegex(ArtifactIntegrityError, "envelope"):
            self.store.read(envelope.artifact_digest)

    def test_self_consistent_bundle_under_the_wrong_address_is_rejected(self) -> None:
        envelope = self.put(b"original")
        wrong_digest = digest(100)
        wrong_path = self.store._path(wrong_digest)
        wrong_path.parent.mkdir(parents=True)
        wrong_path.write_bytes(self.store._path(envelope.artifact_digest).read_bytes())
        with self.assertRaisesRegex(ArtifactIntegrityError, "wrong address"):
            self.store.read(wrong_digest)

    def test_malformed_unknown_and_duplicate_json_fields_fail_closed(self) -> None:
        for index, body in enumerate(
            (
                b"not-json",
                b'{"envelope":{},"content_base64":"","unknown":true}',
                b'{"envelope":{},"envelope":{},"content_base64":""}',
            ),
            start=200,
        ):
            with self.subTest(body=body):
                artifact_digest = digest(index)
                path = self.store._path(artifact_digest)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
                with self.assertRaises(ArtifactIntegrityError):
                    self.store.read(artifact_digest)

    def test_envelope_constructor_rejects_forged_identity_and_unsafe_digests(self) -> None:
        with self.assertRaisesRegex(ArtifactIntegrityError, "digest mismatch"):
            ArtifactEnvelope(
                envelope_version=1,
                artifact_digest=digest(90),
                content_digest=digest(91),
                media_type="text/plain",
                candidate_digest=digest(92),
                dependency_digests=(),
                schema_id="schema",
                schema_version="1",
                schema_digest=digest(93),
                producer_id="producer",
            )
        with self.assertRaisesRegex(ValueError, "candidate_digest"):
            self.put(b"payload", candidate_digest="../escape")
        with self.assertRaisesRegex(ValueError, "dependency_digests"):
            self.put(
                b"payload",
                dependency_digests=("not-a-digest",),
            )


if __name__ == "__main__":
    unittest.main()
