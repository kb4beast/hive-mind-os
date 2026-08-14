#!/usr/bin/env python3
"""Generic DAG dispatch-round compiler and authoring-standard linter.

This module is deliberately repository-agnostic *and* ecosystem-agnostic. It
reads any Autopilot-shaped ``plan.json`` (a document with a ``nodes`` list whose
members carry ``id``, ``dependencies``, ``parallel_safe``, ``file_locks``,
``semantic_locks``, ``read_scope``, ``write_scope`` and contract fields) and
answers two questions that a generated DAG cannot answer about itself:

``dag-rounds``
    A BFS dependency *level* is not an executable wave. A level that contains a
    ``parallel_safe: false`` member must be split into several dispatch rounds,
    a level wider than the host session cap must be split again, and a level
    whose members cannot honestly be proven before a durability node in the same
    level has been integrated must be split once more. This compiler turns
    levels into rounds. Conventional resident plans receive an exact dispatch
    command. External plans receive an executable ``dag-frontier`` assertion
    whose JSON must be consumed by their host adapter; it never pretends that a
    foreign plan can be mutated through the resident control plane.

``dag-frontier``
    Selects the first incomplete compiled round from durable accepted/active
    node identities. It emits only inactive members that fit the runtime cap,
    refuses active work outside that round, and reports plan quiescence only
    after every node is accepted and none remains active.

``dag-lint``
    Validates a plan against the generic authoring standard: graph validity,
    scope syntax, contested shared surfaces (directories and scaffold files),
    write-scope collisions, universal read scopes, durability ordering, serial
    nodes inside parallel levels, ``parallel_safe`` declaration, and contract
    completeness.

**Relationship to the dispatcher (precise claim).** Cycle detection and the
lock-conflict predicate are *reused*, never reimplemented: the exact predicates
used by the dispatcher are imported here and applied to a lightweight in-memory
plan graph. The compiler therefore never packs together two nodes the dispatcher
would refuse to release together. The converse does not hold and is not claimed:
the compiler is deliberately **stricter** than the dispatcher in three places the
dispatcher does not model at all — declared ``write_scope`` overlap, semantic
durability ordering (disable with ``--no-semantic-ordering``), and unparseable
lock patterns, which are treated as conflicting rather than crashing. Every such
divergence makes the compiler more conservative, never less.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from controller import ControlPlane as _CoreControlPlane
from controller import path_matches_scope, scopes_overlap
from durable_controller import AutopilotError, read_json
from release_barrier import ControlPlane as _ReleaseControlPlane

# Reused dispatcher logic. ``_nodes_conflict`` only needs ``self.node(node_id)``
# and ``_find_cycle`` is a static helper, so both are applied to the plan graph
# below without constructing (or forking) a live control plane.
_find_cycle = _CoreControlPlane._find_cycle
_nodes_conflict = _ReleaseControlPlane._nodes_conflict

DEFAULT_MAX_SESSIONS = 8

# Vendor-neutral. This tool is open source and is pointed at other people's
# repositories by other people's agents; no AI vendor's namespace belongs in a
# default. ``--actor`` overrides it.
DEFAULT_ACTOR_NAMESPACE = "orchestrator"

DISPATCH_SCRIPT_RELPATH = ".autopilot/bin/autopilot.py"

SEVERITIES = ("error", "warning", "info")
_SEVERITY_RANK = {severity: index for index, severity in enumerate(SEVERITIES)}

CONTRACT_FIELDS = (
    "required_tests",
    "stopping_condition",
    "rollback",
    "forbidden_scope",
    "write_scope",
)

# Only the fields that reach ``controller.scopes_overlap``. ``read_scope`` and
# ``forbidden_scope`` are matched with ``path_matches_scope``, which tolerates an
# unanchored pattern, and an unanchored *read* scope is a deliberate, documented
# warning (``universal-read-scope``) rather than a defect.
LOCKING_SCOPE_FIELDS = ("write_scope", "file_locks")

# Directory names that mark a test root in *some* ecosystem. ``__tests__`` is the
# dominant JS/TS convention; ``spec``/``specs`` covers Ruby/JS BDD layouts.
TEST_ROOTS = ("test", "tests", "__tests__", "spec", "specs")

_TEST_FILENAME = re.compile(
    r"(^test_|_test\.[^.]+$|\.test\.[^.]+$|\.spec\.[^.]+$|_spec\.[^.]+$|Tests?\.[^.]+$)"
)

_WILDCARD = ("*", "?", "[")


# ---------------------------------------------------------------------------
# Ecosystem scaffold table (an ENHANCEMENT, never the source of the rule)
# ---------------------------------------------------------------------------
#
# The primary contested-surface rule below is stated over the graph alone -- "two
# or more nodes in the same round create the first files in a directory that no
# node owns" -- and therefore protects Go, COBOL, or anything else without this
# table knowing the language. This table only makes the finding *more precise* by
# naming the specific artifact the ecosystem forces the contenders to share. A
# missing extension degrades to the directory rule; it never degrades to silence.
#
# Adding an ecosystem is a one-line data change: extensions it claims, marker
# file templates created inside every new package directory (``{dir}`` expands to
# that directory's own name), extra markers when the directory is under a test
# root, and repository-root manifests a brand-new top-level source root forces.


@dataclass(frozen=True)
class Ecosystem:
    name: str
    extensions: tuple[str, ...]
    package_markers: tuple[str, ...] = ()
    test_markers: tuple[str, ...] = ()
    root_manifests: tuple[str, ...] = ()
    # ``every``: a marker is required in every new package directory (Python
    # packages, Rust modules, TS barrels). ``deepest``: only the directory that
    # directly holds the new files is a project root (C# .csproj).
    placement: str = "every"
    # Some ecosystems constrain directory names (a Python package directory must
    # be an identifier). Directories that fail the pattern stop marker derivation
    # but are still covered by the directory-contention rule.
    segment_pattern: str | None = None
    # A top-level directory is a repository root, not a package, so markers start
    # at depth 2.
    min_depth: int = 2
    # Some markers are only real *below* a named directory. Rust's ``mod.rs``
    # declares a module inside a crate's source root: ``src/engine/mod.rs`` is
    # real, ``crates/engine/src/mod.rs`` and ``crates/engine/mod.rs`` are not
    # (that crate root wants ``Cargo.toml`` and ``src/lib.rs``, which this table
    # cannot locate). When the anchor is absent the marker is simply not emitted
    # and the language-neutral directory rule reports the surface instead --
    # a less precise finding, never a quieter one.
    marker_anchor: str | None = None
    # A test directory is a package in its own right in some ecosystems (a Python
    # test package, a .NET test project) and merely a folder of files in others
    # (a Jest ``__tests__`` directory has no barrel). False suppresses the
    # package marker under a test root without suppressing the directory rule.
    markers_in_test_roots: bool = True


ECOSYSTEMS: tuple[Ecosystem, ...] = (
    Ecosystem(
        name="python",
        extensions=(".py", ".pyi"),
        package_markers=("__init__.py",),
        test_markers=("conftest.py",),
        root_manifests=("pyproject.toml", "setup.cfg", "setup.py", "MANIFEST.in"),
        segment_pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    ),
    Ecosystem(
        name="typescript",
        extensions=(".ts", ".tsx", ".mts", ".cts"),
        package_markers=("index.ts",),
        root_manifests=("package.json", "tsconfig.json"),
        markers_in_test_roots=False,
    ),
    Ecosystem(
        name="javascript",
        extensions=(".js", ".jsx", ".mjs", ".cjs"),
        package_markers=("index.js",),
        root_manifests=("package.json",),
        markers_in_test_roots=False,
    ),
    Ecosystem(
        name="rust",
        extensions=(".rs",),
        package_markers=("mod.rs",),
        root_manifests=("Cargo.toml",),
        marker_anchor="src",
    ),
    Ecosystem(
        name="go",
        extensions=(".go",),
        root_manifests=("go.mod",),
    ),
    Ecosystem(
        name="csharp",
        extensions=(".cs",),
        package_markers=("{dir}.csproj",),
        placement="deepest",
    ),
)

_ECOSYSTEM_BY_EXTENSION: dict[str, Ecosystem] = {
    extension: ecosystem
    for ecosystem in ECOSYSTEMS
    for extension in ecosystem.extensions
}

# Repo-root manifests that a *new* top-level source root usually forces a node to
# touch (package discovery, workspace members, test roots). Derived from the
# table above so the two can never drift apart.
ROOT_MANIFESTS: tuple[str, ...] = tuple(
    dict.fromkeys(
        manifest for ecosystem in ECOSYSTEMS for manifest in ecosystem.root_manifests
    )
)

# A read scope is "universal" when it is a bare recursive glob or a whole
# top-level directory glob. Deeper globs (``src/pkg/sub/**``) stay allowed.
_BARE_RECURSIVE = {"**", "**/*", "**/**"}
_TOP_LEVEL_GLOB = re.compile(r"^[^/*?\[]+/\*\*(?:/\*)?$")

# Recovery vocabulary is restricted to *event and verb* forms: the plan asserting
# that something crashes, restarts, resumes, replays, or is interrupted. Bare
# abstract nouns ("recovery", "recoverable", "resilience") were the dominant
# false-positive source -- they appear in any node that merely *assesses* or
# *catalogues* recovery, which asserts no runtime guarantee of its own.
_RECOVERY_SEMANTICS = re.compile(
    r"\b(crash(?:es|ed)?|restart(?:s|ed|ing)?|resum(?:e|es|ed|ing|ption)"
    r"|interrupt(?:s|ed|ion|ions)?|replay(?:s|ed|ing)?"
    r"|recover(?:s|ed|ing)|power loss)\b",
    re.IGNORECASE,
)
# Deliberately phrase-based. Bare "PR" and bare "remote" appear as provenance
# nouns in almost every contract and are not evidence of an external effect.
_EXTERNAL_EFFECT = re.compile(
    r"\b(push(?:es|ed|ing)?|pull requests?|draft PRs?|PR comments?"
    r"|comment(?:s|ed|ing)?|deploy(?:s|ed|ing|ment|ments)?"
    r"|publish(?:es|ed|ing)?"
    r"|remote (?:write|writes|effect|effects|delivery|operation|operations))\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(
    r"\b(never|no|not|non|without|forbidden|forbids?|prohibit\w*|may not"
    r"|cannot|can not|must not|refus\w*|denie[sd]?|deny)\b",
    re.IGNORECASE,
)
# Passive denials negate the effect even when they trail it ("direct push and
# deploy are denied"), unlike qualifiers such as "without restating context".
_TRAILING_DENIAL = re.compile(
    r"\b(are|is|remain|remains|stay|stays|must be|must remain)\s+"
    r"(denied|forbidden|prohibited|rejected|blocked|refused|unavailable|impossible)\b",
    re.IGNORECASE,
)
# Durability *providers*: the property must be named by a semantic lock (the
# primary, precise signal) or by an objective that says the node *builds* the
# machinery. "Recoverable" and friends are excluded so a node that merely asserts
# recovery cannot certify itself as the thing that provides it.
_DURABILITY_LOCK = re.compile(
    r"durab|crash|replay|restart|resume|persist|checkpoint|idempot|outbox"
    r"|append-only|write-ahead|journal|reconcil",
    re.IGNORECASE,
)
_DURABILITY_PROVIDER_OBJECTIVE = re.compile(
    r"\b(?:implement|provide|build|establish|add|create|introduce|make|prove"
    r"|guarantee|enforce)\w*\b[^.]{0,140}?"
    r"\b(?:durability|durable|crash consistency|crash recovery|mission recovery"
    r"|event replay|replay|restart|resume|persistence|checkpoint(?:ing|s)?"
    r"|idempoten\w*|outbox|append-only|write-ahead log|journal(?:ing|s)?"
    r"|reconcil\w*)\b",
    re.IGNORECASE,
)

# The durability check is a *heuristic* over English prose. It is capped here so
# no keyword match can ever block a plan on its own.
DURABILITY_SEVERITY = "warning"


class DagStandardError(AutopilotError):
    """The supplied plan document cannot be interpreted as a DAG."""


def _text_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _normalize(scope: str) -> str:
    return scope.replace("\\", "/").strip().rstrip("/")


def _is_literal_path(scope: str) -> bool:
    return bool(scope) and not any(marker in scope for marker in _WILDCARD)


def _suffix(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    _, extension = os.path.splitext(name)
    return extension.lower()


def _wildcard_index(scope: str) -> int:
    return min(
        (index for marker in _WILDCARD if (index := scope.find(marker)) >= 0),
        default=len(scope),
    )


def _glob_directory(scope: str) -> str:
    """The concrete directory a glob write scope is rooted in.

    ``pkg/foo/**`` and ``pkg/foo/gen-*.go`` are both rooted in ``pkg/foo``. A
    glob with no static directory part (``**/*.py``) is rooted nowhere and is
    reported by the scope-syntax check instead.
    """

    head = scope[: _wildcard_index(scope)]
    if "/" not in head:
        return ""
    return head.rsplit("/", 1)[0].rstrip("/")


def _scopes_overlap(first: str, second: str, *, on_error: bool) -> bool:
    """``scopes_overlap`` that cannot raise.

    ``controller._scope_static_prefix`` raises ``ValueError`` on idiomatic but
    unanchored patterns (``**/*.py``, ``*.md``), on absolute paths, and on
    traversal. Callers choose what an unusable pattern means: the compiler treats
    it as a conflict (it cannot prove disjointness), the linter treats it as
    non-overlapping and reports the pattern itself through ``scope-syntax``.
    """

    try:
        return bool(scopes_overlap(first, second))
    except ValueError:
        return on_error


def _scope_error(scope: str) -> str | None:
    """The reason ``scope`` cannot be used as a lock pattern, or ``None``."""

    try:
        scopes_overlap(scope, scope)
    except ValueError as error:
        return str(error)
    return None


class PlanGraph:
    """An in-memory, repository-agnostic view of a plan's node graph."""

    def __init__(
        self,
        nodes: Iterable[Mapping[str, Any]],
        *,
        source: Path | None = None,
    ) -> None:
        self.source = source
        self._nodes: dict[str, Mapping[str, Any]] = {}
        self.duplicate_ids: list[str] = []
        for item in nodes:
            if not isinstance(item, Mapping):
                raise DagStandardError("every plan node must be an object")
            node_id = item.get("id")
            if not isinstance(node_id, str) or not node_id.strip():
                raise DagStandardError("every plan node must carry a non-empty string id")
            if node_id in self._nodes:
                self.duplicate_ids.append(node_id)
                continue
            self._nodes[node_id] = item
        if not self._nodes:
            raise DagStandardError("plan contains no nodes")

    # -- basic access -----------------------------------------------------

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._nodes))

    def node(self, node_id: str) -> Mapping[str, Any]:
        try:
            return self._nodes[node_id]
        except KeyError as error:
            raise DagStandardError(f"unknown node: {node_id}") from error

    def declared_dependencies(self, node_id: str) -> tuple[str, ...]:
        return tuple(_text_list(self.node(node_id).get("dependencies")))

    def dependencies(self, node_id: str) -> tuple[str, ...]:
        return tuple(
            dependency
            for dependency in self.declared_dependencies(node_id)
            if dependency in self._nodes
        )

    def missing_dependencies(self, node_id: str) -> tuple[str, ...]:
        return tuple(
            dependency
            for dependency in self.declared_dependencies(node_id)
            if dependency not in self._nodes
        )

    def declares_parallel_safe(self, node_id: str) -> bool:
        return "parallel_safe" in self.node(node_id)

    def parallel_safe(self, node_id: str) -> bool:
        return bool(self.node(node_id).get("parallel_safe"))

    def order_key(self, node_id: str) -> tuple[int, int, str]:
        """Exactly the dispatcher's greedy selection order."""

        node = self.node(node_id)
        return (
            -_int_field(node.get("critical_path_importance")),
            -_int_field(node.get("downstream_unlock_value")),
            node_id,
        )

    def conflicts(self, first_id: str, second_id: str) -> bool:
        """File-lock overlap or semantic-lock intersection (dispatcher logic).

        A lock pattern the dispatcher's own prefix parser rejects is reported as
        a conflict rather than raised: a plan the tool cannot reason about must
        never be *silently* packed into one round, and a linter must never die on
        the document it was asked to inspect.
        """

        try:
            return bool(_nodes_conflict(self, first_id, second_id))
        except ValueError:
            return True

    def write_scopes_overlap(self, first_id: str, second_id: str) -> bool:
        """Two nodes declare a write scope that can resolve to the same path.

        Independent of ``file_locks``: a generic plan may leave locks empty or
        inconsistent with the scopes, and the declared write scope is the thing
        the worker is actually told it may write.
        """

        return bool(self.overlapping_write_scopes(first_id, second_id))

    def overlapping_write_scopes(
        self, first_id: str, second_id: str, *, on_error: bool = True
    ) -> tuple[tuple[str, str], ...]:
        overlaps: list[tuple[str, str]] = []
        for first in _text_list(self.node(first_id).get("write_scope")):
            for second in _text_list(self.node(second_id).get("write_scope")):
                if _scopes_overlap(_normalize(first), _normalize(second), on_error=on_error):
                    overlaps.append((first, second))
        return tuple(overlaps)

    def may_share_round(self, first_id: str, second_id: str) -> bool:
        return not (
            self.conflicts(first_id, second_id)
            or self.write_scopes_overlap(first_id, second_id)
        )

    # -- graph shape ------------------------------------------------------

    def cycle(self) -> tuple[str, ...] | None:
        dependencies = {
            node_id: self.dependencies(node_id) for node_id in self._nodes
        }
        return _find_cycle(dependencies)

    def levels(self) -> dict[int, tuple[str, ...]]:
        """Longest-path BFS depth per node, grouped by level."""

        cycle = self.cycle()
        if cycle:
            raise DagStandardError("dependency cycle: " + " -> ".join(cycle))
        depth: dict[str, int] = {}
        pending = list(self._nodes)
        while pending:
            progressed = False
            remaining: list[str] = []
            for node_id in pending:
                dependencies = self.dependencies(node_id)
                if all(dependency in depth for dependency in dependencies):
                    depth[node_id] = (
                        0
                        if not dependencies
                        else 1 + max(depth[dependency] for dependency in dependencies)
                    )
                    progressed = True
                else:
                    remaining.append(node_id)
            if not progressed:
                raise DagStandardError("plan levels are not computable")
            pending = remaining
        grouped: dict[int, list[str]] = {}
        for node_id, level in depth.items():
            grouped.setdefault(level, []).append(node_id)
        return {
            level: tuple(sorted(grouped[level], key=self.order_key))
            for level in sorted(grouped)
        }

    def level_of(self) -> dict[str, int]:
        return {
            node_id: level
            for level, members in self.levels().items()
            for node_id in members
        }

    def ancestors(self, node_id: str) -> frozenset[str]:
        seen: set[str] = set()
        stack = list(self.dependencies(node_id))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(self.dependencies(current))
        return frozenset(seen)


def _int_field(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def load_plan_graph(path: str | Path) -> PlanGraph:
    plan_path = Path(path)
    if not plan_path.is_file():
        raise DagStandardError(f"plan file not found: {plan_path}")
    document = read_json(plan_path)
    if not isinstance(document, Mapping):
        raise DagStandardError("plan document must be an object")
    nodes = document.get("nodes")
    if not isinstance(nodes, list):
        raise DagStandardError("plan.nodes must be a list")
    return PlanGraph(nodes, source=plan_path)


# ---------------------------------------------------------------------------
# (A) dispatch-round compilation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Round:
    round_id: str
    level: int
    nodes: tuple[str, ...]
    parallel_safe: bool
    reason: str
    command: str
    deferred_after: tuple[str, ...] = ()

    @property
    def sessions(self) -> int:
        return len(self.nodes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_id": self.round_id,
            "level": self.level,
            "nodes": list(self.nodes),
            "sessions": self.sessions,
            "parallel_safe": self.parallel_safe,
            "reason": self.reason,
            "command": self.command,
            "deferred_after": list(self.deferred_after),
        }


@dataclass(frozen=True)
class Frontier:
    """The sole resumable dispatch frontier under one host-capacity lease."""

    state: str
    max_sessions: int
    round_id: str | None
    level: int | None
    round_nodes: tuple[str, ...]
    completed_nodes: tuple[str, ...]
    active_nodes: tuple[str, ...]
    release_nodes: tuple[str, ...]
    reason: str

    @property
    def frontier_id(self) -> str:
        material = {
            "state": self.state,
            "max_sessions": self.max_sessions,
            "round_id": self.round_id,
            "level": self.level,
            "round_nodes": self.round_nodes,
            "completed_nodes": self.completed_nodes,
            "active_nodes": self.active_nodes,
            "release_nodes": self.release_nodes,
        }
        body = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "sha256:" + hashlib.sha256(body).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "frontier_id": self.frontier_id,
            "state": self.state,
            "max_sessions": self.max_sessions,
            "round_id": self.round_id,
            "level": self.level,
            "round_nodes": list(self.round_nodes),
            "completed_nodes": list(self.completed_nodes),
            "active_nodes": list(self.active_nodes),
            "release_nodes": list(self.release_nodes),
            "reason": self.reason,
        }


def _render_path(path: Path) -> str:
    absolute = Path(os.path.abspath(path))
    try:
        rendered = absolute.relative_to(Path.cwd()).as_posix()
    except ValueError:
        rendered = absolute.as_posix()
    rendered = rendered or "."
    return f'"{rendered}"' if " " in rendered else rendered


def _same_file(first: Path, second: Path) -> bool:
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(
        os.path.abspath(second)
    )


def derived_repo_root(plan_path: Path | None) -> Path | None:
    """The repository a plan governs, read off the plan's own location."""

    if plan_path is None:
        return None
    if plan_path.parent.name == ".autopilot":
        return plan_path.parent.parent or Path(".")
    return plan_path.parent or Path(".")


def dispatch_command_prefix(
    *,
    plan_path: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> str:
    """The dispatch command prefix for *this* plan, in *this* checkout.

    A hardcoded ``--repo-root .`` is wrong in a generic clone: it silently
    targets whatever directory the operator happened to be standing in. The
    prefix is derived from the plan being compiled (or, failing that, from how
    this process was actually launched). A foreign plan is routed to the pure
    frontier contract instead of passing an unsupported ``--plan`` argument to
    the resident mutating dispatcher.
    """

    plan = Path(plan_path) if plan_path is not None else None
    root = Path(repo_root) if repo_root is not None else derived_repo_root(plan)
    if root is None:
        root = Path.cwd()
    script = root / DISPATCH_SCRIPT_RELPATH
    if not script.is_file():
        # This module *is* installed next to the dispatcher it is describing, so
        # its own location is the most reliable statement of where the entry
        # point actually lives.
        sibling = Path(__file__).resolve().with_name("autopilot.py")
        if sibling.is_file():
            script = sibling
    parts = ["python", _render_path(script), "--repo-root", _render_path(root)]
    if plan is not None and not _same_file(plan, root / ".autopilot" / "plan.json"):
        parts.extend(["dag-frontier", "--plan", _render_path(plan)])
    else:
        parts.append("dispatch")
    return " ".join(parts)


def _dispatch_command(
    prefix: str,
    actor: str,
    nodes: Sequence[str],
    *,
    max_sessions: int,
    completed_before: Sequence[str] = (),
) -> str:
    if " dag-frontier " in f" {prefix} ":
        return " ".join(
            (
                prefix,
                "--actor",
                actor,
                "--max-sessions",
                str(max_sessions),
                *(f"--complete {node}" for node in completed_before),
                *(f"--expect-release {node}" for node in nodes),
            )
        )
    return " ".join(
        (
            prefix,
            "--actor",
            actor,
            "--max-sessions",
            str(max_sessions),
            *(f"--node {node}" for node in nodes),
        )
    )


def semantic_ordering_constraints(
    graph: PlanGraph,
    level_of: Mapping[str, int],
    findings: Sequence[Finding] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Durability-ordering findings, expressed as scheduling constraints.

    This is the fix for a compiler that used to contradict its own linter: the
    linter would report that a resume/external-effect node cannot be proven
    before its durability provider, and the compiler would then dispatch them in
    the same round anyway.

    A durability provider that blocks a node in *its own level* is a release
    barrier: it is dispatched (and integrated) alone, and the rest of its level
    runs against that base. That is not a stylistic choice -- the whole point of
    the constraint is that the level's other members are proven against durable
    state, which only exists once the provider's round has landed. A provider in
    a *later* level defers only the node that named it.
    """

    if findings is None:
        findings = _check_durability_ordering(graph, level_of)
    members_by_level = graph.levels()
    barriers: dict[int, set[str]] = {}
    deferrals: dict[str, set[str]] = {}
    for finding in findings:
        if finding.check != "durability-ordering":
            continue
        consumer = finding.subject
        if consumer not in level_of:
            continue
        providers = [
            node_id
            for node_id in finding.nodes
            if node_id != consumer and node_id in level_of
        ]
        for provider in providers:
            if level_of[provider] == level_of[consumer]:
                barriers.setdefault(level_of[provider], set()).add(provider)
            else:
                deferrals.setdefault(consumer, set()).add(provider)
    for level, providers in barriers.items():
        for node_id in members_by_level.get(level, ()):
            if node_id in providers:
                continue
            deferrals.setdefault(node_id, set()).update(providers)
    return {node_id: tuple(sorted(value)) for node_id, value in sorted(deferrals.items())}


def _release_ranks(
    graph: PlanGraph,
    level_of: Mapping[str, int],
    constraints: Mapping[str, Sequence[str]],
) -> dict[str, int]:
    """Level, raised so every constrained node follows what it must follow.

    Rounds are emitted in ``(rank, level)`` order. Dependencies are folded into
    the same fixed point so a deferred provider can never be scheduled after a
    node that depends on it.
    """

    rank = {node_id: level_of[node_id] for node_id in graph.node_ids}
    for _ in range(len(rank) + 2):
        changed = False
        for node_id in graph.node_ids:
            floor = rank[node_id]
            for provider in constraints.get(node_id, ()):
                if provider in rank:
                    floor = max(floor, rank[provider] + 1)
            for dependency in graph.dependencies(node_id):
                floor = max(floor, rank[dependency])
            if floor > rank[node_id]:
                rank[node_id] = floor
                changed = True
        if not changed:
            break
    return rank


def contention_pairs(
    graph: PlanGraph,
    level_of: Mapping[str, int],
    findings: Sequence[Finding] | None = None,
    *,
    repo_root: Path | None = None,
) -> set[frozenset[str]]:
    """Scaffold-contention findings, expressed as may-not-share-a-round pairs.

    The durability constraint above stops the compiler contradicting the linter
    about *ordering*; this stops it contradicting the linter about *co-scheduling*.
    A scaffold-collision error says two or more nodes must each create the first
    files in a surface that neither owns. Dispatching them together is exactly the
    collision the linter rejects, so every pair drawn from a reported contention
    is barred from sharing a round. Deferring the loser to a later round makes the
    surface already exist, which is what resolves the contention.

    Only error-severity findings bar co-scheduling. Warnings describe a node
    reaching outside its own declared scope, which is a contract defect for its
    author to fix rather than a reason to reshape the schedule.
    """

    if findings is None:
        # _check_scaffold_collisions already composes the directory-contention
        # rule and suppresses a directory finding whose precise artifact it has
        # named. Calling both here would resurrect the suppressed half and bar
        # pairs the linter never reported -- the exact disagreement this
        # function exists to prevent.
        findings = _check_scaffold_collisions(graph, level_of, repo_root=repo_root)
    pairs: set[frozenset[str]] = set()
    for finding in findings:
        if finding.check != "scaffold-collision" or finding.severity != "error":
            continue
        members = sorted(set(finding.nodes))
        for index, first in enumerate(members):
            for second in members[index + 1 :]:
                pairs.add(frozenset((first, second)))
    return pairs


def compile_rounds(
    graph: PlanGraph,
    *,
    max_sessions: int = DEFAULT_MAX_SESSIONS,
    actor: str | None = None,
    semantic_ordering: bool = True,
    command_prefix: str | None = None,
    ordering_findings: Sequence[Finding] | None = None,
    contention_findings: Sequence[Finding] | None = None,
    repo_root: Path | None = None,
) -> tuple[Round, ...]:
    """Compile deterministic dispatch rounds from any plan.

    Within a release group, parallel-safe nodes are greedily packed into
    conflict-free groups of at most ``max_sessions`` members using the
    dispatcher's own conflict predicate and selection order (plus declared
    write-scope overlap, which the dispatcher does not model); every
    ``parallel_safe: false`` node becomes its own single-node round. Parallel
    groups are emitted before serial nodes so a high-importance serial node can
    never cap a wave at one session.

    With ``semantic_ordering`` enabled (the default) the durability-ordering
    findings additionally split a level, and nodes the linter reports as
    contending for an unowned shared scaffold are never packed together, so a
    compiled round can never be one the linter rejects.
    ``--no-semantic-ordering`` falls back to pure lock/capacity scheduling.
    """

    if max_sessions < 1:
        raise DagStandardError("max_sessions must be at least 1")
    if command_prefix is None:
        command_prefix = dispatch_command_prefix(plan_path=graph.source)
    levels = graph.levels()
    level_of = {
        node_id: level for level, members in levels.items() for node_id in members
    }
    constraints: dict[str, tuple[str, ...]] = {}
    contended: set[frozenset[str]] = set()
    if semantic_ordering:
        constraints = semantic_ordering_constraints(graph, level_of, ordering_findings)
        contended = contention_pairs(
            graph, level_of, contention_findings, repo_root=repo_root
        )
    rank = (
        _release_ranks(graph, level_of, constraints)
        if constraints
        else dict(level_of)
    )
    buckets: dict[tuple[int, int], list[str]] = {}
    for level, members in levels.items():
        for node_id in members:
            buckets.setdefault((rank[node_id], level), []).append(node_id)

    rounds: list[Round] = []
    for key in sorted(buckets):
        _, level = key
        members = buckets[key]
        deferred = tuple(
            sorted({provider for node_id in members for provider in constraints.get(node_id, ())})
        )
        deferral_note = (
            f"; deferred behind durability node(s) {', '.join(deferred)}" if deferred else ""
        )
        parallel = [node_id for node_id in members if graph.parallel_safe(node_id)]
        serial = [node_id for node_id in members if not graph.parallel_safe(node_id)]
        groups: list[list[str]] = []
        for node_id in parallel:
            for group in groups:
                if len(group) < max_sessions and all(
                    graph.may_share_round(node_id, chosen)
                    and frozenset((node_id, chosen)) not in contended
                    for chosen in group
                ):
                    group.append(node_id)
                    break
            else:
                groups.append([node_id])
        for index, group in enumerate(groups):
            if len(groups) == 1:
                reason = f"conflict-free parallel group ({len(group)} sessions)"
            else:
                reason = (
                    f"conflict-free parallel group {index + 1} of {len(groups)} "
                    f"({len(group)} sessions; cap {max_sessions})"
                )
            rounds.append(
                _make_round(
                    len(rounds) + 1,
                    level,
                    tuple(group),
                    True,
                    reason + deferral_note,
                    actor,
                    command_prefix,
                    max_sessions=max_sessions,
                    completed_before=tuple(
                        prior for item in rounds for prior in item.nodes
                    ),
                    deferred_after=deferred,
                )
            )
        for node_id in serial:
            rounds.append(
                _make_round(
                    len(rounds) + 1,
                    level,
                    (node_id,),
                    False,
                    "serial node released alone (parallel_safe: false)" + deferral_note,
                    actor,
                    command_prefix,
                    max_sessions=max_sessions,
                    completed_before=tuple(
                        prior for item in rounds for prior in item.nodes
                    ),
                    deferred_after=deferred,
                )
            )
    return tuple(rounds)


def select_frontier(
    graph: PlanGraph,
    *,
    completed_nodes: Sequence[str] = (),
    active_nodes: Sequence[str] = (),
    max_sessions: int = DEFAULT_MAX_SESSIONS,
    actor: str | None = None,
    semantic_ordering: bool = True,
    command_prefix: str | None = None,
    repo_root: Path | None = None,
) -> Frontier:
    """Select the first incomplete compiled round without redispatching work.

    ``completed_nodes`` must come from the caller's durable acceptance authority;
    this function never manufactures completion. ``active_nodes`` are durable
    launch/lease records. They consume capacity and may occur only in the current
    compiled round. The returned release set therefore excludes both accepted and
    already-active work and can safely be replayed after a controller crash.
    """

    if max_sessions < 1:
        raise DagStandardError("max_sessions must be at least 1")
    known = set(graph.node_ids)
    completed = tuple(dict.fromkeys(str(item) for item in completed_nodes))
    active = tuple(dict.fromkeys(str(item) for item in active_nodes))
    unknown = sorted((set(completed) | set(active)) - known)
    if unknown:
        raise DagStandardError("frontier state names unknown nodes: " + ", ".join(unknown))
    overlap = sorted(set(completed) & set(active))
    if overlap:
        raise DagStandardError("completed nodes cannot remain active: " + ", ".join(overlap))
    if len(active) > max_sessions:
        raise DagStandardError("active node count exceeds the host session cap")

    completed_set = set(completed)
    rounds = compile_rounds(
        graph,
        max_sessions=max_sessions,
        actor=actor,
        semantic_ordering=semantic_ordering,
        command_prefix=command_prefix,
        repo_root=repo_root,
    )
    current = next(
        (item for item in rounds if not set(item.nodes) <= completed_set),
        None,
    )
    if current is None:
        if active:
            raise DagStandardError("active nodes remain after every compiled round is complete")
        return Frontier(
            state="PLAN_QUIESCENT",
            max_sessions=max_sessions,
            round_id=None,
            level=None,
            round_nodes=(),
            completed_nodes=tuple(sorted(completed_set)),
            active_nodes=(),
            release_nodes=(),
            reason="every compiled round is accepted and no work remains active",
        )

    current_set = set(current.nodes)
    outside = sorted(set(active) - current_set)
    if outside:
        raise DagStandardError(
            "active nodes exist outside the first incomplete compiled round: "
            + ", ".join(outside)
        )
    active_in_order = tuple(node for node in current.nodes if node in set(active))
    accepted_in_round = tuple(node for node in current.nodes if node in completed_set)
    pending = tuple(
        node
        for node in current.nodes
        if node not in completed_set and node not in set(active_in_order)
    )
    available = max_sessions - len(active_in_order)
    release = pending[:available]
    state = "ROUND_READY" if release else "ROUND_ACTIVE"
    reason = (
        f"{current.round_id} is the first incomplete compiled round; "
        f"{len(active_in_order)} active, {len(accepted_in_round)} accepted, "
        f"{len(release)} releasable under cap {max_sessions}"
    )
    return Frontier(
        state=state,
        max_sessions=max_sessions,
        round_id=current.round_id,
        level=current.level,
        round_nodes=current.nodes,
        completed_nodes=accepted_in_round,
        active_nodes=active_in_order,
        release_nodes=release,
        reason=reason,
    )


def _make_round(
    index: int,
    level: int,
    nodes: tuple[str, ...],
    parallel_safe: bool,
    reason: str,
    actor: str | None,
    command_prefix: str,
    *,
    max_sessions: int,
    completed_before: tuple[str, ...] = (),
    deferred_after: tuple[str, ...] = (),
) -> Round:
    round_id = f"R{index}"
    resolved_actor = actor or f"{DEFAULT_ACTOR_NAMESPACE}:{round_id.lower()}"
    return Round(
        round_id=round_id,
        level=level,
        nodes=nodes,
        parallel_safe=parallel_safe,
        reason=reason,
        command=_dispatch_command(
            command_prefix,
            resolved_actor,
            nodes,
            max_sessions=max_sessions,
            completed_before=completed_before,
        ),
        deferred_after=deferred_after,
    )


def rounds_by_level(rounds: Sequence[Round]) -> dict[int, tuple[Round, ...]]:
    grouped: dict[int, list[Round]] = {}
    for item in rounds:
        grouped.setdefault(item.level, []).append(item)
    return {level: tuple(grouped[level]) for level in sorted(grouped)}


# ---------------------------------------------------------------------------
# (B) authoring-standard lint
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    check: str
    severity: str
    message: str
    fix: str
    nodes: tuple[str, ...] = ()
    subject: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "severity": self.severity,
            "nodes": list(self.nodes),
            "subject": self.subject,
            "message": self.message,
            "fix": self.fix,
        }


@dataclass
class _Implication:
    """One scaffold file implied by node write scopes."""

    path: str
    kind: str
    by_level: dict[int, list[str]] = field(default_factory=dict)


@dataclass
class _Surface:
    """One directory that plan nodes create the first files in."""

    directory: str
    by_level: dict[int, list[str]] = field(default_factory=dict)
    ecosystems: set[str] = field(default_factory=set)


def _sort_findings(findings: Iterable[Finding]) -> tuple[Finding, ...]:
    return tuple(
        sorted(
            findings,
            key=lambda item: (
                _SEVERITY_RANK.get(item.severity, len(SEVERITIES)),
                item.check,
                item.subject,
                item.nodes,
                item.message,
            ),
        )
    )


def _check_graph_validity(graph: PlanGraph) -> list[Finding]:
    findings: list[Finding] = []
    for node_id in sorted(set(graph.duplicate_ids)):
        findings.append(
            Finding(
                check="graph-validity",
                severity="error",
                nodes=(node_id,),
                subject=node_id,
                message=f"node id {node_id} is declared more than once",
                fix=f"Give every node a unique id; rename or merge the duplicate {node_id}.",
            )
        )
    for node_id in graph.node_ids:
        for dependency in graph.missing_dependencies(node_id):
            findings.append(
                Finding(
                    check="graph-validity",
                    severity="error",
                    nodes=(node_id,),
                    subject=dependency,
                    message=f"{node_id} depends on unknown node {dependency}",
                    fix=(
                        f"Add the missing node {dependency} to the plan or remove it "
                        f"from {node_id}.dependencies."
                    ),
                )
            )
        if node_id in graph.declared_dependencies(node_id):
            findings.append(
                Finding(
                    check="graph-validity",
                    severity="error",
                    nodes=(node_id,),
                    subject=node_id,
                    message=f"{node_id} depends on itself",
                    fix=f"Remove {node_id} from its own dependencies list.",
                )
            )
    cycle = graph.cycle()
    if cycle:
        findings.append(
            Finding(
                check="graph-validity",
                severity="error",
                nodes=tuple(dict.fromkeys(cycle)),
                subject=cycle[0],
                message="dependency cycle: " + " -> ".join(cycle),
                fix=(
                    "Break the cycle by removing one dependency edge, or split the "
                    "shared work into a node both sides can depend on."
                ),
            )
        )
    return findings


def _check_scope_syntax(graph: PlanGraph) -> list[Finding]:
    """Scope patterns the dispatcher's own lock parser cannot use.

    Without this the tool crashed: ``PlanGraph.conflicts`` reaches
    ``controller._scope_static_prefix``, which raises ``ValueError`` on
    unanchored globs (``**/*.py``, ``*.md``), absolute paths, and traversal.
    A malformed scope is an authoring defect that must be reported, not a
    traceback out of ``dag-lint`` and ``dag-rounds``.
    """

    findings: list[Finding] = []
    for node_id in graph.node_ids:
        node = graph.node(node_id)
        for name in LOCKING_SCOPE_FIELDS:
            for raw in _text_list(node.get(name)):
                scope = _normalize(raw)
                reason = _scope_error(scope) if scope else "scope must be non-empty text"
                if reason is None:
                    continue
                findings.append(
                    Finding(
                        check="scope-syntax",
                        severity="error",
                        nodes=(node_id,),
                        subject=raw,
                        message=(
                            f"{node_id}.{name} entry {raw!r} is not a usable scope "
                            f"pattern: {reason}"
                        ),
                        fix=(
                            f"Anchor {raw!r} on {node_id} to a concrete repository-relative "
                            "directory (for example 'src/pkg/**' instead of '**/*.py'); "
                            "conflict detection cannot compare a pattern with no static "
                            "prefix, so the compiler must assume it collides with "
                            "everything."
                        ),
                    )
                )
    return findings


def _check_parallel_safe_declaration(graph: PlanGraph) -> list[Finding]:
    """A plan that never says ``parallel_safe`` is silently fully serialized."""

    missing = tuple(
        node_id for node_id in graph.node_ids if not graph.declares_parallel_safe(node_id)
    )
    if not missing:
        return []
    if len(missing) == len(graph.node_ids):
        return [
            Finding(
                check="parallel-safe-declaration",
                severity="warning",
                nodes=missing,
                subject="plan",
                message=(
                    f"no node in this plan declares parallel_safe ({len(missing)} nodes); "
                    "every node compiles into a single-session round and the whole plan "
                    "is serialized without saying so"
                ),
                fix=(
                    "Declare parallel_safe explicitly on every node. A node is "
                    "parallel_safe when its write scope, locks, and external effects are "
                    "disjoint from its level siblings; say false deliberately, never by "
                    "omission."
                ),
            )
        ]
    return [
        Finding(
            check="parallel-safe-declaration",
            severity="warning",
            nodes=(node_id,),
            subject=node_id,
            message=(
                f"{node_id} does not declare parallel_safe while its siblings do; it is "
                "treated as serial and released alone"
            ),
            fix=(
                f"Declare parallel_safe explicitly on {node_id}; omission is read as "
                "false and silently costs a dispatch round."
            ),
        )
        for node_id in missing
    ]


def _check_contract_completeness(graph: PlanGraph) -> list[Finding]:
    findings: list[Finding] = []
    for node_id in graph.node_ids:
        node = graph.node(node_id)
        for name in CONTRACT_FIELDS:
            value = node.get(name)
            if isinstance(value, str):
                complete = bool(value.strip())
            elif isinstance(value, list):
                complete = bool(
                    [item for item in value if isinstance(item, str) and item.strip()]
                )
            else:
                complete = False
            if not complete:
                findings.append(
                    Finding(
                        check="contract-completeness",
                        severity="error",
                        nodes=(node_id,),
                        subject=name,
                        message=f"{node_id} has no usable {name}",
                        fix=(
                            f"Declare a concrete non-empty {name} on {node_id}; a worker "
                            "prompt is only a contract when every gate field is stated."
                        ),
                    )
                )
    return findings


def _check_read_scopes(graph: PlanGraph) -> list[Finding]:
    findings: list[Finding] = []
    for node_id in graph.node_ids:
        for raw in _text_list(graph.node(node_id).get("read_scope")):
            scope = _normalize(raw)
            universal = scope in _BARE_RECURSIVE or bool(_TOP_LEVEL_GLOB.match(scope))
            if not universal:
                continue
            findings.append(
                Finding(
                    check="universal-read-scope",
                    severity="warning",
                    nodes=(node_id,),
                    subject=raw,
                    message=(
                        f"{node_id} declares universal read scope {raw!r}; a worker is "
                        "invited to read the whole tree it covers"
                    ),
                    fix=(
                        f"Replace {raw!r} on {node_id} with the concrete paths the node "
                        "actually needs plus a metadata-only index (paths/sizes/symbols), "
                        "and allow a budgeted cold expansion that the node must record as "
                        "evidence when it proves its scope was incomplete."
                    ),
                )
            )
    return findings


def _check_write_scope_overlap(
    graph: PlanGraph,
    level_of: Mapping[str, int],
) -> list[Finding]:
    """Two co-schedulable nodes declare a write scope resolving to one path.

    Deliberately independent of ``file_locks``: a generic plan may leave locks
    empty, or narrower than the scope the worker is told it may write. Two nodes
    that literally name the same file in ``write_scope`` produced *zero* findings
    before this check, and were then packed into the same dispatch round.
    """

    findings: list[Finding] = []
    candidates = [
        node_id for node_id in graph.node_ids if graph.parallel_safe(node_id)
    ]
    for index, first_id in enumerate(candidates):
        for second_id in candidates[index + 1 :]:
            if level_of[first_id] != level_of[second_id]:
                continue
            overlaps = graph.overlapping_write_scopes(first_id, second_id, on_error=False)
            if not overlaps:
                continue
            rendered = ", ".join(
                sorted({f"{first!r} vs {second!r}" for first, second in overlaps})
            )
            findings.append(
                Finding(
                    check="write-scope-overlap",
                    severity="error",
                    nodes=(first_id, second_id),
                    subject=overlaps[0][0],
                    message=(
                        f"{first_id} and {second_id} are parallel-safe at the same "
                        f"dependency level ({level_of[first_id]}) and declare overlapping "
                        f"write scopes ({rendered})"
                    ),
                    fix=(
                        f"Give the overlapping paths exactly one owner: narrow one of "
                        f"{first_id}/{second_id}, or make one depend on the other so they "
                        "cannot be released together. Do not rely on file_locks to catch "
                        "this; write_scope is what the worker is told it may write."
                    ),
                )
            )
    return findings


def _created_paths(graph: PlanGraph, node_id: str) -> list[str]:
    """Literal file paths this node's contract obliges it to create."""

    paths: list[str] = []
    for raw in _text_list(graph.node(node_id).get("write_scope")):
        scope = _normalize(raw)
        if _is_literal_path(scope) and "/" in scope and _suffix(scope):
            paths.append(scope)
    return paths


