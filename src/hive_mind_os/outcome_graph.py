"""Versioned outcome graphs compiled into bounded work packages."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterable, Mapping
from .brain_kernel.canonical import canonical_digest

class GraphError(ValueError): pass

@dataclass(frozen=True, slots=True)
class OutcomeWorkPackage:
    package_id: str; outcome_ids: tuple[str,...]; dependencies: tuple[str,...] = ()
    allowed_paths: tuple[str,...] = (); semantic_locks: tuple[str,...] = ()
    acceptance_ids: tuple[str,...] = (); risk_tier: str = "medium"
    required_roles: tuple[str,...] = (); effort: int = 1; rollback: str = "retain prior candidate"
    state: str = "pending"
    def __post_init__(self):
        if not self.package_id or not self.outcome_ids: raise GraphError("package and outcome ids are required")
        if self.effort < 1: raise GraphError("effort must be positive")
        if len(set(self.dependencies)) != len(self.dependencies): raise GraphError("duplicate dependency")
        if self.package_id in self.dependencies: raise GraphError("package cannot depend on itself")

@dataclass(frozen=True, slots=True)
class OutcomeGraphSpec:
    packages: tuple[OutcomeWorkPackage,...]; base_snapshot: str; contract_version: int = 1
    maximum_concurrent: int = 1; court_receipt: str = ""
    @property
    def digest(self): return canonical_digest(self)
    def to_document(self):
        return {"packages":[p.__dict__ if hasattr(p,"__dict__") else {k:getattr(p,k) for k in p.__dataclass_fields__} for p in self.packages],"base_snapshot":self.base_snapshot,"contract_version":self.contract_version,"maximum_concurrent":self.maximum_concurrent,"court_receipt":self.court_receipt}

def compile_outcome_graph(packages: Iterable[OutcomeWorkPackage] | OutcomeGraphSpec, *, base_snapshot: str | None = None, maximum_concurrent: int = 1, court_receipt: str = "") -> OutcomeGraphSpec:
    spec = packages if isinstance(packages, OutcomeGraphSpec) else OutcomeGraphSpec(tuple(packages), base_snapshot or "", 1, maximum_concurrent, court_receipt)
    ids = {p.package_id for p in spec.packages}
    if len(ids) != len(spec.packages): raise GraphError("duplicate package id")
    if not spec.base_snapshot: raise GraphError("base snapshot is required")
    if spec.maximum_concurrent < 1: raise GraphError("capacity must be positive")
    for p in spec.packages:
        missing = set(p.dependencies) - ids
        if missing: raise GraphError(f"missing dependency: {sorted(missing)}")
    visiting=set(); visited=set()
    by_id={p.package_id:p for p in spec.packages}
    def visit(i):
        if i in visiting: raise GraphError("outcome graph contains a cycle")
        if i in visited: return
        visiting.add(i)
        for d in by_id[i].dependencies: visit(d)
        visiting.remove(i); visited.add(i)
    for i in ids: visit(i)
    # Concurrent writers are only safe when packages declare distinct paths.
    for a in spec.packages:
        for b in spec.packages:
            if a.package_id < b.package_id and set(a.allowed_paths)&set(b.allowed_paths) and b.package_id not in a.dependencies and a.package_id not in b.dependencies:
                raise GraphError("overlapping writers require an ordering dependency")
    return spec

def ready_packages(spec: OutcomeGraphSpec, completed: Iterable[str] = ()) -> tuple[OutcomeWorkPackage,...]:
    done=set(completed)
    return tuple(p for p in spec.packages if p.state == "pending" and set(p.dependencies) <= done)

def dispatch_rounds(spec: OutcomeGraphSpec, completed: Iterable[str] = ()) -> tuple[tuple[str,...], ...]:
    """Return deterministic capacity- and conflict-aware dependency rounds."""
    done=set(completed); remaining={p.package_id:p for p in spec.packages if p.package_id not in done}
    rounds=[]
    while remaining:
        candidates=[p for p in remaining.values() if set(p.dependencies)<=done]
        if not candidates: raise GraphError("graph cannot make progress")
        chosen=[]; paths=set(); locks=set()
        for p in sorted(candidates,key=lambda x:x.package_id):
            if len(chosen)>=spec.maximum_concurrent: break
            if paths.intersection(p.allowed_paths) or locks.intersection(p.semantic_locks): continue
            chosen.append(p.package_id); paths.update(p.allowed_paths); locks.update(p.semantic_locks)
        if not chosen: raise GraphError("ready packages conflict at configured capacity")
        rounds.append(tuple(chosen)); done.update(chosen)
        for i in chosen: remaining.pop(i)
    return tuple(rounds)
