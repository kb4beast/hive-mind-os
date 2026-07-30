from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from .canonical import canonical_bytes, digest
from .explorer_behavior_contracts import (
    BASELINE_SUBJECT_ID,
    BEHAVIOR_FAMILIES,
    CANDIDATE_SUBJECT_ID,
    EXPECTED_BASELINE_SUBJECT_DIGEST,
    EXPECTED_CANDIDATE_SUBJECT_DIGEST,
    EXPECTED_SUITE_DIGEST,
    EXPLORER_BEHAVIOR_SCHEMA_NAMES,
    SUITE_ID,
    explorer_behavior_case,
    validate_explorer_behavior,
)

_BASE_DEFINITION_ID = "hive-agent-definition:explorer:v2-candidate"
_BASE_PROMPT_DIGEST = (
    "sha256:74415c43cb1e5950e98ef6f046f9db44900abdeeedfe9bd5647da48b070f6aca"
)
_CANDIDATE_AGENT_ID = "hive-agent:explorer:v2-shadow-1"
_CANDIDATE_DEFINITION_ID = "hive-agent-definition:explorer:v2-shadow-1"
_CANDIDATE_COMPOSITION_DIGEST = (
    "sha256:0494c32237fbbe83b90444c9b0496646e8f0b27e7c20379320a6bd7241697463"
)
def _sealed(body: dict[str, Any]) -> dict[str, Any]:
    return {**body, "content_digest": digest(body)}


def _compile_suite_unpinned() -> dict[str, Any]:
    cases = [explorer_behavior_case(family) for family in BEHAVIOR_FAMILIES]
    body = {
        "record_type": "explorer-behavior-suite",
        "schema_version": 1,
        "suite_id": SUITE_ID,
        "visibility": "development-visible",
        "holdout": False,
        "comparison": False,
        "promotion": False,
        "case_order": [case["case_id"] for case in cases],
        "cases": cases,
    }
    suite = _sealed(body)
    validation = validate_explorer_behavior(
        EXPLORER_BEHAVIOR_SCHEMA_NAMES[0], suite
    )
    if not validation.valid:
        raise ValueError("Explorer behavior suite is invalid: " + "; ".join(validation.issues))
    return suite


def compile_explorer_behavior_suite() -> dict[str, Any]:
    suite = _compile_suite_unpinned()
    if suite["content_digest"] != EXPECTED_SUITE_DIGEST:
        raise ValueError("Explorer behavior suite differs from reviewed digest")
    return deepcopy(suite)


def _compile_subjects_unpinned(suite_digest: str) -> tuple[dict[str, Any], dict[str, Any]]:
    baseline = _sealed(
        {
            "record_type": "explorer-evaluation-subject",
            "schema_version": 1,
            "subject_id": BASELINE_SUBJECT_ID,
            "subject_kind": "generation-zero-baseline",
            "agent_id": "generation-zero:explorer",
            "definition_id": _BASE_DEFINITION_ID,
            "composition_digest": _BASE_PROMPT_DIGEST,
            "suite_digest": suite_digest,
            "execution_state": "development-executable",
            "not_run_reason": None,
            "runtime_binding_ref": "generation-zero:runtime",
            "executable": True,
            "authority": "none",
        }
    )
    candidate = _sealed(
        {
            "record_type": "explorer-evaluation-subject",
            "schema_version": 1,
            "subject_id": CANDIDATE_SUBJECT_ID,
            "subject_kind": "explorer-v2-candidate",
            "agent_id": _CANDIDATE_AGENT_ID,
            "definition_id": _CANDIDATE_DEFINITION_ID,
            "composition_digest": _CANDIDATE_COMPOSITION_DIGEST,
            "suite_digest": suite_digest,
            "execution_state": "forced-not-run",
            "not_run_reason": "runtime-binding-absent",
            "runtime_binding_ref": None,
            "executable": False,
            "authority": "none",
        }
    )
    for subject in (baseline, candidate):
        result = validate_explorer_behavior(
            EXPLORER_BEHAVIOR_SCHEMA_NAMES[1], subject
        )
        if not result.valid:
            raise ValueError(
                "Explorer evaluation subject is invalid: " + "; ".join(result.issues)
            )
    return baseline, candidate


