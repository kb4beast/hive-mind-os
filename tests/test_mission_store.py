from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from hive_mind_os.acceptance import AcceptanceSpecification
from hive_mind_os.autonomy import AutonomyBudget
from hive_mind_os.contracts import (
    tool_intent_digest,
    validate_contract,
    validate_runtime_state,
)
from hive_mind_os.mission import RepositoryMission, ScriptedRepositoryBackend
from hive_mind_os.mission_store import (
    MissionStore,
    ReconciliationError,
    SimulatedCrash,
    StoreIntegrityError,
    StoreVersionError,
    _atomic_write,
    resume_mission,
)
from hive_mind_os.models import WorkStatus
from tests.fixtures.fixture_repo import build_fixture_repo

DURABLE_STEP_COUNT = 18
MAX_PATH = 260
COMPONENT_LIMIT = 255
CRASH_BOUNDARIES = ("before_intent", "after_intent", "after_effect")
FAST_TEST_ARGV = (
    sys.executable,
    "-B",
    "-c",
    (
        "from tiny_pkg.maths import increment; "
        "raise SystemExit(0 if increment(1) == 2 else 1)"
    ),
)
FAST_CRITERION_ARGV = (
    sys.executable,
    "-B",
    "-c",
    "from tiny_pkg.maths import increment; assert increment(1) == 2",
)


def _backend() -> ScriptedRepositoryBackend:
    return ScriptedRepositoryBackend(
        test_argv=FAST_TEST_ARGV,
        criterion_argv=FAST_CRITERION_ARGV,
    )


def _mission(
    root: Path,
    *,
    hook=None,
) -> tuple[RepositoryMission, MissionStore, Path]:
    fixture = build_fixture_repo(root / "repository")
    store = MissionStore(root / "state")
    output = root / "delivery"
    mission = RepositoryMission(
        fixture.root,
        "Fix the failing test",
        acceptance_criteria=("increment(1) returns 2",),
        acceptance_specifications=(
            AcceptanceSpecification(
                "increment-returns-two",
                "increment(1) returns 2",
                FAST_CRITERION_ARGV,
            ),
        ),
        backend=_backend(),
        pin=fixture.commit_two,
        output_dir=output,
        mission_store=store,
        crash_hook=hook,
    )
    return mission, store, output


def _crash_hook(target_step: int, target_boundary: str):
    def hook(step_index: int, boundary: str) -> None:
        if (step_index, boundary) == (target_step, target_boundary):
            raise SimulatedCrash

    return hook


def _remove_workspace_tree(root: Path) -> None:
    def make_writable_and_retry(function, path, _error) -> None:
        os.chmod(path, stat.S_IWRITE)
        function(path)

    shutil.rmtree(root, onerror=make_writable_and_retry)


def _interrupt(
    root: Path,
    step_index: int,
    boundary: str,
) -> tuple[MissionStore, str, Path]:
    mission, store, output = _mission(
        root,
        hook=_crash_hook(step_index, boundary),
    )
    with _assert_raises(SimulatedCrash):
        asyncio.run(mission.run())
    mission.ledger.close()
    assert store.mission(mission.run_id)["status"] == "interrupted"
    return store, mission.run_id, output


@contextmanager
def _assert_raises(
    expected: type[BaseException],
    *,
    match: str | None = None,
) -> Iterator[dict[str, BaseException]]:
    captured: dict[str, BaseException] = {}
    try:
        yield captured
    except expected as error:
        if match is not None and match not in str(error):
            raise AssertionError(
                f"{type(error).__name__} did not contain {match!r}: {error}"
            ) from error
        captured["error"] = error
    else:
        raise AssertionError(f"{expected.__name__} was not raised")


