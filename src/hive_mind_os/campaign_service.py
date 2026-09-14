"""Durable, injectable campaign controller over the existing Scheduler."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import json, sqlite3, time
from pathlib import Path
from typing import Any, Callable, Protocol
from .scheduler import Scheduler

class CampaignStatus(str, Enum): IDLE="IDLE"; PROGRESSED="PROGRESSED"; WAITING_EXTERNAL="WAITING_EXTERNAL"; BLOCKED="BLOCKED"; STOPPED="STOPPED"
@dataclass(frozen=True, slots=True)
class CampaignServiceConfig:
    campaign_id: str; config_id: str; repository_ids: tuple[str,...]; binding_digest: str
    concurrency: int = 1; daily_allowance: int = 100; idle_backoff: float = 30.0
    stop_conditions: tuple[str,...] = ()
@dataclass(frozen=True, slots=True)
class CampaignStep:
    status: CampaignStatus; next_wake: float | None; checkpoint: str | None; message: str = ""
class Continuity(Protocol):
    def recover(self) -> Any: ...
class CampaignService:
    def __init__(self, config: CampaignServiceConfig, scheduler: Scheduler, state_dir: str|Path, *, executor: Callable[[Any], Any] | None=None, clock: Callable[[],float] | None=None):
        if config.concurrency < 1: raise ValueError("concurrency must be positive")
        self.config=config; self.scheduler=scheduler; self.executor=executor; self.clock=clock or time.time
        self.path=Path(state_dir); self.path.mkdir(parents=True, exist_ok=True); self.db=self.path/"campaign.sqlite3"
        self.cx=sqlite3.connect(self.db); self.cx.execute("CREATE TABLE IF NOT EXISTS checkpoints (campaign_id TEXT PRIMARY KEY, body TEXT NOT NULL)"); self.cx.commit()
    def checkpoint(self, payload: dict[str,Any]) -> str:
        body=json.dumps(payload, sort_keys=True, separators=(",",":")); self.cx.execute("INSERT OR REPLACE INTO checkpoints VALUES (?,?)",(self.config.campaign_id,body)); self.cx.commit(); return body
    def load_checkpoint(self)->dict[str,Any]:
        row=self.cx.execute("SELECT body FROM checkpoints WHERE campaign_id=?",(self.config.campaign_id,)).fetchone(); return {} if not row else json.loads(row[0])
    def run_once(self, now: float|None=None) -> CampaignStep:
        now=self.clock() if now is None else now; cp=self.load_checkpoint()
        if cp.get("stopped") or any(x in cp.get("stop_conditions",[]) for x in self.config.stop_conditions): return CampaignStep(CampaignStatus.STOPPED,None,self.checkpoint(cp),"stop condition")
        job=self.scheduler.claim(f"campaign:{self.config.campaign_id}")
        if job is None: return CampaignStep(CampaignStatus.IDLE,now+self.config.idle_backoff,self.checkpoint({**cp,"last_observation":now}),"no actionable work")
        try:
            result=self.executor(job) if self.executor else job.id
            self.scheduler.complete(job.id, job.lease_token or "", mission_id=self.config.campaign_id)
            ref=self.checkpoint({**cp,"last_job":job.id,"last_result":str(result)})
            return CampaignStep(CampaignStatus.PROGRESSED,now,ref)
        except PermissionError as e:
            self.scheduler.fail(job.id,job.lease_token or "",str(e),mission_id=self.config.campaign_id); return CampaignStep(CampaignStatus.WAITING_EXTERNAL,now+self.config.idle_backoff,self.checkpoint({**cp,"blocked":"authority"}),str(e))
        except Exception as e:
            self.scheduler.fail(job.id,job.lease_token or "",str(e),mission_id=self.config.campaign_id); return CampaignStep(CampaignStatus.BLOCKED,now+self.config.idle_backoff,self.checkpoint({**cp,"error":str(e)}),str(e))
