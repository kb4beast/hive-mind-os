"""Sealed adapter for the narrow durable model-backed repository-mission lane.

This module deliberately binds a concrete, injected :class:`ModelBackend` to the
one-shot executor.  It stores only provider identities and configuration digests; it
never writes an endpoint URL, API value, request, prompt, or response to the mission
journal.  The adapter is not a provider authentication or reconciliation protocol.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Protocol, Sequence
from urllib.parse import urlsplit

from .acceptance import AcceptanceSpecification
from .durable_model_execution import (
    DurableModelExecutionContext,
    DurableModelRoleExecutor,
    PreparedDurableModelTurn,
)
from .model_backend import ModelBackend
from .model_turn_state import (
    ModelProviderIdentity,
    ModelTurnBudget,
    ModelTurnOutcome,
    ModelTurnPhase,
    ModelTurnStateError,
    ModelTurnStore,
)
from .models import AgentResult, AutonomyLevel, Evidence, Objective, Role, WorkItem
from .policy import PolicyEngine
from .prompt_registry import generation_zero_prompt, prompt_digest
from .roles import ROLE_CONTRACTS, RoleContract


class DurableRepositoryModelError(RuntimeError):
    """A repository model profile cannot be sealed or re-derived safely."""


@dataclass(frozen=True, slots=True)
class RedactionPolicy:
    """Explicit runtime redaction material for an injected durable-model adapter.

    The commitment is a local anti-drift binding for a caller-supplied secret set; it is
    not a signature, authentication proof, or substitute for an external policy
    authority.  Raw values never enter a mission profile or journal.
    """

    identifier: str
    digest: str
    secrets: Sequence[str] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.identifier, str)
            or not self.identifier
            or len(self.identifier) > 128
            or any(character.isspace() for character in self.identifier)
        ):
            raise ValueError("redaction policy identifier is invalid")
        _require_digest(self.digest, "redaction policy")
        normalized = tuple(
            value for value in self.secrets if isinstance(value, str) and value
        )
        if len(normalized) != len(self.secrets) or len(set(normalized)) != len(normalized):
            raise ValueError("redaction policy secrets must be nonempty and unique")
        object.__setattr__(self, "secrets", normalized)

    @property
    def material_commitment(self) -> str:
        return _digest({"redaction_secrets": list(self.secrets)})


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise DurableRepositoryModelError("durable repository model data is not canonical JSON") from error


def _digest(value: object) -> str:
    return "sha256:" + sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_digest(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise DurableRepositoryModelError(f"{label} must be a SHA-256 digest")
    return value


def _provider_projection(provider: object) -> tuple[dict[str, str], str]:
    config = getattr(provider, "config", None)
    kind = getattr(provider, "kind", None)
    if config is None or kind is None:
        raise DurableRepositoryModelError("model provider lacks a sealed configuration")
    host = urlsplit(config.base_url).hostname
    if host is None:
        raise DurableRepositoryModelError("model provider lacks a hostname")
    try:
        identity = ModelProviderIdentity.from_dict(
            {
                "kind": str(kind),
                "base_url_host": host.casefold(),
                "model_id": config.model,
            }
        )
    except ValueError as error:
        raise DurableRepositoryModelError("model provider identity is invalid") from error
    # The digest binds the effective configuration without retaining a URL, API value,
    # or environment-variable name in durable mission state.
    configuration_digest = _digest(
        {
            "kind": str(kind),
            "base_url": config.base_url,
            "model": config.model,
            "api_key_env": config.api_key_env,
            "timeout_s": config.timeout_s,
            "max_output_tokens": config.max_output_tokens,
            "temperature": config.temperature,
            "max_retries": config.max_retries,
        }
    )
    return identity.to_dict(), configuration_digest


@dataclass(frozen=True, slots=True)
class DurableRepositoryModelProfile:
    """Non-secret profile required to recover a model-backed repository mission.

    A profile is intentionally single-specification and has a fixed model-turn budget.
    It is created before a mission starts and re-derived from an injected runtime backend
    on resume.  A local digest is only a binding/integrity locator, never authentication.
    """

    profile_id: str
    acceptance_specification: AcceptanceSpecification
    budget: ModelTurnBudget
    policy_decision_ref: str
    policy_autonomy: AutonomyLevel
    lease_id: str
    redaction_policy_digest: str
    redaction_policy_id: str
    redaction_secret_commitment: str
    prompt_artifact_digests: Mapping[Role | str, str]
    providers: Mapping[Role | str, Mapping[str, object]]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_id, str)
            or not self.profile_id
            or len(self.profile_id) > 128
            or any(character.isspace() for character in self.profile_id)
        ):
            raise ValueError("durable repository model profile ID is invalid")
        if not isinstance(self.acceptance_specification, AcceptanceSpecification):
            raise ValueError("durable repository model profile requires one typed specification")
        if not isinstance(self.budget, ModelTurnBudget):
            raise ValueError("durable repository model profile requires a typed model budget")
        for field, value in (
            ("policy decision reference", self.policy_decision_ref),
            ("lease reference", self.lease_id),
            ("redaction policy ID", self.redaction_policy_id),
        ):
            if not isinstance(value, str) or not value or len(value) > 128:
                raise ValueError(f"durable repository model {field} is invalid")
        _require_digest(self.redaction_policy_digest, "redaction policy")
        _require_digest(self.redaction_secret_commitment, "redaction secret commitment")
        if not isinstance(self.policy_autonomy, AutonomyLevel):
            raise ValueError("durable repository model policy autonomy is invalid")

        prompts: dict[str, str] = {}
        for raw_role, digest in self.prompt_artifact_digests.items():
            try:
                role = Role(raw_role)
            except ValueError as error:
                raise ValueError("durable repository model profile has an unknown prompt role") from error
            prompts[role.value] = _require_digest(digest, "prompt artifact")
        if set(prompts) != {role.value for role in Role}:
            raise ValueError("durable repository model profile must pin every lifecycle prompt")

        providers: dict[str, dict[str, object]] = {}
        for raw_role, raw_provider in self.providers.items():
            try:
                role = Role(raw_role)
            except (ValueError, ModelTurnStateError) as error:
                raise ValueError("durable repository model profile has an unknown provider role") from error
            if not isinstance(raw_provider, Mapping):
                raise ValueError("durable repository model provider profile is invalid")
            identity = raw_provider.get("identity")
            if not isinstance(identity, Mapping):
                raise ValueError("durable repository model provider identity is invalid")
            try:
                stable_identity = ModelProviderIdentity.from_dict(identity).to_dict()
            except ValueError as error:
                raise ValueError("durable repository model provider identity is invalid") from error
            configuration_digest = _require_digest(
                raw_provider.get("configuration_digest"), "provider configuration"
            )
            selection_digest = _require_digest(
                raw_provider.get("selection_digest"), "provider selection"
            )
            providers[role.value] = {
                "identity": stable_identity,
                "configuration_digest": configuration_digest,
                "selection_digest": selection_digest,
            }
        if set(providers) != {role.value for role in Role}:
            raise ValueError("durable repository model profile must bind every lifecycle provider")
        object.__setattr__(self, "prompt_artifact_digests", MappingProxyType(prompts))
        object.__setattr__(
            self,
            "providers",
            MappingProxyType({name: MappingProxyType(value) for name, value in providers.items()}),
        )

    @classmethod
    def from_backend(
        cls,
        *,
        profile_id: str,
        acceptance_specification: AcceptanceSpecification,
        budget: ModelTurnBudget,
        policy_decision_ref: str,
        policy_autonomy: AutonomyLevel,
        lease_id: str,
        redaction_policy: RedactionPolicy,
        backend: ModelBackend,
    ) -> "DurableRepositoryModelProfile":
        prompts: dict[str, str] = {}
        for role in Role:
            if backend.prompt_registry is None:
                prompts[role.value] = prompt_digest(generation_zero_prompt(ROLE_CONTRACTS[role]))
            else:
                try:
                    _, digest = backend.prompt_registry.champion_prompt(role)
                except KeyError as error:
                    raise ValueError(
                        "durable repository model profiles require an already sealed prompt for every role"
                    ) from error
                prompts[role.value] = digest
        providers: dict[str, dict[str, object]] = {}
        for role in Role:
            identity, configuration_digest = _provider_projection(
                backend.role_providers.get(role, backend.provider)
            )
            providers[role.value] = {
                "identity": identity,
                "configuration_digest": configuration_digest,
                "selection_digest": _digest(
                    {
                        "role": role.value,
                        "provider": identity,
                        "provider_configuration_digest": configuration_digest,
                        "prompt_artifact_digest": prompts[role.value],
                    }
                ),
            }
        return cls(
            profile_id,
            acceptance_specification,
            budget,
            policy_decision_ref,
            policy_autonomy,
            lease_id,
            redaction_policy.digest,
            redaction_policy.identifier,
            redaction_policy.material_commitment,
            prompts,
            providers,
        )

    @classmethod
    def from_dict(cls, document: Mapping[str, object]) -> "DurableRepositoryModelProfile":
        if set(document) != {
            "schema_version",
            "profile_id",
            "acceptance_specification",
            "budget",
            "policy_decision_ref",
            "policy_autonomy",
            "lease_id",
            "redaction_policy_digest",
            "redaction_policy_id",
            "redaction_secret_commitment",
            "prompt_artifact_digests",
            "providers",
        } or document.get("schema_version") != 1:
            raise DurableRepositoryModelError("durable repository model profile has an unknown shape")
        specification = document.get("acceptance_specification")
        budget = document.get("budget")
        prompts = document.get("prompt_artifact_digests")
        providers = document.get("providers")
        if not isinstance(specification, Mapping) or not isinstance(budget, Mapping):
            raise DurableRepositoryModelError("durable repository model profile is incomplete")
        if not isinstance(prompts, Mapping) or not isinstance(providers, Mapping):
            raise DurableRepositoryModelError("durable repository model profile bindings are invalid")
        try:
            return cls(
                str(document.get("profile_id", "")),
                AcceptanceSpecification.from_dict(specification),
                ModelTurnBudget(**dict(budget)),
                str(document.get("policy_decision_ref", "")),
                AutonomyLevel(document.get("policy_autonomy")),
                str(document.get("lease_id", "")),
                str(document.get("redaction_policy_digest", "")),
                str(document.get("redaction_policy_id", "")),
                str(document.get("redaction_secret_commitment", "")),
                {str(key): str(value) for key, value in prompts.items()},
                {
                    str(key): dict(value)
                    for key, value in providers.items()
                    if isinstance(value, Mapping)
                },
            )
        except (TypeError, ValueError) as error:
            raise DurableRepositoryModelError("durable repository model profile is invalid") from error

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "profile_id": self.profile_id,
            "acceptance_specification": self.acceptance_specification.to_dict(),
            "budget": self.budget.to_dict(),
            "policy_decision_ref": self.policy_decision_ref,
            "policy_autonomy": int(self.policy_autonomy),
            "lease_id": self.lease_id,
            "redaction_policy_digest": self.redaction_policy_digest,
            "redaction_policy_id": self.redaction_policy_id,
            "redaction_secret_commitment": self.redaction_secret_commitment,
            "prompt_artifact_digests": dict(self.prompt_artifact_digests),
            "providers": {name: dict(value) for name, value in self.providers.items()},
        }

    @property
    def digest(self) -> str:
        return _digest(self.to_dict())

    def verify_backend(self, backend: ModelBackend) -> None:
        observed = DurableRepositoryModelProfile.from_backend(
            profile_id=self.profile_id,
            acceptance_specification=self.acceptance_specification,
            budget=self.budget,
            policy_decision_ref=self.policy_decision_ref,
            policy_autonomy=self.policy_autonomy,
            lease_id=self.lease_id,
            redaction_policy=RedactionPolicy(
                self.redaction_policy_id,
                self.redaction_policy_digest,
                (),
            ),
            backend=backend,
        )
        # ``from_backend`` cannot reconstruct private redaction material.  It validates
        # every non-secret provider/prompt binding; the runtime policy is checked below.
        observed_document = observed.to_dict()
        expected_document = self.to_dict()
        observed_document["redaction_secret_commitment"] = expected_document[
            "redaction_secret_commitment"
        ]
        if observed_document != expected_document:
            raise DurableRepositoryModelError(
                "injected model backend differs from the sealed durable repository profile"
            )

    def verify_policy(self, policy: PolicyEngine) -> None:
        if type(policy) is not PolicyEngine or policy.autonomy is not self.policy_autonomy:
            raise DurableRepositoryModelError(
                "repository policy differs from the sealed durable model profile"
            )

    def verify_redaction_policy(self, policy: RedactionPolicy) -> None:
        if (
            policy.identifier != self.redaction_policy_id
            or policy.digest != self.redaction_policy_digest
            or policy.material_commitment != self.redaction_secret_commitment
        ):
            raise DurableRepositoryModelError(
                "runtime redaction policy differs from the sealed durable model profile"
            )


class ModelBackendResolver(Protocol):
    """Re-derive an explicitly authorized in-process model backend on resume."""

    def __call__(self, profile: DurableRepositoryModelProfile) -> "DurableRepositoryModelBackend": ...


class ModelRoleAdmissionJournal(Protocol):
    """The narrow MissionStore surface that witnesses durable model dispatch."""

    def mission_root(self, mission_id: str) -> Path: ...

    def register_role_admission(
        self,
        mission_id: str,
        role: Role,
        input_digest: str,
    ) -> Mapping[str, object]: ...

    def role_admission(
        self,
        mission_id: str,
        role: Role,
    ) -> Mapping[str, object] | None: ...


class DurableRepositoryModelBackend:
    """Model backend adapter admitted only by ``RepositoryMission``'s durable lane."""

    def __init__(
        self,
        backend: ModelBackend,
        store: ModelTurnStore,
        profile: DurableRepositoryModelProfile,
        *,
        redaction_policy: RedactionPolicy,
        admission_journal: ModelRoleAdmissionJournal,
    ) -> None:
        if store.path == ":memory:" or "memory" in store.path.casefold():
            raise ValueError("durable repository model backend requires a filesystem turn store")
        try:
            # Import at construction time to avoid the MissionStore serialization
            # dependency cycle while refusing a forged in-memory journal substitute.
            from .mission_store import MissionStore

            if type(admission_journal) is not MissionStore:
                raise DurableRepositoryModelError(
                    "durable repository model admission requires the concrete MissionStore"
                )
            expected_store = (
                Path(admission_journal.mission_root(profile.budget.mission_id))
                / "model-turns.sqlite3"
            ).resolve()
            if Path(store.path).resolve() != expected_store:
                raise DurableRepositoryModelError(
                    "durable model turn store does not belong to its admission journal"
                )
            profile.verify_backend(backend)
            profile.verify_redaction_policy(redaction_policy)
            profile_text = _canonical_json(profile.to_dict())
            if any(secret in profile_text for secret in redaction_policy.secrets):
                raise DurableRepositoryModelError(
                    "sealed durable repository profile contains configured redaction material"
                )
        except BaseException:
            store.close()
            raise
        self.backend = backend
        self.store = store
        self.profile = profile
        self.admission_journal = admission_journal
        self._executor = DurableModelRoleExecutor(
            backend,
            store,
            DurableModelExecutionContext(
                mission_id=profile.budget.mission_id,
                state_ref=f"MISSION_STATE:{profile.budget.mission_id}:1",
                acceptance_specification=profile.acceptance_specification,
                policy_decision_ref=profile.policy_decision_ref,
                lease_id=profile.lease_id,
                redaction_policy_digest=profile.redaction_policy_digest,
                budget=profile.budget,
                prompt_artifact_digests=profile.prompt_artifact_digests,
                redaction_secrets=redaction_policy.secrets,
            ),
        )

    def identity_for_role(self, role: Role) -> Mapping[str, str]:
        provider = self.profile.providers[role.value]
        identity = provider.get("identity")
        if not isinstance(identity, Mapping):
            raise DurableRepositoryModelError("sealed provider identity is malformed")
        kind = identity.get("kind")
        model_id = identity.get("model_id")
        configuration = provider.get("configuration_digest")
        if (
            not isinstance(kind, str)
            or not isinstance(model_id, str)
            or not isinstance(configuration, str)
        ):
            raise DurableRepositoryModelError("sealed provider profile is malformed")
        return {
            "provider_kind": kind,
            "model_id": model_id,
            "configuration": configuration,
        }

    def prepare(
        self,
        contract: RoleContract,
        work_item: WorkItem,
        objective: Objective,
        context: tuple[AgentResult, ...],
    ) -> PreparedDurableModelTurn:
        prepared = self._executor.prepare(contract, work_item, objective, context)
        provider = self.profile.providers[contract.role.value]
        identity = provider.get("identity")
        configuration_digest = provider.get("configuration_digest")
        selection_digest = provider.get("selection_digest")
        if (
            not isinstance(identity, Mapping)
            or not isinstance(configuration_digest, str)
            or not isinstance(selection_digest, str)
        ):
            raise DurableRepositoryModelError("sealed provider profile is malformed")
        if (
            prepared.plan.provider.to_dict() != dict(identity)
            or prepared.plan.configuration_digest != configuration_digest
            or prepared.plan.selection_digest != selection_digest
        ):
            raise DurableRepositoryModelError(
                "prepared model turn differs from the sealed durable repository profile"
            )
        return prepared

    def admit(self, prepared: PreparedDurableModelTurn, input_digest: str) -> None:
        self._executor.admit_prepared(prepared)
        try:
            self.admission_journal.register_role_admission(
                self.profile.budget.mission_id,
                prepared.contract.role,
                input_digest,
            )
        except Exception as error:
            raise DurableRepositoryModelError(
                "durable model admission could not be witnessed by the mission journal"
            ) from error

    def verify_admitted(self, prepared: PreparedDurableModelTurn) -> None:
        """Require an existing model-store admission without recreating it."""

        try:
            record = self.store.record(prepared.plan.logical_turn_id)
            self.store.durable_record(
                prepared.plan,
                budget=self.profile.budget,
                reservation=prepared.reservation,
            )
        except (KeyError, ModelTurnStateError) as error:
            raise DurableRepositoryModelError(
                "sealed model-role admission is unavailable from the durable model store"
            ) from error
        if record.plan.digest != prepared.plan.digest:
            raise DurableRepositoryModelError(
                "sealed model-role admission differs from its prepared turn"
            )

    def _verify_role_admission_witness(
        self,
        prepared: PreparedDurableModelTurn,
    ) -> None:
        """Query the injected journal; caller-supplied witness mappings are insufficient."""

        admission = self.admission_journal.role_admission(
            self.profile.budget.mission_id,
            prepared.contract.role,
        )
        if admission is None:
            raise DurableRepositoryModelError(
                "durable model role admission witness is absent from the mission journal"
            )
        required = {
            "schema_version",
            "role",
            "input_digest",
            "model_turn_id",
            "model_turn_plan_digest",
            "admission_digest",
        }
        if set(admission) != required:
            raise DurableRepositoryModelError(
                "durable model role admission witness has an unknown shape"
            )
        document = {
            key: admission[key]
            for key in required
            if key != "admission_digest"
        }
        digest = admission.get("admission_digest")
        if (
            document.get("schema_version") != 1
            or document.get("role") != prepared.contract.role.value
            or not isinstance(document.get("input_digest"), str)
            or not str(document["input_digest"]).startswith("sha256:")
            or document.get("model_turn_id") != prepared.plan.logical_turn_id
            or document.get("model_turn_plan_digest") != prepared.plan.digest
            or not isinstance(digest, str)
            or digest != _digest(document)
        ):
            raise DurableRepositoryModelError(
                "durable model role admission witness differs from its prepared turn"
            )

    async def execute_prepared(self, prepared: PreparedDurableModelTurn) -> AgentResult:
        del prepared
        raise DurableRepositoryModelError(
            "durable repository model dispatch requires a MissionStore admission witness"
        )

    async def execute_admitted(
        self,
        prepared: PreparedDurableModelTurn,
    ) -> AgentResult:
        self._verify_role_admission_witness(prepared)
        self.verify_admitted(prepared)
        return await self._executor.execute_admitted(prepared)

    def verify_completed_role(
        self,
        completion: Mapping[str, object],
        role: Role,
        work_item_id: str,
    ) -> None:
        """Revalidate a role journal's terminal model-turn binding before rehydration."""

        turn_id = completion.get("model_turn_id")
        plan_digest = completion.get("model_turn_plan_digest")
        role_result_digest = completion.get("model_role_result_digest")
        if (
            not isinstance(turn_id, str)
            or not isinstance(plan_digest, str)
            or not isinstance(role_result_digest, str)
        ):
            raise DurableRepositoryModelError("completed model role lacks terminal turn bindings")
        try:
            record = self.store.record(turn_id)
            self.store.budget_usage(self.profile.budget.mission_id)
        except (KeyError, ModelTurnStateError) as error:
            raise DurableRepositoryModelError(
                "completed model role references an invalid durable model turn"
            ) from error
        if (
            record.phase is not ModelTurnPhase.COMPLETED
            or record.result is None
            or record.result.outcome is not ModelTurnOutcome.SUCCEEDED
            or record.role_result is None
            or record.plan.digest != plan_digest
            or record.plan.role != role.value
            or record.plan.work_item_id != work_item_id
            or record.role_result.digest != role_result_digest
            or record.result.structured_result_digest != role_result_digest
        ):
            raise DurableRepositoryModelError(
                "completed model role differs from its terminal durable model turn"
            )

    async def execute(
        self,
        contract: RoleContract,
        work_item: WorkItem,
        objective: Objective,
        context: tuple[AgentResult, ...],
    ) -> AgentResult:
        raise DurableRepositoryModelError(
            "durable repository model execution requires the RepositoryMission role journal"
        )


