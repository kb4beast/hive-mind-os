from __future__ import annotations

import copy
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from hive_mind_os.local_run_authority import (
    LocalAuthorityError,
    LocalAuthorityStore,
    read_json,
    write_new_json,
)
from hive_mind_os.runtime_contracts import raw_sha256


class LocalRunAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repository = self.root / "FOO BAR"
        self.repository.mkdir()
        self.state = self.root / "run state"
        self.trust = self.root / "operator host"
        self.operator = patch(
            "hive_mind_os.local_run_authority.local_operator",
            return_value="test-host:requesting-operator",
        )
        self.operator.start()
        self.addCleanup(self.operator.stop)
        self.now = datetime(2026, 9, 8, 22, 0, tzinfo=UTC)
        self.plan_digest = raw_sha256(b"exact tournament plan")
        self.host_digest = raw_sha256(b"installed host executable")
        self.request = b"Execute this local tournament and preserve its evidence.\n"
        self.store = LocalAuthorityStore(self.trust, create=True)
        self.grant = self.issue()

    def issue(self, **overrides):
        arguments = {
            "plan_digest": self.plan_digest,
            "repository": self.repository,
            "commit": "a" * 40,
            "tree": "b" * 40,
            "state_directory": self.state,
            "operator_request": self.request,
            "host_digest": self.host_digest,
            "duration_seconds": 600,
            "now": self.now,
        }
        arguments.update(overrides)
        return self.store.issue(**arguments)

    def verify(self, grant=None, *, store=None, **overrides):
        arguments = {
            "plan_digest": self.plan_digest,
            "repository": self.repository,
            "state_directory": self.state,
            "host_digest": self.host_digest,
            "operator_request": self.request,
            "now": self.now,
        }
        arguments.update(overrides)
        return (store or self.store).verify(grant or self.grant, **arguments)

    def test_exact_retry_survives_store_restart_without_second_reservation(self) -> None:
        verified = self.verify()
        self.assertEqual(self.grant["document"], verified)
        reopened = LocalAuthorityStore(self.trust)
        self.assertEqual(verified, self.verify(store=reopened))
        with closing(sqlite3.connect(self.trust / "reservations.sqlite3")) as connection:
            rows = connection.execute("SELECT nonce FROM local_grants").fetchall()
        self.assertEqual([(verified["nonce"],)], rows)
        self.assertEqual("local-operator", verified["authentication_scope"])
        self.assertIs(False, verified["external_effects"])
        self.assertIs(False, verified["protected_merge_authorized"])

    def test_changed_signed_fields_fail_authentication_before_reservation(self) -> None:
        changes = {
            "plan_digest": raw_sha256(b"different plan"),
            "commit": "c" * 40,
            "tree": "d" * 40,
            "nonce": "e" * 64,
            "operator": "another-host:operator",
            "expires_at": (self.now + timedelta(days=2)).isoformat(),
            "external_effects": True,
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                changed = copy.deepcopy(self.grant)
                changed["document"][field] = value
                with self.assertRaisesRegex(LocalAuthorityError, "authentication failed"):
                    self.verify(changed)
        self.assertFalse((self.trust / "reservations.sqlite3").exists())

    def test_wrong_hmac_and_another_operators_key_are_rejected(self) -> None:
        changed = copy.deepcopy(self.grant)
        original = changed["hmac_sha256"]
        changed["hmac_sha256"] = ("0" if original[0] != "0" else "1") + original[1:]
        with self.assertRaisesRegex(LocalAuthorityError, "authentication failed"):
            self.verify(changed)
        other_store = LocalAuthorityStore(self.root / "other operator host", create=True)
        with self.assertRaisesRegex(LocalAuthorityError, "authentication failed"):
            self.verify(store=other_store)
        self.assertFalse((other_store.directory / "reservations.sqlite3").exists())

    def test_changed_run_arguments_do_not_consume_nonce(self) -> None:
        changes = {
            "plan_digest": raw_sha256(b"different plan"),
            "repository": self.root / "ANOTHER REPOSITORY",
            "state_directory": self.root / "another run",
            "host_digest": raw_sha256(b"different host executable"),
            "operator_request": self.request + b"Additional scope.",
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                with self.assertRaisesRegex(LocalAuthorityError, "binding differs"):
                    self.verify(**{field: value})
        self.assertFalse((self.trust / "reservations.sqlite3").exists())
        self.verify()

    def test_another_local_operator_cannot_reuse_a_valid_grant(self) -> None:
        with patch(
            "hive_mind_os.local_run_authority.local_operator",
            return_value="test-host:another-operator",
        ):
            with self.assertRaisesRegex(LocalAuthorityError, "binding differs"):
                self.verify()
        self.assertFalse((self.trust / "reservations.sqlite3").exists())

    def test_validity_includes_issuance_and_excludes_expiry(self) -> None:
        with self.assertRaisesRegex(LocalAuthorityError, "not currently valid"):
            self.verify(now=self.now - timedelta(microseconds=1))
        self.assertFalse((self.trust / "reservations.sqlite3").exists())
        self.verify(now=self.now)
        self.verify(now=self.now + timedelta(seconds=600, microseconds=-1))
        for elapsed in (600, 601):
            with self.subTest(elapsed=elapsed):
                with self.assertRaisesRegex(LocalAuthorityError, "not currently valid"):
                    self.verify(now=self.now + timedelta(seconds=elapsed))

    def test_resigned_same_nonce_cannot_be_transplanted_to_another_run(self) -> None:
        self.verify()
        destination = self.root / "another run"
        document = copy.deepcopy(self.grant["document"])
        document["state_directory"] = str(destination.resolve())
        transplanted = self.store.seal(document)
        with self.assertRaisesRegex(LocalAuthorityError, "nonce was already reserved"):
            self.verify(transplanted, state_directory=destination)
        self.assertEqual(self.grant["document"], self.verify())

    def test_reserved_nonce_cannot_authorize_resigned_commit_or_scope_changes(self) -> None:
        self.verify()
        for field, value in (("commit", "c" * 40), ("tree", "d" * 40)):
            with self.subTest(field=field):
                document = copy.deepcopy(self.grant["document"])
                document[field] = value
                with self.assertRaisesRegex(LocalAuthorityError, "nonce was already reserved"):
                    self.verify(self.store.seal(document))
        for field, value in (
            ("external_effects", True),
            ("protected_merge_authorized", True),
            ("allowed_actions", ["inspect", "push"]),
            ("authentication_scope", "independent-external-issuer"),
        ):
            with self.subTest(field=field):
                document = copy.deepcopy(self.grant["document"])
                document[field] = value
                with self.assertRaisesRegex(LocalAuthorityError, "binding differs"):
                    self.verify(self.store.seal(document))

    def test_issue_requires_explicit_directive_and_bounded_duration(self) -> None:
        for directive in (b"", b" \n\t"):
            with self.subTest(directive=directive):
                with self.assertRaisesRegex(LocalAuthorityError, "explicit operator directive"):
                    self.issue(operator_request=directive)
        for duration in (59, 86_401):
            with self.subTest(duration=duration):
                with self.assertRaisesRegex(LocalAuthorityError, "between 60 seconds and one day"):
                    self.issue(duration_seconds=duration)

    def test_issue_rejects_key_or_run_state_inside_subject(self) -> None:
        for directory in (self.repository, self.repository / "generated state"):
            with self.subTest(directory=directory):
                with self.assertRaisesRegex(LocalAuthorityError, "outside the subject repository"):
                    self.issue(state_directory=directory)
        inside = LocalAuthorityStore(self.repository / "host key", create=True)
        with self.assertRaisesRegex(LocalAuthorityError, "outside the subject repository"):
            inside.issue(
                plan_digest=self.plan_digest,
                repository=self.repository,
                commit="a" * 40,
                tree="b" * 40,
                state_directory=self.state,
                operator_request=self.request,
                host_digest=self.host_digest,
                now=self.now,
            )

    def test_issue_rejects_run_state_containing_key_custody(self) -> None:
        for state in (self.trust, self.root):
            with self.subTest(state=state):
                with self.assertRaisesRegex(LocalAuthorityError, "outside run state"):
                    self.issue(state_directory=state)

    def test_verification_rechecks_key_custody_after_external_grant_is_issued(self) -> None:
        for destination in (self.repository / "copied host", self.state / "copied host"):
            with self.subTest(destination=destination):
                destination.mkdir(parents=True)
                (destination / "local-host.key").write_bytes(
                    (self.trust / "local-host.key").read_bytes()
                )
                transplanted_store = LocalAuthorityStore(destination)
                with self.assertRaisesRegex(LocalAuthorityError, "outside"):
                    self.verify(store=transplanted_store)
                self.assertFalse((destination / "reservations.sqlite3").exists())

    def test_missing_or_malformed_key_does_not_initialize_a_host(self) -> None:
        absent = self.root / "absent host"
        with self.assertRaisesRegex(LocalAuthorityError, "absent"):
            LocalAuthorityStore(absent)
        self.assertFalse(absent.exists())
        malformed = self.root / "malformed host"
        malformed.mkdir()
        (malformed / "local-host.key").write_bytes(b"invalid")
        with self.assertRaisesRegex(LocalAuthorityError, "malformed"):
            LocalAuthorityStore(malformed)

    def test_signed_record_json_roundtrip_never_overwrites_prior_grant(self) -> None:
        grant_path = self.root / "grant.json"
        write_new_json(grant_path, self.grant)
        self.assertEqual(self.grant, read_json(grant_path))
        before = grant_path.read_bytes()
        with self.assertRaises(FileExistsError):
            write_new_json(grant_path, self.issue())
        self.assertEqual(before, grant_path.read_bytes())
        with self.assertRaisesRegex(LocalAuthorityError, "invalid shape"):
            self.store.unseal({"document": self.grant["document"]})


if __name__ == "__main__":
    unittest.main()