def _case_kill_at_every_boundary_resumes_without_duplicate_effects(
    tmp_path: Path,
    step_index: int,
    boundary: str,
) -> None:
    store, mission_id, output = _interrupt(
        tmp_path,
        step_index,
        boundary,
    )
    publish_effect_is_visible = (
        step_index == 17
        or (step_index == 16 and boundary == "after_effect")
    )
    assert output.exists() is publish_effect_is_visible
    report = asyncio.run(resume_mission(store, mission_id))
    assert report.status is WorkStatus.SUCCEEDED
    assert output.is_dir()
    checkpoints = store.checkpoints(mission_id)
    assert len(checkpoints) == DURABLE_STEP_COUNT
    assert store.idempotency_count(mission_id) == DURABLE_STEP_COUNT
    receipt_files = list(
        (
            store.mission_root(mission_id) / "checkpoint-receipts"
        ).glob("*.json")
    )
    assert len(receipt_files) == DURABLE_STEP_COUNT
    assert all(checkpoint.execution_count == 1 for checkpoint in checkpoints)
    if boundary == "after_effect":
        assert checkpoints[step_index].execution_count == 1
    store.close()


def _case_workspace_drift_blocks_with_reconciliation_report(
    tmp_path: Path,
) -> None:
    store, mission_id, output = _interrupt(tmp_path, 4, "after_effect")
    builder = Path(
        store.mission(mission_id)["workspaces"]["builder"]["container"]
    )
    (builder / "repo" / "tiny_pkg" / "maths.py").write_text(
        "def increment(value: int) -> int:\n    return value + 99\n",
        encoding="utf-8",
    )
    with _assert_raises(ReconciliationError) as captured:
        asyncio.run(resume_mission(store, mission_id))
    error = captured["error"]
    assert isinstance(error, ReconciliationError)
    assert "digest mismatch" in str(error)
    assert error.report["workspace"] == "builder"
    assert error.report["expected"] != error.report["observed"]
    assert store.mission(mission_id)["status"] == "blocked"
    assert not output.exists()
    store.close()


def _case_lost_workspace_rebuilds_and_completes(tmp_path: Path) -> None:
    store, mission_id, output = _interrupt(tmp_path, 4, "after_effect")
    builder = Path(
        store.mission(mission_id)["workspaces"]["builder"]["container"]
    )
    _remove_workspace_tree(builder)
    report = asyncio.run(resume_mission(store, mission_id))
    assert report.status is WorkStatus.SUCCEEDED
    assert output.is_dir()
    assert store.idempotency_count(mission_id) == DURABLE_STEP_COUNT
    assert len(store.checkpoints(mission_id)) == DURABLE_STEP_COUNT
    store.close()


def _case_uncheckpointed_partial_workspace_rebuilds(tmp_path: Path) -> None:
    store, mission_id, output = _interrupt(tmp_path, 0, "after_intent")
    partial = store.mission_root(mission_id) / "workspaces" / "explorer"
    partial.mkdir(parents=True)
    (partial / "interrupted-clone").write_text("partial", encoding="utf-8")
    report = asyncio.run(resume_mission(store, mission_id))
    assert report.status is WorkStatus.SUCCEEDED
    assert output.is_dir()
    assert len(store.checkpoints(mission_id)) == DURABLE_STEP_COUNT
    store.close()


def _case_checkpoint_digest_tamper_fails_closed(tmp_path: Path) -> None:
    store, mission_id, output = _interrupt(tmp_path, 4, "after_intent")
    with store._connection:
        store._connection.execute(
            """
            UPDATE checkpoints
            SET intent_digest=?
            WHERE mission_id=? AND step_index=?
            """,
            (f"sha256:{'f' * 64}", mission_id, 4),
        )
    with _assert_raises(StoreIntegrityError, match="digest"):
        asyncio.run(resume_mission(store, mission_id))
    assert not output.exists()
    store.close()


def _case_store_version_fails_closed(tmp_path: Path) -> None:
    state = tmp_path / "state"
    store = MissionStore(state)
    store.close()
    connection = sqlite3.connect(state / "missions.sqlite3")
    with connection:
        connection.execute(
            "UPDATE metadata SET value='999' WHERE key='schema_version'"
        )
    connection.close()
    with _assert_raises(StoreVersionError, match="unsupported"):
        MissionStore(state)


