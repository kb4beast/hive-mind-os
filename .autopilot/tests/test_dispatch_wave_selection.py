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

    def _make_eligible(self, eligible: list[str]) -> None:
        """Report exactly these nodes as ready, leaving the real plan intact."""

        rows = [{"node_id": node_id, "state": "READY"} for node_id in eligible]
        rows += [
            {"node_id": node_id, "state": "COMPLETE"}
            for node_id in self.plane._nodes
            if node_id not in eligible
        ]
        status = {"ready": list(eligible), "nodes": rows}
        self.plane._base_status = lambda: dict(status)  # type: ignore[method-assign]
        self.plane.target_requires_reconciliation = lambda: False  # type: ignore[method-assign]
        self.plane._reconciliation_digest = lambda: "sha256:" + "1" * 64  # type: ignore[method-assign]
        self.plane._snapshot_digest = lambda: "sha256:" + "2" * 64  # type: ignore[method-assign]
        self.plane._recovery_issues = lambda: ()  # type: ignore[method-assign]

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

    def test_priority_wins_so_a_serial_node_is_not_starved(self) -> None:
        release = self.plane.dispatch(actor="test:dispatcher")
        # MIGRATION-460 carries the highest critical_path_importance of this set,
        # so it must take the round rather than being skipped forever.
        self.assertEqual(list(release["released_wave"]), [SERIAL])

    def test_parallel_only_eligibility_still_waves_together(self) -> None:
        self._make_eligible(list(PARALLEL))
        release = self.plane.dispatch(actor="test:dispatcher")
        self.assertEqual(sorted(release["released_wave"]), sorted(PARALLEL))
        self.assertEqual(tuple(self.plane._release_issues(release)), ())

    def test_requesting_a_serial_node_with_a_sibling_is_refused(self) -> None:
        with self.assertRaises(autopilot.AutopilotError) as raised:
            self.plane.dispatch(actor="test:dispatcher", requested_nodes=[SERIAL, PARALLEL[0]])
        self.assertIn("serial node", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
