import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from hive_mind_os.brain_kernel.canonical import canonical_digest
from hive_mind_os.builder_session import BuilderDisposition, BuilderSessionResult
from hive_mind_os.candidate_qualification import CandidateQualifier
from hive_mind_os.cohort_assurance import (
    TerminalAssessment,
    TerminalEvidence,
    convergence_candidate_digest,
)
from hive_mind_os.cohort_runtime import VerificationResult
from hive_mind_os.cortex.repository.mission_bindings import (
    ConfiguredMissionBindingsProvider,
    MissionBindingDescriptor,
)
from hive_mind_os.delivery_broker import (
    ArtifactKind,
    DeliveryBroker,
    DeliveryGrant,
    DeliveryResult,
    DeliveryState,
)
from hive_mind_os.discovery_backlog import (
    BacklogCandidate,
    DiscoveryBacklog,
    DiscoverySignal,
)
from hive_mind_os.outcome_graph import OutcomeWorkPackage, compile_outcome_graph
from hive_mind_os.pr_feedback import FeedbackObservation
from hive_mind_os.repository_profile import (
    CapabilityGrant,
    HostIdentity,
    ProfileCapability,
    RepositoryProfile,
)
from hive_mind_os.scoped_learning import LearningScope
from hive_mind_os.whole_os_composition import (
    BacklogDiscoveryAdapter,
    BoundedBuilderAdapter,
    DeliveryPolicy,
    DurableLearningRecorder,
    WholeOSCompositionHost,
)
from hive_mind_os.whole_os_qualification import (
    CapabilityDeclaration,
    CompositionManifest,
)
from hive_mind_os.whole_os_service import (
    PackageStatus,
    WholeOSService,
    WholeOSServiceConfig,
)

D = "sha256:" + "a" * 64
TREE = "sha256:" + "b" * 64
COMMIT = "c" * 40
TARGET = "https://example.test/owner/repository"


class _Transport:
    def __init__(self) -> None:
        self.pushes = 0
        self.prs = 0

    def push(self, branch, commit):
        self.pushes += 1
        return commit

    def find_or_create_draft(self, branch, base, title, body):
        self.prs += 1
        return "pr-1"


class _Feedback:
    def observations(self, delivery, package):
        return (
            FeedbackObservation(
                "forge",
                delivery.pr_id,
                delivery.branch_head,
                "event-1",
                "checks-bot",
                1,
                "all checks passed",
                canonical_digest({"package": package.package_id, "status": "passed"}),
                ("feedback-receipt",),
            ),
        )


class _Curator:
    curator_id = "curator-agent"

    def assess(self, candidate, payload):
        digest = convergence_candidate_digest(candidate)
        return TerminalAssessment(
            VerificationResult(True, ("independent-terminal-check",), "accepted"),
            TerminalEvidence(
                digest,
                "builder-agent",
                self.curator_id,
                (f"review:{digest}",),
                (f"aggregate:{digest}",),
                (f"verification:{digest}",),
            ),
        )


