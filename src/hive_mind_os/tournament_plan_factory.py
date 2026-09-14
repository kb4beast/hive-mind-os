"""Generate sealed external tournament plans without coupling direct agents to DAGs.

This module belongs to the Hive Mind orchestration host.  It produces inert
portable-plan data for a repository subject; it neither imports direct agent
implementations nor authenticates execution, integration, or promotion.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .dag_standard import (
    COMPILER_PACKAGE_DIGEST,
    COMPILER_PACKAGE_ID,
    STANDARD_SOURCE_PATH,
    STANDARD_VERSION,
    WORK_PACKAGE_COMPILER_PACKAGE_DIGEST,
    WORK_PACKAGE_COMPILER_PACKAGE_ID,
    WORK_PACKAGE_REQUIREMENT_IDS,
    WORK_PACKAGE_REQUIREMENTS_DIGEST,
    WORK_PACKAGE_REQUIREMENTS_PATH,
    WORK_PACKAGE_SOURCE_INVENTORY_DIGEST,
    WORK_PACKAGE_SOURCE_INVENTORY_ID,
    WORK_PACKAGE_SOURCE_INVENTORY_PATH,
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
    NodeEffectMode,
    NodeExecutionContract,
    PortableNode,
    PortablePlanBundle,
    PortableWorkPackageContract,
    PublicationStage,
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
    require_digest,
    require_identifier,
    strict_json_object,
)

_FIXTURE_STAGE_KINDS = {
    "BASELINE-001": "analysis",
    "AGENTS-010": "analysis",
    "ORCHESTRATION-020": "analysis",
    "RUNTIME-030": "runtime-audit",
    "LEARNING-040": "analysis",
    "PROPOSE-042": "proposal",
    "CROSS-045": "cross-examination",
    "REVISE-048": "revision",
    "COURT-050": "court-selection",
    "CHALLENGER-060": "build",
    "VERIFY-070": "verification",
    "JUDGE-075": "court-result",
    "INTEGRATE-080": "integration",
}

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
    """Create an all-role tournament with one bounded idea revision round.

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
            plan_id="external-all-aspect-tournament-v2",
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
        if not inventory or any(
            not isinstance(item, EvidenceReference) for item in inventory
        ):
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
                "Seal the exact request, repository snapshot, target contracts, and constitutional boundaries.",
                (),
                ("orchestrator", "explorer"),
                ("discover",),
                (
                    "The request, subject, target, commit, and tree are retained exactly.",
                    "No historical plan is reused as authority for the fresh objective.",
                    "The repository identity and selected brain destination are recorded without assuming a Hive Mind source layout.",
                ),
                authority_id,
                evidence_ids,
                verify=True,
            ),
            cls._node(
                "AGENTS-010",
                "Inspect the target's behavior, user needs, and ownership to discover concrete improvement opportunities.",
                ("BASELINE-001",),
                ("explorer", "curator"),
                ("discover", "validate"),
                (
                    "Findings cite the target's actual source and tests, including repositories without agent classes.",
                    "Hive Mind's eight worker roles remain external to the target application's architecture.",
                ),
                authority_id,
                evidence_ids,
            ),
            cls._node(
                "ORCHESTRATION-020",
                "Audit the target's architecture, interfaces, delivery boundaries, and compatibility with external orchestration.",
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
                    "Immutable challenger versions retain a stable idea identity or an explicit parent idea link.",
                    "A proposer cannot evaluate or promote its own challenger.",
                ),
                authority_id,
                evidence_ids,
            ),
            cls._node(
                "PROPOSE-042",
                "Champion concrete improvement hypotheses and compare their expected user value with considered alternatives.",
                ("AGENTS-010", "LEARNING-040", "ORCHESTRATION-020", "RUNTIME-030"),
                ("explorer", "optimizer", "orchestrator"),
                ("discover", "grow"),
                (
                    "Each idea has a stable idea identity, source claims, advocate identity, hypothesis, and a bounded experiment or reproduction plan.",
                    "Experiment proposals state expected value, uncertainty, cost, and rollback; they need not already prove superiority.",
                    "Considered alternatives and their selection rationale remain in the brain trace.",
                ),
                authority_id,
                evidence_ids,
            ),
            cls._node(
                "CROSS-045",
                "Independently challenge every proposed idea with concrete counterexamples, failure modes, and proportionate evidence requests.",
                ("PROPOSE-042",),
                ("curator", "steward", "integrator"),
                ("validate", "maintain", "integrate"),
                (
                    "Each idea has a cross-examiner distinct from its advocate and an independent expert witness appropriate to the claim.",
                    "Challenge receipts name checks, evidence, findings, and actionable objections; a completed challenge may find no blocking defect.",
                    "Each objection states the affected claim, severity, reason, and evidence needed at the current stage.",
                ),
                authority_id,
                evidence_ids,
                verify=True,
            ),
            cls._node(
                "REVISE-048",
                "Record an evidence-backed response to each challenge and one bounded revision when it can resolve an actionable objection.",
                ("CROSS-045",),
                ("explorer", "architect", "optimizer"),
                ("discover", "design", "grow"),
                (
                    "A revision keeps the stable idea identity and immutable version history, or creates an explicitly linked child idea.",
                    "Every return to an earlier agent records who returned it, why, the receiving role, and what evidence or change is needed.",
                    "Original objections, dissent, responses, and rejected versions remain visible; a response may explain why no revision is needed.",
                    "This run permits one revision round; further work remains a linked follow-up generation instead of a cycle or silent discard.",
                ),
                authority_id,
                evidence_ids,
            ),
            cls._node(
                "COURT-050",
                "Independently review challenge responses and select proportionate, reversible experiments.",
                ("REVISE-048",),
                ("curator", "architect"),
                ("validate", "design"),
                (
                    "The judge is distinct from the scout, advocate, cross-examiner, architect, builder, and affected champion; material revisions receive independent re-examination.",
                    "Every selected experiment has a supported hypothesis, executable acceptance or reproduction, bounded scope, rollback, and a distinct verifier.",
                    "Selection applies the current design or implementation burden; code receipts, held-out wins, and superiority benchmarks are required only at their later applicable stages.",
                    "Every idea receives adopt, adapt, defer, reject, or quarantine with reasons; remediable gaps identify the next role and concrete return conditions.",
                    "No selected idea is also recorded as promoted; unresolved critical risk and authority gaps still stop the affected experiment.",
                ),
                authority_id,
                evidence_ids,
                verify=True,
            ),
            cls._node(
                "CHALLENGER-060",
                "Implement selected challengers in isolated target workspaces with focused tests and neutral evidence artifacts.",
                ("COURT-050",),
                ("builder", "architect"),
                ("build", "design"),
                (
                    "Changes follow the target repository's architecture and preserve its public contracts.",
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
                "JUDGE-075",
                "Adjudicate independently reproduced results and record whether to retain, revise, defer, reject, or recommend a verified challenger.",
                ("VERIFY-070",),
                ("curator", "optimizer"),
                ("validate", "grow"),
                (
                    "The result judge is distinct from the scout, advocate, cross-examiner, architect, builder, and affected champion and cites independent verification receipts.",
                    "A promotion recommendation requires applicable code, test, outcome, held-out evaluation, regression, and safety evidence; superiority claims require multiple pinned comparators.",
                    "Rejection, deferral, and return decisions name their reason, receiving role, remaining obligations, and any linked follow-up idea.",
                ),
                authority_id,
                evidence_ids,
                verify=True,
            ),
            cls._node(
                "INTEGRATE-080",
                "Prepare reversible delivery and publish a human-readable brain trace of every idea and decision.",
                ("JUDGE-075",),
                ("integrator", "optimizer", "orchestrator"),
                ("integrate", "grow"),
                (
                    "This plan never merges, promotes, or mutates a protected target.",
                    "The recommendation names rollback and the next independently authorized action.",
                    "The selected brain contains readable links from source and idea through championing, challenge, response, revisions, verdict, tests, and delivery receipts.",
                    "Each idea shows current status, immutable history, parent or stable identity, rejection or return reasons, next role, and unfinished obligations even when no challenger is selected.",
                    "The brain projection is repository-scoped and usable as local Markdown without requiring Obsidian or changing target application dependencies.",
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
            NodeExecutionContract(
                stage_kind=_FIXTURE_STAGE_KINDS[node_id],
                execution_role=roles[0],
                worker_capability="candidate-workspace"
                if build
                else "subject-inspector",
                effect_mode=(
                    NodeEffectMode.BOUNDED_WRITE if build else NodeEffectMode.READ_ONLY
                ),
                exclusive_writer=build,
                required_outputs=(
                    "summary",
                    "findings",
                    "acceptance_evidence",
                    "ideas",
                    "selected_idea_ids",
                    "changed_paths",
                ),
                success_transition=(
                    "selected-experiment-or-no-change"
                    if _FIXTURE_STAGE_KINDS[node_id] == "court-selection"
                    else "release-dependents"
                ),
            ),
        )


class WholeOSPlanFactory:
    """Compile the court-selected 34-node handoff into an inert v2 plan.

    The checked node-contract document is the canonical prose-to-contract
    translation.  This factory never reads host configuration, activates a
    plan, signs a manifest, or performs a publication stage.
    """

    PLAN_ID = "whole-os-successor-campaign-v1"
    CONTRACT_SCHEMA = "whole-os-node-contracts/v2"
    NODE_FIELDS = {
        "id",
        "objective",
        "dependencies",
        "owner_role",
        "roles",
        "lifecycle_stages",
        "minimum_route",
        "contract_path",
        "contract_section",
        "contract_digest",
        "requirement_ids",
        "source_ids",
        "semantic_locks",
        "write_paths",
        "acceptance_criteria",
        "rollback",
        "output_contracts",
        "publication_stage",
        "independent_review_required",
        "completion_rule",
    }

    def __init__(self, generator: PlanGenerator | None = None) -> None:
        self._generator = generator or PlanGenerator()

    def build(
        self,
        request: PlanGenerationRequest,
        *,
        standard: PinnedArtifact,
        authority: AuthorityEnvelope,
        evidence: Iterable[EvidenceReference],
        node_contracts: Mapping[str, Any],
        source_inventory: PinnedArtifact,
        requirements: PinnedArtifact,
    ) -> PortablePlanBundle:
        repository = TournamentPlanFactory._repository_subject(request)
        TournamentPlanFactory._validate_standard(standard)
        TournamentPlanFactory._validate_authority(authority)
        evidence_inventory = TournamentPlanFactory._evidence_inventory(evidence)
        admitted_sources, admitted_requirements = self._validate_namespaces(
            evidence_inventory,
            source_inventory=source_inventory,
            requirements=requirements,
        )
        nodes = self._nodes(
            authority.authority_id,
            evidence_inventory,
            node_contracts,
            admitted_sources=admitted_sources,
            admitted_requirements=admitted_requirements,
        )
        return PortablePlanBundle(
            schema_version=2,
            plan_id=self.PLAN_ID,
            request_id=request.request_id,
            objective_digest=request.objective_digest,
            subject=SubjectBinding.for_repository(repository),
            standard=StandardBinding(
                STANDARD_VERSION,
                STANDARD_SOURCE_PATH,
                standard.digest,
                len(standard.content),
                git_blob_id(standard.content),
                WORK_PACKAGE_COMPILER_PACKAGE_ID,
                WORK_PACKAGE_COMPILER_PACKAGE_DIGEST,
            ),
            resources=(
                ResourceRequirement(
                    "implementation-workspaces",
                    "compute",
                    4,
                    "workspace",
                    ("isolated", "reversible"),
                ),
            ),
            capabilities=TournamentPlanFactory._capabilities(authority.authority_id),
            adapters=TournamentPlanFactory._adapters(),
            authority=(authority,),
            budgets=(
                BudgetAllocation(
                    "route-t1", BudgetPolicy(2_700, 12, 120_000, 24_000, 0, 64, 4)
                ),
                BudgetAllocation(
                    "route-t2", BudgetPolicy(5_400, 20, 240_000, 40_000, 0, 128, 4)
                ),
                BudgetAllocation(
                    "route-t3", BudgetPolicy(7_200, 28, 360_000, 60_000, 0, 192, 4)
                ),
            ),
            recovery=RecoveryPolicy(
                3,
                True,
                True,
                (
                    "authority-gap",
                    "capability-gap",
                    "contract-contradiction",
                    "evidence-gap",
                    "resource-exhaustion",
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
                360_000,
                60_000,
                45_000,
                "measured-or-unavailable",
                "stop",
            ),
            evidence=evidence_inventory,
            nodes=nodes,
        )

    def generate(
        self,
        request: PlanGenerationRequest,
        *,
        standard: PinnedArtifact,
        authority: AuthorityEnvelope,
        evidence: Iterable[EvidenceReference],
        node_contracts: Mapping[str, Any],
        source_inventory: PinnedArtifact,
        requirements: PinnedArtifact,
        node_mappings: PinnedArtifact,
        sources: Iterable[PinnedArtifact],
        compiler: PinnedArtifact,
    ) -> tuple[GeneratedPlan, bool]:
        plan = self.build(
            request,
            standard=standard,
            authority=authority,
            evidence=evidence,
            node_contracts=node_contracts,
            source_inventory=source_inventory,
            requirements=requirements,
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
    def _validate_namespaces(
        evidence: tuple[EvidenceReference, ...],
        *,
        source_inventory: PinnedArtifact,
        requirements: PinnedArtifact,
    ) -> tuple[frozenset[str], frozenset[str]]:
        if source_inventory.digest != WORK_PACKAGE_SOURCE_INVENTORY_DIGEST:
            raise ContractViolation(
                "whole-OS source namespace is not the accepted N00 bytes"
            )
        source_document = strict_json_object(
            source_inventory.content, maximum_bytes=1_000_000
        )
        if (
            source_document.get("schema") != "whole-os-source-inventory/v1"
            or source_document.get("inventory_id") != WORK_PACKAGE_SOURCE_INVENTORY_ID
        ):
            raise ContractViolation("whole-OS source namespace is not accepted N00")
        source_entries = source_document.get("sources")
        if not isinstance(source_entries, list) or not source_entries:
            raise ContractViolation("whole-OS source inventory requires sources")
        source_ids: list[str] = []
        for source in source_entries:
            if not isinstance(source, Mapping) or "id" not in source:
                raise ContractViolation("whole-OS source inventory entry lacks id")
            source_id = source["id"]
            require_identifier(source_id, "whole-OS source inventory id")
            source_ids.append(source_id)
        if len(set(source_ids)) != len(source_ids):
            raise ContractViolation("whole-OS source inventory has duplicate ids")

        if requirements.digest != WORK_PACKAGE_REQUIREMENTS_DIGEST:
            raise ContractViolation(
                "whole-OS requirements are not the accepted N00 bytes"
            )
        requirement_document = strict_json_object(
            requirements.content, maximum_bytes=1_000_000
        )
        if requirement_document.get("schema") != "whole-os-handoff-requirements/v1":
            raise ContractViolation("whole-OS requirements schema is unsupported")
        requirement_entries = requirement_document.get("requirements")
        if not isinstance(requirement_entries, list):
            raise ContractViolation("whole-OS requirements inventory requires a list")
        requirement_ids = tuple(
            item.get("id") if isinstance(item, Mapping) else None
            for item in requirement_entries
        )
        if requirement_ids != WORK_PACKAGE_REQUIREMENT_IDS:
            raise ContractViolation("whole-OS requirement ids are not accepted R01-R18")

        accepted_source = tuple(
            item for item in evidence if item.evidence_id == "accepted-n00-inventory"
        )
        accepted_requirements = tuple(
            item for item in evidence if item.evidence_id == "accepted-n00-requirements"
        )
        if (
            len(accepted_source) != 1
            or accepted_source[0].digest != source_inventory.digest
            or accepted_source[0].source != WORK_PACKAGE_SOURCE_INVENTORY_PATH
            or accepted_source[0].claim_ids != ("N00-ACCEPTED",)
            or len(accepted_requirements) != 1
            or accepted_requirements[0].digest != requirements.digest
            or accepted_requirements[0].source != WORK_PACKAGE_REQUIREMENTS_PATH
            or accepted_requirements[0].claim_ids != WORK_PACKAGE_REQUIREMENT_IDS
        ):
            raise ContractViolation(
                "whole-OS namespaces lack accepted N00 evidence bindings"
            )
        return frozenset(source_ids), frozenset(WORK_PACKAGE_REQUIREMENT_IDS)

    @classmethod
    def _nodes(
        cls,
        authority_id: str,
        evidence: tuple[EvidenceReference, ...],
        document: Mapping[str, Any],
        *,
        admitted_sources: frozenset[str],
        admitted_requirements: frozenset[str],
    ) -> tuple[PortableNode, ...]:
        if set(document) != {
            "schema",
            "source_inventory",
            "requirement_inventory",
            "nodes",
        }:
            raise ContractViolation("whole-OS node-contract document is not closed")
        if document["schema"] != cls.CONTRACT_SCHEMA:
            raise ContractViolation("unsupported whole-OS node-contract schema")
        source_inventory = document["source_inventory"]
        if not isinstance(source_inventory, Mapping) or set(source_inventory) != {
            "inventory_id",
            "sha256",
        }:
            raise ContractViolation("whole-OS source inventory binding is incomplete")
        require_digest(source_inventory["sha256"], "whole-OS source inventory digest")
        if (
            source_inventory["inventory_id"] != WORK_PACKAGE_SOURCE_INVENTORY_ID
            or source_inventory["sha256"] != WORK_PACKAGE_SOURCE_INVENTORY_DIGEST
        ):
            raise ContractViolation(
                "whole-OS source namespace is not the accepted N00 inventory"
            )
        if not any(
            item.evidence_id == "accepted-n00-inventory"
            and item.digest == source_inventory["sha256"]
            for item in evidence
        ):
            raise ContractViolation(
                "whole-OS node contracts are not bound to accepted N00 evidence"
            )
        requirement_inventory = document["requirement_inventory"]
        if not isinstance(requirement_inventory, Mapping) or set(
            requirement_inventory
        ) != {"path", "sha256", "requirement_ids"}:
            raise ContractViolation(
                "whole-OS requirement inventory binding is incomplete"
            )
        if (
            requirement_inventory["path"] != WORK_PACKAGE_REQUIREMENTS_PATH
            or requirement_inventory["sha256"] != WORK_PACKAGE_REQUIREMENTS_DIGEST
            or requirement_inventory["requirement_ids"]
            != list(WORK_PACKAGE_REQUIREMENT_IDS)
        ):
            raise ContractViolation(
                "whole-OS requirement namespace is not accepted N00"
            )
        node_documents = document["nodes"]
        if not isinstance(node_documents, list):
            raise ContractViolation("whole-OS nodes must be an object list")
        expected_ids = {f"N{index:02d}" for index in range(34)}
        observed_ids = {
            item.get("id") for item in node_documents if isinstance(item, Mapping)
        }
        if len(node_documents) != 34 or observed_ids != expected_ids:
            raise ContractViolation("whole-OS node set must be exactly N00 through N33")
        evidence_ids = tuple(item.evidence_id for item in evidence)
        result: list[PortableNode] = []
        for item in node_documents:
            if not isinstance(item, Mapping) or set(item) != cls.NODE_FIELDS:
                raise ContractViolation("whole-OS node contract is not closed")
            for field in (
                "dependencies",
                "roles",
                "lifecycle_stages",
                "requirement_ids",
                "source_ids",
                "semantic_locks",
                "write_paths",
                "acceptance_criteria",
                "output_contracts",
            ):
                if not isinstance(item[field], list) or any(
                    type(value) is not str for value in item[field]
                ):
                    raise ContractViolation(
                        f"whole-OS node {item['id']} {field} must be a string list"
                    )
            try:
                publication_stage = PublicationStage(item["publication_stage"])
            except (TypeError, ValueError) as error:
                raise ContractViolation("unknown whole-OS publication stage") from error
            unknown_sources = set(item["source_ids"]) - admitted_sources
            if unknown_sources:
                raise ContractViolation(
                    f"whole-OS node {item['id']} cites unadmitted source id(s): "
                    + ", ".join(sorted(unknown_sources))
                )
            unknown_requirements = set(item["requirement_ids"]) - admitted_requirements
            if unknown_requirements:
                raise ContractViolation(
                    f"whole-OS node {item['id']} cites unadmitted requirement id(s): "
                    + ", ".join(sorted(unknown_requirements))
                )
            package = PortableWorkPackageContract(
                1,
                1,
                item["contract_path"],
                item["contract_section"],
                item["contract_digest"],
                tuple(item["requirement_ids"]),
                tuple(item["source_ids"]),
                tuple(item["semantic_locks"]),
                tuple(item["write_paths"]),
                item["minimum_route"],
                tuple(item["output_contracts"]),
                publication_stage,
                item["independent_review_required"],
                item["completion_rule"],
            )
            route = item["minimum_route"].lower()
            result.append(
                PortableNode(
                    item["id"],
                    item["objective"],
                    tuple(item["dependencies"]),
                    ("implementation-workspaces",),
                    (
                        "inspect-subject",
                        "build-direct-challenger",
                        "run-independent-checks",
                        "record-evidence",
                    ),
                    (
                        "subject-inspector",
                        "candidate-workspace",
                        "test-runner",
                        "evidence-writer",
                    ),
                    authority_id,
                    f"route-{route}",
                    evidence_ids,
                    tuple(item["acceptance_criteria"]),
                    item["rollback"],
                    tuple(item["roles"]),
                    tuple(item["lifecycle_stages"]),
                    NodeExecutionContract(
                        "whole-os-work-package",
                        item["owner_role"].lower(),
                        "candidate-workspace",
                        NodeEffectMode.BOUNDED_WRITE,
                        True,
                        tuple(item["output_contracts"]),
                    ),
                    package,
                )
            )
        observed_requirements = {
            requirement_id
            for node in result
            for requirement_id in node.work_package.requirement_ids  # type: ignore[union-attr]
        }
        if observed_requirements != admitted_requirements:
            raise ContractViolation(
                "whole-OS nodes lose or substitute accepted requirements"
            )
        return tuple(result)


__all__ = [
    "TournamentPlanFactory",
    "WholeOSPlanFactory",
]
