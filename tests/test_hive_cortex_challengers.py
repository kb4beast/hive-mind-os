from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.brain_kernel.challengers import (
    FORBIDDEN_CLASS_REASON,
    FORBIDDEN_SELF_MODIFICATION_CLASSES,
    UNRECOGNIZED_TAG_REASON,
    AcceptedLesson,
    ChallengerGenerationError,
    ChallengerGenerator,
    ChallengerSpec,
    ChallengerSurface,
    ChampionMutationError,
    classify_forbidden,
    lesson_from_document,
)
from hive_mind_os.ledger import EvidenceLedger
from hive_mind_os.models import Role
from hive_mind_os.prompt_registry import (
    PromptRegistry,
    generation_zero_prompt,
    prompt_digest,
)
from hive_mind_os.recursive_improvement import (
    MetricDirection,
    MetricSpec,
    RecursiveImprovementContract,
)
from hive_mind_os.roles import ROLE_CONTRACTS

GENERATED_BY = "optimizer:challenger-510"
FROZEN_TIME = "2030-03-01T00:00:00+00:00"
CHAMPION_PLANNER = "champion:planner:wave-scheduler"
CHAMPION_POLICY = "champion:policy-rule:merge-gate"
CHAMPION_RETRIEVAL = "champion:retrieval:docket-index"
CHAMPION_TOOL = "champion:tool-selection:grep"

NON_PROMPT_CHAMPIONS = {
    "planner:wave-scheduler": CHAMPION_PLANNER,
    "policy-rule:merge-gate": CHAMPION_POLICY,
    "retrieval:docket-index": CHAMPION_RETRIEVAL,
    "tool-selection:grep": CHAMPION_TOOL,
}


def _clock() -> str:
    return FROZEN_TIME


def _lesson(
    lesson_id: str = "lesson-1",
    *,
    applicability: tuple[str, ...] = ("prompt:optimizer",),
    error_class: str = "premature_promotion",
    status: str = "accepted",
    confidence: float = 0.8,
    provenance: tuple[str, ...] = ("evidence:court-77", "evidence:run-12"),
) -> AcceptedLesson:
    return AcceptedLesson(
        lesson_id=lesson_id,
        source_episode_id="episode-9",
        outcome="failure",
        error_class=error_class,
        applicability=applicability,
        confidence=confidence,
        provenance=provenance,
        expires_at="2031-01-01T00:00:00+00:00",
        status=status,
    )


def _lesson_document(**overrides: object) -> dict[str, object]:
    document: dict[str, object] = {
        "id": "lesson-1",
        "episode_id": "episode-9",
        "outcome": "failure",
        "error_class": "premature_promotion",
        "applicability": ["prompt:optimizer"],
        "confidence": 0.8,
        "evidence_refs": ["evidence:court-77", "evidence:run-12"],
        "expiry": "2031-01-01T00:00:00+00:00",
        "status": "accepted",
    }
    document.update(overrides)
    return document


def _spec_fields(
    *,
    champion_ref: str = CHAMPION_PLANNER,
    challenger_id: str = "chal:" + "a" * 64,
    content: str = "challenger content",
) -> dict[str, object]:
    return {
        "challenger_id": challenger_id,
        "surface": ChallengerSurface.PLANNER,
        "champion_ref": champion_ref,
        "target": "wave-scheduler",
        "hypothesis": "applying lesson-1 reduces premature_promotion",
        "changed_scope": ("planner:wave-scheduler",),
        "rollback_ref": champion_ref,
        "lesson_id": "lesson-1",
        "provenance": ("evidence:court-77", "lesson:lesson-1"),
        "created_by": GENERATED_BY,
        "created_at": FROZEN_TIME,
        "content": content,
        "content_digest": prompt_digest(content),
    }


