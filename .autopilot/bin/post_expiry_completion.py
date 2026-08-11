"""Closed construction controls for the OPTIMIZER-370 post-expiry incident.

This module deliberately has no Git push, ref update, receipt publication, node
activation, or release-integration operation.  It can validate sealed construction
evidence and append one bounded AUTHORIZED preparation record in the Git common
directory.  A later capability may consume that record only after separate authority.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

from controller import FULL_SHA, canonical_bytes, digest_json, format_time, parse_time
from durable_controller import AutopilotError, ClaimError, read_json

AUTHORITY_PATH = ".autopilot/optimizer-370-post-expiry-authority.json"
AUTHORITY_SCHEMA_PATH = ".autopilot/optimizer-370-post-expiry-authority.schema.json"
INTENDED_RECEIPT_PATH = ".autopilot/optimizer-370-post-expiry-intended-receipt.json"
NEGATIVE_STATE_PATH = ".autopilot/optimizer-370-post-expiry-negative-state.json"
AUTHORITY_KIND = "hive-mind-autopilot-optimizer-370-post-expiry-authority-v1"
STATE_KIND = "hive-mind-autopilot-optimizer-370-post-expiry-state-v1"
STATE_DIRECTORY = "hive-mind-autopilot/optimizer-370-post-expiry"
STATE_ORDER = ("AUTHORIZED", "CONSUMING", "CONSUMED", "EXPIRED", "ADVERSE")
TERMINAL_STATES = frozenset({"CONSUMED", "EXPIRED", "ADVERSE"})
ZERO_CAPABILITY = "0" * 40
# Resealed to literal C2 only after the construction commit exists.  Keeping this
# equal to ZERO_CAPABILITY preserves validation while making prepare unavailable.
SEALED_CAPABILITY_COMMIT = "7b87eab3a287884549be94415add07825c08c172"

# Resealed after the static documents are constructed.  A mismatch fails closed.
AUTHORITY_DIGEST = "sha256:2933893fbb414005877e06dc5e478b04c33b451e0de4ce19e64b5cf7fd3d4d55"
AUTHORITY_SCHEMA_DIGEST = "sha256:df1cf230da72e6b4e924ed8c90f70324cc886578f7d1f578e51c2e02a11e18ac"
INTENDED_RECEIPT_DIGEST = (
    "sha256:bf5b2cdd03f40b88980a964d843bf8829b9dc2393864b4ded360f04a42e8afdd"
)


def _canonical_file_bytes(value: object) -> bytes:
    return canonical_bytes(value) + b"\n"


def _bytes_digest(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


class PostExpiryCompletionMixin:
    """Non-activating validator/preparer for one exact expired claim."""

    @property
    def post_expiry_authority_path(self) -> Path:
        return self.repo_root / AUTHORITY_PATH

    @property
    def post_expiry_authority_schema_path(self) -> Path:
        return self.repo_root / AUTHORITY_SCHEMA_PATH

    @property
    def post_expiry_intended_receipt_path(self) -> Path:
        return self.repo_root / INTENDED_RECEIPT_PATH

    def _post_expiry_authority(self) -> Mapping[str, Any] | None:
        if not self.post_expiry_authority_path.is_file():
            return None
        value = read_json(self.post_expiry_authority_path)
        return value if isinstance(value, Mapping) else None

    @staticmethod
    def _authority_keys() -> frozenset[str]:
        return frozenset(
            {
                "schema_version", "kind", "authorization_id", "repository",
                "origin_name", "origin_url", "node_id", "claim_owner", "branch",
                "release", "main", "old_receipt", "expired_claim",
                "execution_merge", "candidate", "pull_request", "intended_receipt",
                "negative_state", "quarantined_prior_overlay", "authorized_paths",
                "withheld_powers", "max_lease_minutes", "capability_commit",
                "court_case_id", "appeal_id",
            }
        )

    def post_expiry_static_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        authority = self._post_expiry_authority()
        if not isinstance(authority, Mapping):
            return ("post-expiry authority is missing or invalid",)
        if set(authority) != self._authority_keys():
            issues.append("post-expiry authority shape is not exact")
        if authority.get("schema_version") != 1 or authority.get("kind") != AUTHORITY_KIND:
            issues.append("post-expiry authority schema/kind is unsupported")
        if digest_json(authority) != AUTHORITY_DIGEST:
            issues.append("post-expiry authority material was altered")
        schema = read_json(self.post_expiry_authority_schema_path)
        if digest_json(schema) != AUTHORITY_SCHEMA_DIGEST:
            issues.append("post-expiry authority schema was altered")
        receipt = read_json(self.post_expiry_intended_receipt_path)
        if digest_json(receipt) != INTENDED_RECEIPT_DIGEST:
            issues.append("post-expiry intended receipt was altered")
        if isinstance(authority.get("intended_receipt"), Mapping):
            sealed = authority["intended_receipt"]
            if sealed.get("path") != INTENDED_RECEIPT_PATH or sealed.get("payload_digest") != INTENDED_RECEIPT_DIGEST:
                issues.append("post-expiry intended receipt binding differs")
        else:
            issues.append("post-expiry intended receipt binding is invalid")
        capability = authority.get("capability_commit")
        if not isinstance(capability, str) or FULL_SHA.fullmatch(capability) is None:
            issues.append("post-expiry capability commit is invalid")
        elif capability != SEALED_CAPABILITY_COMMIT:
            issues.append("post-expiry capability commit differs from the compiled pin")
        if authority.get("max_lease_minutes") != 10:
            issues.append("post-expiry maximum lease differs")
        if authority.get("withheld_powers") != [
            "node_completion_activation", "receipt_publication", "remote_mutation",
            "release_integration", "main_movement", "claim_or_dispatcher_mutation",
            "pull_request_mutation",
        ]:
            issues.append("post-expiry withheld powers differ")
        return tuple(dict.fromkeys(issues))

    def _post_expiry_common_dir(self) -> Path:
        completed = self._git(("rev-parse", "--git-common-dir"), check=False)
        raw = completed.stdout.strip()
        if completed.returncode != 0 or not raw:
            raise AutopilotError("post-expiry Git common directory is unavailable")
        common = Path(raw)
        if not common.is_absolute():
            common = (self.repo_root / common).resolve()
        return common

    @property
    def post_expiry_state_dir(self) -> Path:
        return self._post_expiry_common_dir() / STATE_DIRECTORY

    def _state_path(self, status: str) -> Path:
        if status not in STATE_ORDER:
            raise AutopilotError("post-expiry state is unsupported")
        return self.post_expiry_state_dir / f"{status.lower()}.json"

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name != "nt":
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            return
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        handle = create_file(
            str(path), 0x80000000, 0x00000007, None, 3, 0x02000000, None
        )
        if handle == wintypes.HANDLE(-1).value:
            raise OSError(ctypes.get_last_error(), "cannot open durable state directory")
        try:
            if not kernel32.FlushFileBuffers(handle):
                raise OSError(ctypes.get_last_error(), "cannot flush durable state directory")
        finally:
            kernel32.CloseHandle(handle)

    def _o_excl_state_write(self, path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = _canonical_file_bytes(value)
        try:
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                0o600,
            )
        except FileExistsError as error:
            raise ClaimError(f"post-expiry immutable state already exists: {path.name}") from error
        try:
            written = 0
            while written < len(encoded):
                count = os.write(descriptor, encoded[written:])
                if count <= 0:
                    raise OSError("short durable state write")
                written += count
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._fsync_directory(path.parent)

    def _state_records(self) -> list[tuple[str, Mapping[str, Any], str]]:
        records: list[tuple[str, Mapping[str, Any], str]] = []
        for status in STATE_ORDER:
            path = self._state_path(status)
            if not path.exists():
                continue
            raw = path.read_bytes()
            try:
                value = json.loads(raw)
            except (UnicodeError, json.JSONDecodeError) as error:
                raise AutopilotError(f"post-expiry {status} state is unreadable") from error
            if not isinstance(value, Mapping) or raw != _canonical_file_bytes(value):
                raise AutopilotError(f"post-expiry {status} state is not canonical")
            records.append((status, value, _bytes_digest(raw)))
        return records

    def post_expiry_state_issues(self) -> tuple[str, ...]:
        try:
            records = self._state_records()
        except (AutopilotError, OSError) as error:
            return (str(error),)
        if not records:
            return ()
        issues: list[str] = []
        authority = self._post_expiry_authority()
        predecessor = digest_json(authority) if isinstance(authority, Mapping) else None
        allowed: dict[str | None, frozenset[str]] = {
            None: frozenset({"AUTHORIZED"}),
            "AUTHORIZED": frozenset({"CONSUMING", "EXPIRED", "ADVERSE"}),
            "CONSUMING": frozenset({"CONSUMED", "ADVERSE"}),
            "CONSUMED": frozenset(), "EXPIRED": frozenset(), "ADVERSE": frozenset(),
        }
        prior: str | None = None
        for status, value, record_digest in records:
            if status not in allowed[prior]:
                issues.append(f"post-expiry foreign or impossible state transition to {status}")
            if set(value) != {
                "schema_version", "kind", "authorization_id", "status", "actor",
                "recorded_at", "expires_at", "authority_digest", "predecessor_digest",
            }:
                issues.append(f"post-expiry {status} state shape is invalid")
            if value.get("schema_version") != 1 or value.get("kind") != STATE_KIND:
                issues.append(f"post-expiry {status} state schema/kind differs")
            if not isinstance(authority, Mapping) or value.get("authorization_id") != authority.get("authorization_id"):
                issues.append(f"post-expiry {status} state has foreign authorization")
            if value.get("status") != status or value.get("authority_digest") != AUTHORITY_DIGEST:
                issues.append(f"post-expiry {status} state binding differs")
            if value.get("predecessor_digest") != predecessor:
                issues.append(f"post-expiry {status} predecessor differs")
            try:
                recorded = parse_time(value.get("recorded_at"))
                expires = parse_time(value.get("expires_at"))
                if status == "AUTHORIZED" and expires <= recorded:
                    issues.append("post-expiry authorization expiry is not future bounded")
                if status != "AUTHORIZED" and records[0][1].get("expires_at") != value.get("expires_at"):
                    issues.append(f"post-expiry {status} expiry differs")
            except ValueError:
                issues.append(f"post-expiry {status} timestamps are invalid")
            predecessor = record_digest
            prior = status
        return tuple(dict.fromkeys(issues))

    def post_expiry_completion_status(self) -> Mapping[str, Any]:
        static_issues = self.post_expiry_static_issues()
        state_issues = self.post_expiry_state_issues()
        records = [] if state_issues else self._state_records()
        latest = records[-1][0] if records else "UNPREPARED"
        expired = False
        if records and latest not in TERMINAL_STATES:
            try:
                expired = parse_time(records[0][1]["expires_at"]) <= self.clock()
            except ValueError:
                expired = True
        return {
            "authorization_id": "optimizer-370-post-expiry-completion-v1",
            "state": latest,
            "expired": expired,
            "static_valid": not static_issues,
            "state_valid": not state_issues,
            "activation_available": False,
            "release_integration_available": False,
            "issues": [*static_issues, *state_issues],
        }

    def validate_post_expiry_completion(self) -> Mapping[str, Any]:
        """Validate construction evidence without querying or mutating a remote."""

        status = dict(self.post_expiry_completion_status())
        status["valid"] = status["static_valid"] and status["state_valid"]
        status["capability_sealed"] = (
            SEALED_CAPABILITY_COMMIT != ZERO_CAPABILITY
            and self._post_expiry_authority() is not None
            and self._post_expiry_authority().get("capability_commit")
            == SEALED_CAPABILITY_COMMIT
        )
        return status

    def prepare_post_expiry_completion(
        self, *, actor: str, lease_minutes: int = 10
    ) -> Mapping[str, Any]:
        """Append a local bounded preparation record; confer no activation power."""

        if not actor.strip():
            raise ClaimError("post-expiry preparation actor is required")
        issues = self.post_expiry_static_issues()
        if issues:
            raise ClaimError("; ".join(issues))
        authority = self._post_expiry_authority()
        assert isinstance(authority, Mapping)
        if SEALED_CAPABILITY_COMMIT == ZERO_CAPABILITY:
            raise ClaimError("post-expiry capability commit is not yet sealed")
        if not 1 <= lease_minutes <= int(authority["max_lease_minutes"]):
            raise ClaimError("post-expiry preparation lease is outside the bounded maximum")
        if self._state_records():
            raise ClaimError("post-expiry preparation is one-time and already exists")
        now = self.clock()
        record = {
            "schema_version": 1,
            "kind": STATE_KIND,
            "authorization_id": authority["authorization_id"],
            "status": "AUTHORIZED",
            "actor": actor,
            "recorded_at": format_time(now),
            "expires_at": format_time(now + timedelta(minutes=lease_minutes)),
            "authority_digest": AUTHORITY_DIGEST,
            "predecessor_digest": AUTHORITY_DIGEST,
        }
        self._o_excl_state_write(self._state_path("AUTHORIZED"), record)
        return record
