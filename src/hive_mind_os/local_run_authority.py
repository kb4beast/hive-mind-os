"""Operator-local grants, separate from independently signed V4 activation.

The OS account owns the host key and explicitly authorizes an exact local run.
This authenticates custody and detects changed grants; it does not establish
independence from a hostile process running as that same account.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import secrets
import socket
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .runtime_contracts import canonical_json_bytes, raw_sha256


class LocalAuthorityError(ValueError):
    """A local grant is missing, changed, expired, or outside its custody scope."""


def local_operator() -> str:
    return f"{socket.gethostname()}:{getpass.getuser()}"


class LocalAuthorityStore:
    """A dedicated host directory must live outside every subject workspace."""

    def __init__(self, directory: Path, *, create: bool = False) -> None:
        self.directory = directory.resolve()
        if directory.is_symlink():
            raise LocalAuthorityError("host directory cannot be a symbolic link")
        key_path = self.directory / "local-host.key"
        if create:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                with key_path.open("xb") as stream:
                    stream.write(secrets.token_bytes(32))
                if os.name != "nt":
                    key_path.chmod(0o600)
            except FileExistsError:
                pass
        if key_path.is_symlink() or not key_path.is_file():
            raise LocalAuthorityError("local host key is absent or redirected")
        self._key = key_path.read_bytes()
        if len(self._key) != 32:
            raise LocalAuthorityError("local host key is malformed")

    def signature(self, document: dict[str, Any]) -> str:
        return hmac.new(self._key, canonical_json_bytes(document), hashlib.sha256).hexdigest()

    def seal(self, document: dict[str, Any]) -> dict[str, Any]:
        return {"document": document, "hmac_sha256": self.signature(document)}

    def unseal(self, value: dict[str, Any]) -> dict[str, Any]:
        if set(value) != {"document", "hmac_sha256"} or not isinstance(value["document"], dict):
            raise LocalAuthorityError("local signed record has an invalid shape")
        signature = value["hmac_sha256"]
        if not isinstance(signature, str) or not hmac.compare_digest(signature, self.signature(value["document"])):
            raise LocalAuthorityError("local signed record authentication failed")
        return value["document"]

    def issue(
        self, *, plan_digest: str, repository: Path, commit: str, tree: str,
        state_directory: Path, operator_request: bytes, host_digest: str,
        duration_seconds: int = 14_400, now: datetime | None = None,
    ) -> dict[str, Any]:
        if not operator_request or not operator_request.decode("utf-8").strip():
            raise LocalAuthorityError("an explicit operator directive is required")
        if not 60 <= duration_seconds <= 86_400:
            raise LocalAuthorityError("local run duration must be between 60 seconds and one day")
        repository, state_directory = repository.resolve(), state_directory.resolve()
        if self.directory.is_relative_to(repository) or state_directory.is_relative_to(repository):
            raise LocalAuthorityError("host and run state must be outside the subject repository")
        if self.directory == state_directory or self.directory.is_relative_to(state_directory):
            raise LocalAuthorityError("host key custody must be outside run state")
        current = now or datetime.now(UTC)
        grant = self.seal({
            "schema_version": 1, "kind": "hive-mind-operator-local-grant-v1",
            "authentication_scope": "local-operator", "operator": local_operator(),
            "nonce": secrets.token_hex(32), "plan_digest": plan_digest,
            "repository": str(repository), "commit": commit, "tree": tree,
            "state_directory": str(state_directory), "host_digest": host_digest,
            "operator_request_digest": raw_sha256(operator_request),
            "allowed_actions": ["inspect", "isolated-local-edit", "local-test", "write-run-evidence"],
            "external_effects": False, "protected_merge_authorized": False,
            "issued_at": current.isoformat(), "expires_at": (current + timedelta(seconds=duration_seconds)).isoformat(),
        })
        return grant

    def verify(
        self, grant: dict[str, Any], *, plan_digest: str, repository: Path,
        state_directory: Path, host_digest: str, operator_request: bytes,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        repository, state_directory = repository.resolve(), state_directory.resolve()
        if self.directory.is_relative_to(repository) or state_directory.is_relative_to(repository):
            raise LocalAuthorityError("host and run state must be outside the subject repository")
        if self.directory == state_directory or self.directory.is_relative_to(state_directory):
            raise LocalAuthorityError("host key custody must be outside run state")
        document = self.unseal(grant)
        expected = {
            "schema_version": 1,
            "kind": "hive-mind-operator-local-grant-v1", "authentication_scope": "local-operator",
            "operator": local_operator(), "plan_digest": plan_digest,
            "repository": str(repository.resolve()), "state_directory": str(state_directory.resolve()),
            "host_digest": host_digest, "operator_request_digest": raw_sha256(operator_request),
            "external_effects": False, "protected_merge_authorized": False,
            "allowed_actions": ["inspect", "isolated-local-edit", "local-test", "write-run-evidence"],
        }
        if any(document.get(key) != value for key, value in expected.items()):
            raise LocalAuthorityError("local grant binding differs from the requested run")
        current = now or datetime.now(UTC)
        if not datetime.fromisoformat(document["issued_at"]) <= current < datetime.fromisoformat(document["expires_at"]):
            raise LocalAuthorityError("local grant is not currently valid")
        # Exact retries share one reservation. A nonce cannot be transplanted to
        # a different run directory, nor can its signed content be reinterpreted.
        connection = sqlite3.connect(self.directory / "reservations.sqlite3", timeout=30)
        try:
            with connection:
                connection.execute("CREATE TABLE IF NOT EXISTS local_grants (nonce TEXT PRIMARY KEY, digest TEXT NOT NULL)")
                digest = raw_sha256(canonical_json_bytes(document))
                connection.execute("INSERT OR IGNORE INTO local_grants VALUES (?, ?)", (document["nonce"], digest))
                row = connection.execute("SELECT digest FROM local_grants WHERE nonce=?", (document["nonce"],)).fetchone()
                if row != (digest,):
                    raise LocalAuthorityError("local grant nonce was already reserved for another binding")
        finally:
            connection.close()
        return document

    def event_head(self, state_directory: Path) -> tuple[int, str | None]:
        with closing(sqlite3.connect(self.directory / "reservations.sqlite3", timeout=30)) as connection, connection:
            connection.execute("CREATE TABLE IF NOT EXISTS local_event_heads (run TEXT PRIMARY KEY, sequence INTEGER NOT NULL, digest TEXT NOT NULL)")
            row = connection.execute("SELECT sequence, digest FROM local_event_heads WHERE run=?", (str(state_directory.resolve()),)).fetchone()
            return row if row is not None else (0, None)

    def advance_event_head(self, state_directory: Path, *, sequence: int, digest: str, previous_digest: str | None) -> None:
        with closing(sqlite3.connect(self.directory / "reservations.sqlite3", timeout=30)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("CREATE TABLE IF NOT EXISTS local_event_heads (run TEXT PRIMARY KEY, sequence INTEGER NOT NULL, digest TEXT NOT NULL)")
            run = str(state_directory.resolve())
            row = connection.execute("SELECT sequence, digest FROM local_event_heads WHERE run=?", (run,)).fetchone()
            if (row if row is not None else (0, None)) != (sequence - 1, previous_digest):
                raise LocalAuthorityError("event custody checkpoint disagrees with append")
            connection.execute("INSERT INTO local_event_heads VALUES (?, ?, ?) ON CONFLICT(run) DO UPDATE SET sequence=excluded.sequence, digest=excluded.digest", (run, sequence, digest))


def write_new_json(path: Path, document: dict[str, Any]) -> None:
    with path.open("xb") as stream:
        stream.write(canonical_json_bytes(document))
        stream.flush()
        os.fsync(stream.fileno())


def read_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_bytes())
    if not isinstance(document, dict):
        raise LocalAuthorityError("expected a JSON object")
    return document
