"""Provider-backed, effect-free execution of the canonical eight role contracts.

``RoleRuntime`` is the narrow adapter between the authority-bearing kernel role
protocol and the existing structured ``ModelBackend``.  The backend performs
bounded provider calls and ledger receipt work; this module binds the kernel
invocation to every prompt and converts the validated model turn back to a typed
``RoleResult``.  No method in this module writes, commits, merges, deploys,
promotes, accepts, or executes a tool effect.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Mapping, Sequence

from ..ledger import EvidenceLedger
from ..model_backend import ModelBackend
from ..model_provider import ModelProvider
from ..models import AgentResult, Evidence, Objective, Role, WorkItem
from ..roles import ROLE_CONTRACTS
from .canonical import canonical_digest
from .contracts import RoleResult
from .roles import (
    KERNEL_IMPLEMENTED_ROLES,
    RoleInvocation,
    RoleProtocolError,
    next_role,
    result_digest,
    role_allows_action,
    role_capabilities,
    role_prompt,
)


class RoleCapabilityDenied(RoleProtocolError):
    """Raised when a role asks the runtime for a forbidden capability."""


class RoleRuntime:
    """Run bounded provider cognition for all eight kernel roles.

    A runtime owns no authority and accepts no effect executor.  ``provider`` is
    the shared provider used by ``ModelBackend``; ``role_providers`` can bind a
    configured override to a specific role.  The model may propose actions, but
    those proposals are retained in the typed result and are never executed here.
    """

    def __init__(
        self,
        provider: ModelProvider | None = None,
        *,
        backend: ModelBackend | None = None,
        role_providers: Mapping[Role | str, ModelProvider] | None = None,
        ledger: EvidenceLedger | None = None,
    ) -> None:
        if backend is not None and provider is not None:
            raise ValueError("provide either backend or provider, not both")
        if backend is None and provider is None:
            raise ValueError("a configured provider or ModelBackend is required")
        if backend is None:
            assert provider is not None
            normalized_providers = {
                Role(role): value for role, value in (role_providers or {}).items()
            }
            backend = ModelBackend(
                provider,
                ledger=ledger,
                role_providers=normalized_providers,
            )
        self.backend = backend

    @property
    def roles(self) -> tuple[str, ...]:
        """The fixed lifecycle reachable through this runtime."""

        return KERNEL_IMPLEMENTED_ROLES

    def provider_for(self, role: str) -> ModelProvider:
        """Return the configured provider identity without invoking it."""

        try:
            kernel_role = Role(role)
        except ValueError as error:
            raise RoleProtocolError("role has no executable kernel handler") from error
        return self.backend.role_providers.get(kernel_role, self.backend.provider)

    def require_capability(self, role: str, action: str) -> None:
        """Fail closed for forbidden requests; never grants or executes authority."""

        if not role_allows_action(role, action):
            raise RoleCapabilityDenied(
                f"role {role!r} cannot request capability {action!r}"
            )

    def request_capability(self, invocation: RoleInvocation, action: str) -> dict[str, str]:
        """Return inert request metadata for an allowed capability.

        The returned object is deliberately not an executable callable or effect
        intent.  A later authority/effect adapter must independently validate and
        authorize any request.
        """

        self.require_capability(invocation.role, action)
        return {
            "role": invocation.role,
            "executor_id": invocation.executor_id,
            "action": action,
            "authority_envelope_digest": invocation.authority_envelope_digest,
            "status": "requested",
        }

    async def execute(
        self,
        invocation: RoleInvocation,
        *,
        prior_results: Sequence[RoleResult] = (),
    ) -> RoleResult:
        """Invoke one configured provider and return one evidence-bound result."""

        self._validate_invocation(invocation)
        capabilities = role_capabilities(invocation.role)
        legacy_role = Role(invocation.role)
        base_contract = ROLE_CONTRACTS[legacy_role]
        contract = replace(
            base_contract,
            mission=(base_contract.mission + "\n" + role_prompt(invocation.role)),
            required_outputs=capabilities.required_outputs,
            default_capabilities=capabilities.allowed_actions,
        )
        objective = Objective(
            goal=invocation.context.request.query,
            acceptance_criteria=capabilities.required_outputs,
            constraints=(
                "Models may propose typed results only; direct effects are forbidden.",
                "Allowed capability requests: " + ", ".join(capabilities.allowed_actions),
                "Forbidden actions: " + ", ".join(capabilities.forbidden_actions),
                "Role identity: " + invocation.executor_id,
                "Authority envelope: " + invocation.authority_envelope_digest,
            ),
        )
        work_item = WorkItem(
            objective_id=objective.id,
            role=legacy_role,
            instruction=self._instruction(invocation, prior_results),
            dependencies=tuple(item.work_id for item in prior_results),
        )
        context = tuple(self._agent_context(item) for item in prior_results)
        agent_result = await self.backend.execute(contract, work_item, objective, context)
        return self._to_role_result(invocation, capabilities.required_outputs, agent_result)

    async def run(self, invocation: RoleInvocation, *, prior_results: Sequence[RoleResult] = ()) -> RoleResult:
        """Alias for callers that model a role worker as a runnable handler."""

        return await self.execute(invocation, prior_results=prior_results)

    async def run_mission(self, invocations: Sequence[RoleInvocation]) -> tuple[RoleResult, ...]:
        """Run one ordered, bounded mission through each role exactly once."""

        supplied = tuple(invocations)
        observed = tuple(item.role for item in supplied)
        if observed != self.roles:
            raise RoleProtocolError(
                "a role mission must contain each canonical role exactly once in lifecycle order"
            )
        results: list[RoleResult] = []
        for invocation in supplied:
            results.append(await self.execute(invocation, prior_results=tuple(results)))
        return tuple(results)

    @staticmethod
    def _validate_invocation(invocation: RoleInvocation) -> None:
        if invocation.role not in KERNEL_IMPLEMENTED_ROLES:
            raise RoleProtocolError("role has no executable kernel handler")
        if invocation.context.request.evaluator_mode != (
            invocation.role == "curator"
        ):
            raise RoleProtocolError(
                "curator must use evaluator-isolated context and other roles must not"
            )

    @staticmethod
    def _instruction(
        invocation: RoleInvocation, prior_results: Sequence[RoleResult]
    ) -> str:
        manifest = invocation.context.manifest.to_document()
        request = invocation.context.request
        binding = {
            "mission_id": invocation.mission_id,
            "work_id": invocation.work_id,
            "attempt_id": invocation.attempt_id,
            "role": invocation.role,
            "executor_id": invocation.executor_id,
            "authority_envelope_digest": invocation.authority_envelope_digest,
            "context_manifest": manifest,
            "query": request.query,
            "data_scopes": list(request.data_scopes),
            "explicit_pins": list(request.explicit_pins),
            "evidence_refs": list(invocation.evidence_refs),
            "base_artifact_refs": list(invocation.base_artifact_refs),
            "candidate_artifact_refs": list(invocation.candidate_artifact_refs),
            "prior_role_result_digests": [item.result_digest for item in prior_results],
        }
        return (
            "Execute the bounded role contract using only this invocation binding. "
            "Return proposals and typed outputs; do not perform effects.\n"
            + json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )

    @staticmethod
    def _agent_context(result: RoleResult) -> AgentResult:
        return AgentResult(
            role=Role(result.role),
            work_item_id=result.work_id,
            summary=result.self_assessment,
            evidence=(
                Evidence(
                    kind="role-result",
                    summary=result.role,
                    source=f"kernel:{result.result_digest}",
                    payload={"result_digest": result.result_digest},
                ),
            ),
        )

    @staticmethod
    def _to_role_result(
        invocation: RoleInvocation,
        required_outputs: Sequence[str],
        agent_result: AgentResult,
    ) -> RoleResult:
        outputs = {
            evidence.summary: evidence.payload.get("content", "")
            for evidence in agent_result.evidence
            if evidence.kind == "contract-output"
        }
        output_refs = tuple(
            canonical_digest(
                {
                    "role": invocation.role,
                    "work_id": invocation.work_id,
                    "output": name,
                    "content": outputs[name],
                }
            )
            for name in required_outputs
        )
        provisional = RoleResult(
            mission_id=invocation.mission_id,
            work_id=invocation.work_id,
            attempt_id=invocation.attempt_id,
            role=invocation.role,
            executor_id=invocation.executor_id,
            context_manifest_digest=invocation.context.manifest.manifest_digest,
            authority_envelope_digest=invocation.authority_envelope_digest,
            base_artifact_refs=tuple(dict.fromkeys((*invocation.evidence_refs, *invocation.base_artifact_refs))),
            candidate_artifact_refs=invocation.candidate_artifact_refs,
            output_artifact_refs=output_refs,
            claims=tuple(required_outputs),
            effect_receipt_refs=(),
            unresolved_risks=("model proposals are unexecuted until separately authorized",),
            requested_next_role=next_role(invocation.role),
            self_assessment=agent_result.summary,
            result_digest="sha256:" + "0" * 64,
        )
        return replace(provisional, result_digest=result_digest(provisional))
