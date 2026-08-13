"""Local-only Builder and Curator fixture integration for Phase 7.

The module intentionally has no provider, network, remote-Git, or legacy-runtime
dependency.  The sole write adapter is explicit, root-confined, and invoked through
the kernel effect gateway with a capability token.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from ...brain_kernel.authority import AuthorityDenied, AuthorityRegistry
from ...brain_kernel.canonical import canonical_digest
from ...brain_kernel.context import CompiledContext, ContextRequest
from ...brain_kernel.contracts import (
    Budget,
    ConstraintEnvelope,
    ContextManifest,
    EffectIntent,
    RoleResult,
)
from ...brain_kernel.effects import EffectGateway, sealed_intent
from ...brain_kernel.roles import RoleInvocation, result_digest
from ...curator import AcceptanceCheck, CuratorReview, check_context_manifest
from ...ledger import EvidenceLedger
from .role_handlers import RepositoryRoleHandlers

_DIGEST = "sha256:" + "0" * 64
_MISSION_ID = "MISSION-phase7-local"
_TIME = "1970-01-01T00:00:00Z"
_AUTH_TIME = "2029-01-01T00:00:00Z"


@dataclass(frozen=True, slots=True)
class LocalBuilderCuratorFixture:
    """Inspectable local evidence from a sealed Builder/Curator fixture run."""

    builder: RoleResult
    curator: RoleResult
    verdict: str
    seal_sequence: int
    candidate_access_sequence: int


class LocalWorkspaceAdapter:
    """A root-confined local write adapter; callers must use the effect gateway."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._payloads: dict[str, bytes] = {}

    def register_payload(self, content: bytes) -> str:
        digest = f"sha256:{sha256(content).hexdigest()}"
        prior = self._payloads.setdefault(digest, bytes(content))
        if prior != content:
            raise AuthorityDenied("payload digest is already bound to other content")
        return digest

    def materialize(self, source: str | Path, target: str) -> Path:
        destination = self._path(target)
        if destination.exists():
            raise AuthorityDenied("isolated workspace destination already exists")
        source_path = Path(source).resolve()
        if not source_path.is_dir():
            raise AuthorityDenied("isolated workspace source is unavailable")
        shutil.copytree(source_path, destination, ignore=shutil.ignore_patterns(".git"))
        return destination

    def write(self, target: str, content: bytes) -> None:
        path = self._path(target)
        if not path.parent.is_dir():
            raise AuthorityDenied("write target parent does not exist in isolated workspace")
        path.write_bytes(content)

    def apply(self, intent: EffectIntent) -> None:
        if intent.action != "write" or intent.target_adapter != "isolated-write":
            raise AuthorityDenied("local workspace adapter rejects this effect")
        try:
            content = self._payloads[intent.parameters_digest]
        except KeyError as error:
            raise AuthorityDenied("effect payload is unavailable") from error
        self.write(intent.target, content)

    def _path(self, target: str) -> Path:
        candidate = self.root.joinpath(*target.split("/"))
        try:
            candidate.parent.resolve().relative_to(self.root)
        except ValueError as error:
            raise AuthorityDenied("isolated workspace path escapes its root") from error
        if candidate.exists():
            try:
                candidate.resolve().relative_to(self.root)
            except ValueError as error:
                raise AuthorityDenied("isolated workspace target is a link escape") from error
        return candidate


def _context(role: str, work_id: str, attempt_id: str, *, evaluator: bool) -> CompiledContext:
    request = ContextRequest(
        mission_id=_MISSION_ID,
        work_id=work_id,
        attempt_id=attempt_id,
        role=role,
        charter_digest=_DIGEST,
        authority_digest=_DIGEST,
        token_budget=0,
        query="phase 7 sealed local fixture",
        now=_TIME,
        data_scopes=("repository",),
        hot_items=(),
        evaluator_mode=evaluator,
    )
    manifest = ContextManifest(
        request.mission_id,
        request.work_id,
        request.attempt_id,
        role,
        _DIGEST,
        _DIGEST,
        0,
        0,
        (),
        (),
        (),
        (),
        {"budget": 0},
        (),
        evaluator,
        canonical_digest({"role": role, "attempt": attempt_id}),
    )
    return CompiledContext(request, manifest, (), ())


def _invocation(role: str, work_id: str, attempt_id: str, *, evaluator: bool) -> RoleInvocation:
    return RoleInvocation(
        mission_id=_MISSION_ID,
        work_id=work_id,
        attempt_id=attempt_id,
        role=role,
        executor_id=f"phase7:local:{role}",
        context=_context(role, work_id, attempt_id, evaluator=evaluator),
        authority_envelope_digest=_DIGEST,
        evidence_refs=("fixture:evidence",),
        base_artifact_refs=("fixture:base",),
        candidate_artifact_refs=("fixture:candidate",),
    )