def agent_result_document(result: AgentResult) -> dict[str, object]:
    """Return the exact, closed projection used for resumed model context."""

    evidence: list[dict[str, object]] = []
    for item in result.evidence:
        if not isinstance(item.payload, dict):
            raise DurableRepositoryModelError("model role evidence payload is not an object")
        if set(item.payload) - {"content", "receipt_digests"}:
            raise DurableRepositoryModelError("model role evidence payload has an unknown field")
        payload: dict[str, object] = {}
        if "content" in item.payload:
            if not isinstance(item.payload["content"], str):
                raise DurableRepositoryModelError("model role evidence content is invalid")
            payload["content"] = item.payload["content"]
        if "receipt_digests" in item.payload:
            values = item.payload["receipt_digests"]
            if not isinstance(values, list) or any(
                not isinstance(value, str) or _require_digest(value, "receipt") != value
                for value in values
            ):
                raise DurableRepositoryModelError("model role receipt bindings are invalid")
            payload["receipt_digests"] = list(values)
        evidence.append(
            {
                "kind": item.kind,
                "summary": item.summary,
                "source": item.source,
                "payload": payload,
                "created_at": item.created_at,
            }
        )
    document = {
        "schema_version": 1,
        "role": result.role.value,
        "work_item_id": result.work_item_id,
        "summary": result.summary,
        "evidence": evidence,
        "proposed_actions": list(result.proposed_actions),
        "lessons": list(result.lessons),
        "success": result.success,
        "completed_at": result.completed_at,
    }
    # Ensure no noncanonical JSON value can acquire a digest merely by serialization.
    _canonical_json(document)
    return document


