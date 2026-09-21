"""H1 acceptance tests for the generic local repository host.

Everything named ``_Synthetic*`` or ``_Scripted*`` is a labelled test double for an
external dependency (model worker, Curator, host registry, held-out custody). Git,
patch application, verification processes and durable state are real. Nothing here
establishes model availability, sandbox isolation, or independent review.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.builder_session import BuilderDisposition
from hive_mind_os.candidate_qualification import QualificationDisposition
from hive_mind_os.cortex.repository.mission_bindings import MissionBindingDescriptor
from hive_mind_os.delivery_broker import ArtifactKind, DeliveryBroker, DeliveryGrant
from hive_mind_os.discovery_backlog import (
    BacklogCandidate,
    DiscoveryBacklog,
    DiscoverySignal,
)
from hive_mind_os.outcome_graph import OutcomeWorkPackage, compile_outcome_graph
from hive_mind_os.repository_profile import (
    CapabilityGrant,
    HostIdentity,
    ProfileCapability,
    RepositoryProfile,
)
from hive_mind_os.runtime_contracts import raw_sha256
from hive_mind_os.verification_adapters import (
    LocalProcessSandbox,
    PythonUnittestAdapter,
    SandboxRequirements,
    UnavailableSandbox,
)
from hive_mind_os.whole_os_composition import BacklogDiscoveryAdapter
from hive_mind_os.whole_os_qualification import (
    CapabilityDeclaration,
    CompositionManifest,
)
from hive_mind_os.whole_os_repository_host import (
    WINDOWS_PATH_LIMIT,
    AcceptanceSpec,
    CandidateReview,
    HoldoutSpec,
    ProfileRegistryAdmission,
    ReceiptBoundCandidateQualifier,
    RepositoryBindingError,
    RepositoryBuildBudget,
    RepositoryBuilderAdapter,
    RepositoryCompositionHost,
    RepositoryHostBlocked,
    RepositoryHostContext,
    RepositoryHostUnavailable,
    RepositoryHostUncertain,
    RepositoryTaskBinding,
    _git_bytes,
    attempt_key,
    compose_repository_factory,
    environment_identity_digest,
    process_is_alive,
    read_unittest_results,
    sandbox_identity_digest,
    service_context_digest,
    toolchain_identity_digest,
)
from hive_mind_os.whole_os_service import (
    PackageStatus,
    WholeOSService,
    WholeOSServiceConfig,
)

D = "sha256:" + "a" * 64
MARKER = "HOLDOUT-MARKER-7f3a9c-must-never-reach-a-worker"
BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"
VISIBLE = (
    "import unittest\nfrom calc import add\n\n\n"
    "class VisibleTests(unittest.TestCase):\n"
    "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"
)
VISIBLE_SKIPPED = VISIBLE.replace(
    "    def test_add", "    @unittest.skip('synthetic skipped acceptance')\n    def test_add"
)
HOLDOUT = (
    f"# {MARKER}\nimport unittest\nfrom calc import add\n\n\n"
    "class HeldOutTests(unittest.TestCase):\n"
    "    def test_add_large(self):\n        self.assertEqual(add(10, 5), 15)\n"
)


def _patch(path: str, old: str, new: str, *, header: str = "@@ -1,2 +1,2 @@") -> str:
    return (
        f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n{header}\n"
        f" def add(a, b):\n-    {old}\n+    {new}\n"
    )


FIX_PATCH = _patch("src/calc.py", "return a - b", "return a + b")
NOOP_PATCH = _patch("src/calc.py", "return a - b", "return a - b + 0")
README_PATCH = (
    "diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n"
    "@@ -1 +1 @@\n-synthetic external repository\n+synthetic external repository changed\n"
)
VISIBLE_PATCH = (
    "diff --git a/tests/test_visible.py b/tests/test_visible.py\n"
    "--- a/tests/test_visible.py\n+++ b/tests/test_visible.py\n"
    "@@ -1 +1 @@\n-import unittest\n+import unittest  # weakened\n"
)
HOLDOUT_PATCH = VISIBLE_PATCH.replace("test_visible", "test_holdout")
EXTRA_FILE_PATCH = FIX_PATCH + (
    "diff --git a/src/extra.py b/src/extra.py\nnew file mode 100644\n"
    "--- /dev/null\n+++ b/src/extra.py\n@@ -0,0 +1 @@\n+x = 1\n"
)
SYMLINK_PATCH = (
    "diff --git a/src/link.py b/src/link.py\nnew file mode 120000\n"
    "--- /dev/null\n+++ b/src/link.py\n@@ -0,0 +1 @@\n+calc.py\n"
)
FIX = {"patch": FIX_PATCH, "paths": ["src/calc.py"]}
NO_CHANGE = {"patch": None, "paths": []}


def _git(cwd: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return completed.stdout.strip()


def _interpreter_version() -> str:
    completed = subprocess.run(
        [str(Path(sys.executable).resolve()), "--version"], capture_output=True, check=True
    )
    return (completed.stdout + completed.stderr).decode("utf-8", "replace").strip()


def _artifact(reference: str) -> Path:
    return Path(reference[len("file:"):].rpartition("#")[0])


class _SimulatedProcessDeath(BaseException):
    """Stands in for a host process that vanishes mid-worker-call."""


class _ScriptedPatchWorker:
    """SYNTHETIC double for the ``.run`` contract; it is not a model."""

    protocol = "synthetic-scripted-worker-v1"

    def __init__(self, *script) -> None:
        self.script = list(script) or [FIX]
        self.calls: list[dict] = []

    @staticmethod
    def report(patch, paths, status="completed") -> dict:
        return {
            "status": status, "summary": "synthetic proposal", "findings": ["synthetic finding"],
            "acceptance_evidence": ["synthetic evidence"], "ideas": [], "selected_idea_ids": [],
            "changed_paths": list(paths), "tests": ["none run by the worker"],
            "proposed_patch": patch,
        }

    def receipt(self, values: dict, step, index: int) -> dict:
        step = step if isinstance(step, dict) else {}
        report = step["report"] if "report" in step else self.report(step.get("patch"), step.get("paths", ()))
        return {
            "protocol": step.get("protocol", self.protocol),
            "status": step.get("receipt_status", "completed"),
            "actor_id": step.get("actor", values["actor_id"]),
            "role": "builder", "execution_mode": "source-packet",
            "session_id": step.get("session", f"synthetic-session-{index}"),
            "model": "synthetic-model-1", "report": report, "reason": None, "evidence": {},
        }

    def run(self, **values) -> dict:
        index = len(self.calls)
        self.calls.append(values)
        step = self.script[min(index, len(self.script) - 1)]
        directory = values["evidence_directory"]
        directory.mkdir(parents=True)
        (directory / "source-packet.json").write_text(
            json.dumps(values["source_packet"], sort_keys=True, indent=2), encoding="utf-8"
        )
        if step == "die":
            raise _SimulatedProcessDeath()
        if step == "raise":
            raise RuntimeError("synthetic worker failure")
        receipt = self.receipt(values, step, index)
        if not (isinstance(step, dict) and step.get("no_receipt_file")):
            self.write_receipt(index, receipt)
        return receipt

    def write_receipt(self, index: int, receipt: dict) -> None:
        directory = self.calls[index]["evidence_directory"]
        (directory / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")

    def complete_later(self, index: int, step) -> None:
        self.write_receipt(index, self.receipt(self.calls[index], step, index))


class _SyntheticCurator:
    """SYNTHETIC separate Curator: binds its verdict to the exact review packet."""

    reviewer_id = "synthetic-independent-curator"

    def __init__(self, accept: bool = True, *, wrong_packet: bool = False, reviewer_id: str | None = None) -> None:
        self.accept, self.wrong_packet, self.packets = accept, wrong_packet, []
        if reviewer_id is not None:
            self.reviewer_id = reviewer_id

    def review(self, packet) -> CandidateReview:
        self.packets.append(packet)
        digest = canonical_digest(packet)
        return CandidateReview(
            self.reviewer_id, D if self.wrong_packet else digest, self.accept,
            canonical_digest({"synthetic-review-of": digest}),
        )


class _SyntheticRegistry:
    """SYNTHETIC host profile registry; flipping a flag simulates revocation."""

    def __init__(self) -> None:
        self.current = True
        self.authorized = True
        self.calls = 0

    def verify_profile(self, **_values) -> bool:
        self.calls += 1
        return self.current

    def authorize_capability(self, **_values) -> bool:
        return self.authorized

    def claim_identity(self, **_values) -> bool:
        return True


class _SyntheticVault:
    """SYNTHETIC private custody of sealed held-out test bytes."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def read(self, path: str) -> bytes:
        return self.files[path]


class _CountingSandbox:
    """SYNTHETIC wrapper over the real trusted-local sandbox that counts executions."""

    def __init__(self, *, available: bool = True) -> None:
        self.inner = LocalProcessSandbox()
        self.available = available
        self.runs = 0

    @property
    def capabilities(self):
        return self.inner.capabilities if self.available else UnavailableSandbox().capabilities

    def run(self, argv, **keywords):
        self.runs += 1
        return self.inner.run(argv, **keywords)


