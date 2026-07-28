"""Durable single-writer mission checkpoints and exactly-once effect adoption.

P06 does not promise exactly-once execution: a process can die after an effect but before
the completion transaction.  It promises exactly-once *effect adoption*.  Canonical tool
intent digests identify effects, content-addressed checkpoint receipts prove observed
outcomes, and resume adopts a matching receipt before considering re-execution.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Sequence

from .autonomy import AutonomyBudget
from .contracts import tool_intent_digest, validate_contract
from .models import Role, utc_now
from .receipts import sha256_digest

STORE_SCHEMA_VERSION = 1


class MissionStoreError(RuntimeError):
    """Base error for durable mission state."""


class StoreVersionError(MissionStoreError):
    """The database schema version is unknown and cannot be opened safely."""


class StoreIntegrityError(MissionStoreError):
    """Persisted state no longer binds to its canonical digest."""


class ReconciliationError(MissionStoreError):
    """A durable workspace differs from its last completed checkpoint."""

    def __init__(self, message: str, report: Mapping[str, Any]) -> None:
        super().__init__(message)
        self.report = dict(report)


class SimulatedCrash(BaseException):
    """Test-only process interruption that bypasses ordinary mission failure handling."""


@dataclass(frozen=True, slots=True)
class StepCheckpoint:
    mission_id: str
    step_index: int
    intent_digest: str
    state: str
    intent: dict[str, Any]
    outcome: dict[str, Any] | None
    receipt_reference: dict[str, str] | None
    execution_count: int


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _git_text(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", "replace").strip()
        raise ReconciliationError(
            f"workspace Git reconciliation failed: {message}",
            {"repository": str(repository), "git_arguments": list(arguments)},
        )
    return completed.stdout.decode("utf-8", "strict").strip()


def workspace_snapshot(container: str | Path) -> dict[str, str]:
    root = Path(container).resolve()
    repository = root / "repo"
    if not repository.is_dir():
        raise FileNotFoundError(repository)
    inventory = sha256()
    for path in sorted(
        (
            item
            for item in repository.rglob("*")
            if ".git" not in item.relative_to(repository).parts
        ),
        key=lambda item: item.relative_to(repository).as_posix(),
    ):
        relative = path.relative_to(repository).as_posix()
        if path.is_symlink():
            inventory.update(b"L\0")
            inventory.update(relative.encode("utf-8"))
            inventory.update(b"\0")
            inventory.update(os.readlink(path).encode("utf-8"))
        elif path.is_file():
            inventory.update(b"F\0")
            inventory.update(relative.encode("utf-8"))
            inventory.update(b"\0")
            inventory.update(path.read_bytes())
    return {
        "head_sha": _git_text(repository, "rev-parse", "HEAD"),
        "head_tree": _git_text(repository, "rev-parse", "HEAD^{tree}"),
        "status_digest": sha256_digest(
            _git_text(
                repository,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ).encode("utf-8")
        ),
        "content_digest": f"sha256:{inventory.hexdigest()}",
    }


def reopen_workspace(
    container: str | Path,
    trusted_root: str | Path,
    *,
    base_sha: str,
    role: Role,
    policy: Any,
    allowance: Any,
    mission_id: str,
    records: Sequence[Mapping[str, Any]],
) -> Any:
    """Recreate the in-memory adapter around an already reconciled workspace."""

    from .git_adapter import GitWorkspace
    from .sandbox import SandboxRunner, SandboxSpec

    root = Path(container).resolve()
    repository = root / "repo"
    hooks = root / "disabled-hooks"
    git_config = repository / ".git" / "hive-mind-isolated-config"
    if not repository.is_dir() or not hooks.is_dir() or not git_config.is_file():
        raise ReconciliationError(
            "workspace adapter metadata is incomplete",
            {"container": str(root)},
        )
    git_name = Path(shutil.which("git") or "git").name
    runner = SandboxRunner(
        SandboxSpec(
            repository,
            argv_allowlist=(git_name, Path(sys.executable).name),
            env_allowlist=(
                "GIT_AUTHOR_DATE",
                "GIT_COMMITTER_DATE",
                "GIT_CONFIG_GLOBAL",
                "GIT_CONFIG_NOSYSTEM",
                "GIT_TERMINAL_PROMPT",
            ),
            timeout_s=60.0,
            max_output_bytes=10_000_000,
        ),
        Path(trusted_root).resolve(),
        allowance,
        policy=policy,
        role=role,
        runner_identity="git-sandbox-runner-v1",
    )
    workspace = GitWorkspace(
        root=repository,
        container_root=root,
        trusted_root=Path(trusted_root).resolve(),
        hooks_root=hooks,
        git_config=git_config,
        base_sha=base_sha,
        runner=runner,
        policy=policy,
        role=role,
        mission_id=mission_id,
        receipts=[dict(record) for record in records],
    )
    branch = _git_text(repository, "branch", "--show-current")
    workspace.branch_name = branch or None
    return workspace


class MissionStore:
    """SQLite current-state store plus immutable idempotency receipt index."""

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / "missions.sqlite3"
        self._lock = RLock()
        self._connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        try:
            self._initialize()
        except BaseException:
            self._connection.close()
            raise

    def _initialize(self) -> None:
        with self._connection:
            self._connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS missions (
                    mission_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    roles_json TEXT NOT NULL,
                    workspaces_json TEXT NOT NULL,
                    budget_json TEXT NOT NULL,
                    report_json TEXT,
                    blocker TEXT
                );
                CREATE TABLE IF NOT EXISTS checkpoints (
                    mission_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    intent_digest TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('intent','completed')),
                    intent_json TEXT NOT NULL,
                    outcome_json TEXT,
                    receipt_ref_json TEXT,
                    execution_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(mission_id, step_index),
                    UNIQUE(mission_id, intent_digest),
                    FOREIGN KEY(mission_id) REFERENCES missions(mission_id)
                );
                CREATE TABLE IF NOT EXISTS idempotency (
                    intent_digest TEXT PRIMARY KEY,
                    mission_id TEXT NOT NULL,
                    step_index INTEGER NOT NULL,
                    receipt_ref_json TEXT NOT NULL,
                    FOREIGN KEY(mission_id, step_index)
                        REFERENCES checkpoints(mission_id, step_index)
                );
                CREATE TRIGGER IF NOT EXISTS idempotency_no_update
                BEFORE UPDATE ON idempotency
                BEGIN SELECT RAISE(ABORT, 'idempotency records are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS idempotency_no_delete
                BEFORE DELETE ON idempotency
                BEGIN SELECT RAISE(ABORT, 'idempotency records are immutable'); END;
                """
            )
            observed = self._connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
            if observed is None:
                self._connection.execute(
                    "INSERT INTO metadata(key,value) VALUES('schema_version',?)",
                    (str(STORE_SCHEMA_VERSION),),
                )
            elif observed["value"] != str(STORE_SCHEMA_VERSION):
                raise StoreVersionError(
                    "unsupported mission-store schema version "
                    f"{observed['value']}; expected {STORE_SCHEMA_VERSION}"
                )

    def close(self) -> None:
        self._connection.close()

    def mission_root(self, mission_id: str) -> Path:
        return self.state_dir / "missions" / mission_id

    def register_mission(
        self,
        mission_id: str,
        config: Mapping[str, Any],
        budget: AutonomyBudget,
    ) -> None:
        roles = {role.value: "pending" for role in Role}
        budget_payload = self._budget_payload(budget)
        state = self._state_document(
            mission_id,
            "active",
            config,
            roles,
            (),
            (),
            None,
        )
        validation = validate_contract("mission-state", state)
        if not validation.valid:
            raise StoreIntegrityError(
                "initial mission state violates schema: "
                + "; ".join(validation.issues)
            )
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO missions(
                    mission_id,status,config_json,state_json,roles_json,
                    workspaces_json,budget_json
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    mission_id,
                    "active",
                    _canonical_json(dict(config)),
                    _canonical_json(state),
                    _canonical_json(roles),
                    "{}",
                    _canonical_json(budget_payload),
                ),
            )
        self.mission_root(mission_id).mkdir(parents=True, exist_ok=True)

    def has_mission(self, mission_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM missions WHERE mission_id=?",
            (mission_id,),
        ).fetchone()
        return row is not None

    def mission(self, mission_id: str) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM missions WHERE mission_id=?",
            (mission_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown mission: {mission_id}")
        return {
            "mission_id": row["mission_id"],
            "status": row["status"],
            "config": json.loads(row["config_json"]),
            "state": json.loads(row["state_json"]),
            "roles": json.loads(row["roles_json"]),
            "workspaces": json.loads(row["workspaces_json"]),
            "budget": json.loads(row["budget_json"]),
            "report": json.loads(row["report_json"]) if row["report_json"] else None,
            "blocker": row["blocker"],
        }

    def list_missions(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT mission_id,status,config_json,blocker FROM missions "
            "ORDER BY mission_id"
        ).fetchall()
        return [
            {
                "mission_id": row["mission_id"],
                "status": row["status"],
                "objective": json.loads(row["config_json"])["objective"],
                "repository": json.loads(row["config_json"])["repository"],
                "blocker": row["blocker"],
            }
            for row in rows
        ]

    def record_intent(
        self,
        mission_id: str,
        step_index: int,
        intent: Mapping[str, Any],
    ) -> StepCheckpoint:
        digest = tool_intent_digest(intent)
        if intent.get("action_digest") != digest:
            raise StoreIntegrityError("intent action_digest is not canonical")
        validation = validate_contract("tool-intent", dict(intent))
        if not validation.valid:
            raise StoreIntegrityError(
                "checkpoint intent violates schema: "
                + "; ".join(validation.issues)
            )
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT * FROM checkpoints WHERE mission_id=? AND step_index=?",
                (mission_id, step_index),
            ).fetchone()
            if existing is None:
                self._connection.execute(
                    """
                    INSERT INTO checkpoints(
                        mission_id,step_index,intent_digest,state,intent_json
                    ) VALUES(?,?,?,?,?)
                    """,
                    (
                        mission_id,
                        step_index,
                        digest,
                        "intent",
                        _canonical_json(dict(intent)),
                    ),
                )
        return self.checkpoint(mission_id, step_index)

    def checkpoint_for_intent(
        self,
        mission_id: str,
        intent: Mapping[str, Any],
        *,
        minimum_step_index: int = 0,
    ) -> StepCheckpoint:
        """Return or atomically allocate the checkpoint bound to an intent digest."""

        if minimum_step_index < 0:
            raise ValueError("minimum checkpoint index cannot be negative")
        digest = tool_intent_digest(intent)
        if intent.get("action_digest") != digest:
            raise StoreIntegrityError("intent action_digest is not canonical")
        validation = validate_contract("tool-intent", dict(intent))
        if not validation.valid:
            raise StoreIntegrityError(
                "checkpoint intent violates schema: "
                + "; ".join(validation.issues)
            )
        with self._lock, self._connection:
            existing = self._connection.execute(
                """
                SELECT step_index FROM checkpoints
                WHERE mission_id=? AND intent_digest=?
                """,
                (mission_id, digest),
            ).fetchone()
            if existing is None:
                next_step = int(
                    self._connection.execute(
                        """
                        SELECT COALESCE(MAX(step_index),-1)+1 FROM checkpoints
                        WHERE mission_id=?
                        """,
                        (mission_id,),
                    ).fetchone()[0]
                )
                step_index = max(minimum_step_index, next_step)
                self._connection.execute(
                    """
                    INSERT INTO checkpoints(
                        mission_id,step_index,intent_digest,state,intent_json
                    ) VALUES(?,?,?,?,?)
                    """,
                    (
                        mission_id,
                        step_index,
                        digest,
                        "intent",
                        _canonical_json(dict(intent)),
                    ),
                )
            else:
                step_index = int(existing["step_index"])
        checkpoint = self.checkpoint(mission_id, step_index)
        if checkpoint.intent != dict(intent):
            raise StoreIntegrityError(
                "idempotency digest maps to a different canonical intent"
            )
        return checkpoint

    def checkpoint(
        self,
        mission_id: str,
        step_index: int,
    ) -> StepCheckpoint:
        row = self._connection.execute(
            "SELECT * FROM checkpoints WHERE mission_id=? AND step_index=?",
            (mission_id, step_index),
        ).fetchone()
        if row is None:
            raise KeyError((mission_id, step_index))
        intent = json.loads(row["intent_json"])
        observed = tool_intent_digest(intent)
        if (
            row["intent_digest"] != observed
            or intent.get("action_digest") != observed
        ):
            raise StoreIntegrityError(
                f"checkpoint {step_index} digest no longer binds its intent"
            )
        outcome = json.loads(row["outcome_json"]) if row["outcome_json"] else None
        receipt = (
            json.loads(row["receipt_ref_json"])
            if row["receipt_ref_json"]
            else None
        )
        return StepCheckpoint(
            mission_id,
            step_index,
            row["intent_digest"],
            row["state"],
            intent,
            outcome,
            receipt,
            int(row["execution_count"]),
        )

    def checkpoints(self, mission_id: str) -> list[StepCheckpoint]:
        indices = self._connection.execute(
            "SELECT step_index FROM checkpoints WHERE mission_id=? ORDER BY step_index",
            (mission_id,),
        ).fetchall()
        return [self.checkpoint(mission_id, int(row["step_index"])) for row in indices]

    def begin_effect(self, mission_id: str, step_index: int) -> None:
        with self._lock, self._connection:
            row = self._connection.execute(
                """
                SELECT state,execution_count FROM checkpoints
                WHERE mission_id=? AND step_index=?
                """,
                (mission_id, step_index),
            ).fetchone()
            if row is None or row["state"] != "intent":
                raise StoreIntegrityError("effect began outside an intent checkpoint")
            if int(row["execution_count"]) > 0:
                return
            cursor = self._connection.execute(
                """
                UPDATE checkpoints
                SET execution_count=execution_count+1
                WHERE mission_id=? AND step_index=? AND state='intent'
                    AND execution_count=0
                """,
                (mission_id, step_index),
            )
            if cursor.rowcount != 1:
                raise StoreIntegrityError("effect began outside an intent checkpoint")

    def write_effect_receipt(
        self,
        checkpoint: StepCheckpoint,
        outcome: Mapping[str, Any],
        records: Sequence[Mapping[str, Any]],
    ) -> dict[str, str]:
        synthetic = {
            "schema_version": 1,
            "receipt_id": f"REC-P06-{checkpoint.mission_id}-{checkpoint.step_index}",
            "action_id": checkpoint.intent["action_id"],
            "provider": "p06-mission-store-v1",
            "execution_id": (
                f"EXEC-P06-{checkpoint.mission_id}-{checkpoint.step_index}"
            ),
            "mission_id": checkpoint.mission_id,
            "state_ref": checkpoint.intent["state_ref"],
            "actor_id": checkpoint.intent["actor_id"],
            "policy_decision_ref": checkpoint.intent["policy_decision_ref"],
            "lease_id": checkpoint.intent["lease_id"],
            "action_kind": checkpoint.intent["kind"],
            "action_digest": checkpoint.intent_digest,
            "executed": True,
            "result": "succeeded",
            "observed_at": utc_now(),
            "artifacts": [],
            "verified_by": "p06-checkpoint-store-v1",
        }
        validation = validate_contract("tool-receipt", synthetic)
        if not validation.valid:
            raise StoreIntegrityError(
                "checkpoint receipt violates schema: "
                + "; ".join(validation.issues)
            )
        wrapper = {
            "intent_digest": checkpoint.intent_digest,
            "outcome": dict(outcome),
            "records": [dict(record) for record in records],
            "receipt": synthetic,
        }
        encoded = (_canonical_json(wrapper) + "\n").encode("utf-8")
        path = (
            self.mission_root(checkpoint.mission_id)
            / "checkpoint-receipts"
            / f"{checkpoint.intent_digest.removeprefix('sha256:')}.json"
        )
        if path.exists():
            existing = path.read_bytes()
            existing_wrapper = json.loads(existing)
            if existing_wrapper.get("intent_digest") != checkpoint.intent_digest:
                raise StoreIntegrityError("checkpoint receipt path was reused")
            encoded = existing
        else:
            _atomic_write(path, encoded)
        return {
            "path": path.relative_to(self.state_dir).as_posix(),
            "digest": sha256_digest(encoded),
        }

    def find_effect_receipt(
        self,
        checkpoint: StepCheckpoint,
    ) -> tuple[dict[str, str], dict[str, Any]] | None:
        path = (
            self.mission_root(checkpoint.mission_id)
            / "checkpoint-receipts"
            / f"{checkpoint.intent_digest.removeprefix('sha256:')}.json"
        )
        if not path.is_file():
            return None
        content = path.read_bytes()
        wrapper = json.loads(content)
        if wrapper.get("intent_digest") != checkpoint.intent_digest:
            raise StoreIntegrityError("effect receipt belongs to another intent")
        reference = {
            "path": path.relative_to(self.state_dir).as_posix(),
            "digest": sha256_digest(content),
        }
        return reference, wrapper

    def complete_step(
        self,
        checkpoint: StepCheckpoint,
        reference: Mapping[str, str],
        outcome: Mapping[str, Any],
        *,
        budget: AutonomyBudget | None = None,
    ) -> None:
        encoded_reference = _canonical_json(dict(reference))
        encoded_outcome = _canonical_json(dict(outcome))
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT * FROM idempotency WHERE intent_digest=?",
                (checkpoint.intent_digest,),
            ).fetchone()
            if existing is None:
                self._connection.execute(
                    """
                    INSERT INTO idempotency(
                        intent_digest,mission_id,step_index,receipt_ref_json
                    ) VALUES(?,?,?,?)
                    """,
                    (
                        checkpoint.intent_digest,
                        checkpoint.mission_id,
                        checkpoint.step_index,
                        encoded_reference,
                    ),
                )
            elif (
                existing["mission_id"] != checkpoint.mission_id
                or int(existing["step_index"]) != checkpoint.step_index
                or existing["receipt_ref_json"] != encoded_reference
            ):
                raise StoreIntegrityError("idempotency digest maps to another effect")
            self._connection.execute(
                """
                UPDATE checkpoints
                SET state='completed',outcome_json=?,receipt_ref_json=?
                WHERE mission_id=? AND step_index=? AND intent_digest=?
                """,
                (
                    encoded_outcome,
                    encoded_reference,
                    checkpoint.mission_id,
                    checkpoint.step_index,
                    checkpoint.intent_digest,
                ),
            )
            if budget is not None:
                self._connection.execute(
                    "UPDATE missions SET budget_json=? WHERE mission_id=?",
                    (
                        _canonical_json(self._budget_payload(budget)),
                        checkpoint.mission_id,
                    ),
                )
        self.refresh_state(checkpoint.mission_id)

    def idempotency_count(self, mission_id: str) -> int:
        return int(
            self._connection.execute(
                "SELECT COUNT(*) FROM idempotency WHERE mission_id=?",
                (mission_id,),
            ).fetchone()[0]
        )

    def update_workspace(
        self,
        mission_id: str,
        key: str,
        container: str | Path,
    ) -> None:
        mission = self.mission(mission_id)
        workspaces = mission["workspaces"]
        workspaces[key] = {
            "container": str(Path(container).resolve()),
            "snapshot": workspace_snapshot(container),
        }
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE missions SET workspaces_json=? WHERE mission_id=?",
                (_canonical_json(workspaces), mission_id),
            )

    def reconcile_workspaces(self, mission_id: str) -> set[str]:
        mission = self.mission(mission_id)
        missing: set[str] = set()
        for key, record in mission["workspaces"].items():
            container = Path(record["container"])
            if not (container / "repo").is_dir():
                missing.add(key)
                continue
            observed = workspace_snapshot(container)
            if observed != record["snapshot"]:
                report = {
                    "mission_id": mission_id,
                    "workspace": key,
                    "container": str(container),
                    "expected": record["snapshot"],
                    "observed": observed,
                }
                self.mark_status(
                    mission_id,
                    "blocked",
                    blocker="workspace digest mismatch",
                )
                raise ReconciliationError(
                    f"workspace {key} digest mismatch",
                    report,
                )
        return missing

    def mark_role(self, mission_id: str, role: Role, status: str) -> None:
        mission = self.mission(mission_id)
        roles = mission["roles"]
        roles[role.value] = status
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE missions SET roles_json=? WHERE mission_id=?",
                (_canonical_json(roles), mission_id),
            )
        self.refresh_state(mission_id, active_role=role)

    def update_budget(self, mission_id: str, budget: AutonomyBudget) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE missions SET budget_json=? WHERE mission_id=?",
                (_canonical_json(self._budget_payload(budget)), mission_id),
            )

    def mark_status(
        self,
        mission_id: str,
        status: str,
        *,
        blocker: str | None = None,
        report: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                UPDATE missions
                SET status=?,blocker=?,report_json=COALESCE(?,report_json)
                WHERE mission_id=?
                """,
                (
                    status,
                    blocker,
                    _canonical_json(dict(report)) if report is not None else None,
                    mission_id,
                ),
            )
        self.refresh_state(mission_id)

    def refresh_state(
        self,
        mission_id: str,
        *,
        active_role: Role | None = None,
    ) -> dict[str, Any]:
        mission = self.mission(mission_id)
        checkpoints = self.checkpoints(mission_id)
        wrappers: list[dict[str, Any]] = []
        for checkpoint in checkpoints:
            if checkpoint.receipt_reference is None:
                continue
            path = self.state_dir / Path(
                *checkpoint.receipt_reference["path"].split("/")
            )
            wrapper = json.loads(path.read_text(encoding="utf-8"))
            wrappers.append(wrapper)
        state = self._state_document(
            mission_id,
            mission["status"],
            mission["config"],
            mission["roles"],
            [checkpoint.intent for checkpoint in checkpoints],
            [wrapper["receipt"] for wrapper in wrappers],
            active_role,
            blocker=mission["blocker"],
            receipt_paths=[
                checkpoint.receipt_reference["path"]
                for checkpoint in checkpoints
                if checkpoint.receipt_reference is not None
            ],
        )
        validation = validate_contract("mission-state", state)
        if not validation.valid:
            raise StoreIntegrityError(
                "persisted mission state violates schema: "
                + "; ".join(validation.issues)
            )
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE missions SET state_json=? WHERE mission_id=?",
                (_canonical_json(state), mission_id),
            )
        return state

    @staticmethod
    def _budget_payload(budget: AutonomyBudget) -> dict[str, int | float]:
        return {
            "max_episodes": budget.max_episodes,
            "max_tool_calls": budget.max_tool_calls,
            "max_compute_units": budget.max_compute_units,
            "max_tool_calls_per_episode": budget.max_tool_calls_per_episode,
            "max_compute_units_per_episode": budget.max_compute_units_per_episode,
            "episodes_used": budget.episodes_used,
            "tool_calls_used": budget.tool_calls_used,
            "compute_units_used": budget.compute_units_used,
        }

    @staticmethod
    def _state_document(
        mission_id: str,
        status: str,
        config: Mapping[str, Any],
        roles: Mapping[str, str],
        intents: Sequence[Mapping[str, Any]],
        receipts: Sequence[Mapping[str, Any]],
        active_role: Role | None,
        *,
        blocker: str | None = None,
        receipt_paths: Sequence[str] = (),
    ) -> dict[str, Any]:
        complete = status == "succeeded"
        blocked = status in {"failed", "blocked"}
        role = active_role or next(
            (
                Role(name)
                for name, role_status in roles.items()
                if role_status != "succeeded"
            ),
            Role.OPTIMIZER,
        )
        phase_by_role = {
            Role.ORCHESTRATOR: "intake",
            Role.EXPLORER: "discover",
            Role.ARCHITECT: "design",
            Role.BUILDER: "build",
            Role.CURATOR: "validate",
            Role.INTEGRATOR: "integrate",
            Role.STEWARD: "maintain",
            Role.OPTIMIZER: "optimize",
        }
        state_ref = f"MISSION_STATE:{mission_id}:1"
        return {
            "schema_version": 3,
            "mission": {
                "id": mission_id,
                "state_version": 1,
                "objective": config["objective"],
                "active_phase": (
                    "complete"
                    if complete
                    else "blocked"
                    if blocked
                    else phase_by_role[role]
                ),
                "active_role": role.value,
                "status": (
                    "complete"
                    if complete
                    else "blocked"
                    if blocked
                    else "active"
                ),
                "source_pack_fingerprint": config["source_pack_fingerprint"],
            },
            "role_runs": [
                {
                    "role": item.value,
                    "actor_id": f"agent-{item.value}",
                    "status": (
                        "succeeded"
                        if roles.get(item.value) == "succeeded"
                        else "failed"
                        if roles.get(item.value) == "failed"
                        else "running"
                        if item is role and not complete
                        else "pending"
                    ),
                    "evidence_refs": [],
                }
                for item in Role
            ],
            "court_cases": [],
            "evidence": [
                {"kind": "checkpoint-receipt", "path": path}
                for path in receipt_paths
            ],
            "proposed_actions": [dict(intent) for intent in intents],
            "tool_receipts": [dict(receipt) for receipt in receipts],
            "blockers": [blocker or "mission failed"] if blocked else [],
            "independent_verification": (
                [
                    {
                        "actor_id": "p06-store-verifier",
                        "evidence_refs": list(receipt_paths) or ["mission-report"],
                    }
                ]
                if complete
                else []
            ),
            "next_action": {
                "owner_role": role.value,
                "description": (
                    "mission complete"
                    if complete
                    else "resolve blocker"
                    if blocked
                    else "resume from first incomplete checkpoint"
                ),
                "success_condition": (
                    "verified delivery remains reproducible"
                    if complete
                    else "checkpoint evidence and workspace reconcile"
                ),
            },
            "handoff": {
                "schema_version": 1,
                "handoff_id": f"HANDOFF-{mission_id}",
                "mission_id": mission_id,
                "state_ref": state_ref,
                "from_actor_id": "agent-orchestrator",
                "to_role": role.value,
                "unresolved_items": [blocker] if blocker else [],
                "verified_artifacts": list(receipt_paths),
                "next_action": (
                    "retain verified result"
                    if complete
                    else "resume durable mission"
                ),
                "resume_instruction": f"hive-mind resume {mission_id}",
                "created_at": utc_now(),
            },
        }


async def resume_mission(
    store: MissionStore,
    mission_id: str,
) -> Any:
    """Reconcile and continue an interrupted scripted repository mission."""

    from .github_adapter import GitHubClient, GitHubDeliveryTarget
    from .ledger import EvidenceLedger
    from .mission import RepositoryMission, ScriptedRepositoryBackend
    from .models import AutonomyLevel
    from .policy import PolicyEngine

    mission = store.mission(mission_id)
    if mission["status"] == "succeeded":
        raise MissionStoreError("mission is already complete")
    if mission["status"] == "blocked":
        raise ReconciliationError(
            "mission is blocked",
            {
                "mission_id": mission_id,
                "blocker": mission["blocker"],
            },
        )
    config = mission["config"]
    if config.get("backend") != "scripted":
        raise MissionStoreError("P06 resume supports scripted repository missions only")
    missing = store.reconcile_workspaces(mission_id)
    budget_data = mission["budget"]
    budget = AutonomyBudget(**budget_data)
    ledger = EvidenceLedger(store.state_dir / "evidence-ledger.sqlite3")
    backend = ScriptedRepositoryBackend(
        config["scripted_variant"],
        test_argv=config["test_argv"],
        criterion_argv=config["criterion_argv"],
    )
    github_delivery = None
    github_config = config.get("github_delivery")
    policy = PolicyEngine(AutonomyLevel.REPOSITORY)
    if isinstance(github_config, Mapping):
        github_client = GitHubClient(
            str(github_config["owner"]),
            str(github_config["repository"]),
            store.mission_root(mission_id) / "staging" / "evidence",
            token_env=str(github_config["token_env"]),
            api_base=str(github_config["api_base"]),
            policy=policy,
            ledger=ledger,
            mission_store=store,
            mission_id=mission_id,
        )
        github_delivery = GitHubDeliveryTarget(
            github_client,
            str(github_config["base"]),
            str(github_config["title"]),
            str(github_config["body"]),
            Path(str(github_config["desired_rules_path"])),
            int(github_config["max_check_attempts"]),
            float(github_config["check_interval_s"]),
        )
    runner = RepositoryMission(
        config["repository"],
        config["objective"],
        acceptance_criteria=tuple(config["acceptance_criteria"]),
        backend=backend,
        pin=config["pin"],
        output_dir=config["output_dir"],
        policy=policy,
        budget=budget,
        ledger=ledger,
        mission_store=store,
        github_delivery=github_delivery,
        _run_id=mission_id,
        _resume=True,
        _missing_workspaces=missing,
    )
    try:
        return await runner.run()
    finally:
        ledger.close()
