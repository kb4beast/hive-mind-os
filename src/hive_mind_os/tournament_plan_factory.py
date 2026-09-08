"""Generate sealed external tournament plans without coupling direct agents to DAGs.

This module belongs to the Hive Mind orchestration host.  It produces inert
portable-plan data for a repository subject; it neither imports direct agent
implementations nor authenticates execution, integration, or promotion.
"""

from __future__ import annotations

from collections.abc import Iterable

from .dag_standard import (
    COMPILER_PACKAGE_DIGEST,
    COMPILER_PACKAGE_ID,
    STANDARD_SOURCE_PATH,
    STANDARD_VERSION,
    git_blob_id,
)
from .plan_generation import (
    GeneratedPlan,
    PinnedArtifact,
    PlanGenerationRequest,
    PlanGenerator,
)
from .portable_plan import (
    BudgetAllocation,
    PortableNode,
    PortablePlanBundle,
    RepositorySubject,
    StandardBinding,
    SubjectBinding,
)
from .runtime_contracts import (
    AdapterRequirement,
    AuthorityEnvelope,
    BudgetPolicy,
    CapabilityRequirement,
    ContractViolation,
    EvidenceReference,
    IntegrationPolicy,
    RecoveryPolicy,
    ResourceRequirement,
    TokenPolicy,
    canonical_digest,
)

_REQUIRED_LOCAL_ACTIONS = frozenset(
    {"inspect", "local-edit", "local-test", "prepare-evidence"}
)
_REQUIRED_DENIED_ACTIONS = frozenset(
    {
        "credential",
        "deployment",
        "merge",
        "payment",
        "production-mutation",
        "protected-merge",
        "push",
    }
)


