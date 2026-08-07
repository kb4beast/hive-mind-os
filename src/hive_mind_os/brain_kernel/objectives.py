"""Pure, bounded objective-DAG validation for kernel work items."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, cast

from .canonical import canonical_digest
from .contracts import MissionCharter, WorkItem, WorkState


@dataclass(frozen=True, slots=True)
class PlanLimits:
    """Hard limits applied before a proposed work graph may be persisted."""

    max_work_items: int
    max_depth: int
    max_fanout: int = 8

    def __post_init__(self) -> None:
        if min(self.max_work_items, self.max_depth, self.max_fanout) < 1:
            raise ValueError("plan limits must be positive")


def paths_overlap(left: str, right: str) -> bool:
    """Return whether two normalized portable paths overlap by containment."""

    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


class ObjectiveGraph:
    """An immutable, validated work DAG; no role or effect is executed here."""

    def __init__(
        self,
        charter: MissionCharter,
        work_items: Iterable[WorkItem],
        *,
        limits: PlanLimits | None = None,
    ) -> None:
        self.charter = charter
        self.work_items = tuple(work_items)
        self.limits = limits or PlanLimits(
            max_work_items=charter.budget.max_work_items,
            max_depth=charter.budget.max_depth,
        )
        self._by_id = {item.work_id: item for item in self.work_items}
        if len(self._by_id) != len(self.work_items):
            raise ValueError("work item ids must be unique")
        self._validate()

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "mission_id": self.charter.mission_id,
                "items": [item.to_document() for item in self.ordered_items()],
            }
        )

    def item(self, work_id: str) -> WorkItem:
        return self._by_id[work_id]

    def ordered_items(self) -> tuple[WorkItem, ...]:
        """Return deterministic topological order, tie-broken by work id."""

        pending = {item.work_id: set(item.dependencies) for item in self.work_items}
        ordered: list[WorkItem] = []
        while pending:
            ready = sorted(work_id for work_id, dependencies in pending.items() if not dependencies)
            if not ready:
                raise ValueError("work graph contains a cycle")
            for work_id in ready:
                ordered.append(self._by_id[work_id])
                del pending[work_id]
            completed = set(ready)
            for dependencies in pending.values():
                dependencies.difference_update(completed)
        return tuple(ordered)

    def ready_items(self, completed: Iterable[str] = ()) -> tuple[WorkItem, ...]:
        """Return proposed nodes whose explicit dependencies have completed."""

        completed_ids = set(completed)
        return tuple(
            item
            for item in self.ordered_items()
            if item.status is WorkState.PROPOSED
            and set(item.dependencies).issubset(completed_ids)
        )

    def _validate(self) -> None:
        if not self.work_items:
            raise ValueError("work graph needs at least one item")
        if len(self.work_items) > self.limits.max_work_items:
            raise ValueError("work graph exceeds work item limit")
        children: dict[str, int] = {item.work_id: 0 for item in self.work_items}
        acceptance: set[str] = set()
        for item in self.work_items:
            if item.mission_id != self.charter.mission_id:
                raise ValueError("work item belongs to another mission")
            if item.depth > self.limits.max_depth:
                raise ValueError("work graph exceeds depth limit")
            missing = set(item.dependencies) - set(self._by_id)
            if missing:
                raise ValueError("work graph has missing dependency")
            if item.work_id in item.dependencies:
                raise ValueError("work item cannot depend on itself")
            if item.parent_work_id is not None:
                parent = self._by_id.get(item.parent_work_id)
                if parent is None:
                    raise ValueError("work graph has orphan parent")
                if item.depth != parent.depth + 1:
                    raise ValueError("work item depth does not match parent")
                children[parent.work_id] += 1
            acceptance.update(item.acceptance_specs)
        if any(count > self.limits.max_fanout for count in children.values()):
            raise ValueError("work graph exceeds fanout limit")
        if not set(self.charter.acceptance_specs).issubset(acceptance):
            raise ValueError("work graph is missing charter acceptance")
        self.ordered_items()
        self._validate_concurrent_writes()

    def _validate_concurrent_writes(self) -> None:
        for index, left in enumerate(self.work_items):
            for right in self.work_items[index + 1 :]:
                if not any(
                    paths_overlap(left_path, right_path)
                    for left_path in left.write_scope
                    for right_path in right.write_scope
                ):
                    continue
                if not self._ordered(left.work_id, right.work_id) and not self._ordered(
                    right.work_id, left.work_id
                ):
                    raise ValueError("overlapping write scopes require a dependency")

    def _ordered(self, predecessor: str, successor: str) -> bool:
        pending = list(self._by_id[successor].dependencies)
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current == predecessor:
                return True
            if current not in visited:
                visited.add(current)
                pending.extend(self._by_id[current].dependencies)
        return False

    @classmethod
    def from_documents(
        cls,
        charter: MissionCharter,
        documents: Iterable[Mapping[str, object]],
    ) -> "ObjectiveGraph":
        return cls(
            charter,
            (cast(WorkItem, WorkItem.from_document(document)) for document in documents),
        )
