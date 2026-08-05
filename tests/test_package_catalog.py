from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from hive_mind_os.reference.package_system import (
    AgentManifest,
    PackageCatalog,
    PackagePin,
    PackageValidationError,
    WorkflowManifest,
    canonical_json_bytes,
    content_digest,
    load_package,
)
from hive_mind_os.reference.package_system.builtins import (
    hive_core_catalog,
    hive_core_root,
)


def _write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _minimal_package(
    root: Path,
    package_id: str,
    *,
    component_id: str | None = None,
    requires: list[dict[str, str]] | None = None,
    replaces: list[dict[str, str]] | None = None,
    rollback_to: dict[str, str] | None = None,
    license_status: str = "verified",
    trust_state: str = "trusted",
) -> tuple[Path, str]:
    package_root = root / package_id
    component_id = component_id or f"agent.{package_id}"
    agent_path = package_root / "agent.json"
    prompt_path = package_root / "prompt.json"
    _write_json(
        agent_path,
        {
            "schema_version": 1,
            "component_id": component_id,
            "role_binding": "builder",
            "mission": f"Build from {package_id}.",
            "required_outputs": ["implementation"],
            "requested_capabilities": ["read_repository"],
            "quality_gates": ["evidence exists"],
            "prompt_path": "prompt.json",
            "skill_ids": [],
            "tool_ids": [],
        },
    )
    _write_json(prompt_path, {"instructions": f"Inert prompt for {package_id}."})
    manifest = {
        "schema_version": 1,
        "package_id": package_id,
        "version": "1.0.0",
        "license": "MIT",
        "license_status": license_status,
        "trust_state": trust_state,
        "source_refs": ["test:fixture"],
        "court_case_refs": ["court:test"],
        "components": [
            {
                "component_id": component_id,
                "kind": "agent",
                "manifest_path": "agent.json",
            }
        ],
        "files": [
            {
                "path": "agent.json",
                "digest": content_digest(agent_path.read_bytes()),
                "media_type": "application/json",
            },
            {
                "path": "prompt.json",
                "digest": content_digest(prompt_path.read_bytes()),
                "media_type": "application/json",
            },
        ],
        "requires": requires or [],
        "replaces": replaces or [],
        "rollback_to": rollback_to,
    }
    _write_json(package_root / "package.json", manifest)
    return package_root, content_digest(canonical_json_bytes(manifest))


class PackageCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.tmp_path = Path(temporary_directory.name)

    def test_hive_core_is_inert_content_addressed_and_deterministic(self) -> None:
        catalog = hive_core_catalog()
        snapshot = catalog.snapshot()
        assert [item.package_id for item in snapshot.packages] == ["hive-core"]
        assert snapshot == hive_core_catalog().snapshot()
        assert len(catalog.package("hive-core").components) == 22
        builder = catalog.component("agent.builder")
        lifecycle = catalog.component("workflow.default-lifecycle")
        assert isinstance(builder, AgentManifest)
        assert builder.role_binding == "builder"
        assert isinstance(lifecycle, WorkflowManifest)
        assert lifecycle.initial_state == "start"
        assert not hasattr(catalog, "install")
        assert not hasattr(catalog, "activate")

    def test_package_requires_an_explicit_absolute_root(self) -> None:
        with self.assertRaisesRegex(PackageValidationError, "explicit absolute"):
            load_package(Path("relative-package"))
        missing = self.tmp_path / "missing"
        with self.assertRaisesRegex(PackageValidationError, "existing directory"):
            load_package(missing)

    def test_digest_mismatch_and_unlisted_files_fail_closed(self) -> None:
        copied = self.tmp_path / "hive-core"
        shutil.copytree(hive_core_root(), copied)
        (copied / "agents" / "builder.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(PackageValidationError, "digest mismatch"):
            load_package(copied)

        shutil.rmtree(copied)
        shutil.copytree(hive_core_root(), copied)
        _write_json(copied / "undeclared.json", {"authority": "invented"})
        with self.assertRaisesRegex(PackageValidationError, "unlisted"):
            load_package(copied)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        package_root, _ = _minimal_package(self.tmp_path, "duplicate-json")
        (package_root / "package.json").write_text(
            '{"schema_version":1,"schema_version":1}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(PackageValidationError, "duplicate JSON key"):
            load_package(package_root)

    def test_symlinks_are_rejected_when_platform_allows_them(self) -> None:
        package_root, _ = _minimal_package(self.tmp_path, "symlinked")
        link = package_root / "linked.json"
        try:
            os.symlink(package_root / "prompt.json", link)
        except (NotImplementedError, OSError):
            self.skipTest("this environment cannot create symlinks")
        with self.assertRaisesRegex(PackageValidationError, "symlink"):
            load_package(package_root)

    def test_exact_dependency_pins_are_verified_and_ordered(self) -> None:
        dependency_root, dependency_digest = _minimal_package(
            self.tmp_path, "dependency", component_id="agent.dependency"
        )
        required = {
            "package_id": "dependency",
            "version": "1.0.0",
            "manifest_digest": dependency_digest,
        }
        consumer_root, _ = _minimal_package(
            self.tmp_path,
            "consumer",
            component_id="agent.consumer",
            requires=[required],
        )
        catalog = PackageCatalog.from_roots((consumer_root, dependency_root))
        assert [item.manifest.package_id for item in catalog.dependency_order()] == [
            "dependency",
            "consumer",
        ]

        incorrect = dict(required, manifest_digest="sha256:" + "0" * 64)
        bad_root, _ = _minimal_package(
            self.tmp_path,
            "bad-consumer",
            component_id="agent.bad-consumer",
            requires=[incorrect],
        )
        with self.assertRaisesRegex(PackageValidationError, "digest mismatch"):
            PackageCatalog.from_roots((dependency_root, bad_root))

    def test_dependency_cycles_and_nonexact_versions_are_rejected(self) -> None:
        placeholder = "sha256:" + "0" * 64
        first_root, first_digest = _minimal_package(
            self.tmp_path,
            "first",
            requires=[
                {
                    "package_id": "second",
                    "version": "1.0.0",
                    "manifest_digest": placeholder,
                }
            ],
        )
        second_root, second_digest = _minimal_package(
            self.tmp_path,
            "second",
            requires=[
                {
                    "package_id": "first",
                    "version": "1.0.0",
                    "manifest_digest": first_digest,
                }
            ],
        )
        first_manifest = json.loads((first_root / "package.json").read_text())
        first_manifest["requires"][0]["manifest_digest"] = second_digest
        _write_json(first_root / "package.json", first_manifest)
        with self.assertRaisesRegex(PackageValidationError, "cycle"):
            PackageCatalog.from_roots((first_root, second_root))

        with self.assertRaisesRegex(ValueError, "exact semantic version"):
            PackagePin("dependency", ">=1.0", placeholder)

    def test_duplicate_component_ids_across_packages_are_rejected(self) -> None:
        first_root, _ = _minimal_package(
            self.tmp_path, "package-one", component_id="agent.shared"
        )
        second_root, _ = _minimal_package(
            self.tmp_path, "package-two", component_id="agent.shared"
        )
        with self.assertRaisesRegex(PackageValidationError, "duplicate component"):
            PackageCatalog.from_roots((first_root, second_root))

    def test_provenance_license_and_trust_fail_closed(self) -> None:
        pending_root, _ = _minimal_package(
            self.tmp_path,
            "pending-trusted",
            license_status="pending",
            trust_state="trusted",
        )
        with self.assertRaisesRegex(PackageValidationError, "must remain quarantined"):
            load_package(pending_root)

        quarantined_root, _ = _minimal_package(
            self.tmp_path,
            "pending-quarantined",
            license_status="pending",
            trust_state="quarantined",
        )
        quarantined = load_package(quarantined_root)
        assert quarantined.manifest.trust_state.value == "quarantined"

        manifest_path = quarantined_root / "package.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["source_refs"] = []
        _write_json(manifest_path, manifest)
        with self.assertRaisesRegex(
            PackageValidationError, "preserve at least one source"
        ):
            load_package(quarantined_root)

    def test_unresolved_replacement_and_rollback_pins_require_quarantine(self) -> None:
        unresolved = {
            "package_id": "prior-package",
            "version": "1.0.0",
            "manifest_digest": "sha256:" + "0" * 64,
        }
        trusted_root, _ = _minimal_package(
            self.tmp_path,
            "trusted-replacer",
            replaces=[unresolved],
        )
        with self.assertRaisesRegex(PackageValidationError, "must remain quarantined"):
            PackageCatalog.from_roots((trusted_root,))

        quarantined_root, _ = _minimal_package(
            self.tmp_path,
            "quarantined-replacer",
            replaces=[unresolved],
            trust_state="quarantined",
        )
        catalog = PackageCatalog.from_roots((quarantined_root,))
        assert catalog.package("quarantined-replacer").manifest.replaces

        self_pin = {
            "package_id": "rollback-candidate",
            "version": "0.9.0",
            "manifest_digest": "sha256:" + "1" * 64,
        }
        rollback_root, _ = _minimal_package(
            self.tmp_path,
            "rollback-candidate",
            rollback_to=self_pin,
        )
        with self.assertRaisesRegex(PackageValidationError, "must remain quarantined"):
            PackageCatalog.from_roots((rollback_root,))
