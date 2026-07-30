from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import hive_mind_os
import hive_mind_os.package_system as package_system
from hive_mind_os.foundation.canonical import digest
from hive_mind_os.foundation.cognitive import MANAGED_NAMESPACE, project_cognitive_notes
from hive_mind_os.foundation.explorer_idea_lifecycle import (
    append_explorer_idea_lifecycle_event,
    compile_explorer_idea_lifecycle_event,
    semantic_relationship_reference,
)
from hive_mind_os.foundation.public_memory import (
    PUBLIC_MEMORY_RELEASE_ACTION,
    PUBLIC_MEMORY_RELEASER,
    materialize_public_memory,
)
from hive_mind_os.foundation.store import FoundationStore
from hive_mind_os.models import Role
from hive_mind_os.policy import PolicyDecision
from scripts.phase1_surface_inventory import build_inventory, cli_inventory

TENANT = "tenant:test"
REPOSITORY = "repository:test"
SUBJECT = {"ref": "generation-zero:explorer", "digest": digest("generation-zero")}


def _authority(
    action: str,
    *,
    actor: str = "explorer",
    public_payload: dict | None = None,
):
    from hive_mind_os.foundation.authority import decide_foundation_write

    decision = decide_foundation_write(
        role=Role.BUILDER if action != "foundation.memory.write" else Role.EXPLORER,
        action=action,
        policy_decision=PolicyDecision(True, "phase4d fixture"),
        lease_actions={action},
        adapter_actions={action},
        mission_risk_allowed=True,
        budget_available=True,
        tenant_id=TENANT,
        repository_id=REPOSITORY,
        actor_id=actor,
        decision_id=f"decision:{action}:{actor}",
        lease_id=f"lease:{action}:{actor}",
        public_release_decision_id=(
            "release:independent" if public_payload is not None else None
        ),
        public_release_decided_by=(
            "curator:independent" if public_payload is not None else None
        ),
        public_release_subject_digest=(
            digest(public_payload) if public_payload is not None else None
        ),
    )
    if not decision.allowed:
        raise AssertionError(decision)
    return decision


def _identity() -> dict:
    return {
        "record_type": "repository-identity",
        "schema_version": 1,
        "tenant_id": TENANT,
        "repository_id": REPOSITORY,
        "project_lineage_id": "lineage:test",
        "instance_id": "instance:test",
        "remote_evidence_digest": digest("remote"),
        "controller_build_digest": digest("controller"),
        "self_host_depth": 0,
        "parent_run_id": None,
        "subject_commit": "a" * 40,
        "target_cutoff": "a" * 40,
    }


def _compile(
    stage: str,
    *,
    lifecycle_id: str = "idea:test",
    event_id: str | None = None,
    prior: tuple[dict, dict] | None = None,
    classification: str | None = None,
    court_disposition: str | None = None,
    terminal_disposition: str | None = None,
    sensitivity: str = "private",
    stage_reference_override: dict | None = None,
    observed_at: str | None = None,
    recorded_at: str | None = None,
) -> dict:
    previous = (
        (None, None, None)
        if prior is None
        else (
            prior[0]["receipt"]["event_id"],
            prior[1]["record_id"],
            prior[0]["receipt"]["content_digest"],
        )
    )
    if stage == "relationship":
        relationship_basis = {
            "tenant_id": TENANT,
            "repository_id": REPOSITORY,
            "source_record_id": "record:encounter",
            "target_record_id": "record:opportunity",
            "relationship": classification or "new",
            "evidence_digest": digest({"stage": stage}),
        }
        stage_reference = semantic_relationship_reference(
            tenant_id=TENANT,
            repository_id=REPOSITORY,
            source_record_id="record:encounter",
            target_record_id="record:opportunity",
            relationship=classification or "new",
            evidence_digest=digest({"stage": stage}),
        )
    else:
        relationship_basis = None
        stage_reference = {
            "ref": (
                "observation:artifact:test"
                if stage == "encounter"
                else f"{stage}:artifact:test"
            ),
            "digest": digest({"stage": stage}),
        }
    if stage_reference_override is not None:
        stage_reference = stage_reference_override
    return compile_explorer_idea_lifecycle_event(
        lifecycle_id=lifecycle_id,
        event_id=event_id or (
            f"{lifecycle_id}:encounter"
            if stage == "encounter"
            else f"{lifecycle_id}:{stage}:1"
        ),
        stage=stage,
        tenant_id=TENANT,
        repository_id=REPOSITORY,
        mission_id="mission:test",
        run_id="run:test",
        actor_id="explorer",
        owner_id="orchestrator",
        observed_at=observed_at or f"2026-07-30T00:00:0{len(stage) % 10}+00:00",
        recorded_at=recorded_at or f"2026-07-30T00:01:0{len(stage) % 10}+00:00",
        subject_ref=SUBJECT,
        stage_reference=stage_reference,
        encounter_record_id="record:encounter",
        opportunity_record_id=(
            None if stage == "encounter" else "record:opportunity"
        ),
        classification=classification,
        court_disposition=court_disposition,
        terminal_disposition=terminal_disposition,
        relationship_basis=relationship_basis,
        previous_event_id=previous[0],
        previous_event_record_id=previous[1],
        previous_event_digest=previous[2],
        sensitivity=sensitivity,
    )


class ExplorerIdeaLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.private = self.root / "private"
        self.private.mkdir()
        self.store_path = self.private / "foundation.sqlite3"
        self.store = FoundationStore(self.store_path)
        self.store.register_repository(
            _identity(),
            authority=_authority("foundation.repository.register", actor="builder"),
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temporary.cleanup()

    def _append(self, prepared: dict, *, public: bool = False) -> dict:
        return append_explorer_idea_lifecycle_event(
            self.store,
            prepared,
            authority=_authority(
                "foundation.memory.write",
                public_payload=prepared["memory"] if public else None,
            ),
        )

    def test_events_compile_deterministically_as_existing_memory_contract(self) -> None:
        first = _compile("encounter")
        second = _compile("encounter")
        self.assertEqual(first, second)
        self.assertEqual(first["memory"]["memory_kind"], "opportunity")
        self.assertEqual(first["memory"]["content_digest"], first["receipt"]["content_digest"])
        self.assertEqual(first["receipt"]["reference_status"], "pinned-unverified")
        self.assertEqual(first["receipt"]["remaining_stage_status"], "unknown")
        self.assertFalse(first["receipt"]["lifecycle_complete_claimed"])
        self.assertFalse(first["receipt"]["value_claimed"])
        self.assertEqual(first["receipt"]["comparison_status"], "not-run")

    def test_full_reference_chain_and_idempotent_replay(self) -> None:
        encounter_prepared = _compile("encounter")
        encounter = self._append(encounter_prepared)
        replay = self._append(encounter_prepared)
        self.assertEqual(replay["record_id"], encounter["record_id"])

        relation_prepared = _compile(
            "relationship",
            prior=(encounter_prepared, encounter),
            classification="new",
        )
        relation = self._append(relation_prepared)
        court_prepared = _compile(
            "court",
            prior=(relation_prepared, relation),
            court_disposition="adapt",
        )
        court = self._append(court_prepared)
        experiment_prepared = _compile(
            "experiment", prior=(court_prepared, court)
        )
        experiment = self._append(experiment_prepared)
        outcome_prepared = _compile(
            "outcome", prior=(experiment_prepared, experiment)
        )
        outcome = self._append(outcome_prepared)

        records = self.store.records(
            tenant_id=TENANT,
            repository_id=REPOSITORY,
            record_type="memory-record",
        )
        self.assertEqual([record["payload"]["step_id"] for record in records], [
            "encounter",
            "relationship",
            "court",
            "experiment",
            "outcome",
        ])
        self.assertEqual(
            outcome["payload"]["evidence_refs"], ["outcome:artifact:test"]
        )
        self.assertFalse(outcome_prepared["receipt"]["promotion_authorized"])
        self.assertFalse(outcome_prepared["receipt"]["activation_authorized"])

    def test_conflict_broken_predecessor_and_terminal_successor_fail_closed(self) -> None:
        prepared = _compile("encounter")
        encounter = self._append(prepared)
        changed = _compile("encounter")
        changed["receipt"]["stage_reference"]["ref"] = "forged"
        changed["receipt"]["content_digest"] = digest(
            {key: value for key, value in changed["receipt"].items() if key != "content_digest"}
        )
        with self.assertRaisesRegex(ValueError, "does not reproduce"):
            self._append(changed)

        bad = _compile(
            "outcome",
            prior=(prepared, encounter),
        )
        with self.assertRaisesRegex(ValueError, "stage transition"):
            self._append(bad)

        disposed_prepared = _compile(
            "encounter",
            lifecycle_id="idea:disposed",
            terminal_disposition="filtered",
        )
        disposed = self._append(disposed_prepared)
        successor = _compile(
            "relationship",
            lifecycle_id="idea:disposed",
            event_id="idea:disposed:relationship:1",
            prior=(disposed_prepared, disposed),
            classification="new",
        )
        with self.assertRaisesRegex(ValueError, "terminal lifecycle"):
            self._append(successor)

        conflicting = _compile("encounter")
        conflicting["memory"]["owner_id"] = "different"
        with self.assertRaises(ValueError):
            self._append(conflicting)
        self.assertEqual(len(self.store.records(
            tenant_id=TENANT,
            repository_id=REPOSITORY,
            record_type="memory-record",
        )), 2)

    def test_relationship_reference_is_semantic_not_row_identity(self) -> None:
        arguments = {
            "tenant_id": TENANT,
            "repository_id": REPOSITORY,
            "source_record_id": "record:encounter",
            "target_record_id": "record:opportunity",
            "relationship": "duplicate",
            "evidence_digest": digest("same evidence"),
        }
        self.assertEqual(
            semantic_relationship_reference(**arguments),
            semantic_relationship_reference(**arguments),
        )
        changed = {**arguments, "evidence_digest": digest("changed evidence")}
        self.assertNotEqual(
            semantic_relationship_reference(**arguments),
            semantic_relationship_reference(**changed),
        )

        foreign = semantic_relationship_reference(
            **{
                **arguments,
                "tenant_id": "tenant:foreign",
                "relationship": "duplicate",
            }
        )
        with self.assertRaisesRegex(ValueError, "semantic relationship reference"):
            _compile(
                "relationship",
                prior=(
                    _compile("encounter"),
                    {"record_id": "record:prior"},
                ),
                classification="new",
                stage_reference_override=foreign,
            )

    def test_counterfeit_predecessor_hostile_scalars_and_metadata_fail(self) -> None:
        prepared = _compile("encounter", lifecycle_id="idea:counterfeit")
        counterfeit = {
            **prepared["memory"],
            "memory_id": "generic:memory",
            "payload_digest": digest("unrelated"),
            "claim_refs": [],
            "relation_refs": [],
        }
        prior = self.store.append_record(
            authority=_authority("foundation.memory.write"),
            foundation_action="foundation.memory.write",
            tenant_id=TENANT,
            repository_id=REPOSITORY,
            record_type="memory-record",
            schema_name="memory-record-v1",
            stream_id=prepared["stream_id"],
            payload=counterfeit,
            actor_id="explorer",
            idempotency_key=prepared["idempotency_key"],
            observed_at=counterfeit["observed_at"],
            correlation_id="idea:counterfeit",
            causation_id="record:encounter",
            sensitivity="private",
            retention="governed",
            status="active",
        )
        successor = _compile(
            "relationship",
            lifecycle_id="idea:counterfeit",
            prior=(prepared, prior),
            classification="new",
        )
        with self.assertRaisesRegex(ValueError, "previous lifecycle"):
            self._append(successor)

        class HostileString(str):
            calls = 0

            def __hash__(self) -> int:
                type(self).calls += 1
                raise AssertionError("hostile hash executed")

        with self.assertRaisesRegex(ValueError, "built-in string"):
            _compile(
                "encounter",
                lifecycle_id="idea:hostile",
                sensitivity=HostileString("private"),
            )
        self.assertEqual(HostileString.calls, 0)

        with self.assertRaises(ValueError):
            _compile("encounter", lifecycle_id="idea:\x00control")
        with self.assertRaises(ValueError):
            _compile("encounter", observed_at="not-a-timestamp")
        with self.assertRaises(ValueError):
            _compile("encounter", recorded_at="2026-07-30T00:00:00")

    def test_exact_predecessor_with_missing_ancestry_fails_closed(self) -> None:
        encounter_prepared = _compile(
            "encounter",
            lifecycle_id="idea:orphan-ancestry",
        )
        relationship_prepared = _compile(
            "relationship",
            lifecycle_id="idea:orphan-ancestry",
            prior=(encounter_prepared, {"record_id": "record:missing"}),
            classification="new",
        )
        relationship_memory = relationship_prepared["memory"]
        relationship = self.store.append_record(
            authority=_authority("foundation.memory.write"),
            foundation_action="foundation.memory.write",
            tenant_id=TENANT,
            repository_id=REPOSITORY,
            record_type="memory-record",
            schema_name="memory-record-v1",
            stream_id=relationship_prepared["stream_id"],
            payload=relationship_memory,
            actor_id="explorer",
            idempotency_key=relationship_prepared["idempotency_key"],
            observed_at=relationship_memory["observed_at"],
            correlation_id="idea:orphan-ancestry",
            causation_id="record:encounter",
            sensitivity="private",
            retention="governed",
            status="active",
        )
        court = _compile(
            "court",
            lifecycle_id="idea:orphan-ancestry",
            prior=(relationship_prepared, relationship),
            court_disposition="adapt",
        )
        with self.assertRaisesRegex(ValueError, "ancestry is unavailable"):
            self._append(court)

    def test_private_default_is_absent_from_public_snapshot(self) -> None:
        self._append(_compile("encounter"))
        snapshot = FoundationStore.read_public_memory_snapshot(
            self.store_path,
            tenant_id=TENANT,
            repository_id=REPOSITORY,
        )
        self.assertEqual(snapshot.records, ())
        self.assertEqual(snapshot.omitted_sensitive_count, 1)

        public = _compile(
            "encounter",
            lifecycle_id="idea:unreleased",
            sensitivity="safe-public",
        )
        with self.assertRaises(PermissionError):
            append_explorer_idea_lifecycle_event(
                self.store,
                public,
                authority=_authority("foundation.memory.write"),
            )

        wrong_action = _compile(
            "encounter",
            lifecycle_id="idea:wrong-authority",
        )
        with self.assertRaises(PermissionError):
            append_explorer_idea_lifecycle_event(
                self.store,
                wrong_action,
                authority=_authority("foundation.opportunity.write"),
            )

    def test_independently_released_event_projects_through_unchanged_brain(self) -> None:
        prepared = _compile("encounter", sensitivity="safe-public")
        self._append(prepared, public=True)
        self.store.close()

        public_root = self.root / "public"
        public_root.mkdir()
        public_store = public_root / "safe-public.sqlite3"
        release_state = self.root / "release-state"
        release_state.mkdir()
        materialize_public_memory(
            self.store_path,
            public_store,
            self.repository,
            release_state,
            tenant_id=TENANT,
            repository_id=REPOSITORY,
            authority=_authority(
                PUBLIC_MEMORY_RELEASE_ACTION,
                actor=PUBLIC_MEMORY_RELEASER,
            ),
        )
        cognitive_state = self.root / "cognitive-state"
        cognitive_state.mkdir()
        project_cognitive_notes(
            public_store,
            self.repository,
            cognitive_state,
            tenant_id=TENANT,
            repository_id=REPOSITORY,
            authority=_authority(
                "foundation.projection.write",
                actor="foundation-cognitive-projector-v1",
            ),
        )
        ideas = list((self.repository / MANAGED_NAMESPACE / "ideas").glob("*.md"))
        self.assertEqual(len(ideas), 1)
        note = ideas[0].read_text(encoding="utf-8")
        self.assertIn("explorer-lifecycle:reference-only", note)
        self.assertIn("observation", note)
        self.assertIn("generation-zero:explorer", note)
        self.store = FoundationStore(self.store_path)

    def test_surfaces_resources_and_generic_systems_remain_frozen(self) -> None:
        repository = Path(__file__).parents[1]
        inventory = build_inventory(repository)
        self.assertEqual(len(hive_mind_os.__all__), 131)
        self.assertEqual(len(package_system.__all__), 33)
        self.assertEqual(cli_inventory()["parser_count"], 13)
        self.assertEqual(
            inventory["observable_module_surface"]["definition_count"], 304
        )
        self.assertEqual(
            inventory["runtime_effects"]["unclassified_candidate_count"], 0
        )
        self.assertEqual(
            len(tuple((repository / "src/hive_mind_os").rglob("*.json"))), 133
        )


if __name__ == "__main__":
    unittest.main()