class _CountingBroker(DeliveryBroker):
    """SYNTHETIC counter proving no delivery call is made."""

    def __init__(self, **keywords) -> None:
        super().__init__(**keywords)
        self.calls = 0

    def prepare(self, request):
        self.calls += 1
        return super().prepare(request)

    def reconcile(self, request):
        self.calls += 1
        return super().reconcile(request)


class _Transport:
    def push(self, branch, commit):  # pragma: no cover - must never run
        raise AssertionError("local preparation made a remote call")

    def find_or_create_draft(self, branch, base, title, body):  # pragma: no cover
        raise AssertionError("local preparation made a remote call")


class _Rig:
    """One synthetic external repository plus every host dependency around it."""

    def __init__(
        self,
        case: unittest.TestCase,
        *script,
        already_fixed: bool = False,
        skipped_visible: bool = False,
        with_holdout: bool = True,
        requirements: SandboxRequirements | None = None,
        trusted_local: bool = True,
        sandbox=None,
        attempt_id: str = "attempt-one",
        no_change_permitted: bool = False,
        publish_required: bool = False,
        curator: _SyntheticCurator | None = None,
        delivery: DeliveryBroker | None = None,
        verifier: str = "python-unittest",
        budget: RepositoryBuildBudget | None = None,
        profile_tenant: str | None = None,
        binding_overrides: dict | None = None,
        extra_files: dict[str, str] | None = None,
    ) -> None:
        self.case = case
        temporary = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        case.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.tenant, self.repository = "tenant-test", "repository-test"
        self.source = self.root / "source"
        (self.source / "src").mkdir(parents=True)
        (self.source / "tests").mkdir()
        files = {
            "README.md": "synthetic external repository\n",
            "src/calc.py": FIXED if already_fixed else BUGGY,
            "tests/test_visible.py": VISIBLE_SKIPPED if skipped_visible else VISIBLE,
            "tests/test_holdout.py": HOLDOUT,
            **(extra_files or {}),
        }
        for name, text in files.items():
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode("utf-8"))
        _git(self.source, "init", "-b", "main")
        _git(self.source, "config", "user.name", "Synthetic Fixture")
        _git(self.source, "config", "user.email", "fixture@example.invalid")
        _git(self.source, "config", "core.autocrlf", "false")
        _git(self.source, "add", ".")
        _git(self.source, "commit", "-m", "synthetic base")
        self.base = _git(self.source, "rev-parse", "HEAD")
        self.tree = _git(self.source, "rev-parse", "HEAD^{tree}")
        self.acceptance = [AcceptanceSpec("visible-acceptance", ("tests/test_visible.py",))]
        self.holdouts: tuple[HoldoutSpec, ...] = ()
        holdout_files: dict[str, bytes] = {}
        if with_holdout:
            self.acceptance.append(AcceptanceSpec("held-out-acceptance", ("tests/test_holdout.py",)))
            holdout_files["tests/test_holdout.py"] = HOLDOUT.encode("utf-8")
            self.holdouts = (HoldoutSpec("tests/test_holdout.py", raw_sha256(HOLDOUT.encode("utf-8"))),)
        self.vault = _SyntheticVault(holdout_files)
        self.package = OutcomeWorkPackage(
            "repair-package", ("outcome-one",), allowed_paths=("src",),
            acceptance_ids=tuple(spec.acceptance_id for spec in self.acceptance), risk_tier="low",
        )
        graph = compile_outcome_graph((self.package,), base_snapshot=self.base, court_receipt=D)
        self.descriptor = MissionBindingDescriptor(
            "configuration", D, self.tenant, self.repository, "v1", (("local", "v1"),),
            ("provider",), "authority", D, "state",
        )
        self.config = WholeOSServiceConfig(
            "campaign-test", self.tenant, self.repository, self.root / "service", self.descriptor, graph
        )
        other = self.root / "other-repository"
        other.mkdir()
        self.profile = RepositoryProfile(
            "configured-profile",
            HostIdentity(profile_tenant or self.tenant, self.repository, "host-issuer", D),
            str(self.source), str(self.root / "workspace"), str(self.root / "profile-state"),
            str(self.root / "cache"),
            (CapabilityGrant(ProfileCapability.LOCAL_BUILD, "grant-one", D),),
            (), (), (), "public", "registry-handle", 1,
        )
        self.registry = _SyntheticRegistry()
        self.sandbox = sandbox or _CountingSandbox()
        self.worker = _ScriptedPatchWorker(*script)
        self.curator = curator or _SyntheticCurator()
        self.delivery = delivery
        self.publish_required = publish_required
        adapter = PythonUnittestAdapter()
        self.requirements = requirements or SandboxRequirements(
            network_policy="inherit", hostile_code_isolation=False
        )
        self.identities = {
            "sandbox_digest": sandbox_identity_digest(LocalProcessSandbox().capabilities),
            "toolchain_digest": toolchain_identity_digest(
                adapter.adapter_id, adapter.adapter_version, _interpreter_version()
            ),
            "environment_digest": environment_identity_digest(
                (("PYTHONPATH", "src"), ("PYTHONDONTWRITEBYTECODE", "1"))
            ),
        }
        self.binding_values = dict(
            attempt_id=attempt_id, tenant_id=self.tenant, repository_id=self.repository,
            campaign_id="campaign-test", package_id="repair-package",
            source_repository=self.source, base_commit=self.base, base_tree=self.tree,
            graph_digest=graph.digest, context_digest=service_context_digest(self.config),
            objective="Make add() return the sum of its arguments.", allowed_paths=("src",),
            acceptance=tuple(self.acceptance), verifier_adapter_id=verifier,
            sandbox_requirements=self.requirements, trusted_local=trusted_local,
            evaluator_id="synthetic-evaluator", worker_id="synthetic-builder",
            worker_protocol=_ScriptedPatchWorker.protocol, state_root=self.root / "state",
            learning_authorization_digest=D,
            budget=budget or RepositoryBuildBudget(
                3, 600.0, 300.0, 20, 1800.0, 100_000
            ),
            holdouts=self.holdouts, worker_model_prefix="synthetic-", risk_tier="low",
            no_change_permitted=no_change_permitted, **self.identities,
        )
        self.binding_values.update(binding_overrides or {})
        self.context = self.context_for(self.worker)
        self.discovery = self._discovery()
        self.manifest = self._manifest()
        self._host = None

    def _discovery(self):
        backlog = DiscoveryBacklog()
        backlog.ingest(
            DiscoverySignal(
                self.tenant, self.repository, "a" * 40, "owned-test-signal",
                ("discovery-evidence",), D, 1.0,
            )
        )
        backlog.add(
            BacklogCandidate(
                "goal", ("add() must return a sum",), 10, "acceptance tests pass", 1, 0.1,
                dissent=("no-change would retain the old behaviour",),
            )
        )
        return BacklogDiscoveryAdapter(backlog, evidence_refs=("discovery-evidence",), court_receipt=D)

    def _manifest(self) -> CompositionManifest:
        profiles = []
        for name in ("self-python", "external-python", "node-typescript", "go", "rust", "roblox"):
            if name == "roblox":
                profiles.append(CapabilityDeclaration(name, "luau", "studio", False, False, incomplete_reason="none"))
            elif name == "rust":
                profiles.append(CapabilityDeclaration(name, "rust", "compile-only", False, True))
            else:
                profiles.append(CapabilityDeclaration(name, name, "test-execution", True, True))
        return CompositionManifest(
            D, self.descriptor.digest, tuple(profiles),
            {"builder": D, "delivery": D, "qualification": D}, "refuse-ambiguous", False,
        )

    def binding(self, **overrides) -> RepositoryTaskBinding:
        return RepositoryTaskBinding(**{**self.binding_values, **overrides})

    def context_for(
        self, worker, *, attempt_id: str | None = None, path_limit=..., **overrides
    ) -> RepositoryHostContext:
        binding = self.binding(**({"attempt_id": attempt_id} if attempt_id else {}), **overrides)
        limits = {} if path_limit is ... else {"path_limit": path_limit}
        return RepositoryHostContext(
            binding, repository_profile=self.profile,
            admission=ProfileRegistryAdmission(self.profile, self.registry), worker=worker,
            sandbox=self.sandbox, reviewer=self.curator, holdouts=self.vault, **limits,
        )

    def factory(self, context: RepositoryHostContext | None = None):
        return compose_repository_factory(
            context=context or self.context, descriptor=self.descriptor, manifest=self.manifest,
            profile_id="external-python", discovery=self.discovery, delivery=self.delivery,
            publish_required=self.publish_required,
        )

    def host(self, context: RepositoryHostContext | None = None) -> RepositoryCompositionHost:
        return self.factory(context)(self.config).host

    def payload(self) -> dict:
        context = {
            "campaign_id": "campaign-test", "tenant_id": self.tenant, "repository_id": self.repository,
            "configuration_digest": self.descriptor.digest, "graph_digest": self.config.graph.digest,
            "base_snapshot": self.base,
        }
        return {
            "campaign_id": "campaign-test", "tenant_id": self.tenant, "repository_id": self.repository,
            "configuration_digest": self.descriptor.digest, "graph_digest": self.config.graph.digest,
            "package_id": self.package.package_id, "outcome_ids": list(self.package.outcome_ids),
            "acceptance_ids": list(self.package.acceptance_ids),
            "allowed_paths": list(self.package.allowed_paths), "semantic_locks": [],
            "cohort_kickoff": {
                "schema_version": 1, "context_digest": service_context_digest(self.config), "context": context,
            },
        }

    def execute(self, host=None, payload=None):
        return (host or self.host()).execute_package(self.package, ("runtime", "delivery"), payload or self.payload())

    def build(self, context: RepositoryHostContext | None = None):
        context = context or self.context
        payload = self.payload()
        return RepositoryBuilderAdapter(context).build(
            self.package, self.discovery.discover(self.package, payload), payload
        )

    def key(self, context: RepositoryHostContext | None = None) -> str:
        return attempt_key((context or self.context).binding, self.package, self.payload())

    def record(self, identity: str, context: RepositoryHostContext | None = None):
        store = (context or self.context).store
        return store.load_candidate(store.key_for_identity(identity))

    def service(self, factory=None) -> WholeOSService:
        """A service over ``factory`` (default: a freshly composed, preflighted one)."""

        bootstrap = (factory or self.factory())(self.config)
        service = WholeOSService(self.config, bootstrap.bindings, bootstrap.host)
        self.case.addCleanup(service.close)
        return service

    def snapshot(self) -> list[str]:
        """Every non-Git-internal path under the private state root."""

        store = self.context.store
        return sorted(
            item.relative_to(store.root).as_posix()
            for item in store.root.rglob("*")
            if ".git" not in item.relative_to(store.root).parts
        )

    def request(self, record, context: RepositoryHostContext | None = None):
        return (context or self.context).qualification_request(record)

    def source_untouched(self) -> None:
        self.case.assertEqual(_git(self.source, "rev-parse", "HEAD"), self.base)
        self.case.assertEqual(_git(self.source, "status", "--porcelain", "--untracked-files=all"), "")
        self.case.assertIn((self.source / "src" / "calc.py").read_text(encoding="utf-8"), {BUGGY, FIXED})