class WholeOSCompositionTests(unittest.TestCase):
    @staticmethod
    def _descriptor(tenant="tenant", repository="repository"):
        return MissionBindingDescriptor(
            "configuration",
            D,
            tenant,
            repository,
            "v1",
            (("local", "v1"),),
            ("provider",),
            "authority",
            D,
            "state",
        )

    def _profile(
        self,
        root: Path,
        *,
        tenant="tenant",
        repository_id="repository",
        target=TARGET,
        capabilities=None,
    ):
        repository = root / "target"
        repository.mkdir()
        (repository / "app.py").write_text("print('before')\n", encoding="utf-8")
        grants = capabilities or (
            ProfileCapability.LOCAL_BUILD,
            ProfileCapability.CODE_PR,
        )
        profile = RepositoryProfile(
            "configured-profile",
            HostIdentity(tenant, repository_id, "host-issuer", D),
            str(repository),
            str(root / "workspace"),
            str(root / "profile-state"),
            str(root / "cache"),
            tuple(
                CapabilityGrant(capability, f"grant-{index}", D)
                for index, capability in enumerate(grants, start=1)
            ),
            (),
            (),
            (target,),
            "public",
            "registry-handle",
            1,
        )
        return profile, repository

    @staticmethod
    def _manifest(
        profile_id="external-python", *, tenant="tenant", repository="repository"
    ):
        profiles = []
        for item in (
            "self-python",
            "external-python",
            "node-typescript",
            "go",
            "rust",
            "roblox",
        ):
            if item == "roblox":
                profiles.append(
                    CapabilityDeclaration(
                        item,
                        "luau",
                        "studio-engine-and-device",
                        False,
                        False,
                        incomplete_reason="runtime evidence not configured",
                    )
                )
            elif item == "rust":
                profiles.append(
                    CapabilityDeclaration(item, "rust", "compile-only", False, True)
                )
            else:
                profiles.append(
                    CapabilityDeclaration(item, item, "test-execution", True, True)
                )
        # profile_id is selected by the host, while the manifest always declares
        # every N28 profile. Keeping it as an argument makes test intent explicit.
        assert profile_id in {item.profile_id for item in profiles}
        return CompositionManifest(
            D,
            WholeOSCompositionTests._descriptor(tenant, repository).digest,
            tuple(profiles),
            {
                "builder": D,
                "delivery": D,
                "discovery": D,
                "learning": D,
                "qualification": D,
                "tournament-adapters": D,
                "verification-adapters": D,
            },
            "refuse-ambiguous",
            False,
        )

    @staticmethod
    def _discovery(tenant="tenant", repository="repository"):
        backlog = DiscoveryBacklog()
        backlog.ingest(
            DiscoverySignal(
                tenant,
                repository,
                "a" * 40,
                "owned-test-signal",
                ("discovery-evidence",),
                D,
                1.0,
            )
        )
        backlog.add(
            BacklogCandidate(
                "goal",
                ("the fixture output should change",),
                10,
                "external app prints after",
                1,
                0.1,
                dissent=("no-change would retain the old output",),
            )
        )
        return BacklogDiscoveryAdapter(
            backlog, evidence_refs=("discovery-evidence",), court_receipt=D
        )

    @staticmethod
    def _policy(*, target=TARGET, runtime_required=False):
        return DeliveryPolicy(
            target,
            "main",
            "codex/mission",
            "delivery-grant",
            D,
            D,
            D,
            "independent-evaluator",
            LearningScope.TARGET_APP,
            learning_authorization_digest=D,
            roblox_runtime_required=runtime_required,
        )

    def _host(
        self,
        root,
        profile,
        repository,
        transport,
        *,
        profile_id="external-python",
        runtime_required=False,
        delivery=None,
    ):
        tenant = profile.identity.tenant_id
        repository_id = profile.identity.repository_id
        target = profile.external_destinations[0]

        def build(session):
            session.record_tool("edit")
            (repository / "app.py").write_text(
                f"print('{repository_id}')\n", encoding="utf-8"
            )
            return BuilderSessionResult(
                BuilderDisposition.READY_FOR_VERIFICATION,
                COMMIT,
                ("app.py",),
                ("builder-check",),
                evidence_refs=("builder-receipt",),
            )

        return WholeOSCompositionHost(
            state_directory=root / "c",
            manifest=self._manifest(
                profile_id, tenant=tenant, repository=repository_id
            ),
            profile_id=profile_id,
            repository_profile=profile,
            discovery=self._discovery(tenant, repository_id),
            builder=BoundedBuilderAdapter(build, candidate_tree=lambda _: TREE),
            qualifier=CandidateQualifier(lambda _: 1),
            delivery=delivery
            or DeliveryBroker(
                transport,
                grants={
                    "delivery-grant": DeliveryGrant(
                        "delivery-grant",
                        tenant,
                        target,
                        "main",
                        "codex/mission/",
                        (ArtifactKind.APPLICATION,),
                    )
                },
                state_path=root / "delivery.json",
            ),
            delivery_policy=self._policy(
                target=target, runtime_required=runtime_required
            ),
            feedback_source=_Feedback(),
            learning=DurableLearningRecorder(root / "l"),
            curator=_Curator(),
            producer_id="builder-agent",
        )

    @staticmethod
    def _service(root, host):
        tenant = host.repository_profile.identity.tenant_id
        repository_id = host.repository_profile.identity.repository_id
        descriptor = WholeOSCompositionTests._descriptor(tenant, repository_id)
        provider = ConfiguredMissionBindingsProvider(
            descriptor, lambda descriptor, package, runtime: ("runtime", "delivery")
        )
        package = OutcomeWorkPackage(
            "A",
            ("R1",),
            allowed_paths=("app.py",),
            acceptance_ids=("unit",),
        )
        graph = compile_outcome_graph(
            (package,), base_snapshot="a" * 40, court_receipt=D
        )
        service = WholeOSService(
            WholeOSServiceConfig(
                "campaign", tenant, repository_id, root / "s", descriptor, graph
            ),
            provider,
            host,
        )
        return service, package

    def test_full_composed_mission_delivers_observes_and_routes_learning(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile, repository = self._profile(root)
            transport = _Transport()
            host = self._host(root, profile, repository, transport)
            service, package = self._service(root, host)
            payload = service._payload(package)
            try:
                result = service.run_to_completion()
                self.assertEqual(result.status, "complete")
                self.assertEqual(result.completed_packages, ("A",))
                self.assertIsNotNone(result.last_result)
                assert result.last_result is not None
                self.assertEqual(result.last_result.status, PackageStatus.COMPLETED)
                self.assertEqual(transport.pushes, 1)
                self.assertEqual(transport.prs, 1)
                self.assertEqual(len(tuple((root / "l").glob("*.json"))), 1)

                replay = host.execute_package(package, ("runtime", "delivery"), payload)
                self.assertEqual(replay, result.last_result)
                self.assertEqual(transport.pushes, 1)
            finally:
                service.close()

            completed = subprocess.run(
                [sys.executable, str(repository / "app.py")],
                cwd=repository,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(completed.stdout.strip(), "repository")
            self.assertNotIn("hive_mind_os", (repository / "app.py").read_text())

    def test_cross_tenant_profile_fails_before_builder_or_delivery(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile, repository = self._profile(root)
            transport = _Transport()
            host = self._host(root, profile, repository, transport)
            service, package = self._service(root, host)
            payload = service._payload(package)
            payload["tenant_id"] = "another-tenant"
            try:
                result = host.execute_package(package, ("runtime", "delivery"), payload)
                self.assertEqual(result.status, PackageStatus.BLOCKED_AUTHORITY)
                self.assertIn("profile", result.message)
                self.assertEqual(transport.pushes, 0)
                self.assertEqual(
                    (repository / "app.py").read_text(), "print('before')\n"
                )
            finally:
                service.close()

    def test_roblox_runtime_blocks_only_runtime_required_package(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile, repository = self._profile(root)
            transport = _Transport()
            host = self._host(
                root,
                profile,
                repository,
                transport,
                profile_id="roblox",
                runtime_required=True,
            )
            service, package = self._service(root, host)
            try:
                result = service.run_to_completion()
                self.assertEqual(result.status, "blocked")
                self.assertIsNotNone(result.last_result)
                assert result.last_result is not None
                self.assertEqual(
                    result.last_result.status, PackageStatus.BLOCKED_CAPABILITY
                )
                self.assertIn(
                    "BLOCKED_SOURCE:roblox-profile", result.last_result.message
                )
                self.assertEqual(transport.pushes, 0)
            finally:
                service.close()

    def test_retained_delivery_intent_requires_reconciliation_without_reexecution(self):
        class UncertainTransport(_Transport):
            def __init__(self):
                super().__init__()
                self.effect_observed = False

            def find_or_create_draft(self, branch, base, title, body):
                self.prs += 1
                self.effect_observed = True
                raise TimeoutError("response lost after remote effect")

            def observe(self, request):
                if not self.effect_observed:
                    return None
                return DeliveryResult(
                    DeliveryState.PUBLISHED,
                    canonical_digest(request),
                    request.candidate_commit,
                    "pr-1",
                )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile, repository = self._profile(root)
            transport = UncertainTransport()
            host = self._host(
                root,
                profile,
                repository,
                transport,
            )
            service, package = self._service(root, host)
            payload = service._payload(package)
            try:
                first = host.execute_package(package, ("runtime", "delivery"), payload)
                self.assertEqual(first.status, PackageStatus.FAILED)
                self.assertIn("RECONCILIATION_REQUIRED", first.message)

                grant = DeliveryGrant(
                    "delivery-grant",
                    "tenant",
                    TARGET,
                    "main",
                    "codex/mission/",
                    (ArtifactKind.APPLICATION,),
                )
                resumed_broker = DeliveryBroker(
                    transport,
                    grants={"delivery-grant": grant},
                    state_path=root / "delivery.json",
                )
                resumed = self._host(
                    root,
                    profile,
                    repository,
                    transport,
                    delivery=resumed_broker,
                )
                replay = resumed.execute_package(
                    package, ("runtime", "delivery"), payload
                )
                self.assertEqual(replay.status, PackageStatus.COMPLETED)
                self.assertEqual(transport.pushes, 1)
                self.assertEqual(transport.prs, 1)
            finally:
                service.close()

    def test_parallel_subjects_with_colliding_filenames_remain_isolated(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            cases = []
            for suffix, tenant, repository_id in (
                ("x", "tenant-x", "repository-x"),
                ("y", "tenant-y", "repository-y"),
            ):
                case_root = root / suffix
                case_root.mkdir()
                target = f"https://example.test/owner/{repository_id}"
                profile, repository = self._profile(
                    case_root,
                    tenant=tenant,
                    repository_id=repository_id,
                    target=target,
                )
                transport = _Transport()
                host = self._host(case_root, profile, repository, transport)
                service, _ = self._service(case_root, host)
                cases.append((service, repository, repository_id, transport))
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = tuple(
                        pool.map(lambda item: item[0].run_to_completion(), cases)
                    )
                self.assertEqual(
                    tuple(item.status for item in results), ("complete",) * 2
                )
                for service, repository, repository_id, transport in cases:
                    self.assertEqual(
                        (repository / "app.py").read_text(encoding="utf-8"),
                        f"print('{repository_id}')\n",
                    )
                    other = (
                        "repository-y"
                        if repository_id == "repository-x"
                        else "repository-x"
                    )
                    self.assertNotIn(other, (repository / "app.py").read_text())
                    self.assertEqual(transport.pushes, 1)
            finally:
                for service, _, _, _ in cases:
                    service.close()


if __name__ == "__main__":
    unittest.main()