def _created_directories(graph: PlanGraph, node_id: str) -> dict[str, set[str]]:
    """Directories this node writes the first files into, and their extensions.

    Both literal paths and *glob* write scopes count. A node scoped
    ``pkg/foo/**`` still creates files in ``pkg/foo``; treating a glob as
    invisible was what disabled contention analysis for every plan that scopes by
    directory -- in every ecosystem, Python included.

    Note the asymmetry this preserves, which is the sharp distinction the first
    pass got right: a glob is **permission**, a literal path is **obligation**.
    A glob makes a node a *creator* of the directory (it will put files there),
    but it never makes it the *owner* of a shared file inside it -- nothing in
    ``pkg/foo/**`` says who is accountable for ``pkg/foo/index.ts``. Only a node
    that NAMES the file can be its owner.

    **No extension is required.** Requiring a dot in the last segment is a
    language assumption, not a fact about repositories: ``Dockerfile``,
    ``Makefile``, ``BUILD``, ``WORKSPACE``, ``Earthfile``, ``Gemfile``,
    ``Jenkinsfile`` and every extensionless shell entry point are ordinary
    files, and a plan whose two nodes both create the first of them in a new
    directory is contesting that directory exactly as much as two ``.go`` files
    would. A literal multi-segment scope therefore always contributes its parent
    as a created directory; a *top-level* scope (``src``, ``Makefile``) has no
    parent below the repository root and is skipped by the caller, so reading a
    literal directory scope as a file can never invent a surface.
    """

    directories: dict[str, set[str]] = {}
    for raw in _text_list(graph.node(node_id).get("write_scope")):
        scope = _normalize(raw)
        if not scope:
            continue
        if _is_literal_path(scope):
            if "/" not in scope:
                continue
            directory = scope.rsplit("/", 1)[0]
            directories.setdefault(directory, set()).add(_suffix(scope))
            continue
        directory = _glob_directory(scope)
        if directory:
            directories.setdefault(directory, set()).add(_suffix(scope))
    return directories


