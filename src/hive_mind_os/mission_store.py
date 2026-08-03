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
from .custody import CustodyError, Ed25519CustodyVerifier, ExternalCustodyAdapter
from .durable_repository_model import (
    DurableRepositoryModelError,
    agent_result_document,
    agent_result_from_document,
)
from .models import Role, utc_now
from .receipts import sha256_digest
from .source_custody import (
    SourceCustodyError,
    SourceCustodyVerifier,
    SourceLock,
    SourceLockEvidence,
)

STORE_SCHEMA_VERSION = 5


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


def _configuration_digest(config: Mapping[str, Any]) -> str:
    return sha256_digest(_canonical_json(dict(config)).encode("utf-8"))


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
    risk: Any,
    policy: Any,
    allowance: Any,
    mission_id: str,
    records: Sequence[Mapping[str, Any]],
    source_lock: SourceLock | None = None,
    source_lock_evidence: SourceLockEvidence | None = None,
) -> Any:
    """Recreate the in-memory adapter around an already reconciled workspace."""

    from .git_adapter import GitWorkspace
    from .sandbox import SandboxRunner, SandboxSpec

    if (source_lock is None) != (source_lock_evidence is None):
        raise ReconciliationError(
            "authenticated source recovery context is incomplete",
            {"mission_id": mission_id, "container": str(container)},
        )
    if source_lock is not None:
        assert source_lock_evidence is not None
        expected_state_ref = f"MISSION_STATE:{mission_id}:1"
        if source_lock.to_dict() != source_lock_evidence.source_lock.to_dict():
            raise ReconciliationError(
                "authenticated source recovery lock does not match its sealed evidence",
                {"mission_id": mission_id, "container": str(container)},
            )
        if (
            source_lock.mission_id != mission_id
            or source_lock.state_ref != expected_state_ref
        ):
            raise ReconciliationError(
                "authenticated source recovery bindings do not match the workspace",
                {
                    "mission_id": mission_id,
                    "state_ref": expected_state_ref,
                    "container": str(container),
                },
            )

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
        risk=risk,
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
        risk=risk,
        mission_id=mission_id,
        receipts=[dict(record) for record in records],
        source_lock=source_lock,
        source_lock_evidence=source_lock_evidence,
        state_ref=source_lock.state_ref if source_lock is not None else None,
    )
    branch = _git_text(repository, "branch", "--show-current")
    workspace.branch_name = branch or None
    return workspace


