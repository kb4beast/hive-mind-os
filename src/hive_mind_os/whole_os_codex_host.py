"""Trusted local Codex composition for the durable Whole-OS service.

The public service document stays inert.  This host-owned module observes one
real Git checkout and one native Codex installation, seals their identities in
external state, obtains a fresh read-only Curator receipt, and registers the
executable adapters in the same process that invokes ``WholeOSService``.

This bootstrap grants only trusted-local, routine and reversible work.  It does
not discover GitHub credentials, publish a pull request, or claim hostile-code
isolation.  Later service configurations must add those independently admitted
capabilities explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import re
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4

from .brain_kernel.canonical import canonical_digest
from .builder_session import BuilderDisposition, BuilderSessionResult
from .candidate_qualification import CandidateQualifier
from .cohort_assurance import (
    TerminalAssessment,
    TerminalEvidence,
    convergence_candidate_digest,
)
from .cohort_runtime import VerificationResult
from .cortex.repository.mission_bindings import (
    ConfiguredMissionBindingsProvider,
    MissionBindingDescriptor,
)
from .delivery_broker import DeliveryBroker
from .discovery_backlog import BacklogCandidate, DiscoveryBacklog, DiscoverySignal
from .local_codex_worker import CodexLocalWorker, resolve_codex_executable
from .outcome_graph import OutcomeWorkPackage, compile_outcome_graph
from .repository_profile import (
    CapabilityGrant,
    CapabilityReport,
    CapabilityStatus,
    HostIdentity,
    HostToolBinding,
    ProfileCapability,
    RepositoryProfile,
)
from .receipts import filesystem_path
from .runtime_contracts import canonical_json_bytes, raw_sha256
from .scoped_learning import LearningScope
from .verification_adapters import (
    LocalProcessSandbox,
    SandboxRequirements,
    VerificationBudget,
    verify_repository,
)
from .whole_os_bootstrap import (
    WholeOSHostBootstrap,
    WholeOSHostFactoryRegistration,
    run_registered_whole_os,
)
from .whole_os_composition import (
    BacklogDiscoveryAdapter,
    BoundedBuilderAdapter,
    DeliveryPolicy,
    DurableLearningRecorder,
    WholeOSCompositionHost,
)
from .whole_os_qualification import CapabilityDeclaration, CompositionManifest
from .whole_os_service import WholeOSServiceConfig


PROVIDER_ID = "codex-local-whole-os"
PROVIDER_VERSION = "v1"
CONFIGURATION_ID = "whole-os-host-bootstrap"
AUTHORITY_REF = "operator-host-bootstrap"
STATE_ROOT_REF = "whole-os-external-state"
ACCEPTANCE_ID = "host-bootstrap-focused"
PACKAGE_ID = "host-bootstrap-startup"
PRODUCER_ID = "codex-host-builder"
CURATOR_ID = "codex-host-curator"
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$")


class CodexHostBootstrapError(RuntimeError):
    """The trusted local host cannot be admitted or executed."""

    blocker = "blocked_capability"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
        shell=False,
    )
    if result.returncode:
        raise CodexHostBootstrapError(
            f"git {arguments[0]} failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _repository_identity(repository: Path) -> tuple[str, str, str]:
    root = Path(_git(repository, "rev-parse", "--show-toplevel")).resolve()
    if root != repository or not (repository / ".git").exists():
        raise CodexHostBootstrapError(
            "repository must be the exact root of a real Git checkout"
        )
    status = _git(repository, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise CodexHostBootstrapError(
            "repository must be clean, including untracked files, before admission"
        )
    head = _git(repository, "rev-parse", "HEAD")
    tree = _git(repository, "rev-parse", "HEAD^{tree}")
    branch = _git(repository, "branch", "--show-current")
    if not re.fullmatch(r"[0-9a-f]{40}", head) or not re.fullmatch(
        r"[0-9a-f]{40}", tree
    ):
        raise CodexHostBootstrapError("repository HEAD or tree is not a full Git SHA")
    if not branch.startswith("codex/"):
        raise CodexHostBootstrapError(
            "trusted bootstrap requires an attached codex/ branch"
        )
    return head, tree, branch


def _write_once(path: Path, document: Mapping[str, Any]) -> Path:
    body = canonical_json_bytes(dict(document)) + b"\n"
    target = filesystem_path(path)
    filesystem_path(path.parent).mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != body:
            raise CodexHostBootstrapError(
                f"content-addressed host artifact conflicts: {path}"
            )
        return path
    temporary = filesystem_path(
        path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    )
    try:
        with temporary.open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _replace(path: Path, document: Mapping[str, Any]) -> Path:
    body = canonical_json_bytes(dict(document)) + b"\n"
    target = filesystem_path(path)
    filesystem_path(path.parent).mkdir(parents=True, exist_ok=True)
    temporary = filesystem_path(
        path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    )
    try:
        with temporary.open("xb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return path


def _file_ref(path: Path) -> str:
    return (
        f"file:{path}#sha256:"
        f"{hashlib.sha256(filesystem_path(path).read_bytes()).hexdigest()}"
    )


def _component_digest(name: str) -> str:
    path = Path(__file__).with_name(name)
    return raw_sha256(path.read_bytes())


def _codex_version(executable: Path) -> tuple[str, dict[str, Any]]:
    result = subprocess.run(
        [str(executable), "--version"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
        shell=False,
    )
    output = (result.stdout + result.stderr).decode("utf-8", "replace").strip()
    if result.returncode or not output:
        raise CodexHostBootstrapError("native Codex version probe failed")
    match = re.search(r"(\d+(?:\.\d+){1,3})", output)
    if match is None:
        raise CodexHostBootstrapError("native Codex version is not recognizable")
    version = "v" + match.group(1)
    return version, {
        "schema_version": 1,
        "kind": "whole-os-codex-tool-probe",
        "adapter_id": "codex-cli",
        "version": version,
        "executable_path": str(executable),
        "binary_digest": raw_sha256(executable.read_bytes()),
        "version_output": output,
        "version_output_digest": raw_sha256(result.stdout + result.stderr),
        "exit_code": result.returncode,
        "platform": platform.platform(),
    }


class _ProbeProvider:
    provider_id = "codex-host-probe"

    def __init__(self, probe: Mapping[str, Any], receipt_digest: str) -> None:
        self.probe = dict(probe)
        self.receipt_digest = receipt_digest

    def verify_tool_receipt(self, **values: Any) -> bool:
        return values == {
            "adapter_id": self.probe["adapter_id"],
            "version": self.probe["version"],
            "executable_path": self.probe["executable_path"],
            "binary_digest": self.probe["binary_digest"],
            "probe_receipt_digest": self.receipt_digest,
        }


@dataclass(frozen=True, slots=True)
class DeploymentBundle:
    repository: Path
    state_root: Path
    head: str
    tree: str
    branch: str
    codex_executable: Path
    codex_version: str
    seal_digest: str
    implementation_digest: str
    descriptor: MissionBindingDescriptor
    config: WholeOSServiceConfig
    config_path: Path
    profile: RepositoryProfile
    manifest: CompositionManifest
    probe_path: Path
    n28_contract_digest: str


def _profiles() -> tuple[CapabilityDeclaration, ...]:
    return (
        CapabilityDeclaration(
            "external-python", "python", "test-execution", True, True
        ),
        CapabilityDeclaration("go", "go", "test-execution", True, True),
        CapabilityDeclaration(
            "node-typescript", "typescript", "test-execution", True, True
        ),
        CapabilityDeclaration(
            "roblox",
            "luau",
            "studio-engine-and-device",
            False,
            False,
            incomplete_reason="runtime evidence not configured",
        ),
        CapabilityDeclaration("rust", "rust", "compile-only", False, True),
        CapabilityDeclaration(
            "self-python", "python", "test-execution", True, True
        ),
    )


def build_deployment_bundle(
    *,
    repository: Path,
    state_root: Path,
    codex_executable: Path,
    tenant_id: str,
    repository_id: str,
    observed_codex: tuple[str, Mapping[str, Any]] | None = None,
) -> DeploymentBundle:
    """Observe and seal one real checkout without invoking a model worker."""

    repository = repository.resolve(strict=True)
    state_root = state_root.resolve()
    if _IDENTIFIER.fullmatch(tenant_id) is None or _IDENTIFIER.fullmatch(
        repository_id
    ) is None:
        raise CodexHostBootstrapError(
            "tenant and repository IDs must be canonical identifiers"
        )
    try:
        state_root.relative_to(repository)
    except ValueError:
        pass
    else:
        raise CodexHostBootstrapError("host state must remain outside the repository")
    head, tree, branch = _repository_identity(repository)
    codex_executable = codex_executable.resolve(strict=True)
    codex_version, probe = (
        _codex_version(codex_executable)
        if observed_codex is None
        else (observed_codex[0], dict(observed_codex[1]))
    )
    if (
        probe.get("executable_path") != str(codex_executable)
        or probe.get("binary_digest") != raw_sha256(codex_executable.read_bytes())
        or probe.get("adapter_id") != "codex-cli"
        or probe.get("version") != codex_version
    ):
        raise CodexHostBootstrapError("supplied Codex probe differs from executable")
    probe_digest = canonical_digest(probe)
    probe_path = _write_once(
        state_root / "tool-probes" / f"{probe_digest.removeprefix('sha256:')}.json",
        probe,
    )
    n28_path = (
        repository
        / "docs"
        / "plan"
        / "whole-os-tournament-2026-09-13"
        / "NODES-QUALIFICATION.md"
    )
    if not n28_path.is_file():
        raise CodexHostBootstrapError("N28 contract is unavailable in the checkout")
    n28_digest = raw_sha256(n28_path.read_bytes())
    seal = {
        "schema_version": 1,
        "kind": "whole-os-codex-host-seal",
        "repository": str(repository),
        "tenant_id": tenant_id,
        "repository_id": repository_id,
        "head": head,
        "tree": tree,
        "branch": branch,
        "codex_executable": str(codex_executable),
        "codex_version": codex_version,
        "codex_binary_digest": probe["binary_digest"],
        "codex_probe_digest": probe_digest,
        "n28_contract_digest": n28_digest,
        "authority_ref": AUTHORITY_REF,
        "capabilities": ["read_only_plan", "local_build"],
        "external_delivery": "not-granted",
        "credential_reference": "chatgpt-subscription-session",
    }
    seal_digest = canonical_digest(seal)
    _write_once(
        state_root / "host-seals" / f"{seal_digest.removeprefix('sha256:')}.json",
        seal,
    )
    verification_digest = canonical_digest(
        {
            "acceptance_id": ACCEPTANCE_ID,
            "adapter": "python-unittest",
            "sandbox": "trusted-local-process-only",
            "tests": [
                "tests/test_whole_os_bootstrap.py",
                "tests/test_whole_os_codex_host.py",
            ],
        }
    )
    descriptor = MissionBindingDescriptor(
        CONFIGURATION_ID,
        seal_digest,
        tenant_id,
        repository_id,
        "v1",
        ((PROVIDER_ID, PROVIDER_VERSION), ("codex-cli", codex_version)),
        ("codex-cli",),
        AUTHORITY_REF,
        verification_digest,
        STATE_ROOT_REF,
    )
    component_digests = {
        "bootstrap": _component_digest("whole_os_bootstrap.py"),
        "builder": _component_digest("local_codex_worker.py"),
        "composition": _component_digest("whole_os_composition.py"),
        "delivery": _component_digest("delivery_broker.py"),
        "discovery": _component_digest("discovery_backlog.py"),
        "learning": _component_digest("scoped_learning.py"),
        "qualification": _component_digest("candidate_qualification.py"),
        "service": _component_digest("whole_os_service.py"),
        "verification-adapters": _component_digest("verification_adapters.py"),
    }
    implementation_digest = canonical_digest(component_digests)
    manifest = CompositionManifest(
        implementation_digest,
        descriptor.digest,
        _profiles(),
        component_digests,
        "refuse-ambiguous",
        False,
    )
    provider = _ProbeProvider(probe, probe_digest)
    tool = HostToolBinding.admit_real(
        provider,
        adapter_id="codex-cli",
        version=codex_version,
        executable_path=str(codex_executable),
        binary_digest=str(probe["binary_digest"]),
        platform=platform.system().casefold(),
        fixed_argv=(
            "exec",
            "--json",
            "--ephemeral",
            "--ignore-user-config",
            "--sandbox",
            "read-only",
            "--cd",
            "{workspace}",
        ),
        placeholders=("{workspace}",),
        safe_environment_names=(),
        secret_handles=(),
        timeout_seconds=900,
        probe_receipt_digest=probe_digest,
    )
    profile = RepositoryProfile(
        "whole-os-codex-local",
        HostIdentity(
            tenant_id,
            repository_id,
            "whole-os-host-issuer",
            canonical_digest(
                {"authority_ref": AUTHORITY_REF, "seal_digest": seal_digest}
            ),
        ),
        str(repository),
        str(state_root / "workspaces"),
        str(state_root / "profile-state"),
        str(state_root / "cache"),
        (
            CapabilityGrant(
                ProfileCapability.LOCAL_BUILD,
                "grant-local-build",
                canonical_digest(
                    {
                        "authority_ref": AUTHORITY_REF,
                        "capability": ProfileCapability.LOCAL_BUILD.value,
                        "seal_digest": seal_digest,
                    }
                ),
            ),
        ),
        (tool,),
        (
            CapabilityReport(
                "codex-cli",
                CapabilityStatus.REAL,
                "native executable and version probe verified by trusted host",
                probe_digest,
            ),
        ),
        (),
        "public",
        f"whole-os-codex:{seal_digest}",
        1,
    )
    graph = compile_outcome_graph(
        (
            OutcomeWorkPackage(
                PACKAGE_ID,
                ("trusted-host-startup",),
                allowed_paths=(),
                semantic_locks=("host-bootstrap",),
                acceptance_ids=(ACCEPTANCE_ID,),
                risk_tier="low",
                required_roles=("builder", "curator", "integrator", "steward"),
                rollback="remove no repository bytes; retain external receipts",
            ),
        ),
        base_snapshot=head,
        maximum_concurrent=1,
        court_receipt=n28_digest,
    )
    service_state = state_root / "service-state" / seal_digest.removeprefix("sha256:")
    config = WholeOSServiceConfig(
        f"host-bootstrap-{head[:12]}",
        tenant_id,
        repository_id,
        service_state,
        descriptor,
        graph,
        2,
    )
    config_directory = state_root / "deployment" / seal_digest.removeprefix("sha256:")
    relative_state = os.path.relpath(service_state, config_directory)
    config_document = {
        "schema_version": 1,
        "campaign_id": config.campaign_id,
        "tenant_id": tenant_id,
        "repository_id": repository_id,
        "state_dir": relative_state,
        "binding_descriptor": descriptor.to_document(),
        "graph": graph.to_document(),
        "maximum_attempts": config.maximum_attempts,
    }
    config_path = _write_once(config_directory / "service.json", config_document)
    return DeploymentBundle(
        repository,
        state_root,
        head,
        tree,
        branch,
        codex_executable,
        codex_version,
        seal_digest,
        implementation_digest,
        descriptor,
        config,
        config_path,
        profile,
        manifest,
        probe_path,
        n28_digest,
    )


def _worker_receipt_ok(receipt: Mapping[str, Any]) -> bool:
    report = receipt.get("report")
    return bool(
        receipt.get("protocol") == "hive-mind-local-codex-worker-v1"
        and receipt.get("status") == "completed"
        and isinstance(receipt.get("session_id"), str)
        and receipt.get("session_id")
        and isinstance(report, Mapping)
        and report.get("status") == "completed"
        and report.get("changed_paths") == []
        and report.get("acceptance_evidence")
    )


class _AdmissionCurator:
    curator_id = CURATOR_ID

    def __init__(
        self,
        *,
        bundle: DeploymentBundle,
        receipt: Mapping[str, Any],
        receipt_path: Path,
        focused_receipt: Mapping[str, Any],
        focused_path: Path,
    ) -> None:
        self.bundle = bundle
        self.receipt = dict(receipt)
        self.receipt_path = receipt_path
        self.focused_receipt = dict(focused_receipt)
        self.focused_path = focused_path

    def assess(self, candidate: Any, payload: Mapping[str, Any]) -> TerminalAssessment:
        candidate_digest = convergence_candidate_digest(candidate)
        repository_ok = False
        try:
            head, tree, _ = _repository_identity(self.bundle.repository)
            repository_ok = head == self.bundle.head and tree == self.bundle.tree
        except CodexHostBootstrapError:
            repository_ok = False
        passed = bool(
            candidate.accepted
            and payload.get("graph_digest") == self.bundle.config.graph.digest
            and repository_ok
            and self.focused_receipt.get("status") == "PASSED"
            and _worker_receipt_ok(self.receipt)
        )
        review_digest = raw_sha256(self.receipt_path.read_bytes())
        focused_digest = raw_sha256(self.focused_path.read_bytes())
        evidence = TerminalEvidence(
            candidate_digest,
            PRODUCER_ID,
            self.curator_id,
            (f"review:{candidate_digest}:{review_digest}",),
            (f"aggregate:{candidate_digest}:{self.bundle.seal_digest}",),
            (f"verification:{candidate_digest}:{focused_digest}",),
        )
        return TerminalAssessment(
            VerificationResult(
                passed,
                (
                    f"codex-session:{self.receipt['session_id']}",
                    f"focused-receipt:{focused_digest}",
                ),
                "trusted local Codex host startup independently admitted"
                if passed
                else "trusted local Codex host startup evidence is incomplete",
            ),
            evidence,
        )


def compose_factory(
    *,
    bundle: DeploymentBundle,
    worker: CodexLocalWorker,
    admission_receipt: Mapping[str, Any],
    admission_receipt_path: Path,
    focused_receipt: Mapping[str, Any],
    focused_receipt_path: Path,
    timeout_seconds: float,
    builder_receipts: list[Path],
) -> Callable[[WholeOSServiceConfig], WholeOSHostBootstrap]:
    """Compose existing production adapters behind one sealed factory."""

    def factory(supplied: WholeOSServiceConfig) -> WholeOSHostBootstrap:
        if (
            supplied.binding_descriptor.digest != bundle.descriptor.digest
            or supplied.graph.digest != bundle.config.graph.digest
            or supplied.state_dir != bundle.config.state_dir
        ):
            raise CodexHostBootstrapError(
                "launcher factory received a substituted service configuration"
            )

        provider = ConfiguredMissionBindingsProvider(
            bundle.descriptor,
            lambda descriptor, payload, state: (
                {
                    "repository": str(bundle.repository),
                    "head": bundle.head,
                    "tree": bundle.tree,
                },
                {
                    "delivery": "local-artifact-only",
                    "credential_values": "not-present",
                },
            ),
        )
        backlog = DiscoveryBacklog()
        backlog.ingest(
            DiscoverySignal(
                bundle.config.tenant_id,
                bundle.config.repository_id,
                bundle.head,
                "trusted-host-startup",
                (_file_ref(bundle.probe_path),),
                bundle.seal_digest,
                1.0,
            )
        )
        backlog.add(
            BacklogCandidate(
                "admit-trusted-codex-host",
                (
                    "A fresh non-interactive Codex process can inspect the admitted checkout without changing it.",
                ),
                10.0,
                "WholeOSService reaches a terminal accepted startup state with real Codex session evidence",
                1.0,
                0.1,
                dissent=(
                    "A synthetic fixture or PATH lookup alone cannot prove the host runtime.",
                ),
            )
        )

        def build(session: Any) -> BuilderSessionResult:
            session.record_tool("read")
            try:
                head, tree, _ = _repository_identity(bundle.repository)
            except CodexHostBootstrapError as error:
                return BuilderSessionResult(
                    BuilderDisposition.BLOCKED,
                    None,
                    (),
                    failures=(str(error),),
                )
            if head != bundle.head or tree != bundle.tree:
                return BuilderSessionResult(
                    BuilderDisposition.NEEDS_CONTRACT_AMENDMENT,
                    None,
                    (),
                    failures=("admitted repository candidate changed",),
                )
            evidence_directory = (
                bundle.state_root
                / "codex-workers"
                / "builder"
                / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"
            )
            receipt = worker.run(
                node={
                    "id": PACKAGE_ID,
                    "objective": "prove the admitted checkout is usable by the installed non-interactive Codex CLI",
                    "base_snapshot": bundle.head,
                    "allowed_paths": [],
                    "acceptance_ids": [ACCEPTANCE_ID],
                },
                actor_id=PRODUCER_ID,
                role="builder",
                workspace=bundle.repository,
                evidence_directory=evidence_directory,
                predecessor_reports=[],
                objective=(
                    "Inspect this exact clean Git checkout at the admitted HEAD. Verify the repository root, branch, HEAD, "
                    "and governing Whole-OS service files are readable. Do not edit any file and do not run network or "
                    "publication commands. Report concrete read-only evidence that this real checkout is ready for "
                    "routine reversible local work."
                ),
                timeout_seconds=timeout_seconds,
                writable=False,
            )
            receipt_path = evidence_directory / "receipt.json"
            if receipt_path.is_file():
                builder_receipts.append(receipt_path)
            try:
                after_head, after_tree, _ = _repository_identity(bundle.repository)
            except CodexHostBootstrapError as error:
                return BuilderSessionResult(
                    BuilderDisposition.BLOCKED,
                    None,
                    (),
                    failures=(str(error),),
                    evidence_refs=(
                        _file_ref(receipt_path) if receipt_path.is_file() else "codex-builder-receipt-missing",
                    ),
                )
            evidence_refs = (
                _file_ref(receipt_path)
                if receipt_path.is_file()
                else "codex-builder-receipt-missing"
            ,)
            if (
                after_head != bundle.head
                or after_tree != bundle.tree
                or not _worker_receipt_ok(receipt)
            ):
                return BuilderSessionResult(
                    BuilderDisposition.BLOCKED,
                    None,
                    (),
                    failures=(str(receipt.get("reason") or "Codex builder receipt is incomplete"),),
                    evidence_refs=evidence_refs,
                )
            report = receipt["report"]
            return BuilderSessionResult(
                BuilderDisposition.NO_CHANGE,
                bundle.head,
                (),
                checks=tuple(str(item) for item in report.get("tests", ())),
                evidence_refs=evidence_refs,
            )

        def qualify(name: str) -> int:
            if name != ACCEPTANCE_ID:
                return 0
            try:
                head, tree, _ = _repository_identity(bundle.repository)
            except CodexHostBootstrapError:
                return 0
            return int(
                head == bundle.head
                and tree == bundle.tree
                and focused_receipt.get("status") == "PASSED"
                and _worker_receipt_ok(admission_receipt)
            )

        host = WholeOSCompositionHost(
            state_directory=bundle.state_root / "composition",
            manifest=bundle.manifest,
            profile_id="self-python",
            repository_profile=bundle.profile,
            discovery=BacklogDiscoveryAdapter(
                backlog,
                evidence_refs=(_file_ref(bundle.probe_path),),
                court_receipt=bundle.n28_contract_digest,
            ),
            builder=BoundedBuilderAdapter(
                build,
                candidate_tree=lambda result: canonical_digest(
                    {"git_tree": bundle.tree, "candidate": result.candidate}
                ),
            ),
            qualifier=CandidateQualifier(qualify),
            delivery=DeliveryBroker(
                state_path=bundle.state_root
                / "delivery"
                / f"{bundle.seal_digest.removeprefix('sha256:')}.json"
            ),
            delivery_policy=DeliveryPolicy(
                "https://github.com/kb4beast/hive-mind-os",
                "main",
                "codex/whole-os-service",
                "no-external-delivery-grant",
                canonical_digest({"sandbox": "trusted-local-process-only"}),
                canonical_digest({"tool": "python-unittest"}),
                canonical_digest({"repository": str(bundle.repository)}),
                CURATOR_ID,
                LearningScope.TARGET_APP,
                learning_authorization_digest=canonical_digest(
                    {"scope": "target-app", "seal": bundle.seal_digest}
                ),
                publish_required=False,
                feedback_required=False,
            ),
            feedback_source=None,
            learning=DurableLearningRecorder(bundle.state_root / "learning"),
            curator=_AdmissionCurator(
                bundle=bundle,
                receipt=admission_receipt,
                receipt_path=admission_receipt_path,
                focused_receipt=focused_receipt,
                focused_path=focused_receipt_path,
            ),
            producer_id=PRODUCER_ID,
        )
        return WholeOSHostBootstrap(provider, host)

    return factory


def _focused_verification(bundle: DeploymentBundle, attempt_id: str) -> tuple[dict[str, Any], Path]:
    directory = bundle.state_root / "verification" / attempt_id
    receipt = verify_repository(
        bundle.repository,
        evidence_directory=directory,
        selected_paths=(
            "tests/test_whole_os_bootstrap.py",
            "tests/test_whole_os_codex_host.py",
        ),
        adapter_id="python-unittest",
        sandbox=LocalProcessSandbox(),
        requirements=SandboxRequirements(
            network_policy="inherit",
            hostile_code_isolation=False,
        ),
        budget=VerificationBudget(wall_seconds=300),
    )
    return receipt, directory / "receipt.json"


def _admission_review(
    bundle: DeploymentBundle,
    worker: CodexLocalWorker,
    focused_receipt: Mapping[str, Any],
    attempt_id: str,
    timeout_seconds: float,
) -> tuple[dict[str, Any], Path]:
    directory = bundle.state_root / "codex-workers" / "curator" / attempt_id
    receipt = worker.run(
        node={
            "id": "host-bootstrap-admission",
            "objective": "independently admit the exact trusted Codex host candidate",
            "base_snapshot": bundle.head,
            "acceptance_ids": [ACCEPTANCE_ID],
        },
        actor_id=CURATOR_ID,
        role="curator",
        workspace=bundle.repository,
        evidence_directory=directory,
        predecessor_reports=[
            {
                "kind": "deterministic-focused-verification",
                "status": focused_receipt.get("status"),
                "receipt_digest": focused_receipt.get("receipt_digest"),
                "adapter_id": focused_receipt.get("adapter_id"),
                "selected_tests": focused_receipt.get("selected_tests", []),
                "source_repository": focused_receipt.get("source_repository"),
            }
        ],
        objective=(
            "Act as the independent read-only Curator for the exact committed host-bootstrap candidate. Inspect "
            "src/hive_mind_os/whole_os_codex_host.py, whole_os_bootstrap.py, whole_os_composition.py, the trusted "
            "PowerShell launcher, its focused tests, and the sealed-config boundary. Confirm the checkout is clean at "
            f"HEAD {bundle.head}, the installed Codex adapter is process-local, credentials are not stored in service "
            "configuration, state is outside the repository, and no synthetic fixture is represented as live startup "
            "evidence. Do not edit files, access secrets, publish, or use network services. Return specific findings and "
            "acceptance evidence; use blocked if the exact candidate cannot be admitted."
        ),
        timeout_seconds=timeout_seconds,
        writable=False,
    )
    return receipt, directory / "receipt.json"


def _startup_document(
    *,
    attempt_id: str,
    started_at: str,
    bundle: DeploymentBundle | None,
    status: str,
    blocker: str | None,
    cli_exit_code: int | None,
    cli_output: Mapping[str, Any] | None,
    cli_stdout: str,
    cli_stderr: str,
    admission_path: Path | None,
    builder_paths: Sequence[Path],
    focused_path: Path | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "whole-os-codex-host-startup-v1",
        "attempt_id": attempt_id,
        "status": status,
        "blocker": blocker,
        "non_synthetic": True,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "launcher_process_id": os.getpid(),
        "parent_process_id": os.getppid(),
        "repository": str(bundle.repository) if bundle else None,
        "branch": bundle.branch if bundle else None,
        "head": bundle.head if bundle else None,
        "tree": bundle.tree if bundle else None,
        "host_seal_digest": bundle.seal_digest if bundle else None,
        "service_config": str(bundle.config_path) if bundle else None,
        "service_config_digest": raw_sha256(bundle.config_path.read_bytes())
        if bundle
        else None,
        "host_registration_digest": None,
        "codex_executable": str(bundle.codex_executable) if bundle else None,
        "codex_version": bundle.codex_version if bundle else None,
        "credential_values_in_service_config": False,
        "external_delivery_granted": False,
        "cli_exit_code": cli_exit_code,
        "service_observation": dict(cli_output) if cli_output else None,
        "stdout_digest": raw_sha256(cli_stdout.encode("utf-8")),
        "stderr_digest": raw_sha256(cli_stderr.encode("utf-8")),
        "focused_verification_receipt": str(focused_path) if focused_path else None,
        "admission_curator_receipt": str(admission_path) if admission_path else None,
        "builder_receipts": [str(path) for path in builder_paths],
        "codex_session_ids": [],
    }


def execute_trusted_launcher(
    *,
    repository: Path,
    state_root: Path,
    tenant_id: str = "local-operator",
    repository_id: str = "hive-mind-os",
    timeout_seconds: float = 900,
    worker: CodexLocalWorker | None = None,
    executable: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """Execute the real trusted launcher and persist an append-only receipt."""

    started_at = _utc_now()
    attempt_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"
    state_root = state_root.resolve()
    state_root.mkdir(parents=True, exist_ok=True)
    bundle: DeploymentBundle | None = None
    focused_path: Path | None = None
    admission_path: Path | None = None
    builder_paths: list[Path] = []
    stdout = ""
    stderr = ""
    cli_output: dict[str, Any] | None = None
    cli_exit: int | None = None
    registration: WholeOSHostFactoryRegistration | None = None
    blocker: str | None = None
    status = "blocked"
    try:
        native = (executable or resolve_codex_executable()).resolve(strict=True)
        bundle = build_deployment_bundle(
            repository=repository,
            state_root=state_root,
            codex_executable=native,
            tenant_id=tenant_id,
            repository_id=repository_id,
        )
        focused, focused_path = _focused_verification(bundle, attempt_id)
        if focused.get("status") != "PASSED":
            raise CodexHostBootstrapError(
                "focused trusted-local verification did not pass"
            )
        actual_worker = worker or CodexLocalWorker(executable=native)
        admission, admission_path = _admission_review(
            bundle, actual_worker, focused, attempt_id, timeout_seconds
        )
        if not admission_path.is_file() or not _worker_receipt_ok(admission):
            raise CodexHostBootstrapError(
                "fresh Codex Curator did not independently admit the host candidate"
            )
        registration = WholeOSHostFactoryRegistration(
            PROVIDER_ID,
            PROVIDER_VERSION,
            bundle.descriptor.configuration_digest,
            bundle.implementation_digest,
            bundle.descriptor.authority_ref,
            tuple(sorted((_file_ref(focused_path), _file_ref(admission_path)))),
            True,
        )
        factory = compose_factory(
            bundle=bundle,
            worker=actual_worker,
            admission_receipt=admission,
            admission_receipt_path=admission_path,
            focused_receipt=focused,
            focused_receipt_path=focused_path,
            timeout_seconds=timeout_seconds,
            builder_receipts=builder_paths,
        )
        stdout_stream = io.StringIO()
        stderr_stream = io.StringIO()
        with redirect_stdout(stdout_stream), redirect_stderr(stderr_stream):
            cli_exit = run_registered_whole_os(
                (
                    "start",
                    "--config",
                    str(bundle.config_path),
                    "--execution-mode",
                    "cohort",
                    "--max-parallel-packages",
                    "1",
                    "--json",
                ),
                registration=registration,
                factory=factory,
            )
        stdout = stdout_stream.getvalue()
        stderr = stderr_stream.getvalue()
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError as error:
            raise CodexHostBootstrapError(
                "WholeOSService returned no structured observation"
            ) from error
        if isinstance(parsed, dict):
            cli_output = parsed
        admission_session = admission.get("session_id")
        builder_sessions: list[str] = []
        for path in builder_paths:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value.get("session_id"), str):
                    builder_sessions.append(value["session_id"])
            except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
                continue
        if (
            cli_exit != 0
            or not cli_output
            or cli_output.get("status") != "complete"
            or not builder_paths
            or not builder_sessions
            or not isinstance(admission_session, str)
            or admission_session in builder_sessions
        ):
            raise CodexHostBootstrapError(
                "WholeOSService did not complete with distinct real Codex session evidence"
            )
        status = "complete"
    except (OSError, ValueError, TypeError, RuntimeError) as error:
        blocker_kind = getattr(error, "blocker", "blocked_capability")
        blocker = f"{blocker_kind}:{type(error).__name__}:{error}"

    receipt = _startup_document(
        attempt_id=attempt_id,
        started_at=started_at,
        bundle=bundle,
        status=status,
        blocker=blocker,
        cli_exit_code=cli_exit,
        cli_output=cli_output,
        cli_stdout=stdout,
        cli_stderr=stderr,
        admission_path=admission_path,
        builder_paths=builder_paths,
        focused_path=focused_path,
    )
    if registration is not None:
        receipt["host_registration_digest"] = registration.digest
    session_ids: list[str] = []
    for path in ([admission_path] if admission_path else []) + list(builder_paths):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            session = value.get("session_id")
            if isinstance(session, str) and session:
                session_ids.append(session)
        except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
            continue
    receipt["codex_session_ids"] = session_ids
    receipt_path = _write_once(
        state_root / "startup-receipts" / f"{attempt_id}.json", receipt
    )
    receipt["receipt_path"] = str(receipt_path)
    receipt["receipt_digest"] = raw_sha256(receipt_path.read_bytes())
    _replace(state_root / "startup-current.json", receipt)
    return (0 if status == "complete" else 20), receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the trusted local Codex WholeOSService host."
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--tenant-id", default="local-operator")
    parser.add_argument("--repository-id", default="hive-mind-os")
    parser.add_argument("--timeout-seconds", type=float, default=900)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = _parser().parse_args(argv)
    if not 60 <= arguments.timeout_seconds <= 3600:
        raise SystemExit("--timeout-seconds must be between 60 and 3600")
    code, receipt = execute_trusted_launcher(
        repository=Path(arguments.repository),
        state_root=Path(arguments.state_root),
        tenant_id=arguments.tenant_id,
        repository_id=arguments.repository_id,
        timeout_seconds=arguments.timeout_seconds,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    raise SystemExit(code)


if __name__ == "__main__":  # pragma: no cover
    main()


__all__ = [
    "CodexHostBootstrapError",
    "DeploymentBundle",
    "build_deployment_bundle",
    "compose_factory",
    "execute_trusted_launcher",
    "main",
]