def _is_test_path(path: str) -> bool:
    parts = path.split("/")
    if any(segment.lower() in TEST_ROOTS for segment in parts[:-1]):
        return True
    return bool(_TEST_FILENAME.search(parts[-1]))


def _implied_scaffolds(path: str) -> list[tuple[str, str]]:
    """Scaffold files a newly created source path implies, per ecosystem.

    This is the *enhancement* layer: when the extension is recognized it names
    the concrete artifact the ecosystem forces every node in that directory to
    share (``a/b/c.py`` implies ``a/b/__init__.py`` and every package ancestor
    below the top-level directory; ``a/b/c.ts`` implies ``a/b/index.ts``; and so
    on). An unrecognized extension returns nothing here and is handled by the
    language-neutral directory-contention rule instead -- never by silence.
    """

    ecosystem = _ECOSYSTEM_BY_EXTENSION.get(_suffix(path))
    if ecosystem is None or not ecosystem.package_markers:
        return []
    parts = path.split("/")
    directories = parts[:-1]
    if len(directories) < ecosystem.min_depth:
        return []
    test_path = _is_test_path(path)
    if test_path and not ecosystem.markers_in_test_roots:
        return []
    depths = (
        range(ecosystem.min_depth, len(directories) + 1)
        if ecosystem.placement == "every"
        else (len(directories),)
    )
    implied: list[tuple[str, str]] = []
    for depth in depths:
        segments = directories[:depth]
        if ecosystem.segment_pattern and not all(
            re.match(ecosystem.segment_pattern, segment) for segment in segments[1:]
        ):
            break
        if ecosystem.marker_anchor is not None and ecosystem.marker_anchor not in (
            segments[:-1]
        ):
            # The marker only exists strictly below the anchor directory.
            continue
        directory = "/".join(segments)
        for template in ecosystem.package_markers:
            implied.append(
                (
                    f"{directory}/{template.format(dir=segments[-1])}",
                    f"{ecosystem.name}-package-marker",
                )
            )
    if implied and ecosystem.test_markers and test_path:
        deepest = "/".join(directories)
        for template in ecosystem.test_markers:
            implied.append(
                (
                    f"{deepest}/{template.format(dir=directories[-1])}",
                    f"{ecosystem.name}-test-marker",
                )
            )
    return implied