class TournamentPlanFactory:
    """Create one standard all-role tournament topology for a fresh request.

    The caller supplies the already-pinned standard, evidence, and a
    local-reversible authority envelope.  A raw plan produced here is still only
    a proposal: :meth:`generate` seals it through ``PlanGenerator`` and the
    resulting activation material still needs an authenticated external host.
    """

    def __init__(self, generator: PlanGenerator | None = None) -> None:
        self._generator = generator or PlanGenerator()

    def build(
        self,
        request: PlanGenerationRequest,
        *,
        standard: PinnedArtifact,
        authority: AuthorityEnvelope,
        evidence: Iterable[EvidenceReference],
    ) -> PortablePlanBundle:
        """Create an inert, request-bound tournament plan for one repository."""

        repository = self._repository_subject(request)
        self._validate_standard(standard)
        self._validate_authority(authority)
        evidence_inventory = self._evidence_inventory(evidence)
        return PortablePlanBundle(
            schema_version=1,
            plan_id="external-all-aspect-tournament-v1",
            request_id=request.request_id,
            objective_digest=request.objective_digest,
            subject=SubjectBinding.for_repository(repository),
            standard=StandardBinding(
                STANDARD_VERSION,
                STANDARD_SOURCE_PATH,
                standard.digest,
                len(standard.content),
                git_blob_id(standard.content),
                COMPILER_PACKAGE_ID,
                COMPILER_PACKAGE_DIGEST,
            ),
            resources=self._resources(),
            capabilities=self._capabilities(authority.authority_id),
            adapters=self._adapters(),
            authority=(authority,),
            budgets=self._budgets(),
            recovery=RecoveryPolicy(
                3,
                True,
                True,
                (
                    "authority-gap",
                    "candidate-drift",
                    "evidence-gap",
                    "independent-verifier-unavailable",
                ),
            ),
            integration=IntegrationPolicy(
                "compare-and-swap",
                request.target,
                canonical_digest(
                    {"commit": repository.commit, "tree": repository.tree}
                ),
                True,
                True,
            ),
            token_policy=TokenPolicy(
                240_000,
                60_000,
                30_000,
                "measured-or-unavailable",
                "stop",
            ),
            evidence=evidence_inventory,
            nodes=self._nodes(authority.authority_id, evidence_inventory),
        )

    def generate(
        self,
        request: PlanGenerationRequest,
        *,
        standard: PinnedArtifact,
        authority: AuthorityEnvelope,
        evidence: Iterable[EvidenceReference],
        node_mappings: PinnedArtifact,
        sources: Iterable[PinnedArtifact],
        compiler: PinnedArtifact,
    ) -> tuple[GeneratedPlan, bool]:
        """Build and seal the external plan; never execute or activate it."""

        plan = self.build(
            request,
            standard=standard,
            authority=authority,
            evidence=evidence,
        )
        return self._generator.generate(
            request,
            plan,
            node_mappings=node_mappings,
            sources=sources,
            standard=standard,
            standard_version=STANDARD_VERSION,
            compiler=compiler,
        )

    @staticmethod
    def _repository_subject(request: PlanGenerationRequest) -> RepositorySubject:
        if request.subject_kind != "repository":
            raise ContractViolation(
                "external tournament factory currently requires a repository subject"
            )
        if (
            request.repository_id is None
            or request.parent_commit is None
            or request.parent_tree is None
        ):
            raise ContractViolation(
                "repository tournament request requires repository commit and tree bindings"
            )
        return RepositorySubject(
            request.repository_id,
            request.parent_commit,
            request.parent_tree,
            request.target,
        )

    @staticmethod
    def _validate_standard(standard: PinnedArtifact) -> None:
        if not isinstance(standard, PinnedArtifact):
            raise ContractViolation("tournament standard must be a pinned artifact")

    @staticmethod
    def _validate_authority(authority: AuthorityEnvelope) -> None:
        if not isinstance(authority, AuthorityEnvelope):
            raise ContractViolation("tournament authority must be a typed envelope")
        if authority.external_effects:
            raise ContractViolation("tournament plan cannot declare external effects")
        missing_allowed = _REQUIRED_LOCAL_ACTIONS - set(authority.allowed_actions)
        missing_denied = _REQUIRED_DENIED_ACTIONS - set(authority.denied_actions)
        if missing_allowed or missing_denied:
            raise ContractViolation(
                "tournament authority must allow local work and deny external control actions"
            )

    @staticmethod
    def _evidence_inventory(
        evidence: Iterable[EvidenceReference],
    ) -> tuple[EvidenceReference, ...]:
        inventory = tuple(evidence)
        if not inventory or any(not isinstance(item, EvidenceReference) for item in inventory):
            raise ContractViolation("tournament plan requires typed evidence")
        if len({item.evidence_id for item in inventory}) != len(inventory):
            raise ContractViolation("tournament evidence identifiers must be unique")
        return inventory

    @staticmethod
    def _resources() -> tuple[ResourceRequirement, ...]:
        return (
            ResourceRequirement("read-slots", "compute", 4, "worker", ("read-only",)),
            ResourceRequirement(
                "candidate-workspace", "exclusive", 1, "workspace", ("reversible",)
            ),
            ResourceRequirement(
                "verification-slots", "compute", 2, "worker", ("independent",)
            ),
            ResourceRequirement(
                "evidence-ledger", "exclusive", 1, "writer", ("append-only",)
            ),
        )

    @staticmethod
    def _adapters() -> tuple[AdapterRequirement, ...]:
        return (
            AdapterRequirement(
                "subject-inspector",
                "subject.inspect",
                "v1",
                canonical_digest({"mode": "read-only"}),
            ),
            AdapterRequirement(
                "candidate-workspace",
                "candidate.local",
                "v1",
                canonical_digest({"mode": "reversible"}),
            ),
            AdapterRequirement(
                "test-runner",
                "test.local",
                "v1",
                canonical_digest({"mode": "independent"}),
            ),
            AdapterRequirement(
                "evidence-writer",
                "evidence.local",
                "v1",
                canonical_digest({"mode": "append-only"}),
            ),
        )

    @staticmethod
    def _capabilities(authority_id: str) -> tuple[CapabilityRequirement, ...]:
        return (
            CapabilityRequirement(
                "inspect-subject",
                "inspect",
                "none",
                authority_id,
                "subject-inspector",
            ),
            CapabilityRequirement(
                "build-direct-challenger",
                "local-edit",
                "local-reversible",
                authority_id,
                "candidate-workspace",
            ),
            CapabilityRequirement(
                "run-independent-checks",
                "local-test",
                "local-reversible",
                authority_id,
                "test-runner",
            ),
            CapabilityRequirement(
                "record-evidence",
                "prepare-evidence",
                "local-reversible",
                authority_id,
                "evidence-writer",
            ),
        )

    @staticmethod
    def _budgets() -> tuple[BudgetAllocation, ...]:
        return (
            BudgetAllocation(
                "audit-budget", BudgetPolicy(900, 4, 120_000, 30_000, 0, 20, 4)
            ),
            BudgetAllocation(
                "build-budget", BudgetPolicy(3_600, 12, 240_000, 60_000, 0, 64, 4)
            ),
            BudgetAllocation(
                "verification-budget",
                BudgetPolicy(2_400, 8, 180_000, 40_000, 0, 48, 4),
            ),
        )

    @classmethod
    def _nodes(
        cls,
        authority_id: str,
        evidence: tuple[EvidenceReference, ...],
    ) -> tuple[PortableNode, ...]:
        evidence_ids = tuple(item.evidence_id for item in evidence)
        return (
            cls._node(
                "BASELINE-001",
                "Seal the exact request, repository snapshot, direct-agent contracts, and constitutional boundaries.",
                (),
                ("orchestrator", "explorer"),
                ("discover",),
                (
                    "The request, subject, target, commit, and tree are retained exactly.",
                    "No historical plan is reused as authority for the fresh objective.",
                ),
                authority_id,
                evidence_ids,
                verify=True,
            ),
            cls._node(
                "AGENTS-010",
                "Audit direct role ownership and identify only behavior gaps that belong in one class per agent file.",
                ("BASELINE-001",),
                ("explorer", "curator"),
                ("discover", "validate"),
                (
                    "Every constitutional role is inspected as a direct source file.",
                    "Direct agent modules contain no DAG import or DAG reference.",
                ),
                authority_id,
                evidence_ids,
            ),
            cls._node(
                "ORCHESTRATION-020",
                "Audit plan generation, external DAG validation, parallel scheduling, delivery export, and activation boundaries.",
                ("BASELINE-001",),
                ("architect", "integrator"),
                ("design", "integrate"),
                (
                    "The generated plan remains external to delivered application code.",
                    "Raw plan bytes cannot grant execution or integration authority.",
                ),
                authority_id,
                evidence_ids,
            ),
            cls._node(
                "RUNTIME-030",
                "Audit recovery, effect safety, supply-chain controls, CI, and platform portability for regression seams.",
                ("BASELINE-001",),
                ("steward", "curator"),
                ("maintain", "validate"),
                (
                    "Failure and recovery tests are retained and exercised.",
                    "No guardrail is weakened to obtain a passing qualification result.",
                ),
                authority_id,
                evidence_ids,
            ),
            cls._node(
                "LEARNING-040",
                "Audit challenger lineage, independent evaluation, promotion boundaries, and measurement guardrails.",
                ("BASELINE-001",),
                ("optimizer", "explorer"),
                ("grow", "discover"),
                (
                    "Every proposal is an immutable challenger rather than an in-place mutation.",
                    "A proposer cannot evaluate or promote its own challenger.",
                ),
                authority_id,
                evidence_ids,
            ),
            cls._node(
                "COURT-050",
                "Cross-examine audit findings and select only evidence-backed direct-code challengers.",
                ("AGENTS-010", "LEARNING-040", "ORCHESTRATION-020", "RUNTIME-030"),
                ("curator", "architect"),
                ("validate", "design"),
                (
                    "Every selected candidate has a hypothesis, rollback, and distinct verifier.",
                    "Unsafe, coupled, or unsupported candidates are rejected or deferred.",
                ),
                authority_id,
                evidence_ids,
                verify=True,
            ),
            cls._node(
                "CHALLENGER-060",
                "Implement selected challengers as direct source files, focused tests, and neutral evidence artifacts.",
                ("COURT-050",),
                ("builder", "architect"),
                ("build", "design"),
                (
                    "Changed agent behavior remains in one class per agent file.",
                    "Target source and configuration gain no Hive Mind workspace or DAG-plan dependency.",
                ),
                authority_id,
                evidence_ids,
                build=True,
            ),
            cls._node(
                "VERIFY-070",
                "Independently reproduce the candidate's acceptance and delivery-boundary checks.",
                ("CHALLENGER-060",),
                ("curator", "steward"),
                ("validate", "maintain"),
                (
                    "The verifier is distinct from the challenger builder.",
                    "Failures and dissent are retained as evidence rather than suppressed.",
                ),
                authority_id,
                evidence_ids,
                verify=True,
            ),
            cls._node(
                "INTEGRATE-080",
                "Issue an evidence-only recommendation to retain, open a PR, retest, defer, reject, or quarantine.",
                ("VERIFY-070",),
                ("integrator", "optimizer", "orchestrator"),
                ("integrate", "grow"),
                (
                    "This plan never merges, promotes, or mutates a protected target.",
                    "The recommendation names rollback and the next independently authorized action.",
                ),
                authority_id,
                evidence_ids,
                verify=True,
            ),
        )

    @staticmethod
    def _node(
        node_id: str,
        objective: str,
        dependencies: tuple[str, ...],
        roles: tuple[str, ...],
        lifecycle_stages: tuple[str, ...],
        acceptance_criteria: tuple[str, ...],
        authority_id: str,
        evidence_ids: tuple[str, ...],
        *,
        build: bool = False,
        verify: bool = False,
    ) -> PortableNode:
        resource_ids = ["read-slots"]
        capability_ids = ["inspect-subject"]
        adapter_ids = ["subject-inspector"]
        budget_id = "audit-budget"
        if build:
            resource_ids.append("candidate-workspace")
            capability_ids.append("build-direct-challenger")
            adapter_ids.append("candidate-workspace")
            budget_id = "build-budget"
        if verify:
            resource_ids.extend(("verification-slots", "evidence-ledger"))
            capability_ids.extend(("run-independent-checks", "record-evidence"))
            adapter_ids.extend(("test-runner", "evidence-writer"))
            budget_id = "verification-budget"
        return PortableNode(
            node_id,
            objective,
            dependencies,
            tuple(resource_ids),
            tuple(capability_ids),
            tuple(adapter_ids),
            authority_id,
            budget_id,
            evidence_ids,
            acceptance_criteria,
            "Retain receipts and supersede the candidate; never mutate the champion in place.",
            roles,
            lifecycle_stages,
        )


__all__ = ["TournamentPlanFactory"]
