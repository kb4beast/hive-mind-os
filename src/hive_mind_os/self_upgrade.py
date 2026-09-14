"""Immutable runtime challengers and host-broker-mediated activation."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from .brain_kernel.canonical import canonical_digest
class UpgradeDecision(str,Enum): RETAIN="RETAIN"; CANARY="CANARY"; PROMOTE="PROMOTE"; ROLLBACK="ROLLBACK"; DEFER="DEFER"; QUARANTINE="QUARANTINE"
@dataclass(frozen=True,slots=True)
class RuntimeChallenger:
    version:str; artifact_digest:str; champion_parent:str; source_ref:str; dependency_manifest:str; migration_manifest:str; rollback_artifact:str; evaluation_plan:str; evaluation_result:str|None; builder_id:str; evaluator_id:str; judge_id:str; canary_scope:str
    @property
    def digest(self):return canonical_digest(self)
    def __post_init__(self):
        if not all((self.version,self.artifact_digest,self.champion_parent,self.source_ref,self.dependency_manifest,self.migration_manifest,self.rollback_artifact,self.evaluation_plan,self.builder_id,self.evaluator_id,self.judge_id,self.canary_scope)): raise ValueError("challenger manifest is incomplete")
        if not self.artifact_digest.startswith("sha256:"): raise ValueError("artifact digest must be canonical")
@dataclass(frozen=True,slots=True)
class UpgradeReceipt:
    decision:UpgradeDecision; challenger_digest:str; reason:str; activation_digest:str|None=None
class HostBroker(Protocol):
    def activate(self, challenger:RuntimeChallenger)->str: ...
    def rollback(self, challenger:RuntimeChallenger)->str: ...
class UpgradeController:
    def __init__(self,host:HostBroker|None=None): self.host=host; self.active=None; self.state="CHAMPION_ACTIVE"; self.previous=None
    def decide(self,c:RuntimeChallenger, *, qualification_passed:bool, heldout_passed:bool, rollback_valid:bool)->UpgradeReceipt:
        if c.builder_id in {c.evaluator_id,c.judge_id} or c.evaluator_id==c.judge_id:return UpgradeReceipt(UpgradeDecision.QUARANTINE,c.digest,"identity roles are not independent")
        if not qualification_passed or not heldout_passed:return UpgradeReceipt(UpgradeDecision.RETAIN,c.digest,"qualification or held-out evaluation incomplete")
        if not rollback_valid:return UpgradeReceipt(UpgradeDecision.QUARANTINE,c.digest,"rollback artifact is invalid")
        if self.host is None:return UpgradeReceipt(UpgradeDecision.CANARY,c.digest,"host activation authority unavailable")
        try:
            self.state="CANARY_PREPARED"
            activation=self.host.activate(c); self.active=c; return UpgradeReceipt(UpgradeDecision.PROMOTE,c.digest,"independent verdict accepted",activation)
        except PermissionError:return UpgradeReceipt(UpgradeDecision.CANARY,c.digest,"host activation authority unavailable")
        except (TimeoutError,ConnectionError):return UpgradeReceipt(UpgradeDecision.DEFER,c.digest,"activation outcome requires reconciliation")
    def rollback(self,c:RuntimeChallenger)->UpgradeReceipt:
        if self.host is None:return UpgradeReceipt(UpgradeDecision.DEFER,c.digest,"host activation authority unavailable")
        activation=self.host.rollback(c); self.active=None; self.state="CHAMPION_ACTIVE"
        return UpgradeReceipt(UpgradeDecision.ROLLBACK,c.digest,"rollback requested",activation)