def _case_store_crud_idempotency_and_state_schema(tmp_path: Path) -> None:
    mission, store, _ = _mission(tmp_path)
    mission_record = store.mission(mission.run_id)
    assert mission_record["status"] == "active"
    assert validate_contract("mission-state", mission_record["state"]).valid
    intent = {
        "schema_version": 1,
        "action_id": f"ACT-{mission.run_id}",
        "mission_id": mission.run_id,
        "state_ref": f"MISSION_STATE:{mission.run_id}:1",
        "actor_id": "agent-builder",
        "kind": "write",
        "description": "store CRUD fixture",
        "action_digest": f"sha256:{'0' * 64}",
        "policy_decision_ref": "policy-fixture",
        "lease_id": "lease-fixture",
        "idempotency_key": "test-deduplication-key",
        "rollback_ref": None,
        "status": "proposed",
    }
    intent["action_digest"] = tool_intent_digest(intent)
    checkpoint = store.record_intent(mission.run_id, 0, intent)
    store.begin_effect(mission.run_id, 0)
    outcome = {"value": "ok", "records": []}
    reference = store.write_effect_receipt(checkpoint, outcome, ())
    store.complete_step(checkpoint, reference, outcome)
    store.complete_step(checkpoint, reference, outcome)
    assert store.idempotency_count(mission.run_id) == 1
    assert store.checkpoint(mission.run_id, 0).state == "completed"
    assert validate_contract(
        "mission-state",
        store.mission(mission.run_id)["state"],
    ).valid
    with _assert_raises(sqlite3.IntegrityError):
        with store._connection:
            store._connection.execute(
                """
                INSERT INTO idempotency(
                    intent_digest,mission_id,step_index,receipt_ref_json
                ) VALUES(?,?,?,?)
                """,
                (
                    intent["action_digest"],
                    mission.run_id,
                    0,
                    json.dumps(reference),
                ),
            )
    mission.ledger.close()
    store.close()


def _case_completed_state_round_trips_and_validates(tmp_path: Path) -> None:
    mission, store, output = _mission(tmp_path)
    report = asyncio.run(mission.run())
    assert report.status is WorkStatus.SUCCEEDED
    state = store.mission(mission.run_id)["state"]
    validation = validate_runtime_state(state)
    assert validation.valid, validation.issues
    encoded = json.dumps(state, sort_keys=True, separators=(",", ":"))
    assert json.loads(encoded) == state
    assert output.is_dir()
    mission.ledger.close()
    store.close()


def _case_cli_lists_and_resumes_interrupted_mission(tmp_path: Path) -> None:
    store, mission_id, output = _interrupt(tmp_path, 4, "after_effect")
    state_dir = store.state_dir
    store.close()
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        (str(Path(__file__).parents[1] / "src"), str(Path(__file__).parents[1]))
    )
    listed = subprocess.run(
        [
            sys.executable,
            "-m",
            "hive_mind_os.cli",
            "missions",
            "--state-dir",
            str(state_dir),
        ],
        cwd=Path(__file__).parents[1],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
        text=True,
        timeout=60,
    )
    assert listed.returncode == 0, listed.stderr
    inventory = json.loads(listed.stdout)["missions"]
    assert any(
        item["mission_id"] == mission_id and item["status"] == "interrupted"
        for item in inventory
    )
    resumed = subprocess.run(
        [
            sys.executable,
            "-m",
            "hive_mind_os.cli",
            "resume",
            mission_id,
            "--state-dir",
            str(state_dir),
        ],
        cwd=Path(__file__).parents[1],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
        text=True,
        timeout=90,
    )
    assert resumed.returncode == 0, resumed.stderr
    assert json.loads(resumed.stdout)["status"] == "succeeded"
    assert output.is_dir()


def _case_raw_effect_receipt_is_adopted_without_reexecution(
    tmp_path: Path,
) -> None:
    store, mission_id, output = _interrupt(
        tmp_path,
        1,
        "after_capability_effect",
    )
    interrupted = store.checkpoint(mission_id, 1)
    assert interrupted.state == "intent"
    assert interrupted.execution_count == 1
    raw_before = list(
        (
            store.mission_root(mission_id)
            / "staging"
            / "evidence"
            / "r"
        ).glob("*.json")
    )
    assert len(raw_before) == 4

    report = asyncio.run(resume_mission(store, mission_id))
    assert report.status is WorkStatus.SUCCEEDED
    assert output.is_dir()
    assert store.checkpoint(mission_id, 1).execution_count == 1
    raw_after = list(
        (
            store.mission_root(mission_id)
            / "staging"
            / "evidence"
            / "r"
        ).glob("*.json")
    )
    assert len(raw_after) == 45
    assert len(report.receipts) == 45
    assert report.budget_consumption["tool_calls"] == 45
    assert store.mission(mission_id)["budget"]["tool_calls_used"] == 45
    assert len(
        {
            (str(record["path"]), str(record["digest"]))
            for record in report.receipts
        }
    ) == 45
    store.close()


