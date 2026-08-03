from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

from phase5e_to_k_inventory import _lookup, phase_specs

from hive_mind_os.foundation.canonical import digest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Phase 5E-K contracts from an isolated wheel installation."
    )
    parser.add_argument("--installed-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    installed_root = args.installed_root.resolve()
    results: list[dict[str, object]] = []
    for spec in phase_specs():
        imported_paths: list[str] = []
        for source_path in (spec.module_path, spec.contracts_path):
            module_name = source_path.removeprefix("src/").removesuffix(".py").replace("/", ".")
            module = importlib.import_module(module_name)
            if module.__file__ is None:
                raise RuntimeError(f"Phase 5{spec.item} module {module_name} has no file")
            imported_from = Path(module.__file__).resolve()
            if not imported_from.is_relative_to(installed_root):
                raise RuntimeError(
                    f"Phase 5{spec.item} imported from {imported_from}, not {installed_root}"
                )
            imported_paths.append(imported_from.relative_to(installed_root).as_posix())

        request = spec.example()
        spec.validate_request(request)
        envelope = spec.compile(request)
        spec.validate_envelope(envelope)
        if tuple(envelope["outputs"]) != spec.output_fields:
            raise RuntimeError(f"installed Phase 5{spec.item} output order drifted")
        for field in spec.output_fields:
            if envelope["output_digests"][field] != digest(envelope["outputs"][field]):
                raise RuntimeError(
                    f"installed Phase 5{spec.item} {field} digest drifted"
                )
        for path, expected in spec.boundaries:
            observed = _lookup(envelope, path)
            if observed != expected:
                raise RuntimeError(
                    f"installed Phase 5{spec.item} boundary {path} drifted: "
                    f"{observed!r} != {expected!r}"
                )
        results.append(
            {
                "phase_item": spec.item,
                "component": spec.component,
                "imported_paths": imported_paths,
                "request_digest": digest(request),
                "envelope_digest": envelope["envelope_digest"],
                "output_fields": list(spec.output_fields),
                "boundary_assertion_count": len(spec.boundaries),
                "authority_added": False,
                "release_ready": False,
            }
        )

    result = {
        "schema_version": 1,
        "verification": "phase5e-to-k-installed-wheel",
        "installed_root": str(installed_root),
        "phase_count": len(results),
        "phases": results,
        "authenticated_independence_claimed": False,
        "release_ready": False,
        "production_ready": False,
        "deployment_authorized": False,
        "promotion_authorized": False,
        "superiority_claimed": False,
    }
    print(json.dumps(result, sort_keys=True))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
