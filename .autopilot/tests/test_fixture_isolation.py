from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fixture_support import copy_autopilot_fixture

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import durable_controller  # noqa: E402


class ControllerFixtureIsolationTests(unittest.TestCase):
    def test_live_runtime_state_does_not_change_fresh_fixture_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tracked_source = Path(__file__).resolve().parents[1]
            repository = root / "seed"
            seeded = copy_autopilot_fixture(
                tracked_source,
                repository / ".autopilot",
            )
            subprocess.run(("git", "init"), cwd=repository, check=True, capture_output=True)
            subprocess.run(("git", "add", ".autopilot"), cwd=repository, check=True, capture_output=True)
            (repository / ".gitignore").write_text(".autopilot/state/\n*.ignored\n", encoding="utf-8")
            subprocess.run(("git", "add", ".gitignore"), cwd=repository, check=True, capture_output=True)
            (seeded / "state" / "claims").mkdir()
            (seeded / "state" / "github-state.json").write_text(
                json.dumps(
                    {
                        "target_sha": "f" * 40,
                        "pull_requests": [
                            {
                                "node_id": "RECON-010",
                                "number": 999,
                                "state": "open",
                                "merged": False,
                                "ci": "success",
                            }
                        ],
                        "branches": [],
                    }
                ),
                encoding="utf-8",
            )
            for name in (
                "target.json",
                "dispatcher-release.json",
                "claims/RECON-010.json",
            ):
                path = seeded / "state" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
            (seeded / "bin" / "untracked.generated").write_text("sentinel", encoding="utf-8")
            (seeded / "tests" / "__pycache__").mkdir()
            (seeded / "tests" / "__pycache__" / "sentinel.pyc").write_bytes(b"generated")
            (repository / "outside.ignored").write_text("sentinel", encoding="utf-8")

            fixture = copy_autopilot_fixture(
                seeded,
                root / "fixture" / ".autopilot",
            )
            control_path = fixture / "control-plane.json"
            control = json.loads(control_path.read_text(encoding="utf-8"))
            control["verify_git_objects"] = False
            durable_controller.atomic_write_json(control_path, control)
            plane = durable_controller.ControlPlane(root / "fixture")

            # A copied fixture must not inherit live authority.  It therefore
            # remains deliberately pre-READY until the test explicitly runs
            # the runtime migration; reporting DAG readiness before that
            # transition would recreate the retired singleton authority.
            with self.assertRaisesRegex(
                durable_controller.ConfigurationError,
                "runtime authority identity is absent",
            ):
                plane.ready_nodes()
            self.assertFalse((fixture / "bin" / "untracked.generated").exists())
            self.assertFalse((fixture / "tests" / "__pycache__").exists())
            self.assertEqual(plane.github_snapshot(), {})


if __name__ == "__main__":
    unittest.main()
