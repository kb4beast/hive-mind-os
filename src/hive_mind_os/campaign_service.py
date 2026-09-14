"""Durable, injectable campaign controller over the existing Scheduler."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol

from .scheduler import Scheduler


class CampaignStatus(str, Enum):
    IDLE = "IDLE"
    PROGRESSED = "PROGRESSED"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    BLOCKED = "BLOCKED"
    STOPPED = "STOPPED"


@dataclass(frozen=True, slots=True)
class CampaignServiceConfig:
    campaign_id: str
    config_id: str
    repository_ids: tuple[str, ...]
    binding_digest: str
    concurrency: int = 1
    daily_allowance: int = 100
    idle_backoff: float = 30.0
    stop_conditions: tuple[str, ...] = ()
    owner_id: str = "campaign-service"
    job_kinds: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CampaignStep:
    status: CampaignStatus
    next_wake: float | None
    checkpoint: str | None
    message: str = ""


class Continuity(Protocol):
    def recover(self) -> Any: ...


class CampaignService:
    def __init__(
        self,
        config: CampaignServiceConfig,
        scheduler: Scheduler,
        state_dir: str | Path,
        *,
        executor: Callable[[Any], Any] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        if config.concurrency < 1:
            raise ValueError("concurrency must be positive")
        self.config = config
        self.scheduler = scheduler
        self.executor = executor
        self.clock = clock or time.time
        self.path = Path(state_dir)
        self.path.mkdir(parents=True, exist_ok=True)
        self.db = self.path / "campaign.sqlite3"
        self.cx = sqlite3.connect(self.db)
        self.cx.execute(
            "CREATE TABLE IF NOT EXISTS checkpoints (campaign_id TEXT PRIMARY KEY, body TEXT NOT NULL, updated REAL NOT NULL)"
        )
        self.cx.execute(
            "CREATE TABLE IF NOT EXISTS effects (key TEXT PRIMARY KEY, result TEXT NOT NULL)"
        )
        self.cx.execute(
            "CREATE TABLE IF NOT EXISTS effect_intents (key TEXT PRIMARY KEY, job_id TEXT NOT NULL, state TEXT NOT NULL, result TEXT)"
        )
        self.cx.commit()

    def close(self) -> None:
        self.cx.close()

    def checkpoint(self, payload: dict[str, Any]) -> str:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self.cx.execute(
            "INSERT OR REPLACE INTO checkpoints VALUES (?,?,?)",
            (self.config.campaign_id, body, self.clock()),
        )
        self.cx.commit()
        return self.config.campaign_id + ":" + str(self.clock())

    def load_checkpoint(self) -> dict[str, Any]:
        row = self.cx.execute(
            "SELECT body FROM checkpoints WHERE campaign_id=?",
            (self.config.campaign_id,),
        ).fetchone()
        return {} if not row else json.loads(row[0])

    def reconcile_effect(
        self,
        job_id: str,
        *,
        observed_result: str | None = None,
        confirmed_absent: bool = False,
    ) -> None:
        """Resolve one uncertain effect from an external observation."""

        if bool(observed_result) == bool(confirmed_absent):
            raise ValueError("reconciliation requires exactly one observed outcome")
        key = f"{self.config.campaign_id}:{job_id}"
        row = self.cx.execute(
            "SELECT state FROM effect_intents WHERE key=?", (key,)
        ).fetchone()
        if row is None or row[0] not in {"PENDING", "UNCERTAIN"}:
            raise ValueError("no matching uncertain effect intent")
        with self.cx:
            self.cx.execute(
                "UPDATE effect_intents SET state=?,result=? WHERE key=?",
                (
                    "OBSERVED_SUCCEEDED" if observed_result else "CONFIRMED_ABSENT",
                    observed_result,
                    key,
                ),
            )

    def run_once(self, now: float | None = None) -> CampaignStep:
        now = self.clock() if now is None else now
        cp = self.load_checkpoint()
        if cp.get("stopped") or any(
            x in cp.get("stop_conditions", []) for x in self.config.stop_conditions
        ):
            return CampaignStep(
                CampaignStatus.STOPPED, None, self.checkpoint(cp), "stop condition"
            )
        day = int(now // 86400)
        consumed = cp.get("daily_consumed", 0) if cp.get("resource_day") == day else 0
        if consumed >= self.config.daily_allowance:
            return CampaignStep(
                CampaignStatus.BLOCKED,
                (day + 1) * 86400,
                self.checkpoint({**cp, "resource_day": day, "daily_consumed": consumed}),
                "daily resource allowance exhausted",
            )
        progressed = 0
        last_job = None
        last_result = None
        for _ in range(min(self.config.concurrency, self.config.daily_allowance - consumed)):
            job = self.scheduler.claim(
                self.config.owner_id + ":" + self.config.campaign_id,
                mission_id=self.config.campaign_id,
            )
            if job is None:
                break
            if self.config.job_kinds and job.kind not in self.config.job_kinds:
                self.scheduler.fail(
                    job.id,
                    job.lease_token or "",
                    "job kind is outside campaign scope",
                    mission_id=self.config.campaign_id,
                )
                return CampaignStep(
                    CampaignStatus.BLOCKED,
                    now + self.config.idle_backoff,
                    self.checkpoint({**cp, "blocked": "job-kind-scope"}),
                    "job kind is outside campaign scope",
                )
            repository_id = job.payload.get("repository_id")
            if repository_id not in self.config.repository_ids:
                self.scheduler.fail(
                    job.id,
                    job.lease_token or "",
                    "job repository is outside campaign scope",
                    mission_id=self.config.campaign_id,
                )
                return CampaignStep(
                    CampaignStatus.BLOCKED,
                    now + self.config.idle_backoff,
                    self.checkpoint({**cp, "blocked": "repository-scope"}),
                    "job repository is outside campaign scope",
                )
            if self.executor is None:
                self.scheduler.fail(
                    job.id,
                    job.lease_token or "",
                    "canonical executor unavailable",
                    mission_id=self.config.campaign_id,
                )
                return CampaignStep(
                    CampaignStatus.BLOCKED,
                    now + self.config.idle_backoff,
                    self.checkpoint({**cp, "blocked": "executor-unavailable"}),
                    "canonical executor unavailable",
                )
            intent_key = f"{self.config.campaign_id}:{job.id}"
            prior = self.cx.execute(
                "SELECT state,result FROM effect_intents WHERE key=?", (intent_key,)
            ).fetchone()
            if prior and prior[0] in {"PENDING", "UNCERTAIN"}:
                self.scheduler.fail(
                    job.id,
                    job.lease_token or "",
                    "uncertain effect requires reconciliation",
                    mission_id=self.config.campaign_id,
                )
                return CampaignStep(
                    CampaignStatus.WAITING_EXTERNAL,
                    now + self.config.idle_backoff,
                    self.checkpoint({**cp, "uncertain_effect": intent_key}),
                    "uncertain effect requires observation and reconciliation",
                )
            if prior and prior[0] == "OBSERVED_SUCCEEDED":
                self.scheduler.complete(
                    job.id, job.lease_token or "", mission_id=self.config.campaign_id
                )
                progressed += 1
                consumed += 1
                last_job = job.id
                last_result = prior[1]
                continue
            with self.cx:
                self.cx.execute(
                    "INSERT OR REPLACE INTO effect_intents VALUES (?,?,?,NULL)",
                    (intent_key, job.id, "PENDING"),
                )
            self.scheduler.heartbeat(job.id, job.lease_token or "")
            try:
                result = self.executor(job)
                if result is None:
                    raise RuntimeError("executor returned no durable result")
                with self.cx:
                    self.cx.execute(
                        "UPDATE effect_intents SET state='SUCCEEDED',result=? WHERE key=?",
                        (str(result), intent_key),
                    )
                self.scheduler.complete(
                    job.id, job.lease_token or "", mission_id=self.config.campaign_id
                )
                progressed += 1
                consumed += 1
                last_job = job.id
                last_result = str(result)
            except PermissionError as e:
                with self.cx:
                    self.cx.execute(
                        "UPDATE effect_intents SET state='BLOCKED',result=? WHERE key=?",
                        (str(e), intent_key),
                    )
                self.scheduler.fail(
                    job.id,
                    job.lease_token or "",
                    str(e),
                    mission_id=self.config.campaign_id,
                )
                return CampaignStep(
                    CampaignStatus.WAITING_EXTERNAL,
                    now + self.config.idle_backoff,
                    self.checkpoint({**cp, "blocked": "authority"}),
                    str(e),
                )
            except Exception as e:
                with self.cx:
                    self.cx.execute(
                        "UPDATE effect_intents SET state='UNCERTAIN',result=? WHERE key=?",
                        (str(e), intent_key),
                    )
                self.scheduler.fail(
                    job.id,
                    job.lease_token or "",
                    str(e),
                    mission_id=self.config.campaign_id,
                )
                return CampaignStep(
                    CampaignStatus.BLOCKED,
                    now + self.config.idle_backoff,
                    self.checkpoint({**cp, "error": str(e), "uncertain_effect": intent_key}),
                    str(e),
                )
        if not progressed:
            return CampaignStep(
                CampaignStatus.IDLE,
                now + self.config.idle_backoff,
                self.checkpoint({**cp, "last_observation": now}),
                "no actionable work",
            )
        ref = self.checkpoint(
            {
                **cp,
                "last_job": last_job,
                "last_result": last_result,
                "resource_day": day,
                "daily_consumed": consumed,
            }
        )
        return CampaignStep(CampaignStatus.PROGRESSED, now, ref)