class _RegistryFixture:
    """Generation-zero optimizer champion in a throwaway registry root."""

    def __init__(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.ledger = EvidenceLedger(":memory:")
        self.registry = PromptRegistry(Path(self._directory.name), ledger=self.ledger)
        self.content = generation_zero_prompt(ROLE_CONTRACTS[Role.OPTIMIZER])
        self.digest = self.registry.register(
            Role.OPTIMIZER,
            self.content,
            parent_digest=None,
            created_by="repository:generation-0",
        )
        self.registry.promote(
            Role.OPTIMIZER,
            self.digest,
            promoted_by="repository:generation-0",
            experiment_id="generation-0",
            expected_current=None,
        )

    def close(self) -> None:
        self.registry.close()
        self.ledger.close()
        self._directory.cleanup()


class ChallengerGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _RegistryFixture()
        self.addCleanup(self.fixture.close)
        self.generator = ChallengerGenerator(
            generated_by=GENERATED_BY,
            registry=self.fixture.registry,
            now=_clock,
        )

    def test_prompt_challenger_binds_champion_hypothesis_scope_rollback_provenance(
        self,
    ) -> None:
        lesson = _lesson()
        result = self.generator.generate([lesson], champions={})

        self.assertEqual(result.rejections, ())
        self.assertEqual(len(result.challengers), 1)
        spec = result.challengers[0]
        self.assertEqual(spec.surface, ChallengerSurface.PROMPT)
        self.assertEqual(spec.target, "optimizer")
        self.assertEqual(spec.champion_ref, self.fixture.digest)
        self.assertEqual(spec.rollback_ref, self.fixture.digest)
        self.assertEqual(
            spec.hypothesis,
            "applying lesson lesson-1 to prompt:optimizer reduces premature_promotion",
        )
        self.assertEqual(spec.changed_scope, ("prompt:optimizer",))
        self.assertEqual(
            spec.provenance,
            ("evidence:court-77", "evidence:run-12", "lesson:lesson-1"),
        )
        self.assertEqual(spec.lesson_id, "lesson-1")
        self.assertEqual(spec.created_by, GENERATED_BY)
        self.assertEqual(spec.created_at, FROZEN_TIME)
        self.assertTrue(spec.challenger_id.startswith("chal:"))
        self.assertEqual(len(spec.challenger_id), len("chal:") + 64)
        self.assertNotEqual(spec.content_digest, spec.champion_ref)
        self.assertEqual(spec.content_digest, prompt_digest(spec.content))
        self.assertTrue(spec.content.startswith(self.fixture.content))
        self.assertIn(
            "Lesson lesson-1: avoid premature_promotion; evidence: evidence:court-77",
            spec.content,
        )

    def test_planner_policy_retrieval_tool_surfaces_generate_specs(self) -> None:
        lessons = [
            _lesson("lesson-planner", applicability=("planner:wave-scheduler",)),
            _lesson("lesson-policy", applicability=("policy-rule:merge-gate",)),
            _lesson("lesson-retrieval", applicability=("retrieval:docket-index",)),
            _lesson("lesson-tool", applicability=("tool-selection:grep",)),
        ]
        result = self.generator.generate(lessons, champions=NON_PROMPT_CHAMPIONS)

        self.assertEqual(result.rejections, ())
        self.assertEqual(len(result.challengers), 4)
        self.assertEqual(
            [spec.surface for spec in result.challengers],
            [
                ChallengerSurface.PLANNER,
                ChallengerSurface.POLICY_RULE,
                ChallengerSurface.RETRIEVAL,
                ChallengerSurface.TOOL_SELECTION,
            ],
        )
        self.assertEqual(
            [spec.champion_ref for spec in result.challengers],
            [CHAMPION_PLANNER, CHAMPION_POLICY, CHAMPION_RETRIEVAL, CHAMPION_TOOL],
        )
        planner = result.challengers[0]
        self.assertEqual(
            json.loads(planner.content),
            {
                "surface": "planner",
                "target": "wave-scheduler",
                "champion_ref": CHAMPION_PLANNER,
                "lesson_id": "lesson-planner",
                "error_class": "premature_promotion",
                "directive": "counteract premature_promotion",
            },
        )
        self.assertEqual(planner.changed_scope, ("planner:wave-scheduler",))
        self.assertEqual(planner.rollback_ref, CHAMPION_PLANNER)
        for spec in result.challengers:
            self.assertEqual(spec.content_digest, prompt_digest(spec.content))
            self.assertNotEqual(spec.content_digest, spec.champion_ref)

    def test_generation_is_deterministic_across_repeats(self) -> None:
        lessons = [
            _lesson(),
            _lesson("lesson-planner", applicability=("planner:wave-scheduler",)),
        ]
        first = self.generator.generate(lessons, champions=NON_PROMPT_CHAMPIONS)
        other = ChallengerGenerator(
            generated_by=GENERATED_BY,
            registry=self.fixture.registry,
            now=lambda: "2031-12-31T23:59:59+00:00",
        )
        second = other.generate(lessons, champions=NON_PROMPT_CHAMPIONS)

        self.assertEqual(len(first.challengers), 2)
        self.assertEqual(
            [spec.challenger_id for spec in first.challengers],
            [spec.challenger_id for spec in second.challengers],
        )
        self.assertEqual(
            [spec.content_digest for spec in first.challengers],
            [spec.content_digest for spec in second.challengers],
        )
        # created_at is the only field permitted to differ between runs.
        self.assertNotEqual(
            first.challengers[0].created_at, second.challengers[0].created_at
        )

    def test_mapping_lessons_adapt_via_lesson_from_document(self) -> None:
        document = _lesson_document()
        adapted = lesson_from_document(document)
        self.assertEqual(adapted, _lesson())

        from_mapping = self.generator.generate([document], champions={})
        from_dataclass = self.generator.generate([_lesson()], champions={})
        self.assertEqual(len(from_mapping.challengers), 1)
        self.assertEqual(
            from_mapping.challengers[0].challenger_id,
            from_dataclass.challengers[0].challenger_id,
        )
        self.assertEqual(
            from_mapping.challengers[0].content,
            from_dataclass.challengers[0].content,
        )

    def test_missing_champion_yields_rejection_not_parentless_challenger(self) -> None:
        parentless = ChallengerGenerator(generated_by=GENERATED_BY, now=_clock)
        result = parentless.generate(
            [_lesson("lesson-planner", applicability=("planner:wave-scheduler",))],
            champions={},
        )

        self.assertEqual(result.challengers, ())
        self.assertEqual(len(result.rejections), 1)
        rejection = result.rejections[0]
        self.assertEqual(rejection.lesson_id, "lesson-planner")
        self.assertEqual(
            rejection.reason, "no live champion for planner:wave-scheduler"
        )
        self.assertIsNone(rejection.forbidden_class)

    def test_to_experiment_candidate_round_trips_fields(self) -> None:
        spec = self.generator.generate([_lesson()], champions={}).challengers[0]
        candidate = spec.to_experiment_candidate()

        self.assertEqual(candidate.id, spec.content_digest)
        self.assertEqual(candidate.parent_champion_id, spec.champion_ref)
        self.assertEqual(candidate.hypothesis, spec.hypothesis)
        self.assertEqual(candidate.changed_paths, spec.changed_scope)
        self.assertEqual(candidate.rollback_ref, spec.rollback_ref)
        self.assertNotEqual(candidate.id, candidate.parent_champion_id)

    def test_empty_lessons_and_invalid_lesson_fields(self) -> None:
        empty = self.generator.generate([], champions={})
        self.assertEqual(empty.challengers, ())
        self.assertEqual(empty.rejections, ())

        with self.assertRaises(ChallengerGenerationError):
            _lesson(provenance=())
        with self.assertRaises(ChallengerGenerationError):
            _lesson(confidence=0.0)
        with self.assertRaises(ChallengerGenerationError):
            _lesson(confidence=1.5)
        with self.assertRaises(ChallengerGenerationError):
            lesson_from_document(_lesson_document(evidence_refs=[]))
        with self.assertRaises(ChallengerGenerationError):
            lesson_from_document(_lesson_document(confidence="high"))
        with self.assertRaises(ChallengerGenerationError):
            lesson_from_document(_lesson_document(id=""))

    def test_rejections_preserve_lesson_order(self) -> None:
        lessons = [
            _lesson("lesson-a", applicability=("planner:missing-one",)),
            _lesson("lesson-b", applicability=("goal:north-star",)),
            _lesson("lesson-c", applicability=("mystery:thing",)),
        ]
        result = self.generator.generate(lessons, champions={})

        self.assertEqual(result.challengers, ())
        self.assertEqual(
            [rejection.lesson_id for rejection in result.rejections],
            ["lesson-a", "lesson-b", "lesson-c"],
        )

    def test_duplicate_tags_collapse_to_one_challenger(self) -> None:
        lesson = _lesson(applicability=("prompt:optimizer", "prompt:optimizer"))
        result = self.generator.generate([lesson], champions={})

        self.assertEqual(len(result.challengers), 1)
        self.assertEqual(result.rejections, ())


class ChampionImmutabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _RegistryFixture()
        self.addCleanup(self.fixture.close)
        self.generator = ChallengerGenerator(
            generated_by=GENERATED_BY,
            registry=self.fixture.registry,
            now=_clock,
        )

    def test_generate_leaves_champion_digest_and_artifact_bytes_unchanged(self) -> None:
        registry = self.fixture.registry
        before_digest = registry.champion_digest(Role.OPTIMIZER)
        before_bytes = registry.artifact_path(self.fixture.digest).read_bytes()
        pointer_before = registry.pointer_path.read_bytes()

        result = self.generator.generate([_lesson()], champions={})
        self.assertEqual(len(result.challengers), 1)

        self.assertEqual(registry.champion_digest(Role.OPTIMIZER), before_digest)
        self.assertEqual(
            registry.artifact_path(self.fixture.digest).read_bytes(), before_bytes
        )
        self.assertEqual(registry.pointer_path.read_bytes(), pointer_before)
        self.assertEqual(registry.read(before_digest), self.fixture.content)

    def test_spec_aliasing_champion_raises_champion_mutation_error(self) -> None:
        with self.assertRaises(ChampionMutationError):
            ChallengerSpec(**_spec_fields(challenger_id=CHAMPION_PLANNER))

        content = "aliasing content"
        with self.assertRaises(ChampionMutationError):
            ChallengerSpec(
                **_spec_fields(champion_ref=prompt_digest(content), content=content)
            )

    def test_registered_challenger_is_content_addressed_not_promoted(self) -> None:
        registry = self.fixture.registry
        result = self.generator.generate([_lesson()], champions={})
        spec = result.challengers[0]

        self.assertEqual(registry.champion_digest(Role.OPTIMIZER), self.fixture.digest)
        self.assertEqual(registry.read(spec.content_digest), spec.content)

        lineage = registry.lineage(spec.content_digest)
        registrations = [
            record for record in lineage if record.get("kind") == "registration"
        ]
        self.assertEqual(len(registrations), 1)
        self.assertEqual(registrations[0]["parent_digest"], self.fixture.digest)
        self.assertEqual(registrations[0]["role"], Role.OPTIMIZER.value)
        self.assertEqual(registrations[0]["created_by"], GENERATED_BY)
        self.assertEqual(registrations[0]["experiment_id"], "challenger:lesson-1")
        self.assertEqual(
            [record for record in lineage if record.get("kind") == "promotion"], []
        )

    def test_specs_are_frozen(self) -> None:
        spec = self.generator.generate([_lesson()], champions={}).challengers[0]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            spec.champion_ref = "sha256:" + "0" * 64  # type: ignore[misc]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            spec.content = "rewritten"  # type: ignore[misc]

        lesson = _lesson()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            lesson.status = "rejected"  # type: ignore[misc]

    def test_module_source_has_no_champion_pointer_call_sites(self) -> None:
        from hive_mind_os.brain_kernel import challengers

        source = Path(challengers.__file__).read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        for forbidden in (
            ".promote(",
            ".rollback_champion(",
            ".quarantine(",
            ".bootstrap(",
            "champions.json",
        ):
            self.assertNotIn(forbidden, code)


class ScopeDenialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = ChallengerGenerator(generated_by=GENERATED_BY, now=_clock)

    def test_forbidden_class_lessons_are_rejected_with_class_named(self) -> None:
        expected = {
            "champion:optimizer": "live_champion_mutation",
            "policy:core": "policy_mutation",
            "weights:backbone": "self_weight_modification",
            "holdout:p09": "holdout_access",
            "evaluator:gate": "self_evaluation",
            "budget:tokens": "unbounded_resource_acquisition",
        }
        lessons = [
            _lesson(f"lesson-{index}", applicability=(tag,))
            for index, tag in enumerate(expected)
        ]
        result = self.generator.generate(lessons, champions=NON_PROMPT_CHAMPIONS)

        self.assertEqual(result.challengers, ())
        self.assertEqual(len(result.rejections), len(expected))
        for rejection, (tag, forbidden_class) in zip(
            result.rejections, expected.items(), strict=True
        ):
            self.assertEqual(rejection.reason, FORBIDDEN_CLASS_REASON, tag)
            self.assertEqual(rejection.forbidden_class, forbidden_class, tag)
            self.assertIn(
                rejection.forbidden_class, FORBIDDEN_SELF_MODIFICATION_CLASSES, tag
            )

    def test_error_class_matching_forbidden_behavior_is_rejected(self) -> None:
        lesson = _lesson(error_class="metric_gaming")
        self.assertEqual(classify_forbidden(lesson), "metric_gaming")

        result = self.generator.generate([lesson], champions=NON_PROMPT_CHAMPIONS)
        self.assertEqual(result.challengers, ())
        self.assertEqual(len(result.rejections), 1)
        self.assertEqual(result.rejections[0].reason, FORBIDDEN_CLASS_REASON)
        self.assertEqual(result.rejections[0].forbidden_class, "metric_gaming")

    def test_forbidden_classes_mirror_recursive_improvement_contract(self) -> None:
        contract = RecursiveImprovementContract(
            primary=MetricSpec("task_success_rate", MetricDirection.MAXIMIZE),
            guardrails=(),
        )
        self.assertEqual(
            FORBIDDEN_SELF_MODIFICATION_CLASSES, frozenset(contract.forbidden_behaviors)
        )
        self.assertEqual(len(FORBIDDEN_SELF_MODIFICATION_CLASSES), 9)

    def test_unaccepted_lesson_status_rejected(self) -> None:
        with self.assertRaises(ChallengerGenerationError) as raised:
            _lesson(status="proposed")
        self.assertIn("only accepted lessons", str(raised.exception))

        result = self.generator.generate(
            [_lesson_document(status="quarantined")], champions=NON_PROMPT_CHAMPIONS
        )
        self.assertEqual(result.challengers, ())
        self.assertEqual(len(result.rejections), 1)
        self.assertEqual(result.rejections[0].lesson_id, "lesson-1")
        self.assertIn("only accepted lessons", result.rejections[0].reason)

    def test_unknown_applicability_tag_rejected_without_challenger(self) -> None:
        lesson = _lesson(applicability=("telemetry:dashboard",))
        self.assertIsNone(classify_forbidden(lesson))

        result = self.generator.generate([lesson], champions=NON_PROMPT_CHAMPIONS)
        self.assertEqual(result.challengers, ())
        self.assertEqual(len(result.rejections), 1)
        self.assertEqual(result.rejections[0].reason, UNRECOGNIZED_TAG_REASON)
        self.assertIsNone(result.rejections[0].forbidden_class)


if __name__ == "__main__":
    unittest.main()
