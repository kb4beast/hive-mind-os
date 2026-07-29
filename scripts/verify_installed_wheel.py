from __future__ import annotations

import argparse
import hashlib
import json
from importlib.resources import files
from pathlib import Path

import hive_mind_os
from hive_mind_os.package_system.builtins import hive_core_catalog


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resource_paths(root: Path) -> tuple[Path, ...]:
    schema_root = root / "schemas"
    foundation_schema_root = root / "foundation" / "schemas"
    projection_schema_root = root / "foundation" / "projection_schemas"
    public_memory_schema_root = root / "foundation" / "public_memory_schemas"
    foundation_generated_root = root / "foundation" / "generated"
    foundation_canonical_root = root / "foundation" / "canonical"
    package_root = root / "builtin_packages" / "hive-core"
    return tuple(
        sorted(
            (
                *(path for path in schema_root.glob("*.json") if path.is_file()),
                *(
                    path
                    for path in foundation_schema_root.glob("*.json")
                    if path.is_file()
                ),
                *(
                    path
                    for path in projection_schema_root.glob("*.json")
                    if path.is_file()
                ),
                *(
                    path
                    for path in public_memory_schema_root.glob("*.json")
                    if path.is_file()
                ),
                *(
                    path
                    for path in foundation_generated_root.rglob("*.json")
                    if path.is_file()
                ),
                *(
                    path
                    for path in foundation_canonical_root.rglob("*.json")
                    if path.is_file()
                ),
                *(path for path in package_root.rglob("*") if path.is_file()),
            ),
            key=lambda path: path.relative_to(root).as_posix(),
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify an isolated hive-mind-os wheel installation."
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--installed-root", type=Path, required=True)
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    installed_root = args.installed_root.resolve()
    imported_from = Path(hive_mind_os.__file__).resolve()
    if not imported_from.is_relative_to(installed_root):
        raise RuntimeError(
            f"hive_mind_os imported from {imported_from}, not {installed_root}"
        )

    installed_package = Path(str(files("hive_mind_os"))).resolve()
    source_resources = _resource_paths(source_root)
    installed_resources = _resource_paths(installed_package)
    source_digests = {
        path.relative_to(source_root).as_posix(): _digest(path)
        for path in source_resources
    }
    installed_digests = {
        path.relative_to(installed_package).as_posix(): _digest(path)
        for path in installed_resources
    }
    if source_digests != installed_digests:
        missing = sorted(source_digests.keys() - installed_digests.keys())
        unexpected = sorted(installed_digests.keys() - source_digests.keys())
        changed = sorted(
            name
            for name in source_digests.keys() & installed_digests.keys()
            if source_digests[name] != installed_digests[name]
        )
        raise RuntimeError(
            "installed resources differ from source: "
            f"missing={missing}, unexpected={unexpected}, changed={changed}"
        )

    schema_count = sum(name.startswith("schemas/") for name in source_digests)
    package_file_count = sum(
        name.startswith("builtin_packages/hive-core/") for name in source_digests
    )
    foundation_schema_count = sum(
        name.startswith("foundation/schemas/") for name in source_digests
    )
    foundation_generated_count = sum(
        name.startswith("foundation/generated/") for name in source_digests
    )
    foundation_canonical_count = sum(
        name.startswith("foundation/canonical/") for name in source_digests
    )
    projection_schema_count = sum(
        name.startswith("foundation/projection_schemas/")
        for name in source_digests
    )
    public_memory_schema_count = sum(
        name.startswith("foundation/public_memory_schemas/")
        for name in source_digests
    )
    catalog = hive_core_catalog()
    package = catalog.package("hive-core")
    observed = {
        "schema_count": schema_count,
        "foundation_schema_count": foundation_schema_count,
        "foundation_generated_count": foundation_generated_count,
        "foundation_canonical_count": foundation_canonical_count,
        "projection_schema_count": projection_schema_count,
        "public_memory_schema_count": public_memory_schema_count,
        "package_file_count": package_file_count,
        "legacy_resource_count": schema_count + package_file_count,
        "resource_count": len(source_digests),
        "component_count": len(package.components),
        "trust_state": package.manifest.trust_state.value,
    }
    expected = {
        "schema_count": 20,
        "foundation_schema_count": 17,
        "foundation_generated_count": 9,
        "foundation_canonical_count": 8,
        "projection_schema_count": 7,
        "public_memory_schema_count": 3,
        "package_file_count": 48,
        "legacy_resource_count": 68,
        "resource_count": 112,
        "component_count": 22,
        "trust_state": "quarantined",
    }
    if observed != expected:
        raise RuntimeError(f"installed package contract mismatch: {observed!r}")

    print(
        json.dumps(
            {
                "schema_version": 1,
                "verification": "installed-wheel-resources",
                "imported_from": str(imported_from),
                **observed,
                "resource_set_digest": hashlib.sha256(
                    json.dumps(
                        installed_digests,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