class RepositoryHostIntegrationTests(unittest.TestCase):
    def test_h1_01_service_prepares_a_real_committed_candidate_and_reaches_terminal_acceptance(self) -> None:
        rig = _Rig(self, FIX)
        observation = rig.service().run_to_completion()

        self.assertEqual(observation.status, "complete", observation.terminal_message)
        self.assertEqual(observation.last_result.status, PackageStatus.COMPLETED)
        self.assertEqual(len(rig.worker.calls), 1)
        rig.source_untouched()
        self.assertEqual((rig.source / "src" / "calc.py").read_text(encoding="utf-8"), BUGGY)

        store = rig.context.store
        key = store.key_for_identity(observation.last_result.candidate_digest)
        record = store.load_candidate(key)
        task = store.task_dir(key)
        self.assertEqual(record.kind, "changed")
        self.assertEqual(record.changed_paths, ("src/calc.py",))
        self.assertEqual(_git(record.clone_root, "rev-list", "--parents", "-n", "1", record.commit).split(), [record.commit, rig.base])
        self.assertEqual(_git(record.clone_root, "remote"), "")
        self.assertEqual(_git(task / "p000" / "repo", "remote"), "")
        self.assertEqual(_git(record.clone_root, "show", f"{record.commit}:src/calc.py").replace("\r\n", "\n"), FIXED.rstrip("\n"))

        retained = store.load_qualification(key, canonical_digest(rig.request(record)), record)
        self.assertIs(retained.receipt.disposition, QualificationDisposition.PASSED)
        self.assertEqual([check.actual_count for check in retained.receipt.checks], [1, 1])
        self.assertEqual(retained.envelope["profile"], "trusted-local-unqualified")
        self.assertIs(retained.envelope["pilot_production_qualified"], False)
        self.assertTrue(all("trusted-local-unqualified" in check.origin for check in retained.receipt.checks))
        verified = json.loads((task / retained.envelope["checks"][0]["evidence_directory"] / "receipt.json").read_text(encoding="utf-8"))
        self.assertNotEqual(Path(verified["source_repository"]).resolve(), record.clone_root.resolve())
        self.assertIn("qualification", Path(verified["source_repository"]).parts)
        self.assertEqual(len(list((store.root / "learning").glob("*.json"))), 1)
        self.assertFalse((store.root / "delivery.json").exists())
        self.assertEqual(len(rig.curator.packets), 1)
        self.assertEqual(rig.curator.packets[0]["patch"], FIX_PATCH)

    def test_held_out_content_never_reaches_the_worker_but_is_still_enforced(self) -> None:
        rig = _Rig(self, {"patch": README_PATCH, "paths": ["README.md"]}, FIX)
        rig.build()
        self.assertEqual(len(rig.worker.calls), 2, "the repair call carries host feedback")
        for call in rig.worker.calls:
            rendered = json.dumps(call["source_packet"]) + json.dumps(call["predecessor_reports"]) + call["objective"]
            self.assertNotIn(MARKER, rendered)
            self.assertNotIn(raw_sha256(HOLDOUT.encode()).removeprefix("sha256:"), rendered)
            omitted = {item["path"]: item for item in call["source_packet"]["omitted_files"]}
            self.assertIn("held-out", omitted["tests/test_holdout.py"]["reason"])
            self.assertIsNone(omitted["tests/test_holdout.py"]["blob_hash"])
            inventory = {item["path"]: item for item in call["source_packet"]["inventory"]}
            self.assertIsNone(inventory["tests/test_holdout.py"]["blob_hash"])
            selected = {item["path"] for item in call["source_packet"]["selected_files"]}
            self.assertIn("tests/test_visible.py", selected)
            self.assertNotIn("tests/test_holdout.py", selected)
        # The sealed held-out test still decides the outcome in the verifier.
        outcome = rig.build()
        self.assertIs(
            ReceiptBoundCandidateQualifier(rig.context).qualify(rig.request(rig.record(outcome.candidate_tree))).disposition,
            QualificationDisposition.PASSED,
        )

    def test_h1_02_wrong_subject_and_unbounded_inputs_are_rejected_before_any_worker_call(self) -> None:
        cases = {
            "another tenant": {"profile_tenant": "another-tenant"},
            "unknown base commit": {"binding_overrides": {"base_commit": "1" * 40}},
            "wrong base tree": {"binding_overrides": {"base_tree": "2" * 40}},
            "unallowlisted verifier": {"verifier": "not-an-adapter"},
        }
        for name, options in cases.items():
            with self.subTest(name):
                rig = _Rig(self, FIX, **options)
                with self.assertRaises(RepositoryHostUnavailable):
                    rig.factory()
                self.assertEqual(rig.worker.calls, [])
                self.assertEqual(rig.sandbox.runs, 0)

        rig = _Rig(self, FIX, binding_overrides={"context_digest": D})
        with self.assertRaisesRegex(RepositoryHostUnavailable, "differs from the frozen host binding"):
            rig.factory()(rig.config)
        self.assertEqual(rig.worker.calls, [])

        rig = _Rig(self, FIX)
        substituted = rig.payload()
        substituted["acceptance_ids"] = ["weakened-acceptance"]
        result = rig.execute(payload=substituted)
        self.assertIs(result.status, PackageStatus.BLOCKED_AUTHORITY)
        self.assertIn("acceptance manifest", result.message)
        self.assertEqual(rig.worker.calls, [])

    def test_h1_02_budgets_and_private_state_are_validated_at_the_binding_boundary(self) -> None:
        for bad in (float("nan"), float("inf"), 0, -1, True):
            with self.subTest(bad), self.assertRaises(RepositoryBindingError):
                RepositoryBuildBudget(max_total_worker_seconds=bad)
        for bad in ({"max_worker_invocations": 4}, {"worker_timeout_seconds": 5000.0}, {"max_tools": 0}, {"packet_max_bytes": 10**9}):
            with self.subTest(bad), self.assertRaises(RepositoryBindingError):
                RepositoryBuildBudget(**bad)
        rig = _Rig(self, FIX)
        with self.assertRaisesRegex(RepositoryBindingError, "outside the target repository"):
            rig.binding(state_root=rig.source / "private-state")
        with self.assertRaisesRegex(RepositoryBindingError, "labelled trusted-local"):
            rig.binding(trusted_local=False)
        with self.assertRaisesRegex(RepositoryBindingError, "independent"):
            rig.binding(evaluator_id="synthetic-builder")
        with self.assertRaises(RepositoryBindingError):
            rig.binding(allowed_paths=("../escape",))
        self.assertEqual(rig.worker.calls, [])

    def test_h1_03_unsafe_or_inaccurate_proposals_are_refused_from_observed_files(self) -> None:
        rig = _Rig(self, FIX)
        variants = {
            "outside write scope": {"patch": README_PATCH, "paths": ["README.md"]},
            "visible acceptance test": {"patch": VISIBLE_PATCH, "paths": ["tests/test_visible.py"]},
            "held-out acceptance test": {"patch": HOLDOUT_PATCH, "paths": ["tests/test_holdout.py"]},
            "inaccurate declared paths": {"patch": FIX_PATCH, "paths": ["src/other.py"]},
            "extra undeclared file": {"patch": EXTRA_FILE_PATCH, "paths": ["src/calc.py"]},
            "escaping path": {"patch": FIX_PATCH, "paths": ["../evil.py"]},
            "absolute path": {"patch": FIX_PATCH, "paths": ["/etc/passwd"]},
            "windows drive path": {"patch": FIX_PATCH, "paths": ["C:\\evil.py"]},
            "backslash path": {"patch": FIX_PATCH, "paths": ["src\\calc.py"]},
            "symlink creation": {"patch": SYMLINK_PATCH, "paths": ["src/link.py"]},
            "malformed patch": {"patch": "this is not a patch\n", "paths": ["src/calc.py"]},
        }
        single = RepositoryBuildBudget(1, 600.0, 300.0, 20, 1800.0, 100_000)
        for index, (name, step) in enumerate(variants.items()):
            with self.subTest(name):
                worker = _ScriptedPatchWorker(step)
                context = rig.context_for(worker, attempt_id=f"attempt-refusal-{index}", budget=single)
                outcome = rig.build(context)
                self.assertIs(outcome.result.disposition, BuilderDisposition.BUDGET_EXHAUSTED)
                self.assertEqual(len(worker.calls), 1)
                self.assertFalse(context.store.candidate_path(rig.key(context)).exists())
                slot = context.store.load_slot(rig.key(context), 0)
                self.assertEqual(slot.decision["decision"], "refused")
                rig.source_untouched()

    def test_h1_04_an_identical_repeated_repair_failure_fails_closed(self) -> None:
        rig = _Rig(self, {"patch": README_PATCH, "paths": ["README.md"]})
        outcome = rig.build()
        self.assertIs(outcome.result.disposition, BuilderDisposition.BLOCKED)
        self.assertIn("identical repair failure", outcome.result.failures[0])
        self.assertEqual(len(rig.worker.calls), 2, "one refusal, then one identical repair")
        self.assertFalse(rig.context.store.candidate_path(rig.key()).exists())

    def test_h1_04_worker_failures_fail_closed_and_are_never_relabelled_no_change(self) -> None:
        rig = _Rig(self, FIX)
        failures = {
            "worker exception": "raise",
            "failed receipt": {"receipt_status": "failed", "report": None},
            "malformed report": {"report": {"status": "completed", "summary": "malformed"}},
            "foreign actor": {"patch": FIX_PATCH, "paths": ["src/calc.py"], "actor": "another-actor"},
            "foreign protocol": {"patch": FIX_PATCH, "paths": ["src/calc.py"], "protocol": "other-protocol"},
            "worker blocked": {"report": _ScriptedPatchWorker.report(None, [], status="blocked"), "receipt_status": "blocked"},
            "missing receipt file": {"patch": FIX_PATCH, "paths": ["src/calc.py"], "no_receipt_file": True},
        }
        for index, (name, step) in enumerate(failures.items()):
            with self.subTest(name):
                worker = _ScriptedPatchWorker(step)
                context = rig.context_for(worker, attempt_id=f"attempt-failure-{index}")
                outcome = rig.build(context)
                self.assertIs(outcome.result.disposition, BuilderDisposition.BLOCKED)
                self.assertNotEqual(outcome.result.disposition, BuilderDisposition.NO_CHANGE)
                self.assertEqual(len(worker.calls), 1)
                self.assertFalse(context.store.candidate_path(rig.key(context)).exists())

    def test_h1_04_exhausted_budget_and_failed_attempts_survive_a_restart(self) -> None:
        steps = (
            {"patch": README_PATCH, "paths": ["README.md"]},
            {"patch": VISIBLE_PATCH, "paths": ["tests/test_visible.py"]},
            {"patch": "this is not a patch\n", "paths": ["src/calc.py"]},
        )
        rig = _Rig(self, *steps)
        first = rig.build()
        self.assertIs(first.result.disposition, BuilderDisposition.BUDGET_EXHAUSTED)
        self.assertEqual(len(rig.worker.calls), 3)
        # Losing attempts stay on disk, and a restarted process spends nothing more.
        task = rig.context.store.task_dir(rig.key())
        self.assertEqual(len(list(task.glob("slot-*.outcome.json"))), 3)
        restarted = _ScriptedPatchWorker(FIX)
        second = rig.build(rig.context_for(restarted))
        self.assertIs(second.result.disposition, BuilderDisposition.BUDGET_EXHAUSTED)
        self.assertEqual(restarted.calls, [])
        self.assertEqual(len(list(task.glob("slot-*.start.json"))), 3)
        # Through the composition host the exhausted attempt is a failure, never NO_CHANGE.
        result = rig.execute()
        self.assertIs(result.status, PackageStatus.FAILED)
        self.assertEqual(result.message, "builder:BUDGET_EXHAUSTED")

    def test_repair_is_a_complete_replacement_of_the_same_base_and_only_the_winner_is_committed(self) -> None:
        rig = _Rig(self, {"patch": README_PATCH, "paths": ["README.md"]}, FIX)
        outcome = rig.build()
        record = rig.record(outcome.candidate_tree)
        self.assertEqual(len(rig.worker.calls), 2)
        self.assertEqual(rig.worker.calls[1]["predecessor_reports"][0]["kind"], "host-patch-refusal")
        self.assertEqual(_git(record.clone_root, "rev-list", "--parents", "-n", "1", record.commit).split(), [record.commit, rig.base])
        self.assertEqual(_git(record.clone_root, "rev-list", "--count", record.commit), "2")
        self.assertEqual(record.document["worker"]["slot"], 1)
        self.assertEqual(record.document["budget_used"]["worker_invocations"], 2)
        self.assertNotEqual(rig.worker.calls[0]["evidence_directory"], rig.worker.calls[1]["evidence_directory"])

    def test_h1_05_qualification_binds_actual_tests_and_a_distinct_verifier_clone(self) -> None:
        rig = _Rig(self, FIX)
        record = rig.record(rig.build().candidate_tree)
        qualifier = ReceiptBoundCandidateQualifier(rig.context)
        request = rig.request(record)
        receipt = qualifier.qualify(request)
        self.assertIs(receipt.disposition, QualificationDisposition.PASSED)
        self.assertEqual([check.actual_count for check in receipt.checks], [1, 1])
        self.assertTrue(all(len(check.artifacts) == 3 for check in receipt.checks))
        self.assertEqual(qualifier.qualify(request), receipt, "retained by full request digest")
        runs = rig.sandbox.runs
        qualifier.qualify(request)
        self.assertEqual(rig.sandbox.runs, runs, "an intact retained receipt is reused without re-execution")

    def test_h1_05_request_binding_mismatches_never_pass_and_never_execute(self) -> None:
        rig = _Rig(self, FIX)
        record = rig.record(rig.build().candidate_tree)
        qualifier = ReceiptBoundCandidateQualifier(rig.context)
        request = rig.request(record)
        altered = {
            "candidate": {"candidate_id": "3" * 40},
            "base": {"base_id": "4" * 40},
            "acceptance": {"acceptance_manifest": ("visible-acceptance",)},
            "changed surfaces": {"changed_surfaces": ()},
            "risk tier": {"risk_tier": "critical"},
            "sandbox": {"sandbox_digest": D},
            "toolchain": {"toolchain_digest": D},
            "environment": {"environment_digest": D},
            "wrong evaluator": {"evaluator_id": "synthetic-builder"},
            "foreign cache": {"allowed_cache_origins": ("elsewhere",)},
        }
        for name, change in altered.items():
            with self.subTest(name):
                receipt = qualifier.qualify(dataclasses.replace(request, **change))
                self.assertIs(receipt.disposition, QualificationDisposition.QUARANTINED)
        self.assertEqual(rig.sandbox.runs, 0)

    def test_h1_05_failing_or_skipped_checks_never_pass(self) -> None:
        failing = _Rig(self, {"patch": NOOP_PATCH, "paths": ["src/calc.py"]})
        record = failing.record(failing.build().candidate_tree)
        receipt = ReceiptBoundCandidateQualifier(failing.context).qualify(failing.request(record))
        self.assertIs(receipt.disposition, QualificationDisposition.FAILED)
        self.assertEqual({check.status for check in receipt.checks}, {"failed"})

        skipped = _Rig(self, NO_CHANGE, already_fixed=True, skipped_visible=True, no_change_permitted=True)
        record = skipped.record(skipped.build().candidate_tree)
        receipt = ReceiptBoundCandidateQualifier(skipped.context).qualify(skipped.request(record))
        self.assertIsNot(receipt.disposition, QualificationDisposition.PASSED)
        self.assertEqual([check.status for check in receipt.checks], ["failed", "passed"])
        self.assertEqual(receipt.checks[0].actual_count, 0)

    def test_result_reader_counts_only_executed_tests(self) -> None:
        self.assertEqual(read_unittest_results(b"", b"\nRan 3 tests in 0.001s\n\nOK (skipped=3)\n")["executed"], 0)
        self.assertEqual(read_unittest_results(b"", b"\r\nRan 4 tests in 0.5s\r\n\r\nOK (skipped=1)\r\n")["executed"], 3)
        self.assertEqual(read_unittest_results(b"", b"Ran 2 tests in 0.1s\n\nOK\n")["executed"], 2)
        self.assertFalse(read_unittest_results(b"", b"Ran 2 tests in 0.1s\n\nFAILED (failures=1)\n")["ok"])
        self.assertFalse(read_unittest_results(b"OK", b"no summary here")["parsed"])
        self.assertEqual(
            read_unittest_results(b"", b"Ran 2 tests in 0.1s\n\nOK (expected failures=2)\n")["executed"], 0
        )

    def test_h1_05_tampered_or_missing_retained_evidence_blocks_reuse(self) -> None:
        rig = _Rig(self, FIX)
        record = rig.record(rig.build().candidate_tree)
        qualifier = ReceiptBoundCandidateQualifier(rig.context)
        request = rig.request(record)
        receipt = qualifier.qualify(request)
        store, key = rig.context.store, rig.key()
        digest = canonical_digest(request)
        receipt_path, envelope_path = store.qualification_paths(key, digest)
        stdout_path = _artifact(receipt.checks[0].artifacts[1])
        for name, path in (("artifact", stdout_path), ("receipt", receipt_path), ("envelope", envelope_path)):
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            try:
                with self.subTest(f"tampered {name}"):
                    with self.assertRaises(RepositoryHostBlocked):
                        store.load_qualification(key, digest, record)
                    self.assertIs(qualifier.qualify(request).disposition, QualificationDisposition.QUARANTINED)
            finally:
                path.write_bytes(original)
        original = envelope_path.read_bytes()
        envelope_path.unlink()
        try:
            with self.subTest("partial retention"), self.assertRaisesRegex(RepositoryHostBlocked, "partial"):
                store.load_qualification(key, digest, record)
        finally:
            envelope_path.write_bytes(original)
        stdout_path.unlink()
        with self.subTest("missing artifact"), self.assertRaises(RepositoryHostBlocked):
            store.load_qualification(key, digest, record)

    def test_h1_05_a_receipt_copied_from_another_candidate_is_refused(self) -> None:
        rig = _Rig(self, FIX)
        first = rig.record(rig.build().candidate_tree)
        other = rig.context_for(_ScriptedPatchWorker(FIX), attempt_id="attempt-two")
        second = rig.record(rig.build(other).candidate_tree, other)
        self.assertNotEqual(first.commit, second.commit)
        self.assertIs(ReceiptBoundCandidateQualifier(rig.context).qualify(rig.request(first)).disposition, QualificationDisposition.PASSED)
        self.assertIs(ReceiptBoundCandidateQualifier(other).qualify(rig.request(second, other)).disposition, QualificationDisposition.PASSED)
        first_paths = rig.context.store.qualification_paths(rig.key(), canonical_digest(rig.request(first)))
        second_paths = other.store.qualification_paths(rig.key(other), canonical_digest(rig.request(second, other)))
        for source, target in zip(second_paths, first_paths):
            target.write_bytes(source.read_bytes())
        with self.assertRaises(RepositoryHostBlocked):
            rig.context.store.load_qualification(rig.key(), canonical_digest(rig.request(first)), first)

    def test_h1_06_missing_or_weaker_sandbox_blocks_before_any_target_execution(self) -> None:
        strict = _Rig(self, FIX, requirements=SandboxRequirements(), trusted_local=False)
        with self.assertRaisesRegex(RepositoryHostUnavailable, "hostile-code isolation unavailable"):
            strict.factory()
        self.assertEqual((strict.sandbox.runs, strict.worker.calls), (0, []))

        network = _Rig(
            self, FIX, requirements=SandboxRequirements(network_policy="deny", hostile_code_isolation=False)
        )
        with self.assertRaisesRegex(RepositoryHostUnavailable, "network-deny enforcement unavailable"):
            network.factory()
        self.assertEqual((network.sandbox.runs, network.worker.calls), (0, []))

        missing = _Rig(self, FIX, sandbox=_CountingSandbox(available=False))
        with self.assertRaisesRegex(RepositoryHostUnavailable, "sandbox adapter unavailable"):
            missing.factory()
        self.assertEqual((missing.sandbox.runs, missing.worker.calls), (0, []))

    def test_h1_06_sandbox_lost_after_build_retains_an_unqualified_candidate(self) -> None:
        rig = _Rig(self, FIX)
        record = rig.record(rig.build().candidate_tree)
        rig.sandbox.available = False
        receipt = ReceiptBoundCandidateQualifier(rig.context).qualify(rig.request(record))
        self.assertIs(receipt.disposition, QualificationDisposition.INCOMPLETE)
        self.assertTrue(any("sandbox" in item for item in receipt.invalidations))
        self.assertEqual(rig.sandbox.runs, 0)
        self.assertEqual(rig.context.store.load_candidate(rig.key()).commit, record.commit)

    def test_h1_07_restart_after_the_candidate_receipt_makes_no_model_call(self) -> None:
        rig = _Rig(self, FIX)
        first = rig.build()
        candidate_bytes = rig.context.store.candidate_path(rig.key()).read_bytes()
        restarted = _ScriptedPatchWorker("raise")
        second = rig.build(rig.context_for(restarted))
        self.assertEqual(restarted.calls, [])
        self.assertEqual(second.candidate_tree, first.candidate_tree)
        self.assertEqual(second.candidate_commit, first.candidate_commit)
        self.assertEqual(rig.context.store.candidate_path(rig.key()).read_bytes(), candidate_bytes)

    def test_h1_07_uncertain_worker_execution_never_starts_a_duplicate(self) -> None:
        rig = _Rig(self, "die")
        with self.assertRaises(_SimulatedProcessDeath):
            rig.build()
        self.assertEqual(len(rig.worker.calls), 1)
        for attempt in range(2):
            replacement = _ScriptedPatchWorker(FIX)
            with self.assertRaises(RepositoryHostUncertain):
                rig.build(rig.context_for(replacement))
            self.assertEqual(replacement.calls, [])
        # The real process still running is likewise never duplicated.
        evidence = rig.worker.calls[0]["evidence_directory"]
        (evidence / "process.json").write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        self.assertTrue(process_is_alive(os.getpid()))
        with self.assertRaisesRegex(RepositoryHostUncertain, "still running"):
            rig.build(rig.context_for(_ScriptedPatchWorker(FIX)))

    def test_h1_07_a_finished_worker_outcome_is_adopted_without_duplicate_model_work(self) -> None:
        rig = _Rig(self, "die")
        with self.assertRaises(_SimulatedProcessDeath):
            rig.build()
        rig.worker.complete_later(0, FIX)
        replacement = _ScriptedPatchWorker("raise")
        outcome = rig.build(rig.context_for(replacement))
        self.assertEqual(replacement.calls, [])
        self.assertIs(outcome.result.disposition, BuilderDisposition.READY_FOR_VERIFICATION)
        record = rig.record(outcome.candidate_tree)
        slot = rig.context.store.load_slot(rig.key(), 0)
        self.assertTrue(slot.outcome["adopted"])
        self.assertEqual(slot.outcome["elapsed_seconds"], rig.context.binding.budget.worker_timeout_seconds)
        self.assertEqual(record.document["budget_used"]["worker_invocations"], 1)

    def test_h1_07_a_dead_worker_without_a_receipt_is_charged_and_terminal(self) -> None:
        rig = _Rig(self, "die")
        with self.assertRaises(_SimulatedProcessDeath):
            rig.build()
        gone = subprocess.Popen([sys.executable, "-c", "pass"])
        gone.wait()
        (rig.worker.calls[0]["evidence_directory"] / "process.json").write_text(
            json.dumps({"pid": gone.pid}), encoding="utf-8"
        )
        replacement = _ScriptedPatchWorker(FIX)
        outcome = rig.build(rig.context_for(replacement))
        self.assertIs(outcome.result.disposition, BuilderDisposition.BLOCKED)
        self.assertEqual(replacement.calls, [])
        self.assertIn("interrupted", outcome.result.failures[0])

    def test_h1_07_corrupt_or_drifted_candidate_state_is_a_typed_blocker(self) -> None:
        rig = _Rig(self, FIX)
        record = rig.record(rig.build().candidate_tree)
        store, key = rig.context.store, rig.key()
        path = store.candidate_path(key)
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with self.assertRaises(RepositoryHostBlocked):
            rig.build(rig.context_for(_ScriptedPatchWorker(FIX)))
        path.write_bytes(original)
        (record.clone_root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(RepositoryHostBlocked, "dirty"):
            store.load_candidate(key)
        (record.clone_root / "untracked.txt").unlink()
        _git(record.clone_root, "remote", "add", "origin", "https://example.invalid/never-contacted.git")
        with self.assertRaisesRegex(RepositoryHostBlocked, "remote"):
            store.load_candidate(key)
        _git(record.clone_root, "remote", "remove", "origin")
        patch = store.task_dir(key) / "candidate.patch"
        patch.write_bytes(patch.read_bytes() + b"\n")
        with self.assertRaisesRegex(RepositoryHostBlocked, "patch"):
            store.load_candidate(key)

    def test_h1_07_terminal_replay_revalidates_candidate_qualification_admission_and_binding(self) -> None:
        rig = _Rig(self, FIX)
        host = rig.host()
        first = rig.execute(host)
        self.assertIs(first.status, PackageStatus.COMPLETED)
        self.assertEqual(rig.execute(host), first, "an intact retained success replays")
        self.assertEqual(len(rig.worker.calls), 1)
        store, key = rig.context.store, rig.key()
        record = store.load_candidate(key)
        digest = canonical_digest(rig.request(record))
        receipt_path, envelope_path = store.qualification_paths(key, digest)

        original = envelope_path.read_bytes()
        envelope_path.write_bytes(original + b" ")
        blocked = rig.execute(host)
        self.assertIs(blocked.status, PackageStatus.BLOCKED_CAPABILITY)
        self.assertIn("no longer validates", blocked.message)
        self.assertEqual(len(list((store.root / "historical-results").glob("*.json"))), 1)
        envelope_path.write_bytes(original)
        self.assertEqual(rig.execute(host), first, "restored evidence is valid again; the old result was kept")

        receipt_original = receipt_path.read_bytes()
        receipt_path.unlink()
        self.assertIs(rig.execute(host).status, PackageStatus.BLOCKED_CAPABILITY)
        receipt_path.write_bytes(receipt_original)

        (record.clone_root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
        self.assertIs(rig.execute(host).status, PackageStatus.BLOCKED_CAPABILITY)
        (record.clone_root / "untracked.txt").unlink()

        rig.registry.current = False
        revoked = rig.execute(host)
        self.assertIsNot(revoked.status, PackageStatus.COMPLETED)
        with self.assertRaises(RepositoryHostBlocked):
            host.assess_terminal_candidate(None, {})
        rig.registry.current = True
        self.assertEqual(rig.execute(host), first)
        self.assertEqual(len(rig.worker.calls), 1)

        rebound_worker = _ScriptedPatchWorker(FIX)
        rebound = rig.host(rig.context_for(rebound_worker, attempt_id="attempt-rebound"))
        second = rig.execute(rebound)
        self.assertEqual(len(rebound_worker.calls), 1, "a changed host binding never reuses a terminal success")
        self.assertNotEqual(second.candidate_digest, first.candidate_digest)

    def test_h1_08_verified_no_change_makes_zero_delivery_calls_and_honours_the_contract(self) -> None:
        broker = _CountingBroker(state_path=None)
        allowed = _Rig(self, NO_CHANGE, already_fixed=True, no_change_permitted=True, delivery=broker)
        result = allowed.execute()
        self.assertIs(result.status, PackageStatus.NO_CHANGE, result.message)
        self.assertEqual(broker.calls, 0)
        record = allowed.record(result.candidate_digest)
        self.assertEqual((record.kind, record.commit, record.changed_paths), ("no-change", allowed.base, ()))
        self.assertEqual(len(allowed.worker.calls), 1)
        allowed.source_untouched()

        publish_broker = _CountingBroker(state_path=None)
        requested = _Rig(
            self, NO_CHANGE, already_fixed=True, no_change_permitted=True,
            publish_required=True, delivery=publish_broker,
        )
        unmet = requested.execute()
        self.assertIs(unmet.status, PackageStatus.FAILED)
        self.assertIn("requires a change", unmet.message)
        self.assertEqual(publish_broker.calls, 0)

        change_required = _Rig(self, NO_CHANGE, already_fixed=True, no_change_permitted=False)
        self.assertIs(change_required.execute().status, PackageStatus.FAILED)

    def test_h1_08_a_no_change_claim_over_failing_tests_is_never_no_change(self) -> None:
        rig = _Rig(self, NO_CHANGE, no_change_permitted=True)
        result = rig.execute()
        self.assertIs(result.status, PackageStatus.BLOCKED_CAPABILITY)
        self.assertIn("qualification", result.message)

    def test_h1_08_changed_local_preparation_makes_no_remote_call_and_cannot_satisfy_a_pr_contract(self) -> None:
        broker = _CountingBroker(state_path=None)
        rig = _Rig(self, FIX, publish_required=True, delivery=broker)
        result = rig.execute()
        self.assertIs(result.status, PackageStatus.BLOCKED_AUTHORITY)
        self.assertEqual(broker.calls, 0)
        self.assertEqual(rig.context.store.load_candidate(rig.key()).kind, "changed")

        granted = DeliveryBroker(
            _Transport(), grants={"grant": DeliveryGrant("grant", "tenant-test", "target", "main", "hive/", (ArtifactKind.APPLICATION,))}
        )
        with self.assertRaisesRegex(RepositoryBindingError, "no delivery transport"):
            _Rig(self, FIX, delivery=granted).host()

    def test_h1_09_terminal_acceptance_needs_a_separately_supplied_curator_bound_to_the_candidate(self) -> None:
        wrong_packet = _Rig(self, FIX, curator=_SyntheticCurator(wrong_packet=True))
        observation = wrong_packet.service().run_to_completion()
        self.assertNotEqual(observation.status, "complete")

        rejecting = _Rig(self, FIX, curator=_SyntheticCurator(accept=False))
        self.assertNotEqual(rejecting.service().run_to_completion().status, "complete")

        same_identity = _Rig(self, FIX, curator=_SyntheticCurator(reviewer_id="synthetic-builder"))
        with self.assertRaisesRegex(RepositoryHostUnavailable, "independent"):
            same_identity.factory()

        no_reviewer = _Rig(self, FIX)
        no_reviewer.curator = object()
        with self.assertRaisesRegex(RepositoryHostUnavailable, "Curator"):
            no_reviewer.factory(no_reviewer.context_for(no_reviewer.worker))
        self.assertEqual(no_reviewer.worker.calls, [])

    def test_h1_09_missing_authority_or_dependencies_are_typed_blockers_before_any_worker(self) -> None:
        rig = _Rig(self, FIX)
        rig.registry.current = False
        with self.assertRaisesRegex(RepositoryHostUnavailable, "BLOCKED_AUTHORITY"):
            rig.factory()
        rig.registry.current = True
        rig.registry.authorized = False
        with self.assertRaises(RepositoryHostUnavailable):
            rig.factory()
        rig.registry.authorized = True
        no_worker = rig.context_for(object())
        with self.assertRaisesRegex(RepositoryHostUnavailable, "no actual patch-proposing worker"):
            rig.factory(no_worker)
        holdouts = _Rig(self, FIX)
        holdouts.vault.files["tests/test_holdout.py"] = b"substituted held-out bytes\n"
        with self.assertRaisesRegex(RepositoryHostUnavailable, "sealed digest"):
            holdouts.factory()
        self.assertEqual(holdouts.worker.calls, [])
        # A dependency that disappears later is an unsealed typed blocker, not a run.
        late = _Rig(self, FIX)
        host = late.host()
        late.registry.current = False
        result = late.execute(host)
        self.assertIs(result.status, PackageStatus.BLOCKED_AUTHORITY)
        self.assertEqual(late.worker.calls, [])

    def test_h1_10_private_material_stays_out_of_public_sources(self) -> None:
        # Forbidden markers are assembled so this file does not contain them itself.
        forbidden = (
            "cou" + "pon",
            "https://" + "github.com",
            "C:\\" + "Users",
            "HiveMind" + "OS",
        )
        root = Path(__file__).resolve().parents[1]
        public = [
            root / "src" / "hive_mind_os" / "whole_os_repository_host.py",
            root / "src" / "hive_mind_os" / "local_claude_worker.py",
            root / "tests" / "test_whole_os_repository_host.py",
            root / "tests" / "test_local_claude_worker.py",
            *root.glob("docs/architecture/ADR-091-*.md"),
        ]
        for path in public:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path.name):
                for marker in forbidden:
                    self.assertNotIn(marker.casefold(), text.casefold())
        rig = _Rig(self, FIX)
        rig.build()
        state_text = "".join(
            item.read_text(encoding="utf-8", errors="ignore")
            for item in rig.context.store.root.rglob("*.json")
            if item.is_file()
        )
        self.assertIn(
            json.dumps(str(rig.source))[1:-1], state_text,
            "private paths live only in the private state root",
        )
        self.assertNotIn(MARKER, state_text)


class RepositoryHostAmbientGitConfigTests(unittest.TestCase):
    """Judge counterexample: a real Haiku proposal failed only because of ambient Git config.

    The host materializes clones under ``core.autocrlf=false`` but used to apply the
    accepted patch under the machine's configuration, so Windows ``core.autocrlf=true``
    rewrote LF bytes as CRLF before any test ran.  The ambient value is injected for
    child Git processes only; no Git configuration file is ever edited.
    """

    def _ambient(self, rig):
        configuration = rig.root / "ambient-gitconfig"
        configuration.write_text("[core]\n\tautocrlf = true\n", encoding="utf-8", newline="\n")
        self.addCleanup(lambda: self.assertEqual(
            configuration.read_text(encoding="utf-8"), "[core]\n\tautocrlf = true\n"))
        return mock.patch.dict(
            os.environ, {"GIT_CONFIG_GLOBAL": str(configuration), "GIT_CONFIG_NOSYSTEM": "1"})

    def test_ambient_autocrlf_true_preserves_exact_accepted_bytes_through_qualification(self) -> None:
        rig = _Rig(self, FIX)
        with self._ambient(rig):
            outcome = rig.build()
            record = rig.record(outcome.candidate_tree)
            committed = subprocess.run(
                ["git", "-C", str(record.clone_root), "show", f"{record.commit}:src/calc.py"],
                capture_output=True, check=True).stdout
            worktree = (record.clone_root / "src" / "calc.py").read_bytes()
            self.assertEqual(committed, FIXED.encode("utf-8"), "exact accepted bytes in the commit")
            self.assertEqual(worktree, FIXED.encode("utf-8"), "exact accepted bytes in the clone")
            self.assertNotIn(b"\r", committed + worktree)
            self.assertEqual(rig.context.store.load_candidate(rig.key()).commit, record.commit)
            receipt = ReceiptBoundCandidateQualifier(rig.context).qualify(rig.request(record))
            self.assertIs(receipt.disposition, QualificationDisposition.PASSED)
            self.assertEqual([check.actual_count for check in receipt.checks], [1, 1])
        self.assertEqual(len(rig.worker.calls), 1, "one model call, no replay needed")
        rig.source_untouched()

    def test_a_dirty_line_ending_change_in_a_retained_clone_is_seen_despite_ambient_config(self) -> None:
        rig = _Rig(self, FIX)
        outcome = rig.build()
        record = rig.record(outcome.candidate_tree)
        target = record.clone_root / "src" / "calc.py"
        target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
        with self._ambient(rig):
            # Ambient autocrlf=true normalizes CRLF back to LF when Git compares, so an
            # unpinned status could hide this; the pinned policy must still report it.
            with self.assertRaisesRegex(RepositoryHostBlocked, "dirty"):
                rig.context.store.load_candidate(rig.key())


class RepositoryHostReadOnlyGitIsolationTests(unittest.TestCase):
    """Cross-Examiner counterexample: a read-only status query ran an ambient helper.

    An ambient global ``core.fsmonitor`` command was executed by the host's retained-
    state ``git status`` (and still returned clean).  The helpers here only append to a
    marker file, so running them is observable and harmless.  Ambient values are injected
    for child processes only; no Git configuration file is edited.
    """

    def setUp(self) -> None:
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory(ignore_cleanup_errors=True)))
        self.repo = self.root / "retained-clone"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.name", "Synthetic Fixture")
        _git(self.repo, "config", "user.email", "fixture@example.invalid")
        (self.repo / "tracked.txt").write_bytes(b"one\n")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-q", "-m", "synthetic base")
        self.head = _git(self.repo, "rev-parse", "HEAD")

    def _helper(self, name: str) -> tuple[str, Path]:
        """An inert fsmonitor command that records that it was launched."""
        marker = self.root / f"{name}.called"
        script = self.root / f"{name}.py"
        script.write_text(
            f"import pathlib\npathlib.Path({str(marker)!r}).open('a').write('called\\n')\n",
            encoding="utf-8",
        )
        command = f'"{Path(sys.executable).as_posix()}" "{script.as_posix()}"'
        return command, marker

    def _ambient(self, command: str):
        configuration = self.root / "ambient-gitconfig"
        escaped = command.replace("\\", "\\\\").replace('"', '\\"')
        configuration.write_text(f'[core]\n\tfsmonitor = "{escaped}"\n', encoding="utf-8", newline="\n")
        original = configuration.read_bytes()
        self.addCleanup(lambda: self.assertEqual(configuration.read_bytes(), original))
        return mock.patch.dict(
            os.environ, {"GIT_CONFIG_GLOBAL": str(configuration), "GIT_CONFIG_NOSYSTEM": "1"})

    def _plain_status(self) -> bytes:
        return subprocess.run(
            ["git", "--no-optional-locks", "-C", str(self.repo), "status", "--porcelain"],
            capture_output=True, check=True,
        ).stdout

    def _assert_helper_is_live_for_plain_git(self, marker: Path) -> None:
        marker.unlink(missing_ok=True)
        self._plain_status()
        if not marker.exists():
            self.skipTest("this Git does not launch a core.fsmonitor command for status, "
                          "so there is no helper vector to guard on this platform")
        marker.unlink()

    def test_ambient_global_fsmonitor_helper_is_not_executed_by_the_host_reader(self) -> None:
        command, marker = self._helper("ambient-global")
        with self._ambient(command):
            self._assert_helper_is_live_for_plain_git(marker)
            before = dict(os.environ)
            self.assertEqual(_git_bytes(self.repo, "status", "--porcelain", "--untracked-files=all"), b"")
            self.assertFalse(marker.exists(), "the ambient helper was launched by the host reader")
            self.assertEqual(dict(os.environ), before, "the parent environment was not mutated")

    def test_clone_local_fsmonitor_helper_is_overridden_too(self) -> None:
        command, marker = self._helper("clone-local")
        _git(self.repo, "config", "core.fsmonitor", command)
        self._assert_helper_is_live_for_plain_git(marker)
        self.assertEqual(_git_bytes(self.repo, "status", "--porcelain", "--untracked-files=all"), b"")
        self.assertFalse(marker.exists(), "the clone-local helper was launched by the host reader")

    def test_both_helpers_at_once_are_never_launched_and_controlled_reads_still_work(self) -> None:
        ambient_command, ambient_marker = self._helper("both-ambient")
        local_command, local_marker = self._helper("both-local")
        _git(self.repo, "config", "core.fsmonitor", local_command)
        with self._ambient(ambient_command):
            for name in ("status", "diff", "rev-parse", "ls-tree", "remote"):
                arguments = {
                    "status": ("status", "--porcelain", "--untracked-files=all"),
                    "diff": ("diff", "--name-only", "-z", self.head, "HEAD"),
                    "rev-parse": ("rev-parse", "HEAD^{tree}"),
                    "ls-tree": ("ls-tree", "-r", "--name-only", "-z", self.head),
                    "remote": ("remote",),
                }[name]
                with self.subTest(name):
                    _git_bytes(self.repo, *arguments)
            # Reads reflect the real state: HEAD identity, cleanliness, then a real edit.
            self.assertEqual(_git_bytes(self.repo, "rev-parse", "HEAD").decode().strip(), self.head)
            self.assertEqual(_git_bytes(self.repo, "status", "--porcelain", "--untracked-files=all"), b"")
            (self.repo / "tracked.txt").write_bytes(b"two\n")
            (self.repo / "untracked.txt").write_bytes(b"x\n")
            status = _git_bytes(self.repo, "status", "--porcelain", "--untracked-files=all").decode()
            self.assertIn("tracked.txt", status)
            self.assertIn("untracked.txt", status)
            self.assertFalse(ambient_marker.exists() or local_marker.exists())

    def test_retained_candidate_reads_are_isolated_end_to_end(self) -> None:
        """The store's own dirty check is the production caller of the reader."""

        rig = _Rig(self, FIX)
        record = rig.record(rig.build().candidate_tree)
        command, marker = self._helper("store-reader")
        _git(record.clone_root, "config", "core.fsmonitor", command)
        with self._ambient(self._helper("store-ambient")[0]):
            loaded = rig.context.store.load_candidate(rig.key())
        self.assertEqual(loaded.commit, record.commit)
        self.assertFalse(marker.exists())
        self.assertFalse((self.root / "store-ambient.called").exists())


