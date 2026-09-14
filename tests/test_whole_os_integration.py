import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hive_mind_os.cortex.repository.mission_bindings import (
    ConfiguredMissionBindingsProvider,
    MissionBindingDescriptor,
)
from hive_mind_os.outcome_graph import OutcomeWorkPackage, compile_outcome_graph
from hive_mind_os.whole_os_service import (
    PackageExecutionResult,
    PackageStatus,
    WholeOSService,
    WholeOSServiceConfig,
)

D = "sha256:" + "a" * 64


class FakeHost:
    def execute_package(self, package, bindings, payload):
        return PackageExecutionResult(
            package.package_id, PackageStatus.COMPLETED, D, (D,)
        )


class WholeOSIntegrationTests(unittest.TestCase):
    def test_dependency_order_survives_durable_queue(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            descriptor = MissionBindingDescriptor(
                "configuration",
                D,
                "tenant",
                "repository",
                "v1",
                (("local", "v1"),),
                ("provider",),
                "authority",
                D,
                "state",
            )
            provider = ConfiguredMissionBindingsProvider(
                descriptor, lambda d, p, r: ("runtime", "delivery")
            )
            graph = compile_outcome_graph(
                (
                    OutcomeWorkPackage("N00", ("R01",), allowed_paths=("src",)),
                    OutcomeWorkPackage(
                        "N01", ("R02",), dependencies=("N00",), allowed_paths=("docs",)
                    ),
                ),
                base_snapshot="a" * 40,
                maximum_concurrent=2,
                court_receipt=D,
            )
            service = WholeOSService(
                WholeOSServiceConfig(
                    "campaign",
                    "tenant",
                    "repository",
                    root,
                    descriptor,
                    graph,
                ),
                provider,
                FakeHost(),
            )
            self.assertEqual(service.run_once().completed_packages, ("N00",))
            self.assertEqual(service.run_once().status, "complete")
            service.close()


if __name__ == "__main__":
    unittest.main()
