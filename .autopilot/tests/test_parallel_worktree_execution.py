"""End-to-end proof that one dispatched wave executes from two worktrees.

The unit tests in ``test_worktree_coordination`` pin where shared authority
lives. This exercises the property that motivates it: two concurrent worker
processes, in two linked worktrees of one repository, running a real dispatcher
release through claim, work, validation lease, and durable completion.

The arena is cut from this repository's own history at the commit where
EVAL-520 and POISON-540 were genuinely the open parallel wave, so the already
integrated receipt commits validate without anything being restamped. Donor
content and changed-path inventories are read out of the historical receipt
commits rather than transcribed, so a wrong pin fails loudly.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY / ".autopilot" / "bin" / "autopilot.py"

# Immutable coordinates in this repository's history. CUT is the singleton-lineage
# commit whose open parallel wave is exactly the two nodes below; each node names
# the receipt commit carrying its genuine final candidate and path inventory.
CUT = "998b70cee78d775d124862388528bf0e3cb0f461"
NODES = {
    "EVAL-520": {
        "branch": "autopilot/eval-520",
        "receipt_commit": "0c457f034da7b3d72cd18c0924b0c60e34c89809",
        "worktree": "wtA",
    },
    "POISON-540": {
        "branch": "autopilot/poison-540",
        "receipt_commit": "54df2915c0d975cffa998e0b832ab0a35a3f174d",
        "worktree": "wtB",
    },
}
COMPLETION_MARKER = "HIVE-MIND-AUTOPILOT-COMPLETION-V1"
# git log record/field delimiters, chosen because they cannot occur in a message.
SEPARATOR = chr(0x1E)  # git log record delimiter
FIELD = chr(0x1F)  # git log field delimiter


def git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    completed = subprocess.run(
        ("git",) + args, cwd=cwd, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if check and completed.returncode:
        raise AssertionError(
            "git " + " ".join(args) + " failed:\n"
            + completed.stdout + "\n" + completed.stderr
        )
    return completed.stdout.strip()


def show_bytes(commit_path: str, cwd: Path) -> bytes:
    """Return raw bytes; a locale decode corrupts the plan and its fingerprint."""

    return subprocess.run(
        ("git", "show", commit_path), cwd=cwd, capture_output=True, check=True
    ).stdout


def receipt_commits_for(node_id: str, revision: str, cwd: Path) -> int:
    """Count parsed completion receipts for one node reachable from a revision.

    Prose elsewhere in the history also mentions the marker, so the commits are
    parsed rather than string-counted.
    """

    raw = subprocess.run(
        ("git", "log", "--format=%H%x1f%B%x1e", revision),
        cwd=cwd, capture_output=True, check=True,
    ).stdout.decode("utf-8", errors="replace")
    found = 0
    for record in raw.split(SEPARATOR):
        if COMPLETION_MARKER not in record or FIELD not in record:
            continue
        _commit, body = record.split(FIELD, 1)
        try:
            receipt = json.loads(body[body.index("{"): body.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            continue
        if receipt.get("node_id") == node_id:
            found += 1
    return found


def history_is_available() -> bool:
    """A shallow checkout or a fork without this lineage cannot host the arena."""

    if not (REPOSITORY / ".git").exists():
        return False
    wanted = [CUT] + [node["receipt_commit"] for node in NODES.values()]
    return all(
        subprocess.run(
            ("git", "cat-file", "-e", commit + "^{commit}"),
            cwd=REPOSITORY, capture_output=True,
        ).returncode == 0
        for commit in wanted
    )


def force_writable(function, path, _excinfo):
    """Git object files are read-only; clear the bit so cleanup can remove them."""

    os.chmod(path, stat.S_IWRITE)
    function(path)


@unittest.skipUnless(
    history_is_available(),
    "arena requires this repository's full history (shallow clone or foreign fork)",
)
class ParallelWorktreeExecutionTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.mkdtemp(prefix="hive-par-")
        cls.root = Path(cls._temporary)
        cls.origin = cls.root / "origin.git"
        cls.primary = cls.root / "primary"
        cls.transcript = []

        # --no-hardlinks: a local bare clone shares object inodes with the
        # developer's real repository, and arena teardown clears the read-only
        # bit to remove them. Copying keeps that mutation off the real objects.
        git(
            "clone", "--quiet", "--bare", "--no-hardlinks",
            str(REPOSITORY), str(cls.origin),
        )

        cls.control = json.loads(
            show_bytes(CUT + ":.autopilot/control-plane.json", cls.origin).decode("utf-8")
        )
        cls.singleton = cls.control["target"]["branch"]
        cls.fingerprint = cls.control["plan_fingerprint"]

        git("branch", "-f", cls.singleton, CUT, cwd=cls.origin)
        for node in NODES.values():
            # A publish-remote claim creates the node branch itself and refuses a
            # pre-existing one, so the historical tips must not be present.
            git("branch", "-D", node["branch"], cwd=cls.origin, check=False)

        # Long paths: this repository carries evidence paths that exceed the
        # classic Windows limit once nested under a temporary directory.
        git(
            "clone", "--quiet", "-c", "core.longpaths=true",
            "--branch", cls.singleton, str(cls.origin), str(cls.primary),
        )
        git("config", "user.email", "arena@example.invalid", cwd=cls.primary)
        git("config", "user.name", "arena", cwd=cls.primary)

        cls.donors = {}
        for node_id, node in NODES.items():
            message = subprocess.run(
                ("git", "show", "-s", "--format=%B", node["receipt_commit"]),
                cwd=cls.origin, capture_output=True, check=True,
            ).stdout.decode("utf-8")
            receipt = json.loads(message[message.index("{"): message.rindex("}") + 1])
            if receipt["node_id"] != node_id:
                raise AssertionError("receipt pin for " + node_id + " names another node")
            cls.donors[node_id] = receipt

            worktree = cls.root / node["worktree"]
            git("worktree", "add", "--quiet", "--detach", str(worktree), CUT,
                cwd=cls.primary)
            git("config", "user.email", "worker@example.invalid", cwd=worktree)
            git("config", "user.name", "worker", cwd=worktree)

        cls.snapshot = cls.root / "snapshot.json"

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._temporary, onexc=force_writable)

    @classmethod
    def cli(cls, repo: Path, *args: str, check: bool = True):
        completed = subprocess.run(
            (sys.executable, str(MODULE_PATH), "--repo-root", str(repo)) + args,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if check and completed.returncode:
            raise AssertionError(
                "autopilot " + " ".join(args) + " failed:\n"
                + completed.stdout + "\n" + completed.stderr
            )
        return completed

    @classmethod
    def observe(cls, target: str) -> None:
        cls.snapshot.write_text(
            json.dumps({"target_sha": target, "pull_requests": [], "branches": []}),
            encoding="utf-8",
        )
        cls.cli(cls.primary, "install-github-snapshot", str(cls.snapshot))

    def test_01_the_epoch_plan_fingerprint_reproduces(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "arena_controller", REPOSITORY / ".autopilot" / "bin" / "controller.py"
        )
        controller = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = controller
        spec.loader.exec_module(controller)
        plan = json.loads(
            show_bytes(CUT + ":.autopilot/plan.json", self.origin).decode("utf-8")
        )
        document = dict(plan)
        document.pop("plan_fingerprint", None)
        self.assertEqual(controller.digest_json(document), self.fingerprint)

    def test_02_the_dispatcher_releases_both_nodes_together(self) -> None:
        self.observe(CUT)
        self.cli(
            self.primary, "reconcile", "--target-sha", CUT,
            "--actor", "dispatcher:arena", "--reason", "parallel arena baseline",
        )
        requested = []
        for node_id in NODES:
            requested.extend(["--node", node_id])
        # MIGRATION-460 is also open at this cut and, being parallel-unsafe,
        # would win the default wave alone; request the parallel pair.
        release = json.loads(
            self.cli(
                self.primary, "dispatch", "--actor", "dispatcher:arena",
                *requested, "--json",
            ).stdout
        )
        self.assertEqual(sorted(release["released_wave"]), sorted(NODES))
        self.assertEqual(release["directive"], "START TOGETHER NOW")

    def test_03_two_worktrees_execute_the_wave_concurrently(self) -> None:
        names = list(NODES)
        worker_path = Path(__file__).with_name("parallel_worker.py")
        processes = {}
        for index, node_id in enumerate(names):
            rival = names[1 - index]
            processes[node_id] = subprocess.Popen(
                (
                    sys.executable, str(worker_path), str(self.root),
                    str(self.root / NODES[node_id]["worktree"]), node_id,
                    NODES[node_id]["branch"], CUT, self.fingerprint,
                    json.dumps(self.donors[node_id]),
                    "b" if index else "a", rival,
                ),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
        for node_id, process in processes.items():
            output, _ = process.communicate(timeout=600)
            for line in output.splitlines():
                if line.startswith("{"):
                    type(self).transcript.append(json.loads(line))
            self.assertEqual(
                process.returncode, 0, node_id + " worker failed:\n" + output
            )

    def test_04_a_second_worktree_cannot_claim_a_claimed_node(self) -> None:
        probes = [row for row in self.transcript if row["step"] == "double-claim-probe"]
        self.assertTrue(probes, "the arena recorded no cross-worktree claim probe")
        for probe in probes:
            self.assertTrue(probe["rejected"], probe)

    def test_05_the_validation_lease_serializes_across_worktrees(self) -> None:
        waits = [row for row in self.transcript if row["step"] == "lease-wait"]
        self.assertTrue(
            waits, "the second worker never contended for the repository-wide lease"
        )
        self.assertTrue(any("lease is active" in row["message"] for row in waits), waits)
        acquired = [row for row in self.transcript if row["step"] == "lease-acquired"]
        self.assertEqual(len(acquired), len(NODES))
        self.assertTrue(any(row["after_rejections"] > 0 for row in acquired), acquired)

    def test_06_completion_is_durable_and_visible_from_every_worktree(self) -> None:
        git("fetch", "--quiet", "origin", cwd=self.primary)
        for node in NODES.values():
            git(
                "merge", "--no-ff", "--quiet", "-m", "integrate " + node["branch"],
                "origin/" + node["branch"], cwd=self.primary,
            )
        tip = git("rev-parse", "HEAD", cwd=self.primary)
        git("push", "--quiet", "origin", self.singleton, cwd=self.primary)
        self.observe(tip)
        self.cli(
            self.primary, "reconcile", "--target-sha", tip,
            "--actor", "dispatcher:arena", "--reason", "parallel wave integrated",
        )

        # Each arena node must contribute exactly one durable receipt commit that
        # was not reachable before the wave ran.
        for node_id in NODES:
            self.assertEqual(
                receipt_commits_for(node_id, CUT, self.primary), 0,
                node_id + " already had a durable receipt at the cut",
            )
            self.assertEqual(
                receipt_commits_for(node_id, tip, self.primary), 1,
                node_id + " did not publish exactly one durable receipt",
            )

        labels = ["primary"] + [node["worktree"] for node in NODES.values()]
        for label in labels:
            repo = self.primary if label == "primary" else self.root / label
            status = json.loads(self.cli(repo, "status", "--json").stdout)
            states = {
                row["node_id"]: row["state"]
                for row in status["nodes"]
                if row["node_id"] in NODES
            }
            self.assertEqual(
                states, {node: "COMPLETE" for node in NODES}, "observed from " + label
            )

    def test_07_the_verdict_comes_from_shared_evidence_not_local_receipts(self) -> None:
        for node_id in NODES:
            for name, other in NODES.items():
                if name == node_id:
                    continue
                receipt = (
                    self.root / other["worktree"] / ".autopilot" / "state"
                    / "receipts" / (node_id + ".json")
                )
                self.assertFalse(
                    receipt.exists(),
                    other["worktree"] + " holds a local " + node_id + " receipt; the "
                    "COMPLETE verdict would not prove shared authority",
                )


if __name__ == "__main__":
    unittest.main()