def _builder_envelope() -> ConstraintEnvelope:
    return ConstraintEnvelope(
        "AUTH-phase7-local",
        _MISSION_ID,
        "WORK-phase7-builder",
        None,
        "builder",
        "R1",
        ("write",),
        ("network", "push", "merge", "deploy"),
        ("candidate",),
        ("candidate",),
        (),
        (),
        (),
        (),
        Budget(1, 0, 0, 0, 0, 1, 1, 1),
        "2030-01-01T00:00:00Z",
        _DIGEST,
        _DIGEST,
    ).sealed()


def _with_receipt(result: RoleResult, receipt_digest: str) -> RoleResult:
    provisional = RoleResult(
        **{
            **asdict(result),
            "effect_receipt_refs": (receipt_digest,),
            "result_digest": _DIGEST,
        }
    )
    return RoleResult(**{**asdict(provisional), "result_digest": result_digest(provisional)})


def run_sealed_builder_curator_fixture(root: str | Path) -> LocalBuilderCuratorFixture:
    """Run one local Builder write followed by blind, fresh Curator reproduction."""

    root_path = Path(root).resolve()
    base = root_path / "base"
    base.mkdir(parents=True, exist_ok=False)
    (base / "app.txt").write_text("before\n", encoding="utf-8")
    adapter = LocalWorkspaceAdapter(root_path)
    adapter.materialize(base, "candidate")

    handlers = RepositoryRoleHandlers()
    builder = handlers.execute(_invocation("builder", "WORK-phase7-builder", "ATTEMPT-phase7-builder", evaluator=False))
    ledger = EvidenceLedger(root_path / "curator-ledger.sqlite3")
    try:
        review = CuratorReview(
            "PHASE7-local-review",
            ledger,
            objective="change the isolated candidate only",
            acceptance_criteria=(),
            base_workspace=base,
        )
        check = AcceptanceCheck("candidate-content", ("local-fixture-check",))
        review.seal((check,))

        registry = AuthorityRegistry()
        envelope = _builder_envelope()
        registry.mint_root(
            envelope,
            issuer="phase7:local:fixture-owner",
            authority_ref="local-fixture-policy",
            recorded_at=_TIME,
        )
        gateway = EffectGateway(authority=registry, clock=lambda: _AUTH_TIME)
        gateway.register_adapter("isolated-write", adapter.apply)
        parameters_digest = adapter.register_payload(b"after\n")
        intent = sealed_intent(
            EffectIntent(
                _MISSION_ID,
                "WORK-phase7-builder",
                "ATTEMPT-phase7-builder",
                builder.executor_id,
                "builder",
                "write",
                "R1",
                "isolated-write",
                "candidate/app.txt",
                parameters_digest,
                canonical_digest({"fixture": "builder-write"}),
                envelope.digest_value,
                (),
                "discard isolated candidate",
                "local-fixture-policy",
                canonical_digest({"effect": "phase7-builder-write"}),
            )
        )
        token = registry.authorize(
            envelope.digest_value, "write", intent.target, now=_AUTH_TIME
        )
        receipt = gateway.execute(intent, token)
        builder = _with_receipt(builder, receipt.receipt_digest)
        candidate_access_sequence = ledger.append_event(
            "PHASE7-local-review",
            "candidate.available",
            builder.executor_id,
            {"candidate_ref": "candidate/app.txt", "receipt": receipt.receipt_digest},
        )
        check_context_manifest(
            {
                "role": "phase7:local:curator",
                "prior_roles": [],
                "summaries": [],
                "receipt_digests": [],
                "provider_kind": "local-none",
                "model_id": "none",
                "provider_configuration": "none",
            },
            acting_identity=builder.executor_id,
            verifying_identity="phase7:local:curator",
            builder_receipt_digests=builder.effect_receipt_refs,
            seal_sequence=review.seal_sequence,
            head_access_sequence=candidate_access_sequence,
        )

        def command_runner(
            _: AcceptanceCheck,
        ) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
            succeeded = (root_path / "candidate" / "app.txt").read_text(encoding="utf-8") == "after\n"
            outcome = "succeeded" if succeeded else "failed"
            return (
                {
                    "result": outcome,
                    "execution": {
                        "requested_argv": ["local-fixture-check"],
                        "argv": ["local-fixture-check"],
                        "outcome": outcome,
                        "exit_code": 0 if succeeded else 1,
                        "stdout": {"truncated": False},
                        "stderr": {"truncated": False},
                    },
                },
                (),
            )

        verdict, _ = review.reproduce(
            head_workspace=root_path / "candidate",
            declared_paths=("app.txt",),
            command_runner=command_runner,
            repository_test_argv=("local-fixture-check",),
            delivery_verifier=lambda: (True, ()),
            provenance_resolves=True,
        )
        curator = handlers.execute(_invocation("curator", "WORK-phase7-curator", "ATTEMPT-phase7-curator", evaluator=True))
        return LocalBuilderCuratorFixture(
            builder,
            curator,
            verdict.decision,
            review.seal_sequence or 0,
            candidate_access_sequence,
        )
    finally:
        ledger.close()