class RepositoryHostOuterReplayTests(unittest.TestCase):
    """A resumed ``WholeOSService`` must not deliver a success the host cannot re-verify.

    These replay the independent Curator's counterexamples through the real
    service entry point (``run_to_completion``), not through the host alone.
    """

    def _complete(self):
        rig = _Rig(self, FIX)
        factory = rig.factory()
        service = rig.service(factory)
        first = service.run_to_completion()
        self.assertEqual(first.status, "complete", first.terminal_message)
        self.assertEqual(len(rig.worker.calls), 1)
        return rig, factory, service

    def _assert_blocked_without_effects(self, rig, replay, names) -> None:
        self.assertEqual(replay.status, "blocked", replay.terminal_message)
        self.assertIn("failed revalidation", replay.terminal_message)
        self.assertEqual(replay.completed_packages, ())
        self.assertIsNone(replay.terminal_assessment)
        self.assertEqual(len(rig.worker.calls), 1, "no duplicate model work")
        self.assertEqual(rig.snapshot(), names, "no new host, Git or receipt effects")
        rig.source_untouched()

    def test_same_service_resume_after_revoked_admission_is_blocked(self) -> None:
        rig, _, service = self._complete()
        names = rig.snapshot()
        for flag in ("current", "authorized"):
            with self.subTest(flag):
                setattr(rig.registry, flag, False)
                calls = rig.registry.calls
                replay = service.run_to_completion()
                self.assertGreater(rig.registry.calls, calls, "the host was asked again")
                self._assert_blocked_without_effects(rig, replay, names)
                self.assertEqual(service.observe().status, "blocked")
                setattr(rig.registry, flag, True)
                resumed = service.run_to_completion()
                self.assertEqual(resumed.status, "complete", "restored evidence is delivered again")
        self.assertEqual(len(rig.worker.calls), 1)
        self.assertEqual(len(rig.curator.packets), 1, "no second Curator review")

    def test_recreated_service_and_factory_resume_after_revoked_admission_is_blocked(self) -> None:
        rig, factory, service = self._complete()
        names = rig.snapshot()
        rig.registry.current = False
        calls = rig.registry.calls
        reused = rig.service(factory)
        replay = reused.run_to_completion()
        self.assertGreater(rig.registry.calls, calls)
        self._assert_blocked_without_effects(rig, replay, names)
        # A freshly composed factory refuses to exist while admission is revoked.
        with self.assertRaisesRegex(RepositoryHostUnavailable, "BLOCKED_AUTHORITY"):
            rig.factory()
        self.assertEqual(len(rig.worker.calls), 1)

    def test_fresh_factory_resume_after_candidate_receipt_corruption_is_blocked(self) -> None:
        rig, _, service = self._complete()
        store, key = rig.context.store, rig.key()
        path = store.candidate_path(key)
        original = path.read_bytes()
        names = rig.snapshot()
        for name, damaged in (("empty object", b"{}\n"), ("truncated", original[:40]), ("appended", original + b" ")):
            with self.subTest(name):
                path.write_bytes(damaged)
                resumed = rig.service()
                self._assert_blocked_without_effects(rig, resumed.run_to_completion(), names)
                self.assertEqual(service.observe().status, "blocked")
        path.write_bytes(original)
        self.assertEqual(rig.service().run_to_completion().status, "complete")
        self.assertEqual(len(rig.worker.calls), 1)

    def test_resume_after_candidate_clone_or_patch_corruption_is_blocked(self) -> None:
        rig, _, service = self._complete()
        store, key = rig.context.store, rig.key()
        record = store.load_candidate(key)
        names = rig.snapshot()
        patch = store.task_dir(key) / "candidate.patch"
        original = patch.read_bytes()
        patch.write_bytes(original + b"\n")
        self._assert_blocked_without_effects(rig, service.run_to_completion(), names)
        patch.write_bytes(original)
        (record.clone_root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
        blocked = service.run_to_completion()
        (record.clone_root / "untracked.txt").unlink()
        self._assert_blocked_without_effects(rig, blocked, names)
        self.assertEqual(service.run_to_completion().status, "complete")

    def test_resume_after_qualification_evidence_corruption_is_blocked(self) -> None:
        rig, _, service = self._complete()
        store, key = rig.context.store, rig.key()
        record = store.load_candidate(key)
        digest = canonical_digest(rig.request(record))
        receipt_path, envelope_path = store.qualification_paths(key, digest)
        retained = store.load_qualification(key, digest, record)
        stdout_path = _artifact(retained.receipt.checks[0].artifacts[1])
        names = rig.snapshot()
        for name, path in (
            ("verification stdout", stdout_path),
            ("qualification receipt", receipt_path),
            ("qualification envelope", envelope_path),
        ):
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            try:
                with self.subTest(name):
                    self._assert_blocked_without_effects(rig, service.run_to_completion(), names)
            finally:
                path.write_bytes(original)
            self.assertEqual(service.run_to_completion().status, "complete")
        original = envelope_path.read_bytes()
        envelope_path.unlink()
        try:
            with self.subTest("missing qualification envelope"):
                replay = service.run_to_completion()
                self.assertEqual(replay.status, "blocked")
                self.assertIn("partial", replay.terminal_message)
        finally:
            envelope_path.write_bytes(original)
        self.assertEqual(len(rig.worker.calls), 1)

    def test_resume_under_another_host_binding_never_reuses_the_old_success(self) -> None:
        rig, _, _ = self._complete()
        names = rig.snapshot()
        worker = _ScriptedPatchWorker(FIX)
        other = rig.context_for(worker, attempt_id="attempt-rebound")
        resumed = rig.service(rig.factory(other))
        replay = resumed.run_to_completion()
        self.assertEqual(replay.status, "blocked")
        self.assertIn("host terminal receipt is absent for this binding", replay.terminal_message)
        self.assertEqual(worker.calls, [], "another binding never starts model work here")
        self.assertEqual(len(rig.worker.calls), 1)
        self.assertEqual(rig.snapshot(), names)
        self.assertFalse(other.store.root.exists(), "the other binding wrote nothing")

    def test_a_service_receipt_that_disagrees_with_the_host_receipt_is_rejected(self) -> None:
        rig, _, service = self._complete()
        receipts = list(rig.config.state_dir.rglob("packages/*.json"))
        self.assertEqual(len(receipts), 1)
        document = json.loads(receipts[0].read_text(encoding="utf-8"))
        original = receipts[0].read_bytes()
        document["candidate_digest"] = "sha256:" + "9" * 64
        receipts[0].write_bytes(json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n")
        try:
            replay = service.run_to_completion()
            self.assertEqual(replay.status, "blocked")
            self.assertIn("differs from the host terminal receipt", replay.terminal_message)
        finally:
            receipts[0].write_bytes(original)
        self.assertEqual(service.run_to_completion().status, "complete")

    def test_direct_host_validator_is_read_only_and_names_the_reason(self) -> None:
        rig = _Rig(self, FIX)
        host = rig.host()
        result = rig.execute(host)
        payload = rig.payload()
        names = rig.snapshot()
        self.assertIsNone(host.validate_retained_package_result(rig.package, result, payload))
        rig.registry.current = False
        reason = host.validate_retained_package_result(rig.package, result, payload)
        self.assertIn("admission", reason)
        forged = dataclasses.replace(result, status=PackageStatus.NO_CHANGE)
        rig.registry.current = True
        self.assertIn("differs", host.validate_retained_package_result(rig.package, forged, payload))
        failed = dataclasses.replace(result, status=PackageStatus.FAILED, candidate_digest=None)
        self.assertIn("not a success", host.validate_retained_package_result(rig.package, failed, payload))
        self.assertEqual(rig.snapshot(), names, "validation wrote nothing")
        self.assertEqual(len(rig.worker.calls), 1)


class RepositoryHostPathBoundTests(unittest.TestCase):
    """The documented Windows path bound is an early typed preflight, not a mid-run crash.

    The sandbox and Git receipt writers do not use extended-length paths, so a deep
    private state root once failed inside a run.  The bound is checked with an
    explicit limit so it is exercised on every platform.
    """

    SPAN = 187  # documented: state root + fixed artifact path of a verifier clone

    def test_documented_bound_is_exact(self) -> None:
        rig = _Rig(self, FIX)
        length = len(str(rig.context.binding.state_root))
        self.assertEqual(WINDOWS_PATH_LIMIT - self.SPAN, 72, "documented state-root bound")
        self.assertEqual(rig.context_for(rig.worker, path_limit=length + self.SPAN).path_problems(), ())
        tight = rig.context_for(rig.worker, path_limit=length + self.SPAN - 1).path_problems()
        self.assertEqual(len(tight), 1)
        self.assertIn("state root is too deep", tight[0])
        self.assertIsNone(rig.context_for(rig.worker, path_limit=None).max_relative_path())
        with self.assertRaises(RepositoryBindingError):
            rig.context_for(rig.worker, path_limit=0)

    def test_deep_state_root_blocks_before_any_effect(self) -> None:
        rig = _Rig(self, FIX)
        deep = rig.root / ("d" * 70) / "state"
        context = rig.context_for(rig.worker, path_limit=WINDOWS_PATH_LIMIT, state_root=deep)
        self.assertEqual(len(context.path_problems()), 1)
        with self.assertRaisesRegex(RepositoryHostUnavailable, "state root is too deep"):
            rig.factory(context)
        with self.assertRaisesRegex(RepositoryHostBlocked, "unsupported path length"):
            rig.build(context)
        host = RepositoryCompositionHost(
            context, manifest=rig.manifest, profile_id="external-python", discovery=rig.discovery
        )
        result = host.execute_package(rig.package, ("runtime", "delivery"), rig.payload())
        self.assertIs(result.status, PackageStatus.BLOCKED_CAPABILITY)
        self.assertIn("state root is too deep", result.message)
        self.assertEqual(rig.worker.calls, [])
        self.assertEqual(rig.sandbox.runs, 0)
        self.assertFalse(deep.parent.exists(), "no directory was created for the rejected root")

    def test_long_tracked_path_is_a_typed_blocker(self) -> None:
        tracked = "src/" + "a" * 40 + "/" + "b" * 40 + ".py"  # 88 characters
        rig = _Rig(self, FIX, extra_files={tracked: "x = 1\n"})
        length = len(str(rig.context.binding.state_root))
        context = rig.context_for(rig.worker, path_limit=length + self.SPAN)  # room for 71
        problems = context.path_problems()
        self.assertEqual(len(problems), 1)
        self.assertIn("88 characters", problems[0])
        with self.assertRaisesRegex(RepositoryHostUnavailable, "tracked repository path"):
            rig.factory(context)
        self.assertEqual((rig.worker.calls, rig.sandbox.runs), ([], 0))

    def test_a_patch_path_beyond_the_bound_is_refused_before_it_is_applied(self) -> None:
        rig = _Rig(self, FIX)
        length = len(str(rig.context.binding.state_root))
        name = "src/" + "n" * 70 + ".py"  # 77 characters, above the 71 of this limit
        patch = (
            f"diff --git a/{name} b/{name}\nnew file mode 100644\n--- /dev/null\n"
            f"+++ b/{name}\n@@ -0,0 +1 @@\n+x = 1\n"
        )
        worker = _ScriptedPatchWorker({"patch": patch, "paths": [name]})
        single = RepositoryBuildBudget(1, 600.0, 300.0, 20, 1800.0, 100_000)
        context = rig.context_for(
            worker, attempt_id="attempt-long-patch", path_limit=length + self.SPAN, budget=single
        )
        outcome = rig.build(context)
        self.assertIs(outcome.result.disposition, BuilderDisposition.BUDGET_EXHAUSTED)
        slot = context.store.load_slot(rig.key(context), 0)
        self.assertEqual(slot.decision["decision"], "refused")
        self.assertIn("path length bound", slot.decision["reason"])
        self.assertFalse(context.store.candidate_path(rig.key(context)).exists())


if __name__ == "__main__":
    unittest.main()
