"""Durable completion layer for the repository-resident Autopilot controller.

The base controller intentionally keeps leases, GitHub snapshots, retries, and other
runtime state under ignored ``.autopilot/state``. Completion evidence is different:
it must survive a fresh checkout. This module preserves the base controller's receipt
validation and adds repository-resident durable receipt discovery/publication plus a
strict historical bootstrap attestation for PR #120.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from controller import (
    FULL_SHA,
    AutopilotError,
    ClaimError,
    ConfigurationError,
    ControlPlane as BaseControlPlane,
    NodeView,
    ReceiptError,
    append_jsonl,
    atomic_write_json,
    digest_json,
    normalize_path,
    parse_time,
    path_matches_scope,
    read_json,
)

DURABLE_RECEIPT_FILENAME = "autopilot-completion-receipt.json"
BOOTSTRAP_ATTESTATION = ".autopilot/bootstrap-completion.json"
BOOTSTRAP_ATTESTATION_SCHEMA = ".autopilot/bootstrap-completion.schema.json"


class ControlPlane(BaseControlPlane):
    """Base controller with durable, fail-closed completion reconstruction."""

    def durable_receipt_path(self, node_id: str) -> Path:
        """Return the repository-resident receipt path authorized by the node.

        Product nodes already own a node-specific evidence directory. Durable receipts
        live inside that declared write scope rather than expanding authority into a
        global control-plane directory.
        """

        if node_id == "BOOT-000":
            raise ConfigurationError(
                "BOOT-000 uses the historical bootstrap completion attestation"
            )
        node = self.node(node_id)
        for raw_scope in node.get("write_scope", []):
            if not isinstance(raw_scope, str):
                continue
            scope = raw_scope.replace("\\", "/").strip().rstrip("/")
            if not scope.startswith("evidence/") or not scope.endswith("/**"):
                continue
            root = scope[:-3].rstrip("/")
            if root:
                return self.repo_root / root / DURABLE_RECEIPT_FILENAME
        raise ConfigurationError(
            f"{node_id}: no node-owned evidence/** write scope is available for a durable receipt"
        )

    @property
    def bootstrap_attestation_path(self) -> Path:
        return self.repo_root / BOOTSTRAP_ATTESTATION

    @property
    def bootstrap_attestation_schema_path(self) -> Path:
        return self.repo_root / BOOTSTRAP_ATTESTATION_SCHEMA

    def _commit_tree(self, commit: str) -> str | None:
        if FULL_SHA.fullmatch(commit) is None:
            return None
        completed = self._git(("rev-parse", f"{commit}^{{tree}}"), check=False)
        value = completed.stdout.strip()
        return value if completed.returncode == 0 and FULL_SHA.fullmatch(value) else None

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

    def validate_configuration(self) -> tuple[str, ...]:
        issues = list(super().validate_configuration())
        if not self.bootstrap_attestation_path.is_file():
            issues.append(f"required file is missing: {BOOTSTRAP_ATTESTATION}")
        if not self.bootstrap_attestation_schema_path.is_file():
            issues.append(f"required file is missing: {BOOTSTRAP_ATTESTATION_SCHEMA}")
        for node in self.nodes():
            node_id = str(node.get("id"))
            if node_id == "BOOT-000":
                continue
            try:
                self.durable_receipt_path(node_id)
            except ConfigurationError as error:
                issues.append(str(error))
        if self.bootstrap_attestation_path.is_file():
            attestation = read_json(self.bootstrap_attestation_path)
            issues.extend(self.validate_bootstrap_attestation(attestation, require_integrated=True))
        return tuple(dict.fromkeys(issues))

    def validate_receipt(
        self,
        node_id: str,
        value: object,
        *,
        require_integrated: bool = False,
    ) -> tuple[str, ...]:
        """Preserve base validation and additionally bind declared commit trees."""

        issues = list(
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
        if self.verify_git_objects:
            if isinstance(base, str) and FULL_SHA.fullmatch(base):
                observed = self._commit_tree(base)
                if observed is not None and observed != base_tree:
                    issues.append("receipt base_tree does not match base_commit")
            if isinstance(final, str) and FULL_SHA.fullmatch(final):
                observed = self._commit_tree(final)
                if observed is not None and observed != final_tree:
                    issues.append("receipt final_tree does not match final_commit")
        return tuple(dict.fromkeys(issues))

    def _bootstrap_control(self) -> Mapping[str, Any]:
        value = self.control.get("bootstrap_completion")
        if not isinstance(value, Mapping):
            raise ConfigurationError("control-plane.bootstrap_completion must be an object")
        return value

    def validate_bootstrap_attestation(
        self,
        value: object,
        *,
        require_integrated: bool = True,
    ) -> tuple[str, ...]:
        """Validate the one historical bootstrap that predates durable receipts.

        PR #120 was squash-merged. The candidate commit therefore is not an ancestor of
        main, but its candidate tree is byte-identical to the integrated merge tree. We
        retain both identities and require tree equality instead of fabricating the
        planned node branch or pretending a PR title is a receipt.
        """

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

        control = self._bootstrap_control()
        for key in (
            "actual_branch",
            "source_pr",
            "candidate_commit",
            "candidate_tree",
            "integrated_commit",
            "integrated_tree",
        ):
            if value.get(key) != control.get(key):
                issues.append(f"bootstrap attestation {key} does not match sealed provenance")
        if value.get("merge_method") != control.get("merge_method"):
            issues.append("bootstrap attestation merge method does not match sealed provenance")

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
                except ValueError as error:
                    issues.append(f"bootstrap changed path is unsafe: {error}")
                    continue
                normalized_changed.append(path)
                if not any(path_matches_scope(path, scope) for scope in node.get("write_scope", [])):
                    issues.append(f"bootstrap changed path outside node write scope: {path}")
                if any(path_matches_scope(path, scope) for scope in node.get("forbidden_scope", [])):
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

        observed_roles: set[str] = set()
        roles = value.get("role_identities")
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
        if isinstance(candidate_tree, str) and isinstance(integrated_tree, str):
            if candidate_tree != integrated_tree:
                issues.append("bootstrap candidate tree differs from integrated tree")

        if self.verify_git_objects:
            base = value.get("base_commit")
            candidate = value.get("candidate_commit")
            integrated = value.get("integrated_commit")
            if all(isinstance(item, str) and FULL_SHA.fullmatch(item) for item in (base, candidate, integrated)):
                for label, commit in (
                    ("base", str(base)),
                    ("candidate", str(candidate)),
                    ("integrated", str(integrated)),
                ):
                    if not self.git_object_exists(commit):
                        issues.append(f"bootstrap {label} commit is unavailable")
                if self.git_object_exists(str(base)) and self._commit_tree(str(base)) != value.get("base_tree"):
                    issues.append("bootstrap base tree does not match base commit")
                if self.git_object_exists(str(candidate)) and self._commit_tree(str(candidate)) != candidate_tree:
                    issues.append("bootstrap candidate tree does not match candidate commit")
                if self.git_object_exists(str(integrated)) and self._commit_tree(str(integrated)) != integrated_tree:
                    issues.append("bootstrap integrated tree does not match integrated commit")
                if self.git_object_exists(str(base)) and self.git_object_exists(str(integrated)):
                    if not self.is_ancestor(str(base), str(integrated)):
                        issues.append("bootstrap integrated commit does not descend from sealed baseline")
                    if require_integrated and not self.is_ancestor(str(integrated), self.current_target_sha()):
                        issues.append("bootstrap integrated commit is not in target history")
                    observed_paths = self._diff_paths(str(base), str(integrated))
                    if tuple(sorted(set(normalized_changed))) != observed_paths:
                        issues.append("bootstrap changed_paths do not match integrated diff")

        return tuple(dict.fromkeys(issues))

    def _receipt_with_source(self, node_id: str) -> tuple[str, Mapping[str, Any]] | None:
        local = BaseControlPlane.stored_receipt(self, node_id)
        if local is not None:
            return ("local", local)
        if node_id == "BOOT-000":
            return None
        path = self.durable_receipt_path(node_id)
        if not path.is_file():
            return None
        value = read_json(path)
        if not isinstance(value, Mapping):
            raise ConfigurationError(f"durable receipt must be an object: {path}")
        return ("durable", value)

    def stored_receipt(self, node_id: str) -> Mapping[str, Any] | None:
        found = self._receipt_with_source(node_id)
        return found[1] if found is not None else None

    def completed(self, node_id: str) -> bool:
        return self.node_view(node_id).state == "COMPLETE"

    def node_view(self, node_id: str) -> NodeView:
        found = self._receipt_with_source(node_id)
        if found is not None:
            source, receipt = found
            issues = self.validate_receipt(node_id, receipt, require_integrated=True)
            if not issues:
                return NodeView(
                    node_id,
                    "COMPLETE",
                    (),
                    tuple(self.node(node_id).get("dependencies", [])),
                    branch=str(self.node(node_id).get("branch")),
                    pr_number=(
                        int(receipt.get("pr")) if isinstance(receipt.get("pr"), int) else None
                    ),
                )
            return NodeView(
                node_id,
                "REPAIR_REQUIRED",
                (f"invalid {source} completion receipt: " + "; ".join(issues),),
                tuple(self.node(node_id).get("dependencies", [])),
                branch=str(self.node(node_id).get("branch")),
                pr_number=(
                    int(receipt.get("pr")) if isinstance(receipt.get("pr"), int) else None
                ),
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

        return super().node_view(node_id)

    def complete(
        self,
        node_id: str,
        owner: str,
        receipt: Mapping[str, Any],
    ) -> Path:
        """Publish both ephemeral runtime state and a node-owned durable receipt."""

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

        local_path = self.receipt_path(node_id)
        durable_path = self.durable_receipt_path(node_id)
        for label, path in (("local", local_path), ("durable", durable_path)):
            if path.exists():
                existing = read_json(path)
                if digest_json(existing) != digest_json(receipt):
                    raise ReceiptError(f"node already has a different {label} completion receipt")

        if not local_path.exists():
            atomic_write_json(local_path, receipt)
        if not durable_path.exists():
            atomic_write_json(durable_path, receipt)
        append_jsonl(
            self.state_dir / "receipt-index.jsonl",
            {
                "node_id": node_id,
                "receipt_digest": digest_json(receipt),
                "final_commit": receipt.get("final_commit"),
                "durable_path": str(durable_path.relative_to(self.repo_root)).replace("\\", "/"),
                "timestamp": receipt.get("timestamp"),
            },
        )
        claim_path.unlink()
        return durable_path