def _root_manifests(extensions: Iterable[str]) -> tuple[str, ...]:
    manifests: list[str] = []
    for extension in extensions:
        ecosystem = _ECOSYSTEM_BY_EXTENSION.get(extension)
        if ecosystem is None:
            continue
        manifests.extend(ecosystem.root_manifests)
    return tuple(dict.fromkeys(manifests))


def _top_level_source_roots(graph: PlanGraph, node_id: str) -> dict[str, set[str]]:
    roots: dict[str, set[str]] = {}
    for directory, extensions in _created_directories(graph, node_id).items():
        root = directory.split("/")[0]
        if root:
            roots.setdefault(root, set()).update(extensions)
    return roots


def _covers(graph: PlanGraph, node_id: str, path: str) -> bool:
    """The node's write_scope permits writing ``path`` (literally or by glob)."""

    for raw in _text_list(graph.node(node_id).get("write_scope")):
        scope = _normalize(raw)
        if not scope:
            continue
        try:
            if path_matches_scope(path, scope):
                return True
        except ValueError:
            continue
    return False


def _names(graph: PlanGraph, node_id: str, path: str) -> bool:
    """The node's write_scope names ``path`` literally.

    A glob that merely covers a scaffold file is *permission*, not *obligation*:
    nothing in such a contract requires that node to create the file. Only a
    literal entry (or a node that itself creates files in that directory) makes
    an owner accountable for the scaffold.
    """

    return any(
        _normalize(raw) == path
        for raw in _text_list(graph.node(node_id).get("write_scope"))
    )