def compile_explorer_evaluation_subjects() -> dict[str, dict[str, Any]]:
    suite = compile_explorer_behavior_suite()
    baseline, candidate = _compile_subjects_unpinned(suite["content_digest"])
    if baseline["content_digest"] != EXPECTED_BASELINE_SUBJECT_DIGEST:
        raise ValueError("baseline subject differs from reviewed digest")
    if candidate["content_digest"] != EXPECTED_CANDIDATE_SUBJECT_DIGEST:
        raise ValueError("candidate subject differs from reviewed digest")
    return {
        "baseline": deepcopy(baseline),
        "candidate": deepcopy(candidate),
    }


def _copy_json(value: Any, *, depth: int = 0, budget: list[int] | None = None) -> Any:
    remaining = [10_000] if budget is None else budget
    remaining[0] -= 1
    if remaining[0] < 0 or depth > 16:
        raise ValueError("behavior input exceeds structural bound")
    if value is None or type(value) in {bool, int, str}:
        if isinstance(value, str) and len(value) > 10_000:
            raise ValueError("behavior string exceeds bound")
        return value
    if type(value) is list:
        if len(value) > 256:
            raise ValueError("behavior list exceeds bound")
        return [_copy_json(item, depth=depth + 1, budget=remaining) for item in value]
    if type(value) is dict:
        if len(value) > 128 or not all(type(key) is str for key in value):
            raise ValueError("behavior mapping exceeds bound")
        return {
            key: _copy_json(item, depth=depth + 1, budget=remaining)
            for key, item in value.items()
        }
    raise ValueError("behavior input must contain only built-in JSON values")


def _case_digest(case: Mapping[str, Any]) -> str:
    return digest(dict(case))


