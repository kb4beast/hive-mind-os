from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

OUTPUT_PATH = Path(
    "evidence/phase3/phase3_obsidian_vault_refresh_inventory.json"
)
RUN_ROOT = Path("evidence/phase3/obsidian-vault-refresh")
FAILED_RUNS = (
    "20260729T201251Z-windows-obsidian-1.12.7",
    "20260729T202104Z-windows-obsidian-1.12.7",
)
SUPERSEDED_RUNS = (
    "20260729T203709Z-windows-obsidian-1.12.7",
)
PASSING_RUN = "20260729T210732Z-windows-obsidian-1.12.7"
TARGET_PATHS = (
    "hive-mind/generated/README.md",
    "hive-mind/generated-cognitive/HOME.md",
    "hive-mind/generated-cognitive-views/bases/agent-records.base",
    "hive-mind/generated-cognitive-views/bases/ideas.base",
    "hive-mind/generated-cognitive-views/bases/released-war-room.base",
    "hive-mind/generated-cognitive-views/bases/telemetry-metadata.base",
    "hive-mind/generated-cognitive-views/canvases/war-room.canvas",
    "hive-mind/generated-cognitive-views/manifest.json",
)
VISIBLE_CASES = {
    "item1-open-note-replacement": {
        "target": "hive-mind/generated/README.md",
        "before": "safe_public_record_count=6",
        "after": "safe_public_record_count=7",
    },
    "item3-open-home-replacement": {
        "target": "hive-mind/generated-cognitive/HOME.md",
        "before": "evidence_count=2,court_count=1,total_count=7",
        "after": "evidence_count=2,court_count=2,total_count=8",
    },
    "item4-open-base-recomputation": {
        "target": "hive-mind/generated-cognitive-views/bases/ideas.base",
        "before": "ideas=1",
        "after": "ideas=2",
    },
}
PROHIBITED_ACTIONS = {
    "manual_refresh",
    "application_restart",
    "cache_rebuild",
    "community_plugin",
    "sync",
    "importer",
    "external_watcher",
    "network_git_action",
}
SCREENSHOT_NAMES = (
    "01-item1-before.jpg",
    "02-item1-after.jpg",
    "03-item3-before.jpg",
    "04-item3-after.jpg",
    "05-item4-base-before.jpg",
    "06-item4-base-after.jpg",
    "07-item4-canvas-render.jpg",
)
MAX_RUN_RECEIPT_BYTES = 128 * 1024
MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024
MAX_TARGET_BYTES = 1024 * 1024
FIXTURE_KEYS = {
    "vault_kind",
    "vault_head",
    "source_repository_head",
    "tenant_id",
    "repository_id",
    "protected_state_outside_vault",
    "safe_public_synthetic_records_only",
    "source_repository_worktree_opened",
    "source_repository_obsidian_directory_absent",
    "clone_obsidian_directory_present",
    "global_profile_vault_registration_side_effect",
    "fixture_registration_digest",
    "fixture_registration",
}
SANITIZED_REGISTRATION_KEYS = {
    "schema_version",
    "subject_commit",
    "separate_clone",
    "origin_matches_source_repository",
    "tracked_file_count",
    "no_hardlink_file_count",
    "git_object_file_count",
    "no_hardlink_git_object_count",
    "shared_git_object_alternate",
    "local_paths_omitted",
}
RUN_KEYS = {
    "schema_version",
    "run_id",
    "subject_commit",
    "verdict",
    "test_window_seconds",
    "runtime",
    "fixture",
    "cases",
    "final_projection_digest",
    "final_targets",
    "final_target_metadata",
    "screenshots",
    "prohibited_actions",
    "claim_limits",
}
RUNTIME_KEYS = {
    "application",
    "version",
    "executable_sha256",
    "asar_sha256",
    "authenticode_status",
    "signer",
    "signer_thumbprint",
    "os",
    "process_id",
    "window_handle",
    "restarted_during_run",
}
VISIBLE_CASE_KEYS = {
    "case_id",
    "target",
    "before_observed_at",
    "projector_completed_at",
    "after_observed_at",
    "latency_seconds",
    "before",
    "after",
    "verdict",
}
CANVAS_CASE_KEYS = {
    "case_id",
    "target",
    "observed_at",
    "visible_disclosure",
    "embedded_ideas",
    "verdict",
}
INTEGRITY_CASE_KEYS = {
    "case_id",
    "canvas_unloaded_at",
    "stability_interval_seconds",
    "final_checked_at",
    "actual_stability_seconds",
    "item4_check_status",
    "manifest_digest",
    "tree_digest",
    "tree_digest_role",
    "conflict_paths",
    "baseline_targets",
    "verdict",
}
CLAIM_LIMITS = (
    "The evidence covers Obsidian Desktop 1.12.7 on the recorded Windows build only.",
    (
        "The test used an existing Obsidian process and profile; "
        "clean-profile isolation is not proved."
    ),
    "Opening the clone registered a vault in the global Obsidian profile.",
    (
        "Fixture authority and curator labels are synthetic test inputs, "
        "not production release authority."
    ),
    (
        "No remote Git, Sync, multi-device, production-readiness, usefulness, "
        "or superiority claim is made."
    ),
)


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_json(value: Any) -> str:
    return _digest_bytes(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _jpeg_dimensions(value: bytes) -> tuple[int, int]:
    if len(value) < 4 or value[:2] != b"\xff\xd8" or value[-2:] != b"\xff\xd9":
        raise ValueError("invalid JPEG boundary")
    index = 2
    start_of_frame = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while index + 4 <= len(value):
        if value[index] != 0xFF:
            index += 1
            continue
        while index < len(value) and value[index] == 0xFF:
            index += 1
        if index >= len(value):
            break
        marker = value[index]
        index += 1
        if marker in {0x01, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(value):
            break
        segment_length = int.from_bytes(value[index:index + 2], "big")
        if segment_length < 2 or index + segment_length > len(value):
            break
        if marker in start_of_frame and segment_length >= 7:
            height = int.from_bytes(value[index + 3:index + 5], "big")
            width = int.from_bytes(value[index + 5:index + 7], "big")
            if width and height:
                return width, height
        if marker == 0xDA:
            break
        index += segment_length
    raise ValueError("JPEG dimensions are unavailable")


def _bounded_file(root: Path, path: Path, maximum_bytes: int) -> bytes:
    resolved_root = root.resolve(strict=True)
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"evidence path escapes run directory: {path}")
    cursor = root
    for component in path.relative_to(root).parts:
        cursor /= component
        metadata = cursor.lstat()
        if stat.S_ISLNK(metadata.st_mode) or (
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise ValueError(f"linked evidence path is prohibited: {cursor}")
    with path.open("rb") as handle:
        metadata = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size > maximum_bytes
        ):
            raise ValueError(f"invalid bounded evidence file: {path}")
        value = handle.read(maximum_bytes + 1)
    if len(value) != metadata.st_size:
        raise ValueError(f"evidence file changed while reading: {path}")
    return value


def _load_run(repository: Path, run_id: str) -> dict[str, Any]:
    evidence_root = (repository / RUN_ROOT).resolve(strict=True)
    run_dir = repository / RUN_ROOT / run_id
    run_metadata = run_dir.lstat()
    if (
        not stat.S_ISDIR(run_metadata.st_mode)
        or stat.S_ISLNK(run_metadata.st_mode)
        or (
            getattr(run_metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
        or run_dir.resolve(strict=True).parent != evidence_root
    ):
        raise ValueError(f"invalid Obsidian run directory: {run_id}")
    receipt_bytes = _bounded_file(
        run_dir, run_dir / "run.json", MAX_RUN_RECEIPT_BYTES
    )
    run = json.loads(receipt_bytes.decode("utf-8"))
    if (
        run.get("schema_version") != "hive-obsidian-refresh-run/v1"
        or run.get("run_id") != run_id
    ):
        raise ValueError(f"invalid Obsidian run identity: {run_id}")
    screenshots = run.get("screenshots")
    if (
        not isinstance(screenshots, dict)
        or tuple(screenshots) != SCREENSHOT_NAMES
    ):
        raise ValueError(f"invalid Obsidian screenshot inventory: {run_id}")
    for name, expected in screenshots.items():
        path = run_dir / name
        screenshot = _bounded_file(run_dir, path, MAX_SCREENSHOT_BYTES)
        if (
            len(screenshot) < 1024
            or _digest_bytes(screenshot) != expected
        ):
            raise ValueError(f"invalid Obsidian screenshot: {run_id}/{name}")
        width, height = _jpeg_dimensions(screenshot)
        if not 640 <= width <= 3840 or not 480 <= height <= 2160:
            raise ValueError(f"invalid Obsidian screenshot size: {run_id}/{name}")
    return run


def _run_receipt_digest(repository: Path, run_id: str) -> str:
    run_dir = repository / RUN_ROOT / run_id
    return _digest_bytes(
        _bounded_file(run_dir, run_dir / "run.json", MAX_RUN_RECEIPT_BYTES)
    )


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _contains_local_path(value: Any) -> bool:
    if isinstance(value, str):
        return (
            value.startswith(("/", "\\"))
            or (
                len(value) >= 3
                and value[1] == ":"
                and value[2] in {"/", "\\"}
            )
        )
    if isinstance(value, list):
        return any(_contains_local_path(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_local_path(key) or _contains_local_path(item)
            for key, item in value.items()
        )
    return False


def _validate_passing_run(
    repository: Path, run: dict[str, Any]
) -> dict[str, Any]:
    if run.get("verdict") != "pass":
        raise ValueError("passing Obsidian run is unavailable")
    if set(run) != RUN_KEYS or _contains_local_path(run):
        raise ValueError("passing Obsidian run envelope is invalid")
    subject_commit = run.get("subject_commit")
    if (
        not isinstance(subject_commit, str)
        or len(subject_commit) != 40
        or any(character not in "0123456789abcdef" for character in subject_commit)
    ):
        raise ValueError("invalid Obsidian subject commit")
    runtime = run.get("runtime", {})
    expected_runtime = {
        "application": "Obsidian Desktop",
        "version": "1.12.7",
        "executable_sha256": (
            "fb6b2133c21ef7051c41f66d5c06f0e69162febfbb3f838a3556d54d13304b69"
        ),
        "asar_sha256": (
            "2b2483b2e1246772e0d25367ec055cbc5047ea2f0091b667c35656678f86d712"
        ),
        "authenticode_status": "Valid",
        "signer": "Dynalist Inc",
        "signer_thumbprint": "69b4a9ab8355237555686ca7cd67f6763b0f7eaf",
        "os": "Microsoft Windows 11 Home 10.0.26200 x64",
        "restarted_during_run": False,
    }
    if (
        set(runtime) != RUNTIME_KEYS
        or any(runtime.get(key) != value for key, value in expected_runtime.items())
        or not isinstance(runtime.get("process_id"), int)
        or isinstance(runtime.get("process_id"), bool)
        or runtime["process_id"] <= 0
        or not isinstance(runtime.get("window_handle"), int)
        or isinstance(runtime.get("window_handle"), bool)
        or runtime["window_handle"] <= 0
    ):
        raise ValueError("Obsidian runtime pin mismatch")
    if run.get("test_window_seconds") != 15:
        raise ValueError("Obsidian visible-refresh deadline mismatch")
    run_dir = repository / RUN_ROOT / run["run_id"]
    fixture = run.get("fixture", {})
    registration_bytes = _bounded_file(
        run_dir,
        run_dir / "fixture-registration.json",
        MAX_RUN_RECEIPT_BYTES,
    )
    registration = json.loads(registration_bytes.decode("utf-8"))
    if (
        set(fixture) != FIXTURE_KEYS
        or not isinstance(registration, dict)
        or set(registration) != SANITIZED_REGISTRATION_KEYS
        or _contains_local_path(registration)
        or fixture.get("vault_kind")
        != (
            "disposable Git clone with non-hardlinked tracked files "
            "and common Git objects"
        )
        or fixture.get("vault_head") != subject_commit
        or fixture.get("source_repository_head") != subject_commit
        or fixture.get("tenant_id") != "tenant:phase3-item5-refresh"
        or fixture.get("repository_id") != "repository:phase3-item5-refresh"
        or fixture.get("protected_state_outside_vault") is not True
        or fixture.get("safe_public_synthetic_records_only") is not True
        or fixture.get("source_repository_worktree_opened") is not False
        or fixture.get("source_repository_obsidian_directory_absent") is not True
        or fixture.get("clone_obsidian_directory_present") is not True
        or fixture.get("global_profile_vault_registration_side_effect") is not True
        or fixture.get("fixture_registration_digest")
        != _digest_bytes(registration_bytes)
        or fixture.get("fixture_registration") != registration
        or registration.get("subject_commit") != subject_commit
        or registration.get("separate_clone") is not True
        or registration.get("origin_matches_source_repository") is not True
        or registration.get("shared_git_object_alternate") is not False
        or registration.get("local_paths_omitted") is not True
        or registration.get("tracked_file_count", 0) <= 0
        or registration.get("no_hardlink_file_count")
        != registration.get("tracked_file_count")
        or registration.get("git_object_file_count", 0) <= 0
        or registration.get("no_hardlink_git_object_count")
        != registration.get("git_object_file_count")
    ):
        raise ValueError("Obsidian fixture boundary receipt is invalid")
    cases = run.get("cases")
    expected_ids = (
        *VISIBLE_CASES,
        "item4-canvas-render",
        "item4-generated-byte-integrity",
    )
    if (
        not isinstance(cases, list)
        or tuple(case.get("case_id") for case in cases) != expected_ids
        or any(case.get("verdict") != "pass" for case in cases)
    ):
        raise ValueError("Obsidian passing case set is incomplete")
    for case in cases[:3]:
        expectation = VISIBLE_CASES[case["case_id"]]
        before = _timestamp(case.get("before_observed_at"))
        completed = _timestamp(case.get("projector_completed_at"))
        after = _timestamp(case.get("after_observed_at"))
        latency = case.get("latency_seconds")
        if (
            not isinstance(latency, (int, float))
            or isinstance(latency, bool)
            or not math.isfinite(latency)
            or not before < completed < after
            or abs(latency - (after - completed).total_seconds()) > 0.001
            or latency > 15
            or set(case) != VISIBLE_CASE_KEYS
            or case.get("target") != expectation["target"]
            or case.get("before") != expectation["before"]
            or case.get("after") != expectation["after"]
        ):
            raise ValueError(f"invalid Obsidian latency case: {case['case_id']}")
    if not (
        _timestamp(cases[0]["after_observed_at"])
        <= _timestamp(cases[1]["before_observed_at"])
        and _timestamp(cases[1]["after_observed_at"])
        <= _timestamp(cases[2]["before_observed_at"])
        and _timestamp(cases[2]["after_observed_at"])
        <= _timestamp(cases[3]["observed_at"])
    ):
        raise ValueError("Obsidian case chronology is invalid")
    canvas = cases[3]
    integrity = cases[4]
    if (
        set(canvas) != CANVAS_CASE_KEYS
        or set(integrity) != INTEGRITY_CASE_KEYS
        or canvas.get("target")
        != "hive-mind/generated-cognitive-views/canvases/war-room.canvas"
        or canvas.get("visible_disclosure") != "Released cognitive views"
        or canvas.get("embedded_ideas") != "2 results"
    ):
        raise ValueError("Obsidian Canvas observation is invalid")
    observed = _timestamp(canvas.get("observed_at"))
    unloaded = _timestamp(integrity.get("canvas_unloaded_at"))
    checked = _timestamp(integrity.get("final_checked_at"))
    actual_stability = integrity.get("actual_stability_seconds")
    if (
        not observed <= unloaded < checked
        or integrity.get("stability_interval_seconds") != 300
        or (checked - unloaded).total_seconds() < 300
        or not isinstance(actual_stability, (int, float))
        or isinstance(actual_stability, bool)
        or not math.isfinite(actual_stability)
        or abs(actual_stability - (checked - unloaded).total_seconds()) > 0.001
        or integrity.get("item4_check_status") != "unchanged"
        or integrity.get("conflict_paths") != []
    ):
        raise ValueError("Obsidian delayed generated-byte integrity failed")
    final_targets = run.get("final_targets")
    final_metadata = run.get("final_target_metadata")
    if (
        not isinstance(final_targets, dict)
        or tuple(final_targets) != TARGET_PATHS
        or integrity.get("baseline_targets") != final_targets
        or not isinstance(final_metadata, dict)
        or tuple(final_metadata) != TARGET_PATHS
    ):
        raise ValueError("Obsidian target hash set is incomplete")
    for relative, expected in final_targets.items():
        snapshot = run_dir / "targets" / relative
        snapshot_bytes = _bounded_file(run_dir, snapshot, MAX_TARGET_BYTES)
        if _digest_bytes(snapshot_bytes) != expected:
            raise ValueError(f"invalid preserved target: {relative}")
        if (
            set(final_metadata[relative]) != {"length_bytes", "last_write_at"}
            or final_metadata[relative].get("length_bytes") != len(snapshot_bytes)
            or _timestamp(final_metadata[relative].get("last_write_at"))
            > _timestamp(integrity.get("final_checked_at"))
        ):
            raise ValueError(f"invalid preserved target metadata: {relative}")
    final_projection_bytes = _bounded_file(
        run_dir,
        run_dir / "final-projection.json",
        MAX_RUN_RECEIPT_BYTES,
    )
    final_projection = json.loads(final_projection_bytes.decode("utf-8"))
    if (
        not isinstance(final_projection, dict)
        or run.get("final_projection_digest")
        != _digest_bytes(final_projection_bytes)
        or final_projection.get("local_paths_sanitized") is not True
        or _contains_local_path(final_projection)
        or final_projection.get("subject_commit") != subject_commit
        or final_projection.get("targets") != final_targets
        or final_projection.get("fixture_validation") != registration
        or final_projection.get("item1", {}).get("status") != "unchanged"
        or final_projection.get("item1", {}).get("conflict_paths") != []
        or final_projection.get("item1", {}).get("source_record_count") != 9
        or final_projection.get("item1", {}).get("projected_record_count") != 9
        or final_projection.get("item2", {}).get("status") != "unchanged"
        or final_projection.get("item2", {}).get("released_record_count") != 0
        or final_projection.get("item3", {}).get("status") != "unchanged"
        or final_projection.get("item3", {}).get("conflict_paths") != []
        or final_projection.get("item3", {}).get("source_record_count") != 9
        or final_projection.get("item3", {}).get("projected_record_count") != 9
        or final_projection.get("item3", {}).get("note_counts", {}).get("total") != 9
        or final_projection.get("item4", {}).get("status") != "unchanged"
        or final_projection.get("item4", {}).get("conflict_paths") != []
        or final_projection.get("item4", {}).get("base_count") != 4
        or final_projection.get("item4", {}).get("canvas_count") != 1
        or integrity.get("tree_digest_role")
        != "expected manifest identity; not observed-byte proof"
        or integrity.get("manifest_digest")
        != final_targets["hive-mind/generated-cognitive-views/manifest.json"]
        or integrity.get("manifest_digest")
        != final_projection.get("item4", {}).get("manifest_digest")
        or integrity.get("tree_digest")
        != final_projection.get("item4", {}).get("tree_digest")
    ):
        raise ValueError("final projector receipt is invalid")
    prohibited = run.get("prohibited_actions")
    if (
        not isinstance(prohibited, dict)
        or set(prohibited) != PROHIBITED_ACTIONS
        or any(value is not False for value in prohibited.values())
        or tuple(run.get("claim_limits", ())) != CLAIM_LIMITS
    ):
        raise ValueError("a prohibited Obsidian action participated")
    return integrity


def build_phase3_item5_inventory(repository: Path) -> dict[str, Any]:
    failed_runs = {
        run_id: _load_run(repository, run_id) for run_id in FAILED_RUNS
    }
    superseded_runs = {
        run_id: _load_run(repository, run_id) for run_id in SUPERSEDED_RUNS
    }
    passing = _load_run(repository, PASSING_RUN)
    for run_id, run in failed_runs.items():
        if run.get("verdict") != "fail" or not any(
            case.get("verdict") == "fail" for case in run.get("cases", [])
        ):
            raise ValueError(f"failed Obsidian run is not preserved: {run_id}")
    for run_id, run in superseded_runs.items():
        if (
            run.get("verdict") != "pass"
            or run.get("subject_commit") == passing.get("subject_commit")
        ):
            raise ValueError(f"superseded Obsidian run is invalid: {run_id}")
    integrity = _validate_passing_run(repository, passing)
    ignored = {
        line.strip()
        for line in (repository / ".gitignore")
        .read_text(encoding="utf-8")
        .splitlines()
    }
    if ".obsidian/" not in ignored or (repository / ".obsidian").exists():
        raise ValueError("Obsidian configuration is not confined to local ignored state")

    implementation_paths = (
        "scripts/phase3_obsidian_refresh_fixture.py",
        "scripts/phase3_obsidian_vault_refresh_inventory.py",
        "src/hive_mind_os/foundation/cognitive_views.py",
        "tests/test_phase3_cognitive_views.py",
        "tests/test_phase3_obsidian_vault_refresh.py",
    )
    prior = (
        repository
        / "evidence"
        / "phase3"
        / "phase3_cognitive_views_inventory.json"
    )
    body = {
        "schema_version": 1,
        "phase": 3,
        "phase_item": 5,
        "activation": "evidence-only-pinned-runtime-conformance",
        "subject_commit": passing["subject_commit"],
        "runtime": passing["runtime"],
        "source_pins": {
            "obsidian_help_commit": (
                "29e89022c6aeb0a9e9971b6f0c98733dbc2eb716"
            ),
            "obsidian_release": "1.12.7",
            "obsidian_help_license": "NOASSERTION",
        },
        "prior_item4_inventory_digest": _digest_bytes(prior.read_bytes()),
        "implementation": {
            path: _digest_bytes((repository / path).read_bytes())
            for path in implementation_paths
        },
        "runs": {
            run_id: {
                "receipt_digest": _run_receipt_digest(repository, run_id),
                "verdict": run["verdict"],
                "failed_cases": [
                    case["case_id"]
                    for case in run["cases"]
                    if case.get("verdict") == "fail"
                ],
            }
            for run_id, run in failed_runs.items()
        }
        | {
            run_id: {
                "receipt_digest": _run_receipt_digest(repository, run_id),
                "verdict": run["verdict"],
                "promotion_disposition": (
                    "superseded-non-promotable-production-subject"
                ),
            }
            for run_id, run in superseded_runs.items()
        }
        | {
            PASSING_RUN: {
                "receipt_digest": _run_receipt_digest(
                    repository, PASSING_RUN
                ),
                "verdict": passing["verdict"],
                "case_count": len(passing["cases"]),
                "maximum_refresh_latency_seconds": max(
                    case.get("latency_seconds", 0)
                    for case in passing["cases"]
                ),
                "item4_check_status": integrity["item4_check_status"],
            },
        },
        "claim_boundary": {
            "local_markdown_refresh": True,
            "local_cognitive_home_refresh": True,
            "local_base_recomputation": True,
            "local_canvas_render": True,
            "generated_bytes_preserved": True,
            "clean_profile_proven": False,
            "remote_git_proven": False,
            "sync_proven": False,
            "production_ready": False,
            "superiority_claimed": False,
        },
        "obsidian_configuration": {
            "gitignore_rule": ".obsidian/",
            "source_repository_state_absent": True,
            "global_profile_registration_side_effect_recorded": True,
        },
        "external_dependencies_added": 0,
        "generation_zero_activated": False,
    }
    return {**body, "inventory_digest": _digest_json(body)}


def main() -> int:
    repository = Path(__file__).parents[1]
    inventory = build_phase3_item5_inventory(repository)
    destination = repository / OUTPUT_PATH
    destination.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
