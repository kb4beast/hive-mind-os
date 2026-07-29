from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .authority import AuthorityDecision
from .canonical import (
    canonical_bytes,
    digest,
    normalize_fingerprint_text,
    reject_private_content,
)
from .contracts import validate_foundation
from .store import FoundationStore, IdempotencyConflict, ScopeError

NORMALIZATION_VERSION = "phase2-text-v1"
RELATIONSHIPS = frozenset(
    {
        "appeal",
        "complement",
        "contradiction",
        "duplicate",
        "not-duplicate",
        "refinement",
        "reinforcement",
        "semantic-candidate",
        "variant",
    }
)


@dataclass(frozen=True, slots=True)
class OpportunityResult:
    encounter_record_id: str
    opportunity_record_id: str | None
    classification: str
    candidate_record_ids: tuple[str, ...] = ()


class OpportunityLedger:
    """Transactional encounter-first opportunity classification."""

    def __init__(
        self,
        store: FoundationStore,
        *,
        authority: AuthorityDecision,
    ) -> None:
        store._require_authority(authority, "foundation.opportunity.write")
        self.store = store
        self.authority = authority

    def register(
        self,
        *,
        tenant_id: str,
        repository_id: str,
        encounter_id: str,
        problem: str,
        proposal: str,
        structured_key: Mapping[str, Any],
        actor_id: str,
        evidence_digests: Sequence[str],
        semantic_candidate_ids: Sequence[str] = (),
        semantic_evidence: Mapping[str, Any] | None = None,
        disposition: str | None = None,
    ) -> OpportunityResult:
        if not encounter_id.strip():
            raise ValueError("encounter_id is required")
        if not evidence_digests:
            raise ValueError("every encounter requires evidence")
        normalized_problem = normalize_fingerprint_text(problem)
        normalized_proposal = normalize_fingerprint_text(proposal)
        exact_digest = digest(
            {
                "normalization_version": NORMALIZATION_VERSION,
                "problem": normalized_problem,
                "proposal": normalized_proposal,
            }
        )
        structured_digest = digest(
            {
                "normalization_version": NORMALIZATION_VERSION,
                "structured_key": structured_key,
            }
        )
        encounter_payload = {
            "record_type": "idea-encounter",
            "schema_version": 1,
            "encounter_id": encounter_id,
            "normalization_version": NORMALIZATION_VERSION,
            "problem_digest": digest(normalized_problem),
            "proposal_digest": digest(normalized_proposal),
            "structured_digest": structured_digest,
            "evidence_digests": sorted(set(evidence_digests)),
            "disposition": disposition,
        }
        encounter_validation = validate_foundation(
            "idea-encounter-v1", encounter_payload
        )
        if not encounter_validation.valid:
            raise ValueError(
                "invalid idea encounter: " + "; ".join(encounter_validation.issues)
            )
        with self.store._lock, self.store._transaction():
            self.store._require_authority(
                self.authority, "foundation.opportunity.write"
            )
            encounter = self.store._append_record_in_transaction(
                tenant_id=tenant_id,
                repository_id=repository_id,
                record_type="idea-encounter",
                schema_name="idea-encounter-v1",
                stream_id=f"encounter:{encounter_id}",
                payload=encounter_payload,
                actor_id=actor_id,
                idempotency_key=f"encounter:{encounter_id}",
                observed_at=self.store._clock(),
                correlation_id=encounter_id,
                causation_id=None,
                sensitivity="private",
                retention="governed",
                status="recorded",
                destination="local",
                command_digest=self.store._command_digest(
                    tenant_id=tenant_id,
                    repository_id=repository_id,
                    record_type="idea-encounter",
                    schema_name="idea-encounter-v1",
                    stream_id=f"encounter:{encounter_id}",
                    payload=encounter_payload,
                    actor_id=actor_id,
                    idempotency_key=f"encounter:{encounter_id}",
                    correlation_id=encounter_id,
                    causation_id=None,
                    sensitivity="private",
                    retention="governed",
                    status="recorded",
                    destination="local",
                ),
            )
            matches = self.store._connection.execute(
                """
                SELECT opportunity_record_id,exact_digest,structured_digest
                FROM opportunity_keys
                WHERE tenant_id=? AND repository_id=? AND normalization_version=?
                AND (exact_digest=? OR structured_digest=?)
                ORDER BY CASE WHEN exact_digest=? THEN 0 ELSE 1 END
                """,
                (
                    tenant_id,
                    repository_id,
                    NORMALIZATION_VERSION,
                    exact_digest,
                    structured_digest,
                    exact_digest,
                ),
            ).fetchall()
            matched_ids = {str(row["opportunity_record_id"]) for row in matches}
            if len(matched_ids) > 1:
                raise IdempotencyConflict(
                    "exact and structured opportunity keys disagree"
                )
            if matches:
                opportunity_id = str(matches[0]["opportunity_record_id"])
                self._insert_relation(
                    tenant_id,
                    repository_id,
                    encounter["record_id"],
                    opportunity_id,
                    "duplicate",
                    encounter_payload,
                )
                return OpportunityResult(
                    encounter["record_id"], opportunity_id, "duplicate"
                )

            candidates = tuple(dict.fromkeys(semantic_candidate_ids))
            if candidates:
                if semantic_evidence is None:
                    raise ValueError(
                        "semantic candidates require algorithm/index/threshold evidence"
                    )
                required_evidence = {
                    "algorithm_id",
                    "algorithm_version",
                    "index_digest",
                    "threshold_ppm",
                    "neighbor_scores_ppm",
                }
                if set(semantic_evidence) != required_evidence:
                    raise ValueError(
                        "semantic evidence must bind algorithm, index, threshold, "
                        "and neighbor scores"
                    )
                reject_private_content(semantic_evidence)
                scoped_count = self.store._connection.execute(
                    "SELECT COUNT(*) FROM records WHERE tenant_id=? AND repository_id=? "
                    f"AND record_id IN ({','.join('?' for _ in candidates)})",
                    (tenant_id, repository_id, *candidates),
                ).fetchone()[0]
                if int(scoped_count) != len(candidates):
                    raise ScopeError("semantic candidates must exist in the same scope")
                for candidate_id in candidates:
                    self._insert_relation(
                        tenant_id,
                        repository_id,
                        encounter["record_id"],
                        candidate_id,
                        "semantic-candidate",
                        semantic_evidence,
                    )
                return OpportunityResult(
                    encounter["record_id"],
                    None,
                    "semantic-candidate",
                    candidates,
                )

            if disposition is not None:
                return OpportunityResult(
                    encounter["record_id"], None, f"disposed:{disposition}"
                )

            opportunity_payload = {
                "record_type": "opportunity-record",
                "schema_version": 1,
                "opportunity_id": f"opportunity:{exact_digest.removeprefix('sha256:')}",
                "normalization_version": NORMALIZATION_VERSION,
                "problem_digest": digest(normalized_problem),
                "proposal_digest": digest(normalized_proposal),
                "exact_digest": exact_digest,
                "structured_digest": structured_digest,
                "origin_encounter_id": encounter["record_id"],
                "status": "candidate",
            }
            opportunity_validation = validate_foundation(
                "opportunity-record-v1", opportunity_payload
            )
            if not opportunity_validation.valid:
                raise ValueError(
                    "invalid opportunity: " + "; ".join(opportunity_validation.issues)
                )
            opportunity = self.store._append_record_in_transaction(
                tenant_id=tenant_id,
                repository_id=repository_id,
                record_type="opportunity-record",
                schema_name="opportunity-record-v1",
                stream_id=f"opportunity:{exact_digest}",
                payload=opportunity_payload,
                actor_id=actor_id,
                idempotency_key=f"opportunity:{exact_digest}",
                observed_at=self.store._clock(),
                correlation_id=encounter_id,
                causation_id=encounter["record_id"],
                sensitivity="private",
                retention="governed",
                status="candidate",
                destination="local",
                command_digest=self.store._command_digest(
                    tenant_id=tenant_id,
                    repository_id=repository_id,
                    record_type="opportunity-record",
                    schema_name="opportunity-record-v1",
                    stream_id=f"opportunity:{exact_digest}",
                    payload=opportunity_payload,
                    actor_id=actor_id,
                    idempotency_key=f"opportunity:{exact_digest}",
                    correlation_id=encounter_id,
                    causation_id=encounter["record_id"],
                    sensitivity="private",
                    retention="governed",
                    status="candidate",
                    destination="local",
                ),
            )
            self.store._connection.execute(
                "INSERT INTO opportunity_keys VALUES(?,?,?,?,?,?,?)",
                (
                    tenant_id,
                    repository_id,
                    NORMALIZATION_VERSION,
                    exact_digest,
                    structured_digest,
                    opportunity["record_id"],
                    self.store._clock(),
                ),
            )
            self._insert_relation(
                tenant_id,
                repository_id,
                encounter["record_id"],
                opportunity["record_id"],
                "originates",
                encounter_payload,
            )
            return OpportunityResult(
                encounter["record_id"], opportunity["record_id"], "new"
            )

    def classify_semantic_candidate(
        self,
        *,
        tenant_id: str,
        repository_id: str,
        encounter_record_id: str,
        opportunity_record_id: str,
        relationship: str,
        evidence: Mapping[str, Any],
    ) -> int:
        if relationship not in RELATIONSHIPS - {"semantic-candidate"}:
            raise ValueError("unsupported semantic classification")
        return self.store.add_relation(
            authority=self.authority,
            foundation_action="foundation.opportunity.write",
            tenant_id=tenant_id,
            repository_id=repository_id,
            source_record_id=encounter_record_id,
            target_record_id=opportunity_record_id,
            relation=relationship,
            evidence=evidence,
        )

    def _insert_relation(
        self,
        tenant_id: str,
        repository_id: str,
        source_record_id: str,
        target_record_id: str,
        relation: str,
        evidence: Mapping[str, Any],
    ) -> None:
        reject_private_content(evidence)
        self.store._connection.execute(
            "INSERT INTO record_relations("
            "tenant_id,repository_id,source_record_id,target_record_id,"
            "relation,evidence_digest,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (
                tenant_id,
                repository_id,
                source_record_id,
                target_record_id,
                relation,
                digest(evidence),
                canonical_bytes(evidence).decode("utf-8").rstrip("\n"),
                self.store._clock(),
            ),
        )
