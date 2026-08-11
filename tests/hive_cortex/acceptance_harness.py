from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SPECIALIST_ROLES = (
    "orchestrator",
    "explorer",
    "architect",
    "builder",
    "curator",
    "integrator",
    "steward",
    "optimizer",
)

REQUIRED_RECEIPT_TESTS = (
    "acceptance-harness-self-tests",
    "negative-control-tests",
    "cross-language-fixture-tests",
)

GENUINE_HUMAN_AUTHORITY = {
    "credential",
    "legal",
    "financial",
    "production-access",
    "protected-branch",
    "owner-value",
    "consent",
    "external-contract",
}


@dataclass(frozen=True)
class FixtureSpec:
    fixture_id: str
    scenario: str
    language: str
    root: Path
    languages: tuple[str, ...]
    tests_present: bool


@dataclass(frozen=True)
class Consultation:
    requester: str
    consulted: tuple[str, ...]
    independent: bool = True


@dataclass(frozen=True)
class Approval:
    actor: str
    approved_by: str
    candidate_commit: str


@dataclass(frozen=True)
class EffectReceipt:
    role: str
    effect_id: str


@dataclass(frozen=True)
class AcceptanceRun:
    roles: tuple[str, ...]
    consultations: tuple[Consultation, ...]
    approvals: tuple[Approval, ...]
    sealed_candidate: str
    observed_commits: tuple[str, ...]
    sealed_commits: tuple[str, ...]
    future_commits: tuple[str, ...]
    authority_class: str | None
    human_escalated: bool
    expected_effects: tuple[EffectReceipt, ...]
    receipt_candidate: str
    receipt_roles: tuple[str, ...]
    receipt_effects: tuple[EffectReceipt, ...]


def _read_fixture(path: Path) -> FixtureSpec:
    document = json.loads((path / "fixture.json").read_text(encoding="utf-8"))
    languages = tuple(document.get("languages", (document["language"],)))
    return FixtureSpec(
        fixture_id=document["fixture_id"],
        scenario=document["scenario"],
        language=document["language"],
        root=path,
        languages=languages,
        tests_present=bool(document["tests_present"]),
    )


def load_fixture_inventory(root: Path) -> tuple[FixtureSpec, ...]:
    """Load only declared fixtures; source files are never executed by this harness."""

    fixtures = tuple(_read_fixture(path) for path in sorted(root.iterdir()) if path.is_dir())
    if not fixtures:
        raise AssertionError("fixture inventory is empty")
    return fixtures


def validate_fixture_inventory(fixtures: Iterable[FixtureSpec]) -> tuple[str, ...]:
    items = tuple(fixtures)
    issues: list[str] = []
    scenarios = {item.scenario for item in items}
    languages = {language for item in items for language in item.languages}
    required_scenarios = {"hidden-defect", "misleading-README", "no-test", "monorepo"}
    missing_scenarios = required_scenarios - scenarios
    if missing_scenarios:
        issues.append("missing-fixture-scenarios:" + ",".join(sorted(missing_scenarios)))
    missing_languages = {"python", "node", "csharp"} - languages
    if missing_languages:
        issues.append("missing-fixture-languages:" + ",".join(sorted(missing_languages)))
    if not any(item.scenario == "monorepo" and len(item.languages) >= 3 for item in items):
        issues.append("monorepo-fixture-does-not-cover-all-languages")
    for item in items:
        if item.scenario == "no-test" and item.tests_present:
            issues.append(f"no-test-fixture-has-tests:{item.fixture_id}")
        if not (item.root / "fixture.json").is_file():
            issues.append(f"fixture-manifest-missing:{item.fixture_id}")
        if not (item.root / "README.md").is_file():
            issues.append(f"fixture-readme-missing:{item.fixture_id}")
    return tuple(issues)


def validate_run(run: AcceptanceRun) -> tuple[str, ...]:
    """Return stable, machine-readable failures for an adversarial acceptance run."""

    issues: list[str] = []
    missing_roles = set(SPECIALIST_ROLES) - set(run.roles)
    if missing_roles:
        issues.append("missing-role-wiring:" + ",".join(sorted(missing_roles)))
    if len(run.roles) != len(set(run.roles)):
        issues.append("duplicate-role-identity")

    for consultation in run.consultations:
        consulted = set(consultation.consulted)
        if not consultation.independent or consultation.requester in consulted or len(consulted) < 2:
            issues.append("fake-consultation:" + consultation.requester)

    for approval in run.approvals:
        if approval.actor == approval.approved_by:
            issues.append("self-approval:" + approval.actor)
        if approval.candidate_commit != run.sealed_candidate:
            issues.append("approval-candidate-mismatch")

    observed = set(run.observed_commits)
    sealed = set(run.sealed_commits)
    future = set(run.future_commits)
    if not observed.issubset(sealed):
        issues.append("future-leakage:observed-commit-not-sealed")
    if observed.intersection(future):
        issues.append("future-leakage:future-commit-observed")

    if run.human_escalated and run.authority_class not in GENUINE_HUMAN_AUTHORITY:
        issues.append("human-escalation-software-defect")

    expected_effect_ids = tuple(item.effect_id for item in run.expected_effects)
    actual_effect_ids = tuple(item.effect_id for item in run.receipt_effects)
    if run.receipt_candidate != run.sealed_candidate:
        issues.append("receipt-candidate-mismatch")
    if run.receipt_roles != run.roles:
        issues.append("receipt-role-sequence-mismatch")
    if actual_effect_ids != expected_effect_ids:
        issues.append("receipt-effect-sequence-mismatch")
    if any(item.role != run.roles[index] for index, item in enumerate(run.receipt_effects) if index < len(run.roles)):
        issues.append("receipt-effect-role-mismatch")
    return tuple(issues)