class _IrreversibleRemote:
    """A host that accepts one effect per idempotency key and can be asked about it."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.applied: list[str] = []
        self.witnessed: list[bool] = []

    def apply(self, key: str, witness: Callable[[], bool]) -> dict[str, str]:
        self.witnessed.append(witness())
        self.applied.append(key)
        effect = {"key": key, "effect_id": f"remote-effect-{len(self.applied)}"}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(effect, sort_keys=True) + "\n")
        return effect

    def lookup(self, key: str) -> dict[str, str] | None:
        if not self.path.is_file():
            return None
        for line in self.path.read_text(encoding="utf-8").splitlines():
            effect = json.loads(line)
            if effect["key"] == key:
                return effect
        return None


def _register(store: MissionStore, mission_id: str) -> None:
    store.register_mission(
        mission_id,
        {
            "objective": "close A4 defect D1",
            "repository": "hive-mind-os",
            "source_pack_fingerprint": f"sha256:{'0' * 64}",
        },
        AutonomyBudget(1, 4, 10.0),
    )


def _delivery_intent(
    mission_id: str,
    action_id: str,
    key: str,
) -> dict[str, object]:
    intent = {
        "schema_version": 1,
        "action_id": action_id,
        "mission_id": mission_id,
        "state_ref": f"MISSION_STATE:{mission_id}:1",
        "actor_id": "agent-integrator",
        "kind": "network",
        "description": "push the pilot branch to the delivery remote",
        "action_digest": f"sha256:{'0' * 64}",
        "policy_decision_ref": "POLICY-WAL-1200",
        "lease_id": "LEASE-WAL-1200",
        "idempotency_key": key,
        "rollback_ref": None,
        "status": "proposed",
    }
    intent["action_digest"] = tool_intent_digest(intent)
    return intent


def _deep(path: Path) -> str:
    target = os.fspath(path)
    if os.name == "nt":
        return "\\\\?\\" + os.path.abspath(target)
    return target


def _remove_deep_tree(root: Path) -> None:
    shutil.rmtree(_deep(root), ignore_errors=True)


def _case_effect_interrupted_before_receipt_reconciles_from_write_ahead_record(
    tmp_path: Path,
) -> None:
    state_dir = tmp_path / "state"
    mission_id = "MISSION-WAL-1200"
    key = "IDEMPOTENCY-WAL-1200-push"
    remote = _IrreversibleRemote(tmp_path / "remote-effects.jsonl")

    store = MissionStore(state_dir)
    _register(store, mission_id)
    intent = _delivery_intent(mission_id, "ACT-WAL-1200-push", key)
    checkpoint = store.checkpoint_for_intent(mission_id, intent)
    assert store.find_effect_receipt(checkpoint) is None
    written_ahead = store.begin_effect(mission_id, checkpoint.step_index)
    assert written_ahead["idempotency_key"] == key
    assert written_ahead["intent_digest"] == checkpoint.intent_digest
    ahead_path = store.effect_intent_path(mission_id, checkpoint.intent_digest)
    applied = remote.apply(key, ahead_path.is_file)
    store.close()

    assert remote.witnessed == [True]

    resumed = MissionStore(state_dir)
    try:
        pending = resumed.unreconciled_effects(mission_id)
        assert [item["idempotency_key"] for item in pending] == [key]
        assert pending[0]["intent_digest"] == checkpoint.intent_digest
        replayed = resumed.checkpoint(mission_id, int(pending[0]["step_index"]))
        assert replayed.state == "intent"
        assert replayed.execution_count == 1
        observed = remote.lookup(pending[0]["idempotency_key"])
        assert observed == applied
        outcome = {"value": dict(observed), "records": []}
        reference = resumed.reconcile_effect(replayed, outcome, ())
        assert remote.applied == [key]
        assert resumed.unreconciled_effects(mission_id) == []
        settled = resumed.checkpoint(mission_id, replayed.step_index)
        assert settled.state == "completed"
        assert settled.execution_count == 1
        assert settled.receipt_reference == reference
        assert resumed.idempotency_count(mission_id) == 1
        adopted = resumed.find_effect_receipt(settled)
        assert adopted is not None
        assert adopted[1]["outcome"]["value"] == applied

        unbegun = resumed.checkpoint_for_intent(
            mission_id,
            _delivery_intent(
                mission_id,
                "ACT-WAL-1200-comment",
                "IDEMPOTENCY-WAL-1200-comment",
            ),
        )
        with _assert_raises(ReconciliationError, match="write-ahead"):
            resumed.reconcile_effect(unbegun, outcome, ())
    finally:
        resumed.close()


def _case_competing_effect_claim_and_missing_wal_fail_closed(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    mission_id = "MISSION-WAL-CAS-1201"
    store = MissionStore(state_dir)
    try:
        _register(store, mission_id)
        checkpoint = store.checkpoint_for_intent(
            mission_id,
            _delivery_intent(
                mission_id,
                "ACT-WAL-CAS-1201-push",
                "IDEMPOTENCY-WAL-CAS-1201-push",
            ),
        )
        written_ahead = store.begin_effect(mission_id, checkpoint.step_index)
        with _assert_raises(StoreIntegrityError, match="already claimed"):
            store.begin_effect(mission_id, checkpoint.step_index)

        intent_path = store.effect_intent_path(
            mission_id,
            checkpoint.intent_digest,
        )
        intent_path.unlink()
        with _assert_raises(StoreIntegrityError, match="missing its write-ahead"):
            store.unreconciled_effects(mission_id)
        forged = {**written_ahead, "action_id": "ACT-COMPETING"}
        _atomic_write(
            intent_path,
            (json.dumps(forged, sort_keys=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            ),
        )
        with _assert_raises(StoreIntegrityError, match="different intent"):
            store.unreconciled_effects(mission_id)
    finally:
        store.close()


def _case_receipt_tamper_and_path_traversal_fail_closed(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    mission_id = "MISSION-WAL-RECEIPT-1202"
    store = MissionStore(state_dir)
    try:
        with _assert_raises(StoreIntegrityError, match="safe path segment"):
            store.mission_root("../outside")

        _register(store, mission_id)
        checkpoint = store.checkpoint_for_intent(
            mission_id,
            _delivery_intent(
                mission_id,
                "ACT-WAL-RECEIPT-1202-push",
                "IDEMPOTENCY-WAL-RECEIPT-1202-push",
            ),
        )
        store.begin_effect(mission_id, checkpoint.step_index)
        outcome = {"value": {"pushed": True}, "records": []}
        reference = store.write_effect_receipt(checkpoint, outcome, ())
        receipt_path = state_dir / Path(*reference["path"].split("/"))
        wrapper = json.loads(receipt_path.read_text(encoding="utf-8"))
        wrapper["outcome"] = {"value": {"pushed": False}, "records": []}
        _atomic_write(
            receipt_path,
            (json.dumps(wrapper, sort_keys=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            ),
        )
        with _assert_raises(StoreIntegrityError, match="digest does not match"):
            store.complete_step(checkpoint, reference, outcome)
        assert store.checkpoint(mission_id, checkpoint.step_index).state == "intent"
        assert store.idempotency_count(mission_id) == 0
    finally:
        store.close()


def _persist_receipt_under_path_length(root: Path, final_length: int) -> None:
    store = MissionStore(root / "s")
    try:
        padding = final_length - len(str(store.state_dir)) - 100
        assert padding >= 32, padding
        mission_id = "M" + "x" * (padding - 1)
        _register(store, mission_id)
        intent = _delivery_intent(
            mission_id,
            "ACT-WAL-1200-maxpath",
            "IDEMPOTENCY-WAL-1200-maxpath",
        )
        checkpoint = store.checkpoint_for_intent(mission_id, intent)
        receipts = store.mission_root(mission_id) / "checkpoint-receipts"
        receipt_path = (
            receipts / f"{checkpoint.intent_digest.removeprefix('sha256:')}.json"
        )
        legacy_temporary = receipt_path.with_name(
            f".{receipt_path.name}.tmp-{os.getpid()}"
        )
        assert len(str(receipt_path)) == final_length
        assert len(str(legacy_temporary)) > MAX_PATH

        store.begin_effect(mission_id, checkpoint.step_index)
        outcome = {"value": {"pushed": True}, "records": []}
        reference = store.write_effect_receipt(checkpoint, outcome, ())
        store.complete_step(checkpoint, reference, outcome)

        assert receipt_path.name in {entry.name for entry in os.scandir(receipts)}
        adopted = store.find_effect_receipt(checkpoint)
        assert adopted is not None
        assert adopted[0] == reference
        assert adopted[1]["outcome"] == outcome
        assert store.checkpoint(mission_id, checkpoint.step_index).state == "completed"
        assert store.idempotency_count(mission_id) == 1
        assert validate_runtime_state(store.mission(mission_id)["state"]).valid
    finally:
        store.close()
        _remove_deep_tree(root)


def _case_receipt_persists_when_the_legacy_temporary_name_exceeds_max_path(
    tmp_path: Path,
) -> None:
    _persist_receipt_under_path_length(tmp_path / "a", MAX_PATH - 5)
    _persist_receipt_under_path_length(tmp_path / "b", MAX_PATH + 40)


def _case_durable_write_survives_a_name_at_the_component_limit(
    tmp_path: Path,
) -> None:
    deep = tmp_path / "d"
    deep.mkdir()
    name = "c" * 245 + ".json"
    legacy_temporary = f".{name}.tmp-{os.getpid()}"
    assert len(name) == COMPONENT_LIMIT - 5
    assert len(legacy_temporary) > COMPONENT_LIMIT
    try:
        with _assert_raises(OSError):
            (deep / legacy_temporary).open("xb").close()
        content = b'{"intent_digest":"sha256:probe"}\n'
        _atomic_write(deep / name, content)
        assert name in {entry.name for entry in os.scandir(deep)}
        with open(_deep(deep / name), "rb") as stream:
            assert stream.read() == content
    finally:
        _remove_deep_tree(deep)


class TestMissionStore(unittest.TestCase):
    pass


def _temporary_case(case, *arguments):
    def run_case(_self: unittest.TestCase) -> None:
        with tempfile.TemporaryDirectory(prefix="hive-mind-p06-test-") as root:
            case(Path(root), *arguments)

    return run_case


for _boundary in CRASH_BOUNDARIES:
    for _step_index in range(DURABLE_STEP_COUNT):
        setattr(
            TestMissionStore,
            f"test_crash_{_boundary}_{_step_index:02d}",
            _temporary_case(
                _case_kill_at_every_boundary_resumes_without_duplicate_effects,
                _step_index,
                _boundary,
            ),
        )

for _case in (
    _case_workspace_drift_blocks_with_reconciliation_report,
    _case_lost_workspace_rebuilds_and_completes,
    _case_uncheckpointed_partial_workspace_rebuilds,
    _case_checkpoint_digest_tamper_fails_closed,
    _case_store_version_fails_closed,
    _case_store_crud_idempotency_and_state_schema,
    _case_completed_state_round_trips_and_validates,
    _case_cli_lists_and_resumes_interrupted_mission,
    _case_raw_effect_receipt_is_adopted_without_reexecution,
    _case_effect_interrupted_before_receipt_reconciles_from_write_ahead_record,
    _case_competing_effect_claim_and_missing_wal_fail_closed,
    _case_receipt_tamper_and_path_traversal_fail_closed,
    _case_receipt_persists_when_the_legacy_temporary_name_exceeds_max_path,
    _case_durable_write_survives_a_name_at_the_component_limit,
):
    setattr(
        TestMissionStore,
        f"test_{_case.__name__.removeprefix('_case_')}",
        _temporary_case(_case),
    )
