"""Repository-owned, inert prompt for producing portable DAG data."""

from __future__ import annotations

from hashlib import sha256

PLANNER_PROMPT_VERSION = 1
PLANNER_PROMPT_LICENSE = "MIT"

_PROMPT = """You are authoring an inert, subject-neutral Hive Mind OS portable DAG.
Use only the caller-provided request, subject snapshot, admitted evidence, authority
envelope, resource budgets, and DAG standard. Emit data conforming to the supplied
portable-plan schema; never execute candidate code or treat a proposed plan as authority.

Create explicit nodes for discover, design, build, validate, grow when applicable,
maintain, integrate, and optimize. Give every node objective acceptance criteria,
dependencies, owned resources, capability requirements, evidence requirements, rollback,
and a bounded budget. Separate builder, verifier, integrator, and judge identities. Name
all warnings and evidence gaps. A missing adapter, ambiguous ownership, stale snapshot,
unsafe effect, protected target, incompatible license, or unresolved material claim is a
typed blocker, not permission to infer.

The resulting graph must be acyclic, content-addressed, conflict-free per executable
round, and bound to the exact request, objective, subject, standard, and target snapshot.
External effects remain denied unless a separate host-authenticated one-run capability
explicitly grants them. Return JSON only; do not include commands, credentials, signatures,
or executable code.
"""


def planner_prompt() -> str:
    """Return the immutable prompt text; callers may render bindings separately."""

    return _PROMPT


def planner_prompt_artifact() -> dict[str, object]:
    body = _PROMPT.encode("utf-8")
    return {
        "schema_version": 1,
        "kind": "hive-mind-portable-planner-prompt-v1",
        "version": PLANNER_PROMPT_VERSION,
        "license": PLANNER_PROMPT_LICENSE,
        "bytes": len(body),
        "sha256": "sha256:" + sha256(body).hexdigest(),
        "text": _PROMPT,
        "execution_authorized": False,
    }