def _forbids(graph: PlanGraph, node_id: str, path: str) -> bool:
    for raw in _text_list(graph.node(node_id).get("forbidden_scope")):
        scope = _normalize(raw)
        if not scope:
            continue
        try:
            if path_matches_scope(path, scope):
                return True
        except ValueError:
            continue
    return False


def _check_directory_contention(
    graph: PlanGraph,
    level_of: Mapping[str, int],
    *,
    repo_root: Path | None,
    covered: Iterable[str] = (),
) -> list[Finding]:
    """PRIMARY RULE, language-neutral: two creators, one unowned directory.

    If two or more nodes in the same release group each create the *first* files
    inside a directory that no node names as an owner, that directory is a
    contested shared surface. This needs no knowledge of the ecosystem, so a Go,
    Rust, C#, TypeScript, or COBOL plan is protected identically to a Python one.

    "First files" is meant literally, so a directory that already exists in the
    repository is not a new shared surface and is skipped -- but only when a
    repository is actually available to look at. With no repo (a synthetic or
    pre-clone plan) every directory is treated as new, which is the conservative
    reading.
    """

    already_reported = set(covered)
    surfaces: dict[str, _Surface] = {}
    for node_id in graph.node_ids:
        for directory, extensions in _created_directories(graph, node_id).items():
            if directory.count("/") < 1:
                # A top-level directory is a repository root, not a package.
                continue
            surface = surfaces.setdefault(directory, _Surface(directory=directory))
            surface.by_level.setdefault(level_of[node_id], []).append(node_id)
            surface.ecosystems.update(extensions)

    findings: list[Finding] = []
    for directory in sorted(surfaces):
        if directory in already_reported:
            # The ecosystem table already named the concrete contested artifact
            # inside this directory; one precise finding beats two vague ones.
            continue
        if repo_root is not None and (repo_root / directory).is_dir():
            continue
        surface = surfaces[directory]
        earliest = min(surface.by_level)
        creators = tuple(sorted(dict.fromkeys(surface.by_level[earliest])))
        if len(creators) < 2:
            continue
        owners = tuple(
            sorted(
                node_id
                for node_id in graph.node_ids
                if level_of[node_id] <= earliest and _names(graph, node_id, directory)
            )
        )
        if len(owners) == 1:
            continue
        if all(_forbids(graph, node_id, directory) for node_id in creators):
            continue
        findings.append(
            Finding(
                check="scaffold-collision",
                severity="error",
                nodes=creators,
                subject=directory,
                message=(
                    f"{directory}/ is a contested shared surface: {', '.join(creators)} "
                    f"all create the first files in it at level {earliest} and no node "
                    "names it as an owner"
                ),
                fix=(
                    f"Give {directory}/ exactly one named owner before those nodes run: "
                    "add the directory (and any marker/manifest file the ecosystem "
                    "requires inside it) to one node's write_scope and file_locks and "
                    "make the others depend on it, or hoist its creation into a prior "
                    "node all contenders depend on."
                ),
            )
        )
    return findings


