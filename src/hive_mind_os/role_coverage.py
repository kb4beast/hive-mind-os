"""Mission-level accounting for all eight specialist responsibilities."""

from __future__ import annotations

from dataclasses import dataclass

from .brain_kernel.canonical import canonical_digest

ROLES = (
    "orchestrator",
    "explorer",
    "architect",
    "builder",
    "curator",
    "integrator",
    "steward",
    "optimizer",
)


@dataclass(frozen=True, slots=True)
class RoleRow:
    role: str
    identity: str
    packages: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    mode: str = "direct"
    revisit_triggers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RoleCoveragePlan:
    mission_id: str
    cohort_id: str
    graph_digest: str
    policy_digest: str
    rows: tuple[RoleRow, ...]

    def __post_init__(self):
        if len(self.rows) != len(ROLES) or {r.role for r in self.rows} != set(ROLES):
            raise ValueError("coverage requires exactly eight specialist roles")
        if (
            any(not r.identity.strip() for r in self.rows)
            or len({r.identity for r in self.rows}) != 8
        ):
            raise ValueError("role identities must be present and distinct")

    @property
    def digest(self):
        return canonical_digest(self)


@dataclass(frozen=True, slots=True)
class RoleCoverageReceipt:
    plan_digest: str
    results: tuple[tuple[str, str, str], ...]
    complete: bool
    missing: tuple[str, ...] = ()

    @property
    def digest(self):
        return canonical_digest(self)


def build_coverage(
    plan: RoleCoveragePlan, results: dict[str, tuple[str, str]]
) -> RoleCoverageReceipt:
    rows = []
    missing = []
    for role in ROLES:
        result = results.get(role)
        row = next(r for r in plan.rows if r.role == role)
        if (
            not result
            or not all(isinstance(x, str) and x.strip() for x in result)
            or (row.packages and not row.evidence)
        ):
            missing.append(role)
            continue
        rows.append((role, result[0], result[1]))
    return RoleCoverageReceipt(plan.digest, tuple(rows), not missing, tuple(missing))
