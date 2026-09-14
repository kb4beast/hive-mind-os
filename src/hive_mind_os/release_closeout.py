"""N33 evidence-to-release closeout builder."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .whole_os_qualification import (
    NODE_IDS,
    REQUIREMENT_IDS,
    CloseoutManifest,
    Disposition,
    EvidenceKind,
    EvidenceRef,
    ExternalObligation,
    canonical_digest,
)


class CloseoutBuilder:
    def __init__(
        self, *, release_id: str, candidate_digest: str, previous_release_digest: str
    ) -> None:
        if not release_id.strip() or "\x00" in release_id:
            raise ValueError("release identity is required")
        self.release_id = release_id
        self.candidate_digest = candidate_digest
        self.previous_release_digest = previous_release_digest
        self.requirements: dict[str, tuple[EvidenceRef, ...]] = {}
        self.nodes: dict[str, Disposition] = {}
        self.obligations: dict[str, ExternalObligation] = {}

    def record_requirement(
        self, requirement_id: str, evidence: Iterable[EvidenceRef]
    ) -> None:
        if requirement_id not in REQUIREMENT_IDS:
            raise ValueError("unknown whole-OS requirement")
        values = tuple(evidence)
        if (
            requirement_id in self.requirements
            and self.requirements[requirement_id] != values
        ):
            raise ValueError("requirement evidence is append-only")
        self.requirements[requirement_id] = values

    def disposition_node(self, node_id: str, disposition: Disposition) -> None:
        if node_id not in NODE_IDS:
            raise ValueError("unknown campaign node")
        previous = self.nodes.get(node_id)
        if previous is not None and previous != disposition:
            raise ValueError("node disposition requires a successor closeout")
        self.nodes[node_id] = disposition

    def add_obligation(self, obligation: ExternalObligation) -> None:
        previous = self.obligations.get(obligation.obligation_id)
        if previous is not None and previous != obligation:
            raise ValueError("obligation identity already has different content")
        self.obligations[obligation.obligation_id] = obligation

    def missing(self) -> dict[str, tuple[str, ...]]:
        return {
            "requirements": tuple(
                item for item in REQUIREMENT_IDS if item not in self.requirements
            ),
            "nodes": tuple(item for item in NODE_IDS if item not in self.nodes),
        }

    def seal(
        self,
        *,
        startup_command: tuple[str, ...],
        rollback_command: tuple[str, ...],
        independent_judge_id: str,
        sealed_at: int,
    ) -> CloseoutManifest:
        if (
            not startup_command
            or not rollback_command
            or any(
                type(part) is not str or not part or "\x00" in part
                for part in (*startup_command, *rollback_command)
            )
        ):
            raise ValueError("startup and rollback commands must be direct arguments")
        if (
            not independent_judge_id.strip()
            or type(sealed_at) is not int
            or sealed_at < 0
        ):
            raise ValueError("independent judge and seal timestamp are required")
        missing = self.missing()
        if any(missing.values()):
            raise ValueError(f"closeout is incomplete: {missing}")
        manifest = CloseoutManifest(
            self.release_id,
            self.candidate_digest,
            self.previous_release_digest,
            dict(self.requirements),
            dict(self.nodes),
            tuple(self.obligations.values()),
            startup_command,
            rollback_command,
            independent_judge_id,
            sealed_at,
        )
        return manifest


def write_release_manifest(path: str | Path, manifest: CloseoutManifest) -> str:
    document = asdict(manifest)
    document["manifest_digest"] = canonical_digest(document)
    encoded = (
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(target)
    return document["manifest_digest"]


def load_release_manifest(path: str | Path) -> tuple[CloseoutManifest, str]:
    """Load a manifest only when its embedded digest matches its content."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        supplied = document.pop("manifest_digest")
        expected = canonical_digest(document)
        if supplied != expected:
            raise ValueError("release manifest digest mismatch")
        evidence = {}
        for key, values in document["requirement_evidence"].items():
            evidence[key] = tuple(
                EvidenceRef(
                    item["uri"],
                    item["digest"],
                    EvidenceKind(item["kind"]),
                    item["subject_id"],
                    item["observed_at"],
                )
                for item in values
            )
        obligations = tuple(
            ExternalObligation(
                item["obligation_id"],
                Disposition(item["kind"]),
                item["description"],
                tuple(item["blocks_claims"]),
            )
            for item in document["obligations"]
        )
        manifest = CloseoutManifest(
            document["release_id"],
            document["candidate_digest"],
            document["previous_release_digest"],
            evidence,
            {
                key: Disposition(value)
                for key, value in document["node_dispositions"].items()
            },
            obligations,
            tuple(document["startup_command"]),
            tuple(document["rollback_command"]),
            document["independent_judge_id"],
            document["sealed_at"],
        )
        return manifest, supplied
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        if (
            isinstance(exc, ValueError)
            and str(exc) == "release manifest digest mismatch"
        ):
            raise
        raise ValueError("release manifest is corrupt") from exc