def _check_scaffold_collisions(
    graph: PlanGraph,
    level_of: Mapping[str, int],
    *,
    repo_root: Path | None,
) -> list[Finding]:
    implications: dict[str, _Implication] = {}

    def record(path: str, kind: str, node_id: str) -> None:
        entry = implications.setdefault(path, _Implication(path=path, kind=kind))
        entry.by_level.setdefault(level_of[node_id], []).append(node_id)

    for node_id in graph.node_ids:
        for path in _created_paths(graph, node_id):
            for scaffold, kind in _implied_scaffolds(path):
                record(scaffold, kind, node_id)

    # New top-level source roots additionally imply the repo-root manifests that
    # declare packages, workspace members, or test roots -- taken from the
    # ecosystem table of the files actually being created under that root.
    seen_roots: dict[str, int] = {}
    for node_id in sorted(graph.node_ids, key=lambda item: (level_of[item], item)):
        for root in _top_level_source_roots(graph, node_id):
            seen_roots.setdefault(root, level_of[node_id])
    for root, first_level in seen_roots.items():
        introducing: list[str] = []
        extensions: set[str] = set()
        for node_id in graph.node_ids:
            roots = _top_level_source_roots(graph, node_id)
            if level_of[node_id] == first_level and root in roots:
                introducing.append(node_id)
                extensions.update(roots[root])
        if len(introducing) < 2:
            continue
        # Without a repository to inspect there is no way to know which manifests
        # exist, and guessing would bury real scaffold findings under noise.
        manifests = (
            ()
            if repo_root is None
            else tuple(
                name for name in _root_manifests(extensions) if (repo_root / name).is_file()
            )
        )
        for name in manifests:
            entry = implications.setdefault(name, _Implication(path=name, kind="root-manifest"))
            entry.by_level.setdefault(first_level, []).extend(sorted(introducing))

    findings: list[Finding] = []
    covered_directories: set[str] = set()
    for path in sorted(implications):
        # Only a scaffold that does not yet exist is contended, and only inside a
        # directory that does not yet exist. An established directory has already
        # settled its markers -- a missing conftest.py beside working tests means
        # none is needed, not that two nodes are racing to add one. This mirrors
        # the base directory-contention rule, which likewise judges only *first*
        # files. Without a repo_root (a synthetic or pre-clone plan) nothing
        # exists yet, so every implied scaffold stays in scope.
        entry = implications[path]
        if repo_root is not None and entry.kind != "root-manifest":
            if (repo_root / path).exists():
                continue
            parent = path.rsplit("/", 1)[0] if "/" in path else ""
            if parent and (repo_root / parent).is_dir():
                continue
        earliest = min(entry.by_level)
        impliers = tuple(sorted(dict.fromkeys(entry.by_level[earliest])))
        # An owner is a node that names the scaffold literally, or an implier
        # whose own write scope already covers it. Every other node whose glob
        # happens to cover the path only *permits* the write.
        owners = tuple(
            sorted(
                {
                    node_id
                    for node_id in graph.node_ids
                    if level_of[node_id] <= earliest and _names(graph, node_id, path)
                }
                | {
                    node_id
                    for node_id in impliers
                    if _covers(graph, node_id, path)
                }
            )
        )
        permissive = tuple(
            node_id
            for node_id in graph.node_ids
            if node_id not in owners
            and level_of[node_id] <= earliest
            and _covers(graph, node_id, path)
        )
        forbidding = tuple(
            node_id for node_id in impliers if _forbids(graph, node_id, path)
        )
        manifest = entry.kind == "root-manifest"
        if not manifest and "/" in path and len(impliers) >= 2:
            covered_directories.add(path.rsplit("/", 1)[0])
        if len(owners) == 1:
            continue
        if forbidding and len(forbidding) == len(impliers) and not owners:
            # Explicitly forbidden for everyone who could create it: the plan has
            # made a deliberate, auditable decision.
            continue
        permission_note = (
            f" (only covered by the glob write scope of {', '.join(permissive)}, which is "
            "permission, not obligation)"
            if permissive
            else ""
        )
        if len(impliers) >= 2:
            severity = "warning" if manifest else "error"
            if owners:
                message = (
                    f"{path} is implied by {', '.join(impliers)} at level {earliest} and "
                    f"owned by {len(owners)} nodes ({', '.join(owners)})"
                )
                fix = (
                    f"Name {path} in exactly one node's write_scope and file_locks; remove "
                    "it from the others and let them depend on that single owner."
                )
            else:
                message = (
                    f"{path} is implied by {', '.join(impliers)} at level {earliest} but is "
                    f"named in no node's write_scope{permission_note}"
                )
                fix = (
                    f"Name exactly one owner node for {path} (add the literal path to its "
                    "write_scope and file_locks, and make the other nodes depend on it), or "
                    "forbid it explicitly in every other node's forbidden_scope; same-level "
                    "nodes cannot both create it."
                )
        else:
            severity = "warning"
            if manifest:
                continue
            message = (
                f"{path} is implied by {impliers[0]} but is outside its declared "
                f"write_scope{permission_note}"
            )
            fix = (
                f"Add {path} to {impliers[0]}'s write_scope and file_locks so the scaffold "
                "has one named owner instead of an undeclared write."
            )
        findings.append(
            Finding(
                check="scaffold-collision",
                severity=severity,
                nodes=impliers,
                subject=path,
                message=message,
                fix=fix,
            )
        )
    findings.extend(
        _check_directory_contention(
            graph, level_of, repo_root=repo_root, covered=covered_directories
        )
    )
    return findings


