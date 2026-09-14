from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hive_mind_os.cortex.repository.mission_bindings import (
    ConfiguredMissionBindingsProvider,
    MissionBindingDescriptor,
)
from hive_mind_os.outcome_graph import OutcomeWorkPackage, compile_outcome_graph
from hive_mind_os.whole_os_bootstrap import (
    WholeOSBootstrapError,
    WholeOSHostBootstrap,
    WholeOSHostFactoryRegistration,
    WholeOSHostFactoryRegistry,
    WholeOSHostUnavailable,
    run_registered_whole_os,
)
from hive_mind_os.whole_os_service import WholeOSServiceConfig

D = "sha256:" + "a" * 64


class _Host:
    def execute_package(self, package, bindings, payload):  # pragma: no cover
        raise AssertionError("resolution must not execute the host")

    def assess_terminal_candidate(self, candidate, payload):  # pragma: no cover
        raise AssertionError("resolution must not execute the curator")


class WholeOSBootstrapTests(unittest.TestCase):
    @staticmethod
    def _config(root: Path, *, adapter_id: str = "whole-os-host"):
        descriptor = MissionBindingDescriptor(
            "configuration",
            D,
            "tenant",
            "repository",
            "v1",
            ((adapter_id, "v1"),),
            ("provider",),
            "authority",
            D,
            "state",
        )
        graph = compile_outcome_graph(
            (OutcomeWorkPackage("package", ("outcome",)),),
            base_snapshot="b" * 40,
            court_receipt=D,
        )
        return WholeOSServiceConfig(
            "campaign", "tenant", "repository", root / "state", descriptor, graph
        )

    @staticmethod
    def _registration(**changes):
        values = {
            "provider_id": "whole-os-host",
            "provider_version": "v1",
            "configuration_digest": D,
            "implementation_digest": "sha256:" + "b" * 64,
            "authority_ref": "authority",
            "evidence_refs": ("curator:whole-os-host-v1",),
            "independently_validated": True,
        }
        values.update(changes)
        return WholeOSHostFactoryRegistration(**values)

    def test_resolves_one_sealed_host_owned_factory(self):
        with TemporaryDirectory() as directory:
            config = self._config(Path(directory))
            provider = ConfiguredMissionBindingsProvider(
                config.binding_descriptor,
                lambda descriptor, payload, root: ("runtime", "delivery"),
            )
            expected = WholeOSHostBootstrap(provider, _Host())
            registry = WholeOSHostFactoryRegistry()
            registration = self._registration()
            registry.register(registration, lambda supplied: expected)

            resolved = registry.resolve(config)

            self.assertIs(resolved, expected)
            self.assertEqual(
                registry.registrations["whole-os-host"].digest,
                registration.digest,
            )
            self.assertRegex(registration.digest, r"^sha256:[0-9a-f]{64}$")

    def test_unknown_provider_is_a_typed_capability_blocker(self):
        with TemporaryDirectory() as directory:
            config = self._config(Path(directory), adapter_id="another-host")
            registry = WholeOSHostFactoryRegistry()
            registry.register(
                self._registration(),
                lambda supplied: WholeOSHostBootstrap(
                    ConfiguredMissionBindingsProvider(
                        supplied.binding_descriptor,
                        lambda descriptor, payload, root: (None, None),
                    ),
                    _Host(),
                ),
            )

            with self.assertRaises(WholeOSHostUnavailable) as raised:
                registry.resolve(config)

            self.assertEqual(raised.exception.blocker, "blocked_capability")

    def test_unvalidated_or_substituted_factory_is_rejected(self):
        with self.assertRaisesRegex(
            WholeOSBootstrapError, "independent validation"
        ):
            self._registration(independently_validated=False)

        registry = WholeOSHostFactoryRegistry()
        def factory(supplied):
            return WholeOSHostBootstrap(
                ConfiguredMissionBindingsProvider(
                    supplied.binding_descriptor,
                    lambda descriptor, payload, root: (None, None),
                ),
                _Host(),
            )

        registry.register(self._registration(), factory)
        with self.assertRaisesRegex(WholeOSBootstrapError, "already bound"):
            registry.register(
                self._registration(implementation_digest="sha256:" + "c" * 64),
                factory,
            )

    def test_factory_cannot_substitute_descriptor_bindings(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            foreign = self._config(root, adapter_id="foreign-host")
            registry = WholeOSHostFactoryRegistry()
            registry.register(
                self._registration(),
                lambda supplied: WholeOSHostBootstrap(
                    ConfiguredMissionBindingsProvider(
                        foreign.binding_descriptor,
                        lambda descriptor, payload, state: (None, None),
                    ),
                    _Host(),
                ),
            )

            with self.assertRaisesRegex(WholeOSBootstrapError, "differ"):
                registry.resolve(config)

    def test_host_owned_launcher_registers_factory_in_the_execution_process(self):
        def factory(supplied):  # pragma: no cover - CLI call is intercepted below.
            raise AssertionError("launcher test resolves no campaign")

        with patch("hive_mind_os.cli._run_whole_os", return_value=17) as run:
            result = run_registered_whole_os(
                ("start", "--config", "service.json"),
                registration=self._registration(),
                factory=factory,
            )

        self.assertEqual(result, 17)
        args = run.call_args.args[0]
        registry = run.call_args.kwargs["host_factories"]
        self.assertEqual(args.whole_os_command, "start")
        self.assertIn("whole-os-host", registry.registrations)


if __name__ == "__main__":
    unittest.main()