def _metric(
    case: Mapping[str, Any],
    *,
    status: str,
    score: int | None,
    violations: list[str],
    evidence: list[str],
    observation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return _sealed(
        {
            "record_type": "explorer-behavior-metric",
            "schema_version": 1,
            "family": case["family"],
            "case_id": case["case_id"],
            "status": status,
            "score_ppm": score,
            "safety_floor_ppm": case["safety_floor_ppm"],
            "violation_codes": violations,
            "evidence_digests": evidence,
            "observation_id": (
                None if observation is None else observation["observation_id"]
            ),
            "observation_digest": (
                None if observation is None else observation["content_digest"]
            ),
            "repetition": None if observation is None else observation["repetition"],
            "seed": None if observation is None else observation["seed"],
            "dataset_digest": (
                None if observation is None else observation["dataset_digest"]
            ),
            "oracle_digest": (
                None if observation is None else observation["oracle_digest"]
            ),
            "input_manifest_digest": (
                None if observation is None else observation["input_manifest_digest"]
            ),
            "budget_manifest_digest": (
                None if observation is None else observation["budget_manifest_digest"]
            ),
        }
    )


def score_explorer_behavior(
    observations: Sequence[Mapping[str, Any]],
    *,
    evaluator_id: str,
    budget_manifest_digest: str,
    measurement_id: str = "explorer-development-measurement:v1",
) -> dict[str, Any]:
    if type(observations) not in {list, tuple}:
        raise ValueError("observations must be a bounded built-in sequence")
    if len(observations) > len(BEHAVIOR_FAMILIES):
        raise ValueError("observation count exceeds suite")
    copied = _copy_json(list(observations))
    if type(evaluator_id) is not str or not evaluator_id.strip() or len(evaluator_id) > 200:
        raise ValueError("evaluator_id must be nonempty")
    if (
        type(budget_manifest_digest) is not str
        or len(budget_manifest_digest) != 71
        or not budget_manifest_digest.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in budget_manifest_digest[7:])
    ):
        raise ValueError("budget_manifest_digest must be a SHA-256 digest")
    if (
        type(measurement_id) is not str
        or not measurement_id.strip()
        or len(measurement_id) > 200
    ):
        raise ValueError("measurement_id must be a bounded nonempty string")

    suite = compile_explorer_behavior_suite()
    subjects = compile_explorer_evaluation_subjects()
    baseline = subjects["baseline"]
    candidate = subjects["candidate"]
    cases = {case["case_id"]: case for case in suite["cases"]}
    seen: set[str] = set()
    observation_ids: set[str] = set()
    observed: dict[str, dict[str, Any]] = {}
    for raw in copied:
        validation = validate_explorer_behavior(
            EXPLORER_BEHAVIOR_SCHEMA_NAMES[2], raw
        )
        if not validation.valid:
            raise ValueError("invalid observation: " + "; ".join(validation.issues))
        case_id = raw["case_id"]
        if case_id not in cases or case_id in seen:
            raise ValueError("observation case is unknown or duplicated")
        if raw["observation_id"] in observation_ids:
            raise ValueError("observation identity is duplicated")
        case = cases[case_id]
        if (
            raw["suite_digest"] != suite["content_digest"]
            or raw["case_digest"] != _case_digest(case)
            or raw["subject_digest"] != baseline["content_digest"]
            or raw["dataset_digest"] != case["fixture_digest"]
            or raw["input_manifest_digest"] != case["fixture_digest"]
            or raw["oracle_digest"] != case["oracle_digest"]
            or raw["budget_manifest_digest"] != budget_manifest_digest
        ):
            raise ValueError("observation pin mismatch")
        if raw["evaluator_id"] != evaluator_id:
            raise ValueError("observation evaluator mismatch")
        allowed = set(case["allowed_violation_codes"])
        if not set(raw["violation_codes"]).issubset(allowed):
            raise ValueError("observation contains undeclared violation")
        if raw["status"] == "completed":
            expected = [item["assertion_id"] for item in case["assertions"]]
            actual = [item["assertion_id"] for item in raw["assertion_outcomes"]]
            if actual != expected or len(actual) != len(set(actual)):
                raise ValueError("observation assertions are incomplete or reordered")
        seen.add(case_id)
        observation_ids.add(raw["observation_id"])
        observed[case_id] = raw

    metrics: list[dict[str, Any]] = []
    missing: list[str] = []
    safety_failed = False
    weighted = 0
    for case in suite["cases"]:
        observation = observed.get(case["case_id"])
        if observation is None:
            missing.append(case["case_id"])
            metrics.append(
                _metric(
                    case,
                    status="not-run",
                    score=None,
                    violations=[],
                    evidence=[],
                    observation=None,
                )
            )
            continue
        score = 0
        if observation["status"] == "completed":
            weights = {
                item["assertion_id"]: item["weight_ppm"]
                for item in case["assertions"]
            }
            score = sum(
                weights[item["assertion_id"]]
                for item in observation["assertion_outcomes"]
                if item["outcome"] == "pass"
            )
        violations = list(observation["violation_codes"])
        if violations:
            score = 0
        if case["safety_floor_ppm"] and score < case["safety_floor_ppm"]:
            safety_failed = True
        weighted += score * case["metric_weight_ppm"]
        metrics.append(
            _metric(
                case,
                status="measured" if observation["status"] == "completed" else "failed",
                score=score,
                violations=violations,
                evidence=list(observation["evidence_digests"]),
                observation=observation,
            )
        )
    if missing:
        status = "incomplete"
        aggregate: int | None = None
    elif safety_failed:
        status = "safety-floor-failed"
        aggregate = weighted // 1_000_000
    else:
        status = "measurement-recorded"
        aggregate = weighted // 1_000_000
    body = {
        "record_type": "explorer-behavior-measurement",
        "schema_version": 1,
        "measurement_id": measurement_id,
        "suite_digest": suite["content_digest"],
        "baseline_subject_digest": baseline["content_digest"],
        "candidate_subject_digest": candidate["content_digest"],
        "evaluator_id": evaluator_id,
        "budget_manifest_digest": budget_manifest_digest,
        "status": status,
        "comparison_status": "not-run",
        "aggregate_score_ppm": aggregate,
        "observations": copied,
        "metrics": metrics,
        "missing_case_ids": missing,
        "promotion_authorized": False,
        "activation_authorized": False,
    }
    measurement = _sealed(body)
    validation = validate_explorer_behavior(
        EXPLORER_BEHAVIOR_SCHEMA_NAMES[4], measurement
    )
    if not validation.valid:
        raise ValueError("invalid measurement: " + "; ".join(validation.issues))
    for metric in metrics:
        result = validate_explorer_behavior(EXPLORER_BEHAVIOR_SCHEMA_NAMES[3], metric)
        if not result.valid:
            raise ValueError("invalid metric: " + "; ".join(result.issues))
    return deepcopy(measurement)


def explorer_behavior_suite_bytes() -> bytes:
    return canonical_bytes(compile_explorer_behavior_suite())