def _asserted_semantics(node: Mapping[str, Any]) -> tuple[str, ...]:
    """Criteria that assert recovery or external-effect semantics.

    A criterion is ignored when a negation appears *before* the matched phrase
    ("No hidden deploy authority is introduced"), but not when the negation
    follows it ("resumes after interruption without restating context").
    """

    statements = [node.get("objective"), *(_text_list(node.get("acceptance_criteria")))]
    asserted: list[str] = []
    for statement in statements:
        if not isinstance(statement, str) or not statement.strip():
            continue
        match = _RECOVERY_SEMANTICS.search(statement) or _EXTERNAL_EFFECT.search(statement)
        if match is None:
            continue
        if _TRAILING_DENIAL.search(statement):
            continue
        negation = _NEGATION.search(statement)
        if negation is not None and negation.start() < match.start():
            continue
        asserted.append(statement.strip())
    return tuple(asserted)


def _is_durability_provider(node: Mapping[str, Any]) -> bool:
    """The node *builds* the durable state others rely on.

    ``semantic_locks`` first: a lock is a declared, machine-meaningful name and
    is far more reliable than prose. The objective fallback requires an
    implementing verb governing a durability noun, so a node that merely claims
    to be recoverable cannot certify itself, while a node whose whole job is
    "implement the reconciler for mission recovery" is correctly recognized
    instead of being reported as its own violator.
    """

    locks = " ".join(_text_list(node.get("semantic_locks")))
    if locks and _DURABILITY_LOCK.search(locks):
        return True
    objective = node.get("objective")
    return isinstance(objective, str) and bool(
        _DURABILITY_PROVIDER_OBJECTIVE.search(objective)
    )


def _check_durability_ordering(
    graph: PlanGraph,
    level_of: Mapping[str, int],
) -> list[Finding]:
    providers = tuple(
        node_id
        for node_id in graph.node_ids
        if _is_durability_provider(graph.node(node_id))
    )
    findings: list[Finding] = []
    for node_id in graph.node_ids:
        node = graph.node(node_id)
        if node_id in providers:
            continue
        asserted = _asserted_semantics(node)
        if not asserted:
            continue
        if not providers:
            findings.append(
                Finding(
                    check="durability-ordering",
                    severity=DURABILITY_SEVERITY,
                    nodes=(node_id,),
                    subject=node_id,
                    message=(
                        f"{node_id} asserts crash/restart/resume or external-effect "
                        f"semantics ({asserted[0]!r}) but the plan has no durability node"
                    ),
                    fix=(
                        f"Add a durability node (crash consistency, replay, append-only "
                        f"state) and make {node_id} depend on it; otherwise this claim "
                        "cannot be honestly proven."
                    ),
                )
            )
            continue
        ancestors = graph.ancestors(node_id)
        pending = [
            provider
            for provider in providers
            if provider not in ancestors and level_of[provider] >= level_of[node_id]
        ]
        if not pending:
            continue
        # Name only the earliest unproven durability node(s): those are the ones
        # this node must be ordered behind.
        blocking_level = min(level_of[provider] for provider in pending)
        unsatisfied = tuple(
            provider for provider in pending if level_of[provider] == blocking_level
        )
        where = (
            f"at the same dependency level ({level_of[node_id]})"
            if blocking_level == level_of[node_id]
            else f"at dependency level {blocking_level}"
        )
        findings.append(
            Finding(
                check="durability-ordering",
                severity=DURABILITY_SEVERITY,
                nodes=(node_id, *unsatisfied),
                subject=node_id,
                message=(
                    f"{node_id} asserts crash/restart/resume or external-effect semantics "
                    f"({asserted[0]!r}) but does not depend on durability node(s) "
                    f"{', '.join(unsatisfied)} {where}"
                ),
                fix=(
                    f"Depend {node_id} on {', '.join(unsatisfied)}. Until that edge exists "
                    "dag-rounds enforces the ordering as round order: the durability node "
                    "is released alone and the rest of its level follows (pass "
                    "--no-semantic-ordering to see the unordered schedule). A resume/replay "
                    "or external effect claim is unprovable before durability exists."
                ),
            )
        )
    return findings


