from __future__ import annotations

import hashlib
import json
import math
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
PASSING_RUN = "20260729T203709Z-windows-obsidian-1.12.7"
TARGET_PATHS = (
    "hive-mind/generated/README.md",
    "hive-mind/generated-cognitive/HOME.md",
    "hive-mind/generated-cognitive-views/bases/ideas.base",
    "hive-mind/generated-cognitive-views/canvases/war-room.canvas",
)
VISIBLE_CASES = (
    "item1-open-note-replacement",
    "item3-open-home-replacement",
    "item4-open-base-recomputation",
)
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


def _load_run(repository: Path, run_id: str) -> dict[str, Any]:
    run_dir = repository / RUN_ROOT / run_id
    receipt_bytes = (run_dir / "run.json").read_bytes()
    if len(receipt_bytes) > MAX_RUN_RECEIPT_BYTES:
        raise ValueError(f"oversized Obsidian run receipt: {run_id}")
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
        if not path.is_file():
            raise ValueError(f"invalid Obsidian screenshot: {run_id}/{name}")
        screenshot = path.read_bytes()
        if (
            len(screenshot) > MAX_SCREENSHOT_BYTES
            or _digest_bytes(screenshot) != expected
        ):
            raise ValueError(f"invalid Obsidian screenshot: {run_id}/{name}")
        width, height = _jpeg_dimensions(screenshot)
        if not 640 <= width <= 3840 or not 480 <= height <= 2160:
            raise ValueError(f"invalid Obsidian screenshot size: {run_id}/{name}")
    return run


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _validate_passing_run(
    repository: Path, run: dict[str, Any]
) -> dict[str, Any]:
    if run.get("verdict") != "pass":
        raise ValueError("passing Obsidian run is unavailable")
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
    if any(runtime.get(key) != value for key, value in expected_runtime.items()):
        raise ValueError("Obsidian runtime pin mismatch")
    if run.get("test_window_seconds") != 15:
        raise ValueError("Obsidian visible-refresh deadline mismatch")
    fixture = run.get("fixture", {})
    if (
        fixture.get("vault_head") != subject_commit
        or fixture.get("source_repository_head") != subject_commit
        or fixture.get("source_repository_worktree_opened") is not False
        or fixture.get("source_repository_obsidian_directory_absent") is not True
        or fixture.get("global_profile_vault_registration_side_effect") is not True
        or fixture.get("representative_file_hardlinked") is not False
        or fixture.get("representative_source_file_id")
        == fixture.get("representative_clone_file_id")
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
            or case.get("before") == case.get("after")
        ):
            raise ValueError(f"invalid Obsidian latency case: {case['case_id']}")
    canvas = cases[3]
    integrity = cases[4]
    observed = _timestamp(canvas.get("observed_at"))
    unloaded = _timestamp(integrity.get("canvas_unloaded_at"))
    checked = _timestamp(integrity.get("final_checked_at"))
    if (
        not observed <= unloaded < checked
        or integrity.get("stability_interval_seconds") != 300
        or (checked - unloaded).total_seconds() < 300
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
    run_dir = repository / RUN_ROOT / run["run_id"]
    for relative, expected in final_targets.items():
        snapshot = run_dir / "targets" / relative
        if not snapshot.is_file() or _digest_bytes(snapshot.read_bytes()) != expected:
            raise ValueError(f"invalid preserved target: {relative}")
        if (
            final_metadata[relative].get("length_bytes") != snapshot.stat().st_size
            or _timestamp(final_metadata[relative].get("last_write_at"))
            > _timestamp(integrity.get("final_checked_at"))
        ):
            raise ValueError(f"invalid preserved target metadata: {relative}")
    prohibited = run.get("prohibited_actions")
    if (
        not isinstance(prohibited, dict)
        or set(prohibited) != PROHIBITED_ACTIONS
        or any(value is not False for value in prohibited.values())
    ):
        raise ValueError("a prohibited Obsidian action participated")
    return integrity


def build_phase3_item5_inventory(repository: Path) -> dict[str, Any]:
    failed_runs = {
        run_id: _load_run(repository, run_id) for run_id in FAILED_RUNS
    }
    passing = _load_run(repository, PASSING_RUN)
    for run_id, run in failed_runs.items():
        if run.get("verdict") != "fail" or not any(
            case.get("verdict") == "fail" for case in run.get("cases", [])
        ):
            raise ValueError(f"failed Obsidian run is not preserved: {run_id}")
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
                "receipt_digest": _digest_bytes(
                    (repository / RUN_ROOT / run_id / "run.json").read_bytes()
                ),
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
            PASSING_RUN: {
                "receipt_digest": _digest_bytes(
                    (repository / RUN_ROOT / PASSING_RUN / "run.json").read_bytes()
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
