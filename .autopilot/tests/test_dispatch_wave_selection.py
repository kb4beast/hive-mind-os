"""The CLI's own dispatcher must never write a release its validator rejects.

``autopilot.ControlPlane`` overrides ``dispatch``, so the release-barrier suite
never exercised the wave selection the CLI actually runs. That override chose a
wave on lock-disjointness alone and ignored ``parallel_safe``, which seats a
serial node beside parallel siblings — precisely the pairing
``_release_issues`` rejects. The release was therefore invalid the moment it
was written: ``ready`` stayed empty, no node could ever be claimed, and an
auto-dispatching healer rewrote the same invalid wave on every pass.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fixture_support import copy_autopilot_fixture

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, BIN / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


autopilot = _load("dispatch_autopilot", "autopilot.py")

SERIAL = "MIGRATION-460"          # parallel_safe: false in the sealed plan
PARALLEL = ("SELFHEAL-450", "CHALLENGER-510", "POISON-540")


class DispatchWaveSelectionTests(unittest.TestCase):
    """A release the dispatcher writes must satisfy its own validator."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "work"
        self.root.mkdir()
        subprocess.run(
            ("git", "init", "--quiet", "--initial-branch=main", str(self.root)),
            check=True,
            capture_output=True,
        )
        copy_autopilot_fixture(Path(__file__).resolve().parents[1], self.root / ".autopilot")
        control_path = self.root / ".autopilot" / "control-plane.json"
        control = json.loads(control_path.read_text(encoding="utf-8"))
        control["verify_git_objects"] = False
        control_path.write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8")
        self.plane = autopilot.ControlPlane(self.root)
        self._make_eligible([SERIAL, *PARALLEL])

    def _make_eligible(self, eligible: list[str], *, active: tuple[str, ...] = ()) -> None:
        """Report exactly these nodes as ready, leaving the real plan intact."""

        rows = [{"node_id": node_id, "state": "READY"} for node_id in eligible]
        rows += [{"node_id": node_id, "state": "CLAIMED"} for node_id in active]
        rows += [
            {"node_id": node_id, "state": "COMPLETE"}
            for node_id in self.plane._nodes
            if node_id not in eligible and node_id not in active
        ]
        status = {"ready": list(eligible), "nodes": rows}
        self.plane._base_status = lambda: dict(status)  # type: ignore[method-assign]
        self.plane.target_requires_reconciliation = lambda: False  # type: ignore[method-assign]
        self.plane._reconciliation_digest = lambda: "sha256:" + "1" * 64  # type: ignore[method-assign]
        self.plane._snapshot_digest = lambda: "sha256:" + "2" * 64  # type: ignore[method-assign]
        self.plane._recovery_issues = lambda: ()  # type: ignore[method-assign]
        self.plane.active_claims = lambda: {node_id: {"node_id": node_id} for node_id in active}  # type: ignore[method-assign]

    def test_a_serial_node_is_never_seated_beside_parallel_siblings(self) -> None:
        release = self.plane.dispatch(actor="test:dispatcher")
        wave = list(release["released_wave"])
        serial = [n for n in wave if not self.plane.node(n).get("parallel_safe")]
        if serial:
            self.assertEqual(
                wave, serial[:1],
                "a serial node must be released alone, never with siblings",
            )

    def test_the_written_release_satisfies_its_own_validator(self) -> None:
        """The invariant that actually matters, whatever the wave turns out to be."""

        release = self.plane.dispatch(actor="test:dispatcher")
        issues = self.plane._release_issues(release)
        self.assertEqual(
            tuple(issues), (),
            f"dispatch wrote a self-invalidating release for wave {release['released_wave']}",
        )

    def test_compiled_order_governs_and_serial_work_remains_releasable(self) -> None:
        first = self.plane.dispatch(actor="test:dispatcher")
        self.assertEqual(list(first["released_wave"]), list(PARALLEL))
        self._make_eligible([SERIAL])
        second = self.plane.dispatch(actor="test:dispatcher")
        self.assertEqual(list(second["released_wave"]), [SERIAL])

    def test_parallel_only_eligibility_still_waves_together(self) -> None:
        self._make_eligible(list(PARALLEL))
        release = self.plane.dispatch(actor="test:dispatcher")
        self.assertEqual(sorted(release["released_wave"]), sorted(PARALLEL))
        self.assertEqual(tuple(self.plane._release_issues(release)), ())

    def test_default_dispatch_never_exceeds_runtime_capacity(self) -> None:
        self._make_eligible(list(PARALLEL))
        release = self.plane.dispatch(actor="test:dispatcher", max_sessions=2)
        self.assertEqual(list(release["released_wave"]), list(PARALLEL[:2]))
        self.assertEqual(release["session_cap"], 2)

    def test_explicit_release_above_capacity_is_refused(self) -> None:
        self._make_eligible(list(PARALLEL))
        with self.assertRaisesRegex(autopilot.AutopilotError, "above the 2-session cap"):
            self.plane.dispatch(
                actor="test:dispatcher",
                requested_nodes=list(PARALLEL),
                max_sessions=2,
            )

    def test_identical_valid_dispatch_is_a_read_only_retry(self) -> None:
        self._make_eligible(list(PARALLEL))
        first = self.plane.dispatch(actor="test:dispatcher", max_sessions=2)
        history = self.plane.state_dir / "dispatcher-releases.jsonl"
        before = history.read_bytes()
        second = self.plane.dispatch(actor="test:other", max_sessions=2)
        self.assertEqual(first["release_id"], second["release_id"])
        self.assertEqual(before, history.read_bytes())

    def test_crash_resume_stays_inside_the_active_compiled_round(self) -> None:
        self._make_eligible(list(PARALLEL[1:]), active=(PARALLEL[0],))
        release = self.plane.dispatch(actor="test:dispatcher", max_sessions=3)
        self.assertEqual(list(release["round_nodes"]), list(PARALLEL))
        self.assertEqual(list(release["released_wave"]), list(PARALLEL[1:]))
        self.assertTrue(str(release["frontier_id"]).startswith("sha256:"))

    def test_requesting_a_serial_node_with_a_sibling_is_refused(self) -> None:
        with self.assertRaises(autopilot.AutopilotError) as raised:
            self.plane.dispatch(actor="test:dispatcher", requested_nodes=[SERIAL, PARALLEL[0]])
        self.assertIn("compiled frontier", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
