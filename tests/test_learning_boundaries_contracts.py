import unittest

from hive_mind_os.endpoint_curriculum import EndpointEpisodeManifest, EpisodeState
from hive_mind_os.endpoint_oracle import CustodyError, EndpointSeal
from hive_mind_os.isolated_execution import (
    IsolationAttestation,
    IsolationError,
    ProbeResult,
    require_attested,
)
from hive_mind_os.lesson_drafts import DraftError, ProcessingState, create_draft
from hive_mind_os.roblox_runtime import RuntimeVerdict, blocked_runtime
from hive_mind_os.tenant_memory import (
    BoundaryError,
    ScopedMemoryHandle,
    SubjectMemoryBoundary,
    SubjectNamespace,
)


class BoundaryContractsTests(unittest.TestCase):
    def test_unavailable_isolation_fails_closed(self):
        a = IsolationAttestation(
            "x",
            "1",
            None,
            "t",
            "r",
            "s",
            "n",
            "c",
            (),
            {},
            "p",
            ProbeResult.UNAVAILABLE,
            "1970-01-01T00:00:00Z",
        )
        with self.assertRaises(IsolationError):
            require_attested(a)

    def test_subjects_do_not_collide(self):
        a = SubjectMemoryBoundary("a", "same", "pa", "ca", "la", "p", "e", "r")
        b = SubjectMemoryBoundary("b", "same", "pb", "cb", "lb", "p", "e", "r")
        store = SubjectNamespace()
        store.put(a, "k", "secret")
        h = ScopedMemoryHandle(a.digest, "builder", "m", ("private",))
        with self.assertRaises(BoundaryError):
            store.get(h, b, "k")

    def test_draft_requires_review_receipt(self):
        d = create_draft(
            draft_id="d",
            processing_state=ProcessingState.CAPTURED_PRIVATE,
            origin_subject_token="s",
            origin_mission_token="m",
            statement="x",
            applicability=(),
            outcome_class="unknown",
            evidence_tokens=(),
            private_custody_token="p",
            confidence_basis="one observation",
            counterexamples=(),
            disposition_refs=(),
            generator_id="g",
            export_policy_digest="e",
            withheld_reason_code=None,
        )
        with self.assertRaises(DraftError):
            d.transition(ProcessingState.REVIEWED_DRAFT)

    def test_identical_endpoints_are_degenerate(self):
        m = EndpointEpisodeManifest(
            "e",
            "s",
            "endpoint_reconstruction",
            "c",
            "t",
            "c",
            "t",
            None,
            None,
            "initial_readme",
            "f",
            "training",
            "d",
            "f",
            (),
            (),
        )
        self.assertEqual(m.state, EpisodeState.DEGENERATE_EPISODE)

    def test_seal_identities_differ(self):
        with self.assertRaises(CustodyError):
            EndpointSeal("e", "i", "c", "l", "p", "t", "r", "b", "same", "same", "now")

    def test_runtime_unavailable_is_typed(self):
        self.assertEqual(
            blocked_runtime("Studio unavailable").verdict,
            RuntimeVerdict.BLOCKED_RUNTIME,
        )