def agent_result_from_document(document: Mapping[str, object]) -> AgentResult:
    required = {
        "schema_version",
        "role",
        "work_item_id",
        "summary",
        "evidence",
        "proposed_actions",
        "lessons",
        "success",
        "completed_at",
    }
    if set(document) != required or document.get("schema_version") != 1:
        raise DurableRepositoryModelError("completed model role result has an unknown shape")
    try:
        role = Role(document["role"])
    except ValueError as error:
        raise DurableRepositoryModelError("completed model role result has an invalid role") from error
    work_item_id = document.get("work_item_id")
    summary = document.get("summary")
    evidence_value = document.get("evidence")
    actions = document.get("proposed_actions")
    lessons = document.get("lessons")
    completed_at = document.get("completed_at")
    if (
        not isinstance(work_item_id, str)
        or not isinstance(summary, str)
        or not isinstance(evidence_value, list)
        or not isinstance(actions, list)
        or not isinstance(lessons, list)
        or type(document.get("success")) is not bool
        or not isinstance(completed_at, str)
    ):
        raise DurableRepositoryModelError("completed model role result is malformed")
    evidence: list[Evidence] = []
    for item in evidence_value:
        if not isinstance(item, Mapping) or set(item) != {
            "kind", "summary", "source", "payload", "created_at"
        }:
            raise DurableRepositoryModelError("completed model evidence is malformed")
        payload = item.get("payload")
        if not isinstance(payload, dict):
            raise DurableRepositoryModelError("completed model evidence payload is malformed")
        evidence.append(
            Evidence(
                str(item.get("kind", "")),
                str(item.get("summary", "")),
                str(item.get("source", "")),
                dict(payload),
                str(item.get("created_at", "")),
            )
        )
    if any(not isinstance(item, str) for item in actions + lessons):
        raise DurableRepositoryModelError("completed model role text fields are malformed")
    result = AgentResult(
        role,
        work_item_id,
        summary,
        tuple(evidence),
        tuple(actions),
        tuple(lessons),
        bool(document["success"]),
        completed_at,
    )
    # Reapply the exact serializer to make malformed nested values fail closed.
    if agent_result_document(result) != dict(document):
        raise DurableRepositoryModelError("completed model role result is noncanonical")
    return result


def agent_result_digest(result: AgentResult) -> str:
    return _digest(agent_result_document(result))


def document_digest(document: Mapping[str, object]) -> str:
    return _digest(dict(document))