def _check_serial_in_level(
    graph: PlanGraph,
    rounds: Sequence[Round],
    *,
    max_sessions: int,
) -> list[Finding]:
    findings: list[Finding] = []
    grouped = rounds_by_level(rounds)
    for level, members in graph.levels().items():
        serial = [node_id for node_id in members if not graph.parallel_safe(node_id)]
        parallel = [node_id for node_id in members if graph.parallel_safe(node_id)]
        level_rounds = grouped.get(level, ())
        if serial and parallel:
            findings.append(
                Finding(
                    check="serial-in-level",
                    severity="info",
                    nodes=tuple(serial),
                    subject=str(level),
                    message=(
                        f"level {level} mixes {len(parallel)} parallel-safe nodes with "
                        f"serial node(s) {', '.join(serial)}; it compiles into "
                        f"{len(level_rounds)} dispatch rounds"
                    ),
                    fix=(
                        "Dispatch this level as compiled rounds "
                        f"({', '.join(item.round_id for item in level_rounds)}), never as "
                        "one wave; greedy selection can otherwise release the serial node "
                        "first and cap the wave at one session."
                    ),
                )
            )
        if len(parallel) > max_sessions:
            findings.append(
                Finding(
                    check="capacity-split",
                    severity="info",
                    nodes=tuple(parallel),
                    subject=str(level),
                    message=(
                        f"level {level} has {len(parallel)} parallel-safe nodes, above the "
                        f"{max_sessions}-session cap; it compiles into "
                        f"{len(level_rounds)} dispatch rounds"
                    ),
                    fix=(
                        "Release the compiled rounds in order "
                        f"({', '.join(item.round_id for item in level_rounds)}); one wave "
                        "of this width cannot be hosted."
                    ),
                )
            )
    return findings


def lint_plan(
    graph: PlanGraph,
    *,
    max_sessions: int = DEFAULT_MAX_SESSIONS,
    repo_root: Path | None = None,
    semantic_ordering: bool = True,
) -> tuple[Finding, ...]:
    findings = _check_graph_validity(graph)
    findings.extend(_check_scope_syntax(graph))
    findings.extend(_check_parallel_safe_declaration(graph))
    findings.extend(_check_contract_completeness(graph))
    findings.extend(_check_read_scopes(graph))
    try:
        level_of = graph.level_of()
    except DagStandardError as error:
        findings.append(
            Finding(
                check="graph-validity",
                severity="error",
                nodes=(),
                subject="levels",
                message=f"dependency levels are not computable: {error}",
                fix="Fix the graph errors above; level-dependent checks were skipped.",
            )
        )
        return _sort_findings(findings)
    ordering = _check_durability_ordering(graph, level_of)
    rounds = compile_rounds(
        graph,
        max_sessions=max_sessions,
        semantic_ordering=semantic_ordering,
        ordering_findings=ordering,
    )
    findings.extend(_check_scaffold_collisions(graph, level_of, repo_root=repo_root))
    findings.extend(_check_write_scope_overlap(graph, level_of))
    findings.extend(ordering)
    findings.extend(_check_serial_in_level(graph, rounds, max_sessions=max_sessions))
    return _sort_findings(findings)


def severity_counts(findings: Sequence[Finding]) -> dict[str, int]:
    counts = {severity: 0 for severity in SEVERITIES}
    for item in findings:
        counts[item.severity] = counts.get(item.severity, 0) + 1
    return counts


def lint_exit_code(findings: Sequence[Finding], *, strict: bool = False) -> int:
    counts = severity_counts(findings)
    if counts.get("error"):
        return 1
    if strict and counts.get("warning"):
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI adapters (wired into autopilot.py)
# ---------------------------------------------------------------------------


def resolve_plan_path(args: argparse.Namespace) -> Path:
    explicit = getattr(args, "plan", None)
    if explicit:
        return Path(explicit)
    return Path(getattr(args, "repo_root", ".")) / ".autopilot" / "plan.json"


def effective_repo_root(args: argparse.Namespace, plan_path: Path) -> Path | None:
    """The repository this invocation is really about.

    ``--repo-root`` defaults to ``.``, which is indistinguishable from an
    operator explicitly naming the current directory. Trusting it blindly makes
    every emitted dispatch command target whatever directory the caller happened
    to be standing in. A declared root only wins when the plan being compiled
    actually lives inside it; otherwise the plan's own location decides.
    """

    declared = Path(getattr(args, "repo_root", "."))
    absolute_plan = Path(os.path.abspath(plan_path))
    if declared.is_dir():
        try:
            absolute_plan.relative_to(Path(os.path.abspath(declared)))
        except ValueError:
            pass
        else:
            return declared
    derived = derived_repo_root(absolute_plan)
    return derived if derived is not None and derived.is_dir() else None


def add_dag_standard_arguments(commands: Any) -> None:
    """Register ``dag-rounds`` and ``dag-lint`` on an existing subparser set."""

    rounds = commands.add_parser("dag-rounds")
    rounds.add_argument("--json", action="store_true", dest="json_output")
    rounds.add_argument("--max-sessions", type=int, default=DEFAULT_MAX_SESSIONS)
    rounds.add_argument("--actor")
    rounds.add_argument("--plan")
    rounds.add_argument(
        "--no-semantic-ordering",
        action="store_false",
        dest="semantic_ordering",
        default=True,
    )

    frontier = commands.add_parser("dag-frontier")
    frontier.add_argument("--json", action="store_true", dest="json_output")
    frontier.add_argument("--max-sessions", type=int, default=DEFAULT_MAX_SESSIONS)
    frontier.add_argument("--actor")
    frontier.add_argument("--plan")
    frontier.add_argument("--complete", action="append", default=[])
    frontier.add_argument("--active", action="append", default=[])
    frontier.add_argument("--expect-release", action="append", default=[])
    frontier.add_argument(
        "--no-semantic-ordering",
        action="store_false",
        dest="semantic_ordering",
        default=True,
    )

    lint = commands.add_parser("dag-lint")
    lint.add_argument("--json", action="store_true", dest="json_output")
    lint.add_argument("--strict", action="store_true")
    lint.add_argument("--max-sessions", type=int, default=DEFAULT_MAX_SESSIONS)
    lint.add_argument("--plan")
    lint.add_argument(
        "--no-semantic-ordering",
        action="store_false",
        dest="semantic_ordering",
        default=True,
    )


def _print_rounds(rounds: Sequence[Round], max_sessions: int) -> None:
    print(f"DISPATCH ROUNDS: {len(rounds)} (max sessions per round: {max_sessions})")
    for item in rounds:
        print(
            f"{item.round_id} level {item.level} sessions {item.sessions} "
            f"[{'parallel' if item.parallel_safe else 'serial'}] {item.reason}"
        )
        print("  nodes: " + " ".join(item.nodes))
        print("  " + item.command)


def _print_findings(findings: Sequence[Finding]) -> None:
    counts = severity_counts(findings)
    for item in findings:
        nodes = ", ".join(item.nodes) if item.nodes else "-"
        print(f"{item.severity.upper()} {item.check} [{nodes}]: {item.message}")
        print(f"  fix: {item.fix}")
    print(
        "SUMMARY: "
        + ", ".join(f"{counts[severity]} {severity}" for severity in SEVERITIES)
    )


def run_dag_standard_command(args: argparse.Namespace) -> int:
    """Execute pure DAG analysis/frontier commands without a live control plane."""

    plan_path = resolve_plan_path(args)
    graph = load_plan_graph(plan_path)
    repo_root = effective_repo_root(args, plan_path)
    semantic_ordering = bool(getattr(args, "semantic_ordering", True))
    if args.command == "dag-rounds":
        rounds = compile_rounds(
            graph,
            max_sessions=args.max_sessions,
            actor=getattr(args, "actor", None),
            semantic_ordering=semantic_ordering,
            command_prefix=dispatch_command_prefix(
                plan_path=plan_path, repo_root=repo_root
            ),
            repo_root=repo_root,
        )
        if args.json_output:
            print(
                json.dumps(
                    {
                        "max_sessions": args.max_sessions,
                        "semantic_ordering": semantic_ordering,
                        "rounds": [item.to_dict() for item in rounds],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            _print_rounds(rounds, args.max_sessions)
        return 0
    if args.command == "dag-frontier":
        frontier = select_frontier(
            graph,
            completed_nodes=getattr(args, "complete", ()),
            active_nodes=getattr(args, "active", ()),
            max_sessions=args.max_sessions,
            actor=getattr(args, "actor", None),
            semantic_ordering=semantic_ordering,
            command_prefix=dispatch_command_prefix(
                plan_path=plan_path, repo_root=repo_root
            ),
            repo_root=repo_root,
        )
        document = frontier.to_dict()
        expected = tuple(getattr(args, "expect_release", ()))
        if expected and tuple(frontier.release_nodes) != expected:
            raise DagStandardError(
                "compiled frontier release differs from the asserted external round"
            )
        if args.json_output:
            print(json.dumps(document, indent=2, sort_keys=True))
        else:
            print(
                f"{document['state']}: {document['round_id'] or '-'} "
                f"release {' '.join(document['release_nodes']) or '-'}"
            )
            print(str(document["reason"]))
        return 0
    if args.command == "dag-lint":
        findings = lint_plan(
            graph,
            max_sessions=args.max_sessions,
            repo_root=repo_root,
            semantic_ordering=semantic_ordering,
        )
        exit_code = lint_exit_code(findings, strict=args.strict)
        if args.json_output:
            print(
                json.dumps(
                    {
                        "findings": [item.to_dict() for item in findings],
                        "counts": severity_counts(findings),
                        "strict": bool(args.strict),
                        "exit_code": exit_code,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            _print_findings(findings)
        return exit_code
    raise DagStandardError(f"unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    root = argparse.ArgumentParser(prog="dag-standard")
    root.add_argument("--repo-root", default=".")
    commands = root.add_subparsers(dest="command", required=True)
    add_dag_standard_arguments(commands)
    return run_dag_standard_command(root.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
