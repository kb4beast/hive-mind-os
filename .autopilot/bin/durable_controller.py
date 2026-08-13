"""Durable completion layer for the repository-resident Autopilot controller.

Live leases, GitHub snapshots, retries, and reconciliation state remain under ignored
``.autopilot/state``. Completion evidence is different: it must survive a fresh
checkout without granting a worker new file authority.

Normal nodes therefore retain completion as an empty Git commit whose tree is exactly
the validated final candidate tree and whose message contains the canonical receipt.
That commit is created on the claimed node branch and must later remain in the configured
singleton release branch through an ancestry-preserving merge. The historical BOOT-000 squash merge
predates this mechanism and is recovered through one sealed bootstrap attestation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from controller import (
    FULL_SHA,
    AutopilotError,
    ClaimError,
    ConfigurationError,
    ControlPlane as BaseControlPlane,
    GitCommitObservation,
    GitCommitObservationError,
    NodeView,
    ReceiptError,
    append_jsonl,
    atomic_write_json,
    canonical_bytes,
    digest_json,
    normalize_path,
    parse_time,
    path_matches_scope,
    read_json,
)

RECEIPT_COMMIT_MARKER = "HIVE-MIND-AUTOPILOT-COMPLETION-V1"
REMOTE_CLAIM_KIND = "hive-mind-autopilot-remote-claim-v1"
BOOTSTRAP_ATTESTATION = ".autopilot/bootstrap-completion.json"
BOOTSTRAP_ATTESTATION_SCHEMA = ".autopilot/bootstrap-completion.schema.json"


class ControlPlane(BaseControlPlane):
    """Base controller with durable, fail-closed completion reconstruction."""

    @property
    def bootstrap_attestation_path(self) -> Path:
        return self.repo_root / BOOTSTRAP_ATTESTATION

    @property
    def bootstrap_attestation_schema_path(self) -> Path:
        return self.repo_root / BOOTSTRAP_ATTESTATION_SCHEMA

    def _has_git_repository(self) -> bool:
        return (self.repo_root / ".git").exists()

    def current_target_sha(self) -> str:
        """Keep fixture mode deterministic while allowing fresh Git-backed tests."""

        if self.verify_git_objects:
            return super().current_target_sha()
        snapshot = self.github_snapshot()
        value = snapshot.get("target_sha")
        if isinstance(value, str) and FULL_SHA.fullmatch(value):
            return value
        if self._has_git_repository():
            for reference in (
                f"refs/remotes/origin/{self.target_branch}",
                f"refs/heads/{self.target_branch}",
            ):
                completed = self._git(("rev-parse", "--verify", reference))
                candidate = completed.stdout.strip()
                if completed.returncode == 0 and FULL_SHA.fullmatch(candidate):
                    return candidate
        return self.baseline_sha

    def _commit_tree(self, commit: str) -> str | None:
        if FULL_SHA.fullmatch(commit) is None:
            return None
        completed = self._git(("rev-parse", f"{commit}^{{tree}}"), check=False)
        value = completed.stdout.strip()
        return value if completed.returncode == 0 and FULL_SHA.fullmatch(value) else None

    def _commit_parents(self, commit: str) -> tuple[str, ...]:
        completed = self._git(("show", "-s", "--format=%P", commit), check=False)
        if completed.returncode != 0:
            return ()
        return tuple(item for item in completed.stdout.strip().split() if FULL_SHA.fullmatch(item))

    def _diff_paths(self, base: str, final: str) -> tuple[str, ...]:
        completed = self._git(("diff", "--name-only", f"{base}..{final}"), check=True)
        return tuple(
            sorted(
                {
                    normalize_path(line)
                    for line in completed.stdout.splitlines()
                    if line.strip()
                }
            )
        )

    def _bootstrap_control(self) -> Mapping[str, Any]:
        value = self.control.get("bootstrap_completion")
        if not isinstance(value, Mapping):
            raise ConfigurationError("control-plane.bootstrap_completion must be an object")
        return value

    def validate_configuration(self) -> tuple[str, ...]:
        issues = list(super().validate_configuration())
        if not self.bootstrap_attestation_path.is_file():
            issues.append(f"required file is missing: {BOOTSTRAP_ATTESTATION}")
        if not self.bootstrap_attestation_schema_path.is_file():
            issues.append(f"required file is missing: {BOOTSTRAP_ATTESTATION_SCHEMA}")
        if self.bootstrap_attestation_path.is_file():
            value = read_json(self.bootstrap_attestation_path)
            issues.extend(self.validate_bootstrap_attestation(value, require_integrated=True))
        return tuple(dict.fromkeys(issues))

    def _normalized_receipt_changed_paths(self, value: Mapping[str, Any]) -> tuple[str, ...]:
        changed = value.get("changed_paths")
        if not isinstance(changed, list):
            return ()
        normalized: list[str] = []
        for raw in changed:
            try:
                normalized.append(normalize_path(raw))
            except (TypeError, ValueError):
                continue
        return tuple(sorted(set(normalized)))

    def validate_receipt(
        self,
        node_id: str,
        value: object,
        *,
        require_integrated: bool = False,
        commit_observation: GitCommitObservation | None = None,
    ) -> tuple[str, ...]:
        """Preserve base checks and additionally bind trees and the exact Git diff."""

        issues: list[str] = []
        observation_is_usable = False
        if commit_observation is not None:
            if not isinstance(commit_observation, GitCommitObservation):
                issues.append("commit observation has an invalid type")
            elif not isinstance(value, Mapping):
                issues.append("commit observation cannot cover a non-object receipt")
            else:
                observed_commits = tuple(
                    dict.fromkeys(
                        commit
                        for commit in (value.get("base_commit"), value.get("final_commit"))
                        if isinstance(commit, str) and FULL_SHA.fullmatch(commit)
                    )
                )
                try:
                    commit_observation.assert_repository(self.repo_root)
                    if commit_observation.oids != observed_commits:
                        issues.append(
                            "commit observation does not exactly cover receipt commits"
                        )
                    elif len(observed_commits) != 2:
                        issues.append(
                            "commit observation cannot cover invalid receipt commits"
                        )
                    else:
                        observation_is_usable = True
                except GitCommitObservationError as error:
                    issues.append(f"commit observation is invalid: {error}")

        issues.extend(
            super().validate_receipt(
                node_id,
                value,
                require_integrated=require_integrated,
            )
        )
        if not isinstance(value, Mapping):
            return tuple(dict.fromkeys(issues))

        base = value.get("base_commit")
        final = value.get("final_commit")
        base_tree = value.get("base_tree")
        final_tree = value.get("final_tree")
        if not isinstance(base_tree, str) or FULL_SHA.fullmatch(base_tree) is None:
            issues.append("receipt base_tree is invalid")
        if not isinstance(final_tree, str) or FULL_SHA.fullmatch(final_tree) is None:
            issues.append("receipt final_tree is invalid")

        can_inspect_git = self._has_git_repository()
        if (
            can_inspect_git
            and isinstance(base, str)
            and isinstance(final, str)
            and FULL_SHA.fullmatch(base)
            and FULL_SHA.fullmatch(final)
            and self.git_object_exists(base)
            and self.git_object_exists(final)
        ):
            try:
                observed_base_tree = (
                    commit_observation.tree(base)
                    if observation_is_usable and commit_observation is not None
                    else self._commit_tree(base)
                )
                observed_final_tree = (
                    commit_observation.tree(final)
                    if observation_is_usable and commit_observation is not None
                    else self._commit_tree(final)
                )
            except GitCommitObservationError as error:
                issues.append(f"commit observation is invalid: {error}")
            else:
                if observed_base_tree != base_tree:
                    issues.append("receipt base_tree does not match base_commit")
                if observed_final_tree != final_tree:
                    issues.append("receipt final_tree does not match final_commit")
            if self.is_ancestor(base, final):
                if self._diff_paths(base, final) != self._normalized_receipt_changed_paths(value):
                    issues.append("receipt changed_paths do not match the exact base..final diff")
            if require_integrated and not self.is_ancestor(final, self.current_target_sha()):
                issues.append("receipt final commit is not integrated into target history")

        return tuple(dict.fromkeys(issues))

    def validate_bootstrap_attestation(
        self,
        value: object,
        *,
        require_integrated: bool = True,
    ) -> tuple[str, ...]:
        """Validate truthful recovery evidence for the squash-merged PR #120 bootstrap."""

        issues: list[str] = []
        if not isinstance(value, Mapping):
            return ("bootstrap completion attestation must be an object",)

        required = (
            "schema_version",
            "plan_fingerprint",
            "node_id",
            "contract_version",
            "planned_branch",
            "actual_branch",
            "source_pr",
            "merge_method",
            "base_commit",
            "base_tree",
            "candidate_commit",
            "candidate_tree",
            "integrated_commit",
            "integrated_tree",
            "changed_paths",
            "tests",
            "evidence_refs",
            "role_identities",
            "authority",
            "acceptance_decision",
            "timestamp",
            "rollback_ref",
        )
        for key in required:
            if key not in value:
                issues.append(f"bootstrap attestation missing {key}")

        if value.get("schema_version") != 1:
            issues.append("bootstrap attestation schema_version is unsupported")
        if value.get("plan_fingerprint") != self.expected_plan_fingerprint:
            issues.append("bootstrap attestation plan fingerprint is stale")
        if value.get("node_id") != "BOOT-000":
            issues.append("bootstrap attestation node ID does not match")

        node = self.node("BOOT-000")
        if value.get("contract_version") != node.get("contract_version"):
            issues.append("bootstrap attestation contract version does not match")
        if value.get("planned_branch") != node.get("branch"):
            issues.append("bootstrap attestation planned branch does not match node contract")

        sealed = self._bootstrap_control()
        for key in (
            "actual_branch",
            "source_pr",
            "candidate_commit",
            "candidate_tree",
            "integrated_commit",
            "integrated_tree",
            "merge_method",
        ):
            if value.get(key) != sealed.get(key):
                issues.append(f"bootstrap attestation {key} does not match sealed provenance")

        historical_scope = sealed.get("historical_write_scope")
        if not isinstance(historical_scope, list) or not historical_scope or any(
            not isinstance(scope, str) for scope in historical_scope
        ):
            issues.append("bootstrap historical write scope is missing or invalid")
            historical_scope = []

        target = self.control.get("target")
        target = target if isinstance(target, Mapping) else {}
        if value.get("base_commit") != target.get("baseline_sha"):
            issues.append("bootstrap attestation base commit does not match sealed baseline")
        if value.get("base_tree") != target.get("baseline_tree"):
            issues.append("bootstrap attestation base tree does not match sealed baseline")

        for key in (
            "base_commit",
            "base_tree",
            "candidate_commit",
            "candidate_tree",
            "integrated_commit",
            "integrated_tree",
        ):
            raw = value.get(key)
            if not isinstance(raw, str) or FULL_SHA.fullmatch(raw) is None:
                issues.append(f"bootstrap attestation {key} is invalid")

        if value.get("actual_branch") == value.get("planned_branch"):
            issues.append("bootstrap provenance unexpectedly collapses actual and planned branches")
        if not isinstance(value.get("source_pr"), int):
            issues.append("bootstrap attestation source_pr must be an integer")
        if value.get("merge_method") != "squash":
            issues.append("bootstrap attestation must retain the historical squash merge method")

        changed = value.get("changed_paths")
        normalized_changed: list[str] = []
        if not isinstance(changed, list) or not changed:
            issues.append("bootstrap attestation changed_paths must be non-empty")
        else:
            for raw in changed:
                try:
                    path = normalize_path(raw)
                except (TypeError, ValueError) as error:
                    issues.append(f"bootstrap changed path is unsafe: {error}")
                    continue
                normalized_changed.append(path)
                if historical_scope and not any(
                    path_matches_scope(path, scope) for scope in historical_scope
                ):
                    issues.append(f"bootstrap changed path outside sealed historical scope: {path}")
                if any(
                    path_matches_scope(path, scope)
                    for scope in node.get("forbidden_scope", [])
                ):
                    issues.append(f"bootstrap changed path enters forbidden scope: {path}")

        tests = value.get("tests")
        if not isinstance(tests, list):
            issues.append("bootstrap attestation tests must be a list")
        else:
            passed = {
                item.get("name")
                for item in tests
                if isinstance(item, Mapping) and item.get("status") == "passed"
            }
            for required_test in node.get("required_tests", []):
                if required_test not in passed:
                    issues.append(f"bootstrap required test did not pass: {required_test}")
            if any(
                isinstance(item, Mapping) and item.get("status") != "passed"
                for item in tests
            ):
                issues.append("bootstrap attestation contains a non-passing test")

        evidence = value.get("evidence_refs")
        if not isinstance(evidence, list) or not evidence:
            issues.append("bootstrap attestation requires retained evidence references")

        roles = value.get("role_identities")
        observed_roles: set[str] = set()
        if not isinstance(roles, list):
            issues.append("bootstrap attestation role_identities must be a list")
        else:
            for record in roles:
                if isinstance(record, Mapping) and isinstance(record.get("role"), str):
                    observed_roles.add(str(record.get("role")))
            missing = set(node.get("roles", [])) - observed_roles
            if missing:
                issues.append(
                    "bootstrap attestation omits required role identities: "
                    + ", ".join(sorted(missing))
                )

        authority = value.get("authority")
        if not isinstance(authority, Mapping) or authority.get("node_id") != "BOOT-000":
            issues.append("bootstrap attestation authority is not bound to BOOT-000")
        if value.get("acceptance_decision") not in {"ADOPT", "ADAPT"}:
            issues.append("bootstrap acceptance decision must be ADOPT or ADAPT")
        try:
            parse_time(value.get("timestamp"))
        except ValueError:
            issues.append("bootstrap attestation timestamp is invalid")
        if not isinstance(value.get("rollback_ref"), str) or not value.get("rollback_ref"):
            issues.append("bootstrap attestation rollback_ref must be non-empty")

        candidate_tree = value.get("candidate_tree")
        integrated_tree = value.get("integrated_tree")
        if (
            isinstance(candidate_tree, str)
            and isinstance(integrated_tree, str)
            and candidate_tree != integrated_tree
        ):
            issues.append("bootstrap candidate tree differs from integrated tree")

        if self._has_git_repository():
            base = value.get("base_commit")
            candidate = value.get("candidate_commit")
            integrated = value.get("integrated_commit")
            if all(
                isinstance(item, str) and FULL_SHA.fullmatch(item)
                for item in (base, candidate, integrated)
            ):
                base = str(base)
                candidate = str(candidate)
                integrated = str(integrated)
                if not self.git_object_exists(base):
                    issues.append("bootstrap base commit is unavailable")
                if not self.git_object_exists(integrated):
                    issues.append("bootstrap integrated commit is unavailable")
                if self.git_object_exists(base) and self._commit_tree(base) != value.get("base_tree"):
                    issues.append("bootstrap base tree does not match base commit")
                # The historical source branch was deleted after merge. Its exact head
                # identity/tree are sealed from PR #120. If the object remains locally
                # reachable, verify it too; its absence alone is not normalized into a
                # fabricated replacement branch.
                if self.git_object_exists(candidate) and self._commit_tree(candidate) != candidate_tree:
                    issues.append("bootstrap candidate tree does not match candidate commit")
                if self.git_object_exists(integrated) and self._commit_tree(integrated) != integrated_tree:
                    issues.append("bootstrap integrated tree does not match integrated commit")
                if self.git_object_exists(base) and self.git_object_exists(integrated):
                    if not self.is_ancestor(base, integrated):
                        issues.append("bootstrap integrated commit does not descend from sealed baseline")
                    if require_integrated and not self.is_ancestor(
                        integrated, self.current_target_sha()
                    ):
                        issues.append("bootstrap integrated commit is not in target history")
                    observed_paths = self._diff_paths(base, integrated)
                    if tuple(sorted(set(normalized_changed))) != observed_paths:
                        issues.append("bootstrap changed_paths do not match integrated diff")

        return tuple(dict.fromkeys(issues))

    def _receipt_message(self, receipt: Mapping[str, Any]) -> str:
        payload = canonical_bytes(receipt).decode("utf-8")
        return f"{RECEIPT_COMMIT_MARKER}\n{payload}"

    def _parse_receipt_message(self, message: str) -> Mapping[str, Any] | None:
        prefix = RECEIPT_COMMIT_MARKER + "\n"
        stripped = message.strip()
        if not stripped.startswith(prefix):
            return None
        try:
            value = json.loads(stripped[len(prefix) :])
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, Mapping) else None

    def _durable_receipt_records(self) -> dict[str, list[dict[str, Any]]]:
        target = self.current_target_sha()
        cache = getattr(self, "_durable_receipt_cache", None)
        if isinstance(cache, tuple) and len(cache) == 2 and cache[0] == target:
            return cache[1]
        records: dict[str, list[dict[str, Any]]] = {}
        if not self._has_git_repository() or FULL_SHA.fullmatch(target) is None:
            self._durable_receipt_cache = (target, records)
            return records
        completed = self._git(
            ("log", "--format=%H%x1f%P%x1f%T%x1f%B%x1e", target),
            check=False,
        )
        if completed.returncode != 0:
            self._durable_receipt_cache = (target, records)
            return records
        for raw_record in completed.stdout.split("\x1e"):
            raw_record = raw_record.strip("\n")
            if not raw_record:
                continue
            parts = raw_record.split("\x1f", 3)
            if len(parts) != 4:
                continue
            commit, parents_text, tree, message = parts
            receipt = self._parse_receipt_message(message)
            if receipt is None:
                continue
            node_id = receipt.get("node_id")
            if not isinstance(node_id, str) or node_id not in self._nodes:
                continue
            records.setdefault(node_id, []).append(
                {
                    "commit": commit,
                    "parents": tuple(parents_text.split()),
                    "tree": tree,
                    "receipt": receipt,
                }
            )
        self._durable_receipt_cache = (target, records)
        return records

    def _claim_provenance_issues(
        self,
        node_id: str,
        receipt: Mapping[str, Any],
    ) -> tuple[str, ...]:
        if not self._has_git_repository():
            return ()
        base = receipt.get("base_commit")
        final = receipt.get("final_commit")
        if not (
            isinstance(base, str)
            and isinstance(final, str)
            and FULL_SHA.fullmatch(base)
            and FULL_SHA.fullmatch(final)
            and self.git_object_exists(base)
            and self.git_object_exists(final)
        ):
            return ()
        completed = self._git(
            ("log", "--format=%H%x1f%P%x1f%T%x1f%B%x1e", f"{base}..{final}"),
            check=False,
        )
        if completed.returncode != 0:
            return ("cannot inspect node claim provenance",)
        matches: list[tuple[str, tuple[str, ...], str, Mapping[str, Any]]] = []
        for raw_record in completed.stdout.split("\x1e"):
            raw_record = raw_record.strip("\n")
            if not raw_record:
                continue
            parts = raw_record.split("\x1f", 3)
            if len(parts) != 4:
                continue
            commit, parents_text, tree, message = parts
            try:
                value = json.loads(message.strip())
            except json.JSONDecodeError:
                continue
            if not isinstance(value, Mapping) or value.get("kind") != REMOTE_CLAIM_KIND:
                continue
            if value.get("node_id") == node_id:
                matches.append((commit, tuple(parents_text.split()), tree, value))
        if len(matches) != 1:
            return (f"expected exactly one retained remote claim for {node_id}",)
        _, parents, tree, claim = matches[0]
        issues: list[str] = []
        node = self.node(node_id)
        if claim.get("plan_fingerprint") != self.expected_plan_fingerprint:
            issues.append("retained remote claim plan fingerprint is stale")
        if claim.get("target_sha") != base:
            issues.append("retained remote claim target does not match receipt base")
        if claim.get("branch") != node.get("branch"):
            issues.append("retained remote claim branch does not match node contract")
        if parents != (base,):
            issues.append("retained remote claim is not directly parented by receipt base")
        if tree != receipt.get("base_tree"):
            issues.append("retained remote claim tree does not match receipt base tree")
        return tuple(issues)

    def _validate_receipt_commit_record(
        self,
        node_id: str,
        record: Mapping[str, Any],
    ) -> tuple[str, ...]:
        receipt = record.get("receipt")
        if not isinstance(receipt, Mapping):
            return ("durable completion record has no receipt payload",)
        issues = list(self.validate_receipt(node_id, receipt, require_integrated=True))
        commit = record.get("commit")
        parents = record.get("parents")
        tree = record.get("tree")
        final = receipt.get("final_commit")
        final_tree = receipt.get("final_tree")
        if not isinstance(commit, str) or FULL_SHA.fullmatch(commit) is None:
            issues.append("durable receipt commit identity is invalid")
        if not isinstance(parents, tuple) or parents != (final,):
            issues.append("durable receipt commit must have exactly the final candidate as parent")
        if tree != final_tree:
            issues.append("durable receipt commit tree differs from final candidate tree")
        if (
            self._has_git_repository()
            and isinstance(commit, str)
            and FULL_SHA.fullmatch(commit)
            and self.git_object_exists(commit)
        ):
            if self._commit_tree(commit) != final_tree:
                issues.append("durable receipt commit tree does not match Git object")
            if require := isinstance(final, str) and FULL_SHA.fullmatch(final):
                if require and not self.is_ancestor(final, commit):
                    issues.append("durable receipt commit does not descend from final candidate")
            if not self.is_ancestor(commit, self.current_target_sha()):
                issues.append("durable receipt commit is not integrated into target history")
            issues.extend(self._claim_provenance_issues(node_id, receipt))
        return tuple(dict.fromkeys(issues))

    def completed(self, node_id: str) -> bool:
        return self.node_view(node_id).state == "COMPLETE"

    def node_view(self, node_id: str) -> NodeView:
        local = BaseControlPlane.stored_receipt(self, node_id)
        if local is not None:
            issues = self.validate_receipt(node_id, local, require_integrated=True)
            if not issues:
                return NodeView(
                    node_id,
                    "COMPLETE",
                    (),
                    tuple(self.node(node_id).get("dependencies", [])),
                    branch=str(self.node(node_id).get("branch")),
                    pr_number=(int(local.get("pr")) if isinstance(local.get("pr"), int) else None),
                )
            return NodeView(
                node_id,
                "REPAIR_REQUIRED",
                ("invalid local completion receipt: " + "; ".join(issues),),
                tuple(self.node(node_id).get("dependencies", [])),
                branch=str(self.node(node_id).get("branch")),
                pr_number=(int(local.get("pr")) if isinstance(local.get("pr"), int) else None),
            )

        if node_id == "BOOT-000" and self.bootstrap_attestation_path.is_file():
            attestation = read_json(self.bootstrap_attestation_path)
            issues = self.validate_bootstrap_attestation(attestation, require_integrated=True)
            if not issues:
                return NodeView(
                    node_id,
                    "COMPLETE",
                    (),
                    (),
                    branch=str(attestation.get("actual_branch")),
                    pr_number=(
                        int(attestation.get("source_pr"))
                        if isinstance(attestation.get("source_pr"), int)
                        else None
                    ),
                )
            return NodeView(
                node_id,
                "BOOTSTRAP_INVALID",
                ("invalid durable bootstrap attestation: " + "; ".join(issues),),
                (),
                branch=str(attestation.get("actual_branch")),
                pr_number=(
                    int(attestation.get("source_pr"))
                    if isinstance(attestation.get("source_pr"), int)
                    else None
                ),
            )

        records = self._durable_receipt_records().get(node_id, [])
        if len(records) > 1:
            return NodeView(
                node_id,
                "REPAIR_REQUIRED",
                ("multiple durable completion receipt commits exist for the same node",),
                tuple(self.node(node_id).get("dependencies", [])),
                branch=str(self.node(node_id).get("branch")),
            )
        if len(records) == 1:
            record = records[0]
            receipt = record.get("receipt")
            issues = self._validate_receipt_commit_record(node_id, record)
            if not issues:
                assert isinstance(receipt, Mapping)
                return NodeView(
                    node_id,
                    "COMPLETE",
                    (),
                    tuple(self.node(node_id).get("dependencies", [])),
                    branch=str(self.node(node_id).get("branch")),
                    pr_number=(
                        int(receipt.get("pr"))
                        if isinstance(receipt.get("pr"), int)
                        else None
                    ),
                )
            return NodeView(
                node_id,
                "REPAIR_REQUIRED",
                ("invalid durable completion receipt commit: " + "; ".join(issues),),
                tuple(self.node(node_id).get("dependencies", [])),
                branch=str(self.node(node_id).get("branch")),
                pr_number=(
                    int(receipt.get("pr"))
                    if isinstance(receipt, Mapping) and isinstance(receipt.get("pr"), int)
                    else None
                ),
            )

        return super().node_view(node_id)

    def publish_remote_claim(
        self,
        node_id: str,
        owner: str,
        expires_at: str,
        *,
        remote: str = "origin",
    ) -> str:
        """Publish the normal mutex claim plus the exact claimed branch in provenance."""

        node = self.node(node_id)
        branch = str(node.get("branch"))
        if self.remote_branch_sha(branch, remote=remote) is not None:
            raise ClaimError(
                f"remote branch {branch!r} already exists; reconcile it before claiming"
            )
        target = self.current_target_sha()
        tree = self._git(("rev-parse", f"{target}^{{tree}}"), check=True).stdout.strip()
        message = json.dumps(
            {
                "branch": branch,
                "expires_at": expires_at,
                "kind": REMOTE_CLAIM_KIND,
                "node_id": node_id,
                "owner": owner,
                "plan_fingerprint": self.expected_plan_fingerprint,
                "target_sha": target,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        identity = {
            "GIT_AUTHOR_NAME": "Hive Mind Autopilot Claim",
            "GIT_AUTHOR_EMAIL": "autopilot-claim@hive-mind.invalid",
            "GIT_COMMITTER_NAME": "Hive Mind Autopilot Claim",
            "GIT_COMMITTER_EMAIL": "autopilot-claim@hive-mind.invalid",
        }
        created = self._git(
            (
                "-c",
                "user.name=Hive Mind Autopilot Claim",
                "-c",
                "user.email=autopilot-claim@hive-mind.invalid",
                "commit-tree",
                tree,
                "-p",
                target,
                "-m",
                message,
            ),
            check=True,
            environment=identity,
        ).stdout.strip()
        if FULL_SHA.fullmatch(created) is None:
            raise ClaimError("failed to create a remote claim commit")
        pushed = self._git(("push", remote, f"{created}:refs/heads/{branch}"), check=False)
        if pushed.returncode != 0:
            raise ClaimError("remote claim race or push failure: " + pushed.stderr.strip())
        observed = self.remote_branch_sha(branch, remote=remote)
        if observed != created:
            raise ClaimError("remote claim branch does not bind the created claim commit")
        return created

    def _create_receipt_commit(
        self,
        node_id: str,
        receipt: Mapping[str, Any],
    ) -> str:
        if not self._has_git_repository():
            raise ReceiptError("durable completion requires a Git repository")
        branch = str(self.node(node_id).get("branch"))
        symbolic = self._git(("symbolic-ref", "--quiet", "--short", "HEAD"), check=False)
        current_branch = symbolic.stdout.strip()
        if symbolic.returncode != 0 or current_branch != branch:
            raise ReceiptError(
                f"durable completion must be created while checked out on {branch!r}"
            )
        final = str(receipt.get("final_commit"))
        head = self._git(("rev-parse", "HEAD"), check=True).stdout.strip()
        if head != final:
            raise ReceiptError("receipt final_commit must equal the checked-out node HEAD")
        tree = self._git(("rev-parse", f"{final}^{{tree}}"), check=True).stdout.strip()
        if tree != receipt.get("final_tree"):
            raise ReceiptError("receipt final_tree does not match the checked-out node HEAD")
        message = self._receipt_message(receipt)
        identity = {
            "GIT_AUTHOR_NAME": "Hive Mind Autopilot Receipt",
            "GIT_AUTHOR_EMAIL": "autopilot-receipt@hive-mind.invalid",
            "GIT_COMMITTER_NAME": "Hive Mind Autopilot Receipt",
            "GIT_COMMITTER_EMAIL": "autopilot-receipt@hive-mind.invalid",
        }
        created = self._git(
            (
                "-c",
                "user.name=Hive Mind Autopilot Receipt",
                "-c",
                "user.email=autopilot-receipt@hive-mind.invalid",
                "commit-tree",
                tree,
                "-p",
                final,
                "-m",
                message,
            ),
            check=True,
            environment=identity,
        ).stdout.strip()
        if FULL_SHA.fullmatch(created) is None:
            raise ReceiptError("failed to create durable receipt commit")
        updated = self._git(
            ("update-ref", f"refs/heads/{branch}", created, final),
            check=False,
        )
        if updated.returncode != 0:
            raise ReceiptError("node branch moved while publishing durable receipt commit")
        return created

    def complete(
        self,
        node_id: str,
        owner: str,
        receipt: Mapping[str, Any],
    ) -> str:
        """Validate completion and append an immutable, zero-path receipt commit."""

        if node_id == "BOOT-000":
            raise ReceiptError("historical BOOT-000 completion is sealed by bootstrap attestation")
        claim_path = self.claim_path(node_id)
        if not claim_path.is_file():
            raise ClaimError("node completion requires an active claim")
        claim = read_json(claim_path)
        if not isinstance(claim, Mapping) or claim.get("owner") != owner:
            raise ClaimError("claim owner does not match")
        if parse_time(claim.get("expires_at")) <= self.clock():
            raise ClaimError("claim expired before receipt publication")

        issues = self.validate_receipt(node_id, receipt, require_integrated=False)
        if issues:
            raise ReceiptError("; ".join(issues))
        provenance = self._claim_provenance_issues(node_id, receipt)
        if provenance:
            raise ReceiptError("; ".join(provenance))

        local_path = self.receipt_path(node_id)
        if local_path.exists():
            existing = read_json(local_path)
            if digest_json(existing) != digest_json(receipt):
                raise ReceiptError("node already has a different local completion receipt")

        receipt_commit = self._create_receipt_commit(node_id, receipt)
        if not local_path.exists():
            atomic_write_json(local_path, receipt)
        append_jsonl(
            self.state_dir / "receipt-index.jsonl",
            {
                "node_id": node_id,
                "receipt_commit": receipt_commit,
                "receipt_digest": digest_json(receipt),
                "final_commit": receipt.get("final_commit"),
                "timestamp": receipt.get("timestamp"),
            },
        )
        claim_path.unlink()
        return receipt_commit
