"""Fail-closed dispatcher release barrier and RECON-010 authority amendment.

The static Autopilot DAG computes eligibility. Eligibility is not execution authority.
A worker becomes claimable only when a current dispatcher release record explicitly
assigns START NOW to that exact node. Release records are bound to the exact target,
latest reconciliation event, GitHub snapshot, plan fingerprint, and conflict state.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from controller import format_time, scopes_overlap
from durable_controller import (
    AutopilotError,
    ClaimError,
    ConfigurationError,
    ControlPlane as DurableControlPlane,
    atomic_write_json,
    append_jsonl,
    digest_json,
    normalize_path,
    path_matches_scope,
    read_json,
)

AUTHORITY_AMENDMENTS = ".autopilot/authority-amendments.json"
CURRENT_RELEASE = "dispatcher-release.json"
RELEASE_HISTORY = "dispatcher-releases.jsonl"
RELEASE_KIND = "hive-mind-autopilot-dispatch-release-v1"
VERDICTS = {"START NOW", "WAIT", "STOP"}
READY_STATES = {"READY", "INTEGRATION_READY", "PROMOTION_READY"}
STOP_STATES = {
    "COMPLETE",
    "SUPERSEDED",
    "CANCELLED",
    "QUARANTINED",
    "PR_OPEN",
    "CI_FAILED",
    "REPAIR_REQUIRED",
    "ESCALATION_REQUIRED",
    "RUNNING",
    "CLAIMED",
    "WAITING_FOR_RECEIPT",
    "BOOTSTRAP_INVALID",
}


def _string_list(value: object) -> list[str] | None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        return None
    return list(value)


def _merge_unique(first: Sequence[str], second: Sequence[str]) -> list[str]:
    return list(dict.fromkeys((*first, *second)))


class ControlPlane(DurableControlPlane):
    """Durable controller plus exact-path authority amendment and release barrier."""

    @property
    def authority_amendments_path(self):
        return self.repo_root / AUTHORITY_AMENDMENTS

    @property
    def current_release_path(self):
        return self.state_dir / CURRENT_RELEASE

    def _authority_document(self) -> Mapping[str, Any] | None:
        if not self.authority_amendments_path.is_file():
            return None
        value = read_json(self.authority_amendments_path)
        return value if isinstance(value, Mapping) else None

    def _authority_record_issues(self, record: object) -> tuple[str, ...]:
        issues: list[str] = []
        if not isinstance(record, Mapping):
            return ("authority amendment must be an object",)
        node_id = record.get("node_id")
        if node_id != "RECON-010":
            issues.append("authority amendment may only target RECON-010")
        if record.get("amendment_id") != "recon-010-pr120-dispatcher-release-barrier-v1":
            issues.append("authority amendment id is not the sealed PR #120 amendment")
        if record.get("decision") != "ADAPT":
            issues.append("authority amendment decision must be ADAPT")
        if record.get("source_pr") != 120:
            issues.append("authority amendment source_pr must be merged PR #120")
        sealed_bootstrap = self.control.get("bootstrap_completion")
        if not isinstance(sealed_bootstrap, Mapping):
            issues.append("control-plane bootstrap completion is unavailable")
            sealed_bootstrap = {}
        if record.get("source_integrated_commit") != sealed_bootstrap.get(
            "integrated_commit"
        ):
            issues.append(
                "authority amendment source commit is not the sealed PR #120 integration"
            )
        if record.get("plan_fingerprint") != self.expected_plan_fingerprint:
            issues.append("authority amendment plan fingerprint is stale")
        evidence_ref = record.get("authority_evidence")
        raw_node = super().node("RECON-010")
        if not isinstance(evidence_ref, str) or not any(
            path_matches_scope(evidence_ref, scope)
            for scope in raw_node.get("write_scope", [])
        ):
            issues.append(
                "authority amendment evidence is not retained in original RECON scope"
            )

        additional_write = _string_list(record.get("additional_write_scope"))
        additional_locks = _string_list(record.get("additional_file_locks"))
        required_tests = _string_list(record.get("additional_required_tests"))
        acceptance = _string_list(record.get("additional_acceptance_criteria"))
        constraints = _string_list(record.get("constraints"))
        if not additional_write:
            issues.append("authority amendment requires exact additional_write_scope")
            additional_write = []
        if not additional_locks:
            issues.append("authority amendment requires exact additional_file_locks")
            additional_locks = []
        if set(additional_write) != set(additional_locks):
            issues.append(
                "authority amendment file locks must exactly match added write scope"
            )
        if required_tests != ["dispatcher-release-barrier-tests"]:
            issues.append(
                "authority amendment must require dispatcher-release-barrier-tests"
            )
        if not acceptance:
            issues.append("authority amendment requires explicit acceptance criteria")
        if not constraints:
            issues.append("authority amendment requires explicit constraints")
        for scope in additional_write:
            try:
                normalize_path(scope)
            except ValueError as error:
                issues.append(
                    f"authority amendment has unsafe scope {scope!r}: {error}"
                )
                continue
            if any(
                scopes_overlap(scope, forbidden)
                for forbidden in raw_node.get("forbidden_scope", [])
            ):
                issues.append(
                    f"authority amendment overlaps forbidden RECON scope: {scope}"
                )
        if any(
            scope.startswith("src/") or scope.startswith("tests/")
            for scope in additional_write
        ):
            issues.append("authority amendment may not enter product runtime/test paths")
        return tuple(dict.fromkeys(issues))

    def authority_issues(self) -> tuple[str, ...]:
        document = self._authority_document()
        if document is None:
            return (
                f"required authority amendment file is missing: {AUTHORITY_AMENDMENTS}",
            )
        if document.get("schema_version") != 1:
            return ("authority amendments schema_version is unsupported",)
        amendments = document.get("amendments")
        if not isinstance(amendments, list) or len(amendments) != 1:
            return (
                "authority amendments must contain exactly the sealed RECON-010 amendment",
            )
        return self._authority_record_issues(amendments[0])

    def _amendment_for_node(self, node_id: str) -> Mapping[str, Any] | None:
        document = self._authority_document()
        if document is None or document.get("schema_version") != 1:
            return None
        amendments = document.get("amendments")
        if not isinstance(amendments, list):
            return None
        matches = [
            item
            for item in amendments
            if isinstance(item, Mapping) and item.get("node_id") == node_id
        ]
        if len(matches) != 1 or self._authority_record_issues(matches[0]):
            return None
        return matches[0]

    def node(self, node_id: str) -> Mapping[str, Any]:
        raw = super().node(node_id)
        amendment = self._amendment_for_node(node_id)
        if amendment is None:
            return raw
        updated = dict(raw)
        updated["write_scope"] = _merge_unique(
            list(raw.get("write_scope", [])),
            list(amendment.get("additional_write_scope", [])),
        )
        updated["file_locks"] = _merge_unique(
            list(raw.get("file_locks", [])),
            list(amendment.get("additional_file_locks", [])),
        )
        updated["required_tests"] = _merge_unique(
            list(raw.get("required_tests", [])),
            list(amendment.get("additional_required_tests", [])),
        )
        updated["acceptance_criteria"] = _merge_unique(
            list(raw.get("acceptance_criteria", [])),
            list(amendment.get("additional_acceptance_criteria", [])),
        )
        return updated

    def validate_configuration(self) -> tuple[str, ...]:
        issues = list(super().validate_configuration())
        issues.extend(self.authority_issues())
        return tuple(dict.fromkeys(issues))

    def _reconciliation_digest(self) -> str | None:
        path = self.state_dir / "target.json"
        if not path.is_file():
            return None
        value = read_json(path)
        if not isinstance(value, Mapping):
            return None
        if value.get("target_sha") != self.current_target_sha():
            return None
        if value.get("plan_fingerprint") != self.expected_plan_fingerprint:
            return None
        return digest_json(value)

    def _snapshot_digest(self) -> str | None:
        snapshot = self.github_snapshot()
        if not snapshot:
            return None
        if snapshot.get("target_sha") != self.current_target_sha():
            return None
        return digest_json(snapshot)

    def _base_status(self) -> dict[str, object]:
        return super().status()

    def _nodes_conflict(self, first_id: str, second_id: str) -> bool:
        first = self.node(first_id)
        second = self.node(second_id)
        if any(
            scopes_overlap(first_scope, second_scope)
            for first_scope in first.get("file_locks", [])
            for second_scope in second.get("file_locks", [])
        ):
            return True
        return bool(
            set(first.get("semantic_locks", []))
            & set(second.get("semantic_locks", []))
        )

    def _candidate_verdicts(
        self,
        base_status: Mapping[str, object],
        released_wave: Sequence[str],
    ) -> dict[str, str]:
        released = set(released_wave)
        verdicts: dict[str, str] = {}
        nodes = base_status.get("nodes", [])
        if not isinstance(nodes, list):
            raise AutopilotError("status node inventory is unavailable")
        for item in nodes:
            if not isinstance(item, Mapping) or not isinstance(
                item.get("node_id"), str
            ):
                continue
            node_id = str(item["node_id"])
            state = str(item.get("state"))
            if node_id in released:
                verdict = "START NOW"
            elif state in STOP_STATES:
                verdict = "STOP"
            else:
                verdict = "WAIT"
            verdicts[node_id] = verdict
        if set(verdicts) != set(self._nodes):
            raise AutopilotError(
                "dispatcher could not assign exactly one verdict to every candidate"
            )
        return verdicts

    @staticmethod
    def _action_sentence(wave: Sequence[str]) -> tuple[str, str]:
        if len(wave) > 1:
            return (
                "START TOGETHER NOW",
                f"Open these {len(wave)} sessions now: " + ", ".join(wave),
            )
        if len(wave) == 1:
            return "START NOW", f"Open this 1 session now: {wave[0]}"
        return "WAIT", "Do not open any worker sessions yet"

    def dispatch(
        self,
        *,
        actor: str,
        requested_nodes: Sequence[str] = (),
    ) -> Mapping[str, Any]:
        if not actor.strip():
            raise AutopilotError("dispatcher actor is required")
        if self.target_requires_reconciliation():
            raise AutopilotError(
                "dispatcher release is forbidden until live target reconciliation completes"
            )
        reconciliation_digest = self._reconciliation_digest()
        if reconciliation_digest is None:
            raise AutopilotError(
                "dispatcher release requires a current reconciliation event"
            )
        snapshot_digest = self._snapshot_digest()
        if snapshot_digest is None:
            raise AutopilotError(
                "dispatcher release requires a current GitHub snapshot"
            )

        base_status = self._base_status()
        eligible_raw = base_status.get("ready", [])
        eligible = (
            [str(item) for item in eligible_raw]
            if isinstance(eligible_raw, list)
            else []
        )
        if requested_nodes:
            wave = list(dict.fromkeys(str(item) for item in requested_nodes))
            unavailable = [node_id for node_id in wave if node_id not in eligible]
            if unavailable:
                raise AutopilotError(
                    "dispatcher cannot release non-eligible nodes: "
                    + ", ".join(unavailable)
                )
            for index, first in enumerate(wave):
                for second in wave[index + 1 :]:
                    if self._nodes_conflict(first, second):
                        raise AutopilotError(
                            f"requested parallel release conflicts: {first} vs {second}"
                        )
        else:
            wave = []
            for node_id in sorted(eligible):
                if all(
                    not self._nodes_conflict(node_id, chosen) for chosen in wave
                ):
                    wave.append(node_id)

        verdicts = self._candidate_verdicts(base_status, wave)
        directive, action = self._action_sentence(wave)
        record: dict[str, Any] = {
            "schema_version": 1,
            "kind": RELEASE_KIND,
            "actor": actor,
            "target_sha": self.current_target_sha(),
            "plan_fingerprint": self.expected_plan_fingerprint,
            "reconciliation_digest": reconciliation_digest,
            "github_snapshot_digest": snapshot_digest,
            "released_wave": wave,
            "directive": directive,
            "action": action,
            "verdicts": verdicts,
            "issued_at": format_time(self.clock()),
        }
        record["release_id"] = digest_json(record)
        atomic_write_json(self.current_release_path, record)
        append_jsonl(self.state_dir / RELEASE_HISTORY, record)
        return record

    def _release_issues(self, record: object) -> tuple[str, ...]:
        issues: list[str] = []
        if not isinstance(record, Mapping):
            return ("dispatcher release record is missing or invalid",)
        if record.get("schema_version") != 1 or record.get("kind") != RELEASE_KIND:
            issues.append("dispatcher release schema/kind is invalid")
        release_id = record.get("release_id")
        material = dict(record)
        material.pop("release_id", None)
        if release_id != digest_json(material):
            issues.append("dispatcher release digest is invalid")
        if record.get("plan_fingerprint") != self.expected_plan_fingerprint:
            issues.append("dispatcher release plan fingerprint is stale")
        if record.get("target_sha") != self.current_target_sha():
            issues.append("dispatcher release target is stale")
        if record.get("reconciliation_digest") != self._reconciliation_digest():
            issues.append("dispatcher release was invalidated by reconciliation")
        if record.get("github_snapshot_digest") != self._snapshot_digest():
            issues.append(
                "dispatcher release was invalidated by GitHub snapshot change"
            )
        wave = _string_list(record.get("released_wave"))
        verdicts = record.get("verdicts")
        if wave is None:
            issues.append("dispatcher release wave is invalid")
            wave = []
        if not isinstance(verdicts, Mapping) or set(verdicts) != set(self._nodes):
            issues.append("dispatcher release does not cover every candidate node")
            verdicts = {}
        elif any(value not in VERDICTS for value in verdicts.values()):
            issues.append("dispatcher release contains an invalid candidate verdict")
        for node_id in wave:
            if verdicts.get(node_id) != "START NOW":
                issues.append(f"released node lacks START NOW verdict: {node_id}")
        directive, action = self._action_sentence(wave)
        if record.get("directive") != directive or record.get("action") != action:
            issues.append(
                "dispatcher release directive/action is inconsistent with released wave"
            )

        claims = self.active_claims()
        for node_id in wave:
            conflicts = self._claim_conflicts(node_id, claims)
            if conflicts:
                issues.append(
                    f"dispatcher release invalidated by conflicting claim for {node_id}: "
                    + "; ".join(conflicts)
                )
        return tuple(dict.fromkeys(issues))

    def current_release(self) -> Mapping[str, Any] | None:
        if not self.current_release_path.is_file():
            return None
        value = read_json(self.current_release_path)
        return value if isinstance(value, Mapping) else None

    def status(self) -> dict[str, object]:
        base = self._base_status()
        original_eligible = (
            list(base.get("ready", []))
            if isinstance(base.get("ready"), list)
            else []
        )
        record = self.current_release()
        issues = (
            self._release_issues(record)
            if record is not None
            else ("no current dispatcher release",)
        )
        if record is not None and not issues:
            verdicts = dict(record.get("verdicts", {}))
            wave = list(record.get("released_wave", []))
            directive = str(record.get("directive"))
            action = str(record.get("action"))
            release_id = str(record.get("release_id"))
        else:
            verdicts = self._candidate_verdicts(base, ())
            wave = []
            directive, action = self._action_sentence(())
            release_id = None
        state_by_node = {
            str(item.get("node_id")): str(item.get("state"))
            for item in base.get("nodes", [])
            if isinstance(item, Mapping) and isinstance(item.get("node_id"), str)
        }
        released_ready = [
            node_id
            for node_id in wave
            if verdicts.get(node_id) == "START NOW"
            and state_by_node.get(node_id) in READY_STATES
        ]
        base["eligible"] = original_eligible
        base["ready"] = released_ready
        base["dispatch_release"] = {
            "valid": not issues,
            "issues": list(issues),
            "release_id": release_id,
            "directive": directive,
            "action": action,
            "released_wave": wave,
            "verdicts": verdicts,
        }
        return base

    def ready_nodes(self) -> tuple[str, ...]:
        status = self.status()
        ready = status.get("ready", [])
        return (
            tuple(str(item) for item in ready)
            if isinstance(ready, list)
            else ()
        )

    def assert_start_now(self, node_id: str) -> Mapping[str, Any]:
        record = self.current_release()
        issues = self._release_issues(record)
        if issues:
            raise ClaimError(
                "worker release is stale or unavailable: " + "; ".join(issues)
            )
        assert record is not None
        verdicts = record.get("verdicts")
        if not isinstance(verdicts, Mapping) or verdicts.get(node_id) != "START NOW":
            raise ClaimError(
                f"node {node_id} is WAIT; explicit START NOW was not released"
            )
        view = self.node_view(node_id)
        if view.state not in READY_STATES:
            raise ClaimError(
                f"node {node_id} cannot start from current state {view.state}"
            )
        return record

    def claim(
        self,
        node_id: str,
        owner: str,
        *,
        lease_minutes: int = 90,
        publish_remote: bool = False,
        remote: str = "origin",
    ) -> Mapping[str, Any]:
        self.assert_start_now(node_id)
        return super().claim(
            node_id,
            owner,
            lease_minutes=lease_minutes,
            publish_remote=publish_remote,
            remote=remote,
        )

    def render_worker_prompt(self, node_id: str) -> str:
        rendered = super().render_worker_prompt(node_id)
        release = self.status().get("dispatch_release", {})
        verdicts = release.get("verdicts", {}) if isinstance(release, Mapping) else {}
        verdict = (
            verdicts.get(node_id, "WAIT")
            if isinstance(verdicts, Mapping)
            else "WAIT"
        )
        directive = (
            release.get("directive", "WAIT")
            if isinstance(release, Mapping)
            else "WAIT"
        )
        return (
            f"DISPATCH VERDICT FOR {node_id}: {verdict}\n"
            f"DISPATCH DIRECTIVE: {directive}\n"
            "Static DAG/level eligibility is not execution authority. If the verdict is not "
            "START NOW, do not claim or implement this node.\n\n"
            + rendered
        )
