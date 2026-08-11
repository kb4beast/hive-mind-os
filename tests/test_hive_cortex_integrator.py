from __future__ import annotations

import unittest

from hive_mind_os.brain_kernel.integrator import (
    BuilderRemand,
    CompatibilityReport,
    ContractAdapter,
    DataLineage,
    IntegrationStatus,
    IntegrationValidationError,
    Integrator,
    VersionedContract,
)


def digest(letter: str) -> str:
    return "sha256:" + letter * 64


def provider() -> VersionedContract:
    return VersionedContract(
        "mission-result",
        1,
        "legacy-runtime",
        digest("a"),
        DataLineage("artifact:provider", (), ("evidence:provider",)),
    )


def consumer(*, sources: tuple[str, ...] = ("artifact:provider",), version: int = 2) -> VersionedContract:
    return VersionedContract(
        "mission-result",
        version,
        "canonical-runtime",
        digest("b"),
        DataLineage("artifact:consumer", sources, ("evidence:consumer",)),
    )


def adapter(
    source: VersionedContract,
    target: VersionedContract,
    *,
    preserves_lineage: bool = True,
) -> ContractAdapter:
    return ContractAdapter(
        "adapter:mission-result-v1-v2",
        source.identity,
        target.identity,
        ("evidence:adapter",),
        preserves_lineage,
    )


class HiveCortexIntegratorTests(unittest.TestCase):
    def test_contract_and_lineage_compatibility_is_deterministic(self) -> None:
        source = provider()
        target = consumer()
        first = Integrator().validate(source, target, adapter(source, target), accepted_consumer_versions=(2,))
        second = Integrator().validate(source, target, adapter(source, target), accepted_consumer_versions=(2,))
        self.assertIs(IntegrationStatus.COMPATIBLE, first.status)
        self.assertFalse(first.builder_remands)
        self.assertEqual(first.digest, second.digest)
        self.assertTrue(first.lineage_digest.startswith("sha256:"))

    def test_breaking_version_is_explicit_and_becomes_builder_remand(self) -> None:
        source = provider()
        target = consumer(version=3)
        report = Integrator().validate(source, target, adapter(source, target), accepted_consumer_versions=(2,))
        self.assertIs(IntegrationStatus.REMAND, report.status)
        self.assertIn("consumer contract version is not accepted", report.findings[0])
        self.assertEqual("BUILDER-REMAND-1", report.builder_remands[0].work_id)

    def test_lineage_gap_and_non_preserving_adapter_cannot_be_concealed(self) -> None:
        source = provider()
        target = consumer(sources=("artifact:unrelated",))
        report = Integrator().validate(
            source,
            target,
            adapter(source, target, preserves_lineage=False),
            accepted_consumer_versions=(2,),
        )
        self.assertIs(IntegrationStatus.REMAND, report.status)
        self.assertEqual(2, len(report.findings))
        self.assertTrue(all(isinstance(item, BuilderRemand) for item in report.builder_remands))
        self.assertTrue(any("consumer lineage omits" in item for item in report.findings))

    def test_wrong_adapter_binding_is_remanded_not_repaired(self) -> None:
        source = provider()
        target = consumer()
        wrong_source = VersionedContract(
            "other-contract", 1, "other-runtime", digest("c"), DataLineage("artifact:other", (), ("evidence:other",))
        )
        report = Integrator().validate(source, target, adapter(wrong_source, target), accepted_consumer_versions=(2,))
        self.assertIs(IntegrationStatus.REMAND, report.status)
        self.assertTrue(any("adapter source identity does not bind" in item for item in report.findings))

    def test_malformed_lineage_and_incompatible_report_are_rejected(self) -> None:
        with self.assertRaisesRegex(IntegrationValidationError, "cannot cite itself"):
            DataLineage("artifact:self", ("artifact:self",), ("evidence:self",))
        source = provider()
        target = consumer()
        with self.assertRaisesRegex(IntegrationValidationError, "compatible report cannot request"):
            CompatibilityReport(
                IntegrationStatus.COMPATIBLE,
                source,
                target,
                "adapter:test",
                digest("d"),
                ("compatible",),
                (BuilderRemand("BUILDER-REMAND-1", "should not exist", ("artifact:provider",)),),
            )


if __name__ == "__main__":
    unittest.main()