class MissionStore:
    """SQLite current-state store plus immutable idempotency receipt index."""

    def __init__(
        self,
        state_dir: str | Path,
        *,
        custody_verifier: Ed25519CustodyVerifier | None = None,
        require_authenticated_custody: bool = False,
    ) -> None:
        if require_authenticated_custody and custody_verifier is None:
            raise ValueError(
                "authenticated custody mode requires an external custody verifier"
            )
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / "missions.sqlite3"
        self._lock = RLock()
        self._connection = sqlite3.connect(
            self.path,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self.custody_verifier = custody_verifier
        self.require_authenticated_custody = require_authenticated_custody
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
                    config_digest TEXT NOT NULL,
                    config_custody_json TEXT,
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
                CREATE TABLE IF NOT EXISTS mission_role_work_plans (
                    mission_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    work_item_id TEXT NOT NULL,
                    plan_digest TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(mission_id, role),
                    UNIQUE(mission_id, ordinal),
                    UNIQUE(mission_id, work_item_id),
                    FOREIGN KEY(mission_id) REFERENCES missions(mission_id)
                );
                CREATE TABLE IF NOT EXISTS mission_role_inputs (
                    mission_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    work_plan_digest TEXT NOT NULL,
                    input_digest TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(mission_id, role),
                    UNIQUE(mission_id, input_digest),
                    FOREIGN KEY(mission_id, role)
                        REFERENCES mission_role_work_plans(mission_id, role)
                );
                CREATE TABLE IF NOT EXISTS mission_role_effects (
                    mission_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    input_digest TEXT NOT NULL,
                    effect_ordinal INTEGER NOT NULL,
                    step_index INTEGER NOT NULL,
                    intent_digest TEXT NOT NULL,
                    PRIMARY KEY(mission_id, role, effect_ordinal),
                    UNIQUE(mission_id, step_index),
                    FOREIGN KEY(mission_id, role)
                        REFERENCES mission_role_inputs(mission_id, role),
                    FOREIGN KEY(mission_id, step_index)
                        REFERENCES checkpoints(mission_id, step_index)
                );
                CREATE TABLE IF NOT EXISTS mission_role_completions (
                    mission_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    input_digest TEXT NOT NULL,
                    completion_digest TEXT NOT NULL,
                    completion_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(mission_id, role),
                    UNIQUE(mission_id, completion_digest),
                    FOREIGN KEY(mission_id, role)
                        REFERENCES mission_role_inputs(mission_id, role)
                );
                CREATE TABLE IF NOT EXISTS mission_role_admissions (
                    mission_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    input_digest TEXT NOT NULL,
                    admission_digest TEXT NOT NULL,
                    admission_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(mission_id, role),
                    UNIQUE(mission_id, admission_digest),
                    FOREIGN KEY(mission_id, role)
                        REFERENCES mission_role_inputs(mission_id, role)
                );
                CREATE TRIGGER IF NOT EXISTS mission_role_work_plans_no_update
                BEFORE UPDATE ON mission_role_work_plans
                BEGIN SELECT RAISE(ABORT, 'model role work plans are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS mission_role_work_plans_no_delete
                BEFORE DELETE ON mission_role_work_plans
                BEGIN SELECT RAISE(ABORT, 'model role work plans are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS mission_role_inputs_no_update
                BEFORE UPDATE ON mission_role_inputs
                BEGIN SELECT RAISE(ABORT, 'model role inputs are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS mission_role_inputs_no_delete
                BEFORE DELETE ON mission_role_inputs
                BEGIN SELECT RAISE(ABORT, 'model role inputs are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS mission_role_effects_no_update
                BEFORE UPDATE ON mission_role_effects
                BEGIN SELECT RAISE(ABORT, 'model role effects are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS mission_role_effects_no_delete
                BEFORE DELETE ON mission_role_effects
                BEGIN SELECT RAISE(ABORT, 'model role effects are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS mission_role_completions_no_update
                BEFORE UPDATE ON mission_role_completions
                BEGIN SELECT RAISE(ABORT, 'model role completions are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS mission_role_completions_no_delete
                BEFORE DELETE ON mission_role_completions
                BEGIN SELECT RAISE(ABORT, 'model role completions are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS mission_role_admissions_no_update
                BEFORE UPDATE ON mission_role_admissions
                BEGIN SELECT RAISE(ABORT, 'model role admissions are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS mission_role_admissions_no_delete
                BEFORE DELETE ON mission_role_admissions
                BEGIN SELECT RAISE(ABORT, 'model role admissions are append-only'); END;
                """
            )
            observed = self._connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
            if observed is not None and observed["value"] not in {"1", "2", "3", "4", "5"}:
                raise StoreVersionError(
                    "unsupported mission-store schema version "
                    f"{observed['value']}; expected {STORE_SCHEMA_VERSION}"
                )
            columns = {
                str(row["name"])
                for row in self._connection.execute("PRAGMA table_info(missions)")
            }
            if "config_digest" not in columns:
                self._connection.execute(
                    "ALTER TABLE missions ADD COLUMN config_digest TEXT"
                )
                rows = self._connection.execute(
                    "SELECT mission_id,config_json FROM missions"
                ).fetchall()
                for row in rows:
                    config = json.loads(row["config_json"])
                    self._connection.execute(
                        "UPDATE missions SET config_digest=? WHERE mission_id=?",
                        (_configuration_digest(config), row["mission_id"]),
                    )
            if "config_custody_json" not in columns:
                self._connection.execute(
                    "ALTER TABLE missions ADD COLUMN config_custody_json TEXT"
                )
            if observed is None:
                self._connection.execute(
                    "INSERT INTO metadata(key,value) VALUES('schema_version',?)",
                    (str(STORE_SCHEMA_VERSION),),
                )
            elif observed["value"] in {"1", "2", "3", "4"}:
                self._connection.execute(
                    "UPDATE metadata SET value=? WHERE key='schema_version'",
                    (str(STORE_SCHEMA_VERSION),),
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
        *,
        configuration_attestation: Mapping[str, object] | None = None,
    ) -> None:
        roles = {role.value: "pending" for role in Role}
        config_payload = dict(config)
        config_digest = _configuration_digest(config_payload)
        custody_payload: dict[str, object] | None = None
        if self.custody_verifier is not None:
            if configuration_attestation is None:
                if self.require_authenticated_custody:
                    raise StoreIntegrityError(
                        "authenticated custody mode requires a signed mission configuration"
                    )
            else:
                custody_payload = self.custody_verifier.verify_configuration(
                    mission_id,
                    config_payload,
                    configuration_attestation,
                )
        elif configuration_attestation is not None:
            raise StoreIntegrityError(
                "configuration custody was supplied without a custody verifier"
            )
        budget_payload = self._budget_payload(budget)
        state = self._state_document(
            mission_id,
            "active",
            config_payload,
            roles,
            (),
            (),
            None,
        )
        validation = validate_contract("mission-state", state)
        if not validation.valid:
            raise StoreIntegrityError(
                "initial mission state violates schema: " + "; ".join(validation.issues)
            )
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO missions(
                    mission_id,status,config_json,config_digest,config_custody_json,state_json,roles_json,
                    workspaces_json,budget_json
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    mission_id,
                    "active",
                    _canonical_json(config_payload),
                    config_digest,
                    _canonical_json(custody_payload) if custody_payload is not None else None,
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
        config = self._checked_config(row)
        configuration_custody = self._checked_configuration_custody(
            row,
            config,
        )
        return {
            "mission_id": row["mission_id"],
            "status": row["status"],
            "config": config,
            "configuration_custody": configuration_custody,
            "state": json.loads(row["state_json"]),
            "roles": json.loads(row["roles_json"]),
            "workspaces": json.loads(row["workspaces_json"]),
            "budget": json.loads(row["budget_json"]),
            "report": json.loads(row["report_json"]) if row["report_json"] else None,
            "blocker": row["blocker"],
        }

    def list_missions(self) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT mission_id,status,config_json,config_digest,blocker FROM missions "
            "ORDER BY mission_id"
        ).fetchall()
        return [
            {
                "mission_id": row["mission_id"],
                "status": row["status"],
                "objective": self._checked_config(row)["objective"],
                "repository": self._checked_config(row)["repository"],
                "blocker": row["blocker"],
            }
            for row in rows
        ]

    @staticmethod
    def _checked_config(row: sqlite3.Row) -> dict[str, Any]:
        config = json.loads(row["config_json"])
        if not isinstance(config, dict):
            raise StoreIntegrityError("mission configuration is not an object")
        observed = _configuration_digest(config)
        if row["config_digest"] != observed:
            raise StoreIntegrityError(
                "mission configuration no longer binds its canonical digest"
            )
        return config

    def _checked_configuration_custody(
        self,
        row: sqlite3.Row,
        config: Mapping[str, Any],
    ) -> dict[str, object] | None:
        encoded = row["config_custody_json"]
        if encoded is None:
            if self.require_authenticated_custody:
                raise StoreIntegrityError(
                    "authenticated custody mode cannot open a legacy unsigned configuration"
                )
            return None
        try:
            attestation = json.loads(encoded)
        except json.JSONDecodeError as error:
            raise StoreIntegrityError("mission configuration custody is malformed") from error
        if not isinstance(attestation, dict):
            raise StoreIntegrityError("mission configuration custody is not an object")
        if self.custody_verifier is None:
            raise StoreIntegrityError(
                "mission stores a custody attestation but no verifier is configured"
            )
        try:
            return self.custody_verifier.verify_configuration(
                str(row["mission_id"]),
                config,
                attestation,
            )
        except (CustodyError, ValueError) as error:
            raise StoreIntegrityError(
                f"mission configuration custody is invalid: {error}"
            ) from None

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
                "checkpoint intent violates schema: " + "; ".join(validation.issues)
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
                "checkpoint intent violates schema: " + "; ".join(validation.issues)
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
        if row["intent_digest"] != observed or intent.get("action_digest") != observed:
            raise StoreIntegrityError(
                f"checkpoint {step_index} digest no longer binds its intent"
            )
        outcome = json.loads(row["outcome_json"]) if row["outcome_json"] else None
        receipt = (
            json.loads(row["receipt_ref_json"]) if row["receipt_ref_json"] else None
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
        current = self.checkpoint(checkpoint.mission_id, checkpoint.step_index)
        if (
            current.intent_digest != checkpoint.intent_digest
            or current.state != "intent"
            or current.execution_count != 1
        ):
            raise StoreIntegrityError(
                "checkpoint receipt may be written only after its single effect start"
            )
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
                "checkpoint receipt violates schema: " + "; ".join(validation.issues)
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
            self._validated_effect_wrapper(current, json.loads(existing))
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
        current = self.checkpoint(checkpoint.mission_id, checkpoint.step_index)
        if current.intent_digest != checkpoint.intent_digest:
            raise StoreIntegrityError("checkpoint reference does not bind its intent")
        path = (
            self.mission_root(checkpoint.mission_id)
            / "checkpoint-receipts"
            / f"{checkpoint.intent_digest.removeprefix('sha256:')}.json"
        )
        if not path.is_file():
            return None
        content = path.read_bytes()
        wrapper = self._validated_effect_wrapper(current, json.loads(content))
        reference = {
            "path": path.relative_to(self.state_dir).as_posix(),
            "digest": sha256_digest(content),
        }
        if current.execution_count != 1:
            raise StoreIntegrityError(
                "effect receipt exists before its effect was durably started"
            )
        if (
            current.receipt_reference is not None
            and current.receipt_reference != reference
        ):
            raise StoreIntegrityError("completed checkpoint receipt reference changed")
        return reference, wrapper

    @staticmethod
    def _validated_effect_wrapper(
        checkpoint: StepCheckpoint,
        wrapper: object,
    ) -> dict[str, Any]:
        if not isinstance(wrapper, dict):
            raise StoreIntegrityError("checkpoint receipt is not an object")
        if wrapper.get("intent_digest") != checkpoint.intent_digest:
            raise StoreIntegrityError("effect receipt belongs to another intent")
        outcome = wrapper.get("outcome")
        records = wrapper.get("records")
        receipt = wrapper.get("receipt")
        if not isinstance(outcome, dict) or not isinstance(records, list):
            raise StoreIntegrityError(
                "checkpoint receipt outcome or records are malformed"
            )
        if any(not isinstance(record, dict) for record in records):
            raise StoreIntegrityError("checkpoint receipt records are malformed")
        if not isinstance(receipt, dict):
            raise StoreIntegrityError("checkpoint receipt lacks a tool receipt")
        validation = validate_contract("tool-receipt", receipt)
        if not validation.valid:
            raise StoreIntegrityError(
                "checkpoint receipt violates schema: " + "; ".join(validation.issues)
            )
        bindings = {
            "mission_id": checkpoint.mission_id,
            "state_ref": checkpoint.intent["state_ref"],
            "actor_id": checkpoint.intent["actor_id"],
            "policy_decision_ref": checkpoint.intent["policy_decision_ref"],
            "lease_id": checkpoint.intent["lease_id"],
            "action_kind": checkpoint.intent["kind"],
            "action_digest": checkpoint.intent_digest,
        }
        for field, expected in bindings.items():
            if receipt.get(field) != expected:
                raise StoreIntegrityError(
                    f"checkpoint receipt {field} does not bind its intent"
                )
        if receipt.get("executed") is not True or receipt.get("result") != "succeeded":
            raise StoreIntegrityError("checkpoint receipt does not record success")
        return wrapper

    def complete_step(
        self,
        checkpoint: StepCheckpoint,
        reference: Mapping[str, str],
        outcome: Mapping[str, Any],
        *,
        budget: AutonomyBudget | None = None,
    ) -> None:
        found = self.find_effect_receipt(checkpoint)
        if found is None:
            raise StoreIntegrityError("completed checkpoint lacks its effect receipt")
        observed_reference, wrapper = found
        if dict(reference) != observed_reference:
            raise StoreIntegrityError(
                "checkpoint completion reference is not canonical"
            )
        if wrapper["outcome"] != dict(outcome):
            raise StoreIntegrityError(
                "checkpoint completion outcome differs from receipt"
            )
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

    @staticmethod
    def _checked_journal_document(
        encoded: str,
        digest: str,
        label: str,
    ) -> dict[str, Any]:
        try:
            document = json.loads(encoded)
        except json.JSONDecodeError as error:
            raise StoreIntegrityError(f"{label} is malformed") from error
        if not isinstance(document, dict):
            raise StoreIntegrityError(f"{label} is not an object")
        if _configuration_digest(document) != digest:
            raise StoreIntegrityError(f"{label} no longer binds its canonical digest")
        return document

    def register_role_work_plans(
        self,
        mission_id: str,
        plans: Sequence[Mapping[str, Any]],
    ) -> None:
        """Append deterministic model work plans, or verify exact prior records."""

        if len(plans) != len(Role):
            raise StoreIntegrityError("durable model missions require every lifecycle work plan")
        normalized: list[tuple[int, str, str, str, str]] = []
        observed_roles: set[str] = set()
        for ordinal, plan in enumerate(plans):
            document = dict(plan)
            if set(document) != {
                "schema_version",
                "ordinal",
                "role",
                "work_item_id",
                "instruction",
                "dependencies",
                "role_contract_digest",
                "source_pack_fingerprint",
                "acceptance_specification_digest",
                "profile_digest",
            }:
                raise StoreIntegrityError("durable model work plan has an unknown shape")
            role = document.get("role")
            work_item_id = document.get("work_item_id")
            if (
                document.get("schema_version") != 1
                or document.get("ordinal") != ordinal
                or role not in {item.value for item in Role}
                or not isinstance(work_item_id, str)
                or not work_item_id.startswith("WORK-")
                or not isinstance(document.get("instruction"), str)
                or not isinstance(document.get("dependencies"), list)
                or any(not isinstance(item, str) for item in document["dependencies"])
            ):
                raise StoreIntegrityError("durable model work plan is malformed")
            for field in (
                "role_contract_digest",
                "source_pack_fingerprint",
                "acceptance_specification_digest",
                "profile_digest",
            ):
                value = document.get(field)
                if not isinstance(value, str) or not value.startswith("sha256:"):
                    raise StoreIntegrityError("durable model work plan lacks a digest binding")
            if role in observed_roles:
                raise StoreIntegrityError("durable model work plan repeats a role")
            observed_roles.add(role)
            normalized.append(
                (
                    ordinal,
                    role,
                    work_item_id,
                    _configuration_digest(document),
                    _canonical_json(document),
                )
            )
        with self._lock, self._connection:
            for ordinal, role, work_item_id, digest, encoded in normalized:
                existing = self._connection.execute(
                    "SELECT plan_digest,plan_json FROM mission_role_work_plans "
                    "WHERE mission_id=? AND role=?",
                    (mission_id, role),
                ).fetchone()
                if existing is None:
                    self._connection.execute(
                        """
                        INSERT INTO mission_role_work_plans(
                            mission_id,ordinal,role,work_item_id,plan_digest,plan_json,recorded_at
                        ) VALUES(?,?,?,?,?,?,?)
                        """,
                        (mission_id, ordinal, role, work_item_id, digest, encoded, utc_now()),
                    )
                elif existing["plan_digest"] != digest or existing["plan_json"] != encoded:
                    raise StoreIntegrityError("durable model work plan differs from its sealed plan")

    def role_work_plan(self, mission_id: str, role: Role) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT plan_digest,plan_json FROM mission_role_work_plans "
            "WHERE mission_id=? AND role=?",
            (mission_id, role.value),
        ).fetchone()
        if row is None:
            raise KeyError((mission_id, role.value))
        document = self._checked_journal_document(
            str(row["plan_json"]), str(row["plan_digest"]), "durable model work plan"
        )
        document["plan_digest"] = str(row["plan_digest"])
        return document

    def register_role_input(
        self,
        mission_id: str,
        role: Role,
        document: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Seal one model request projection before model-turn admission."""

        payload = dict(document)
        required = {
            "schema_version",
            "role",
            "work_item_id",
            "work_plan_digest",
            "prior_completion_digests",
            "context_digest",
            "execution_objective_digest",
            "model_turn_id",
            "model_turn_plan_digest",
        }
        if set(payload) != required or payload.get("schema_version") != 1:
            raise StoreIntegrityError("durable model role input has an unknown shape")
        plan = self.role_work_plan(mission_id, role)
        if (
            payload.get("role") != role.value
            or payload.get("work_item_id") != plan["work_item_id"]
            or payload.get("work_plan_digest") != plan["plan_digest"]
            or not isinstance(payload.get("prior_completion_digests"), list)
            or any(not isinstance(item, str) or not item.startswith("sha256:") for item in payload["prior_completion_digests"])
        ):
            raise StoreIntegrityError("durable model role input does not bind its work plan")
        for field in (
            "context_digest",
            "execution_objective_digest",
            "model_turn_plan_digest",
        ):
            value = payload.get(field)
            if not isinstance(value, str) or not value.startswith("sha256:"):
                raise StoreIntegrityError("durable model role input lacks a digest binding")
        if not isinstance(payload.get("model_turn_id"), str) or not str(
            payload["model_turn_id"]
        ).startswith("MTURN-"):
            raise StoreIntegrityError("durable model role input lacks its model turn ID")
        digest = _configuration_digest(payload)
        encoded = _canonical_json(payload)
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT input_digest,input_json FROM mission_role_inputs "
                "WHERE mission_id=? AND role=?",
                (mission_id, role.value),
            ).fetchone()
            if existing is None:
                self._connection.execute(
                    """
                    INSERT INTO mission_role_inputs(
                        mission_id,role,work_plan_digest,input_digest,input_json,recorded_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (
                        mission_id,
                        role.value,
                        str(payload["work_plan_digest"]),
                        digest,
                        encoded,
                        utc_now(),
                    ),
                )
            elif existing["input_digest"] != digest or existing["input_json"] != encoded:
                raise StoreIntegrityError("durable model role input differs from its sealed input")
        return {**payload, "input_digest": digest}

    def role_input(self, mission_id: str, role: Role) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT input_digest,input_json FROM mission_role_inputs "
            "WHERE mission_id=? AND role=?",
            (mission_id, role.value),
        ).fetchone()
        if row is None:
            raise KeyError((mission_id, role.value))
        document = self._checked_journal_document(
            str(row["input_json"]), str(row["input_digest"]), "durable model role input"
        )
        document["input_digest"] = str(row["input_digest"])
        return document

    def register_role_admission(
        self,
        mission_id: str,
        role: Role,
        input_digest: str,
    ) -> dict[str, Any]:
        """Witness model-store admission before any provider dispatch is permitted."""

        input_record = self.role_input(mission_id, role)
        if input_record["input_digest"] != input_digest:
            raise StoreIntegrityError("model role admission references another role input")
        document = {
            "schema_version": 1,
            "role": role.value,
            "input_digest": input_digest,
            "model_turn_id": input_record["model_turn_id"],
            "model_turn_plan_digest": input_record["model_turn_plan_digest"],
        }
        digest = _configuration_digest(document)
        encoded = _canonical_json(document)
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT admission_digest,admission_json FROM mission_role_admissions "
                "WHERE mission_id=? AND role=?",
                (mission_id, role.value),
            ).fetchone()
            if existing is None:
                self._connection.execute(
                    """
                    INSERT INTO mission_role_admissions(
                        mission_id,role,input_digest,admission_digest,admission_json,recorded_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (mission_id, role.value, input_digest, digest, encoded, utc_now()),
                )
            elif existing["admission_digest"] != digest or existing["admission_json"] != encoded:
                raise StoreIntegrityError("model role admission differs from its sealed admission")
        return {**document, "admission_digest": digest}

    def role_admission(self, mission_id: str, role: Role) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT admission_digest,admission_json FROM mission_role_admissions "
            "WHERE mission_id=? AND role=?",
            (mission_id, role.value),
        ).fetchone()
        if row is None:
            return None
        document = self._checked_journal_document(
            str(row["admission_json"]),
            str(row["admission_digest"]),
            "durable model role admission",
        )
        input_record = self.role_input(mission_id, role)
        if (
            document.get("input_digest") != input_record["input_digest"]
            or document.get("model_turn_id") != input_record["model_turn_id"]
            or document.get("model_turn_plan_digest")
            != input_record["model_turn_plan_digest"]
        ):
            raise StoreIntegrityError("model role admission no longer binds its input")
        document["admission_digest"] = str(row["admission_digest"])
        return document

    def bind_role_effect_intent(
        self,
        mission_id: str,
        role: Role,
        input_digest: str,
        effect_ordinal: int,
        checkpoint: StepCheckpoint,
    ) -> None:
        """Bind a P06 checkpoint to one sealed model-role input before its effect."""

        if checkpoint.mission_id != mission_id or effect_ordinal < 0:
            raise StoreIntegrityError("durable model effect binding is invalid")
        input_record = self.role_input(mission_id, role)
        if input_record["input_digest"] != input_digest:
            raise StoreIntegrityError("durable model effect references another role input")
        with self._lock, self._connection:
            existing = self._connection.execute(
                """
                SELECT input_digest,step_index,intent_digest FROM mission_role_effects
                WHERE mission_id=? AND role=? AND effect_ordinal=?
                """,
                (mission_id, role.value, effect_ordinal),
            ).fetchone()
            values = (input_digest, checkpoint.step_index, checkpoint.intent_digest)
            if existing is None:
                existing_completion = self._connection.execute(
                    "SELECT 1 FROM mission_role_completions WHERE mission_id=? AND role=?",
                    (mission_id, role.value),
                ).fetchone()
                if existing_completion is not None:
                    raise StoreIntegrityError(
                        "completed model role cannot acquire another capability effect"
                    )
                self._connection.execute(
                    """
                    INSERT INTO mission_role_effects(
                        mission_id,role,input_digest,effect_ordinal,step_index,intent_digest
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (mission_id, role.value, input_digest, effect_ordinal, checkpoint.step_index, checkpoint.intent_digest),
                )
            elif tuple(existing) != values:
                raise StoreIntegrityError("durable model effect differs from its sealed binding")

    def role_effects(self, mission_id: str, role: Role, input_digest: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            """
            SELECT effect_ordinal,step_index,intent_digest FROM mission_role_effects
            WHERE mission_id=? AND role=? AND input_digest=? ORDER BY effect_ordinal
            """,
            (mission_id, role.value, input_digest),
        ).fetchall()
        effects: list[dict[str, Any]] = []
        for expected, row in enumerate(rows):
            if int(row["effect_ordinal"]) != expected:
                raise StoreIntegrityError("durable model effect ordinals are not contiguous")
            checkpoint = self.checkpoint(mission_id, int(row["step_index"]))
            if checkpoint.intent_digest != row["intent_digest"]:
                raise StoreIntegrityError("durable model effect no longer binds its checkpoint")
            effects.append(
                {
                    "effect_ordinal": expected,
                    "step_index": checkpoint.step_index,
                    "intent_digest": checkpoint.intent_digest,
                    "state": checkpoint.state,
                    "receipt_reference": checkpoint.receipt_reference,
                }
            )
        return effects

    def _model_role_receipt_bindings(
        self,
        mission_id: str,
        role: Role,
        input_digest: str,
    ) -> tuple[list[dict[str, str]], list[str]]:
        """Validate effect wrappers and return their synthetic refs and raw digests."""

        references: list[dict[str, str]] = []
        raw_digests: list[str] = []
        for effect in self.role_effects(mission_id, role, input_digest):
            if effect["state"] != "completed" or not isinstance(effect["receipt_reference"], Mapping):
                raise StoreIntegrityError("model role completion lacks a completed capability receipt")
            checkpoint = self.checkpoint(mission_id, int(effect["step_index"]))
            found = self.find_effect_receipt(checkpoint)
            if found is None:
                raise StoreIntegrityError("model role capability receipt is missing")
            reference, wrapper = found
            if dict(effect["receipt_reference"]) != reference:
                raise StoreIntegrityError("model role capability receipt reference changed")
            references.append(reference)
            for record in wrapper["records"]:
                digest = record.get("digest")
                if not isinstance(digest, str) or not digest.startswith("sha256:"):
                    raise StoreIntegrityError("model role raw capability receipt is malformed")
                raw_digests.append(digest)
        return references, raw_digests

    @staticmethod
    def _validate_model_role_result_receipts(
        result: Mapping[str, Any],
        expected_digests: Sequence[str],
    ) -> None:
        try:
            typed = agent_result_from_document(result)
        except (DurableRepositoryModelError, TypeError, ValueError) as error:
            raise StoreIntegrityError("model role completion result is malformed") from error
        if agent_result_document(typed) != dict(result):
            raise StoreIntegrityError("model role completion result is noncanonical")
        observed_lists: list[list[str]] = []
        for evidence in typed.evidence:
            values = evidence.payload.get("receipt_digests")
            if values is None:
                continue
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value.startswith("sha256:")
                for value in values
            ):
                raise StoreIntegrityError("model role receipt evidence is malformed")
            observed_lists.append(values)
        if expected_digests:
            if not observed_lists or any(values != list(expected_digests) for values in observed_lists):
                raise StoreIntegrityError(
                    "model role receipt evidence does not bind completed capability receipts"
                )
        elif observed_lists:
            raise StoreIntegrityError("effect-free model role has receipt evidence")

    def complete_model_role(
        self,
        mission_id: str,
        role: Role,
        input_digest: str,
        *,
        model_turn_id: str,
        model_turn_plan_digest: str,
        model_role_result_digest: str,
        agent_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Atomically retain the final context projection and mark the role successful."""

        input_record = self.role_input(mission_id, role)
        if (
            input_record["input_digest"] != input_digest
            or input_record["model_turn_id"] != model_turn_id
            or input_record["model_turn_plan_digest"] != model_turn_plan_digest
        ):
            raise StoreIntegrityError("model role completion differs from its sealed input")
        admission = self.role_admission(mission_id, role)
        if admission is None:
            raise StoreIntegrityError("model role completion lacks a pre-dispatch admission witness")
        plan = self.role_work_plan(mission_id, role)
        result = dict(agent_result)
        if result.get("role") != role.value or result.get("work_item_id") != plan["work_item_id"]:
            raise StoreIntegrityError("model role completion result does not bind its work plan")
        receipt_references, raw_receipt_digests = self._model_role_receipt_bindings(
            mission_id, role, input_digest
        )
        self._validate_model_role_result_receipts(result, raw_receipt_digests)
        document = {
            "schema_version": 1,
            "role": role.value,
            "input_digest": input_digest,
            "model_turn_id": model_turn_id,
            "model_turn_plan_digest": model_turn_plan_digest,
            "model_role_result_digest": model_role_result_digest,
            "agent_result": result,
            "agent_result_digest": _configuration_digest(result),
            "capability_receipts": receipt_references,
        }
        digest = _configuration_digest(document)
        encoded = _canonical_json(document)
        with self._lock, self._connection:
            existing = self._connection.execute(
                "SELECT completion_digest,completion_json FROM mission_role_completions "
                "WHERE mission_id=? AND role=?",
                (mission_id, role.value),
            ).fetchone()
            if existing is None:
                self._connection.execute(
                    """
                    INSERT INTO mission_role_completions(
                        mission_id,role,input_digest,completion_digest,completion_json,recorded_at
                    ) VALUES(?,?,?,?,?,?)
                    """,
                    (mission_id, role.value, input_digest, digest, encoded, utc_now()),
                )
                mission = self.mission(mission_id)
                roles = mission["roles"]
                roles[role.value] = "succeeded"
                self._connection.execute(
                    "UPDATE missions SET roles_json=? WHERE mission_id=?",
                    (_canonical_json(roles), mission_id),
                )
            elif existing["completion_digest"] != digest or existing["completion_json"] != encoded:
                raise StoreIntegrityError("model role completion differs from its sealed completion")
        return {**document, "completion_digest": digest}

    def completed_model_role(self, mission_id: str, role: Role) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT completion_digest,completion_json FROM mission_role_completions "
            "WHERE mission_id=? AND role=?",
            (mission_id, role.value),
        ).fetchone()
        if row is None:
            return None
        document = self._checked_journal_document(
            str(row["completion_json"]), str(row["completion_digest"]), "model role completion"
        )
        result = document.get("agent_result")
        if not isinstance(result, dict) or document.get("agent_result_digest") != _configuration_digest(result):
            raise StoreIntegrityError("model role completion result no longer binds its digest")
        input_record = self.role_input(mission_id, role)
        if document.get("input_digest") != input_record["input_digest"]:
            raise StoreIntegrityError("model role completion no longer binds its input")
        if self.role_admission(mission_id, role) is None:
            raise StoreIntegrityError("model role completion lacks its admission witness")
        receipts = document.get("capability_receipts")
        if not isinstance(receipts, list):
            raise StoreIntegrityError("model role completion receipts are malformed")
        observed, raw_receipt_digests = self._model_role_receipt_bindings(
            mission_id, role, str(input_record["input_digest"])
        )
        if receipts != observed:
            raise StoreIntegrityError("model role completion receipt list no longer binds effects")
        self._validate_model_role_result_receipts(result, raw_receipt_digests)
        document["completion_digest"] = str(row["completion_digest"])
        return document

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
                    "complete" if complete else "blocked" if blocked else "active"
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
                {"kind": "checkpoint-receipt", "path": path} for path in receipt_paths
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
                    "retain verified result" if complete else "resume durable mission"
                ),
                "resume_instruction": f"hive-mind resume {mission_id}",
                "created_at": utc_now(),
            },
        }


async def resume_mission(
    store: MissionStore,
    mission_id: str,
    *,
    custody: ExternalCustodyAdapter | None = None,
    source_custody: SourceCustodyVerifier | None = None,
    model_backend_resolver: Any | None = None,
) -> Any:
    """Reconcile a scripted mission or an explicitly injected model profile."""

    from .durable_repository_model import (
        DurableRepositoryModelBackend,
        DurableRepositoryModelProfile,
    )
    from .github_adapter import GitHubClient, GitHubDeliveryTarget
    from .ledger import EvidenceLedger
    from .mission import RepositoryMission, ScriptedRepositoryBackend
    from .models import AutonomyLevel, RiskTier
    from .policy import PolicyEngine

    mission = store.mission(mission_id)
    if store.require_authenticated_custody and custody is None:
        raise MissionStoreError(
            "authenticated custody mission resumption requires an external custody adapter"
        )
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
    backend_kind = config.get("backend")
    if backend_kind not in {"scripted", "durable-model-repository-v1"}:
        raise MissionStoreError("P06 resume does not recognize this repository backend")
    missing = store.reconcile_workspaces(mission_id)
    budget_data = mission["budget"]
    budget = AutonomyBudget(**budget_data)
    if backend_kind == "scripted":
        backend: Any = ScriptedRepositoryBackend(
            config["scripted_variant"],
            test_argv=config["test_argv"],
            criterion_argv=config["criterion_argv"],
        )
    else:
        profile_data = config.get("durable_model_profile")
        if not isinstance(profile_data, Mapping):
            raise MissionStoreError("durable model mission lacks its sealed profile")
        profile = DurableRepositoryModelProfile.from_dict(profile_data)
        if profile.budget.mission_id != mission_id:
            raise MissionStoreError("durable model profile does not bind the mission ID")
        if model_backend_resolver is None:
            raise MissionStoreError(
                "durable model repository resumption requires an injected backend resolver"
            )
        backend = model_backend_resolver(profile)
        if not isinstance(backend, DurableRepositoryModelBackend):
            raise MissionStoreError(
                "durable model repository resolver returned an unsealed backend"
            )
        if backend.profile.to_dict() != profile.to_dict():
            raise MissionStoreError(
                "durable model repository resolver differs from the sealed profile"
            )
    source_lock: SourceLockEvidence | None = None
    authenticated_source = config.get("authenticated_source")
    if authenticated_source is not None:
        if source_custody is None:
            raise MissionStoreError(
                "authenticated source mission resumption requires a source custody verifier"
            )
        if not isinstance(authenticated_source, Mapping):
            raise MissionStoreError("authenticated source configuration is malformed")
        lock_value = authenticated_source.get("source_lock")
        attestation_value = authenticated_source.get("attestation")
        evidence_digest = authenticated_source.get("evidence_digest")
        if (
            not isinstance(lock_value, Mapping)
            or not isinstance(attestation_value, Mapping)
            or not isinstance(evidence_digest, str)
        ):
            raise MissionStoreError("authenticated source configuration is incomplete")
        try:
            source_lock = SourceLockEvidence(
                SourceLock.from_dict(
                    lock_value,
                    allowed_hosts=source_custody.allowed_hosts,
                ),
                dict(attestation_value),
            )
        except SourceCustodyError as error:
            raise MissionStoreError(
                f"authenticated source configuration is malformed: {error}"
            ) from error
        if source_lock.digest() != evidence_digest:
            raise StoreIntegrityError(
                "authenticated source configuration digest does not bind source evidence"
            )
    ledger = EvidenceLedger(store.state_dir / "evidence-ledger.sqlite3")
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
    if backend_kind == "durable-model-repository-v1" and github_delivery is not None:
        raise MissionStoreError(
            "durable model repository resumption does not authorize external delivery"
        )
    try:
        runner = RepositoryMission(
            config["repository"],
            config["objective"],
            acceptance_criteria=tuple(config["acceptance_criteria"]),
            acceptance_specifications=tuple(config.get("acceptance_specifications", ())),
            risk=RiskTier[str(config.get("risk", "moderate")).upper()],
            backend=backend,
            pin=config["pin"],
            output_dir=config["output_dir"],
            policy=policy,
            budget=budget,
            ledger=ledger,
            mission_store=store,
            custody=custody,
            source_lock=source_lock,
            source_custody=source_custody,
            github_delivery=github_delivery,
            _run_id=mission_id,
            _resume=True,
            _missing_workspaces=missing,
        )
        return await runner.run()
    finally:
        ledger.close()
