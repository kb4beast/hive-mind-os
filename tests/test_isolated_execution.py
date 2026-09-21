import unittest
from datetime import datetime, timedelta, timezone
from tempfile import TemporaryDirectory
from typing import Any, cast
from unittest.mock import patch

from hive_mind_os.isolated_execution import (
    IsolationAttestation,
    IsolationError,
    IsolationRegistry,
    ProbeResult,
    UnavailableIsolationBackend,
    require_attested,
)

D = "sha256:" + "a" * 64
BEFORE_EXPIRY = datetime(2026, 9, 14, tzinfo=timezone.utc)


class IsolatedExecutionTests(unittest.TestCase):
    def attestation(self, **changes):
        values = {
            "backend_id": "oci.host",
            "backend_version": "1",
            "image_digest": D,
            "tenant_id": "tenant-a",
            "repository_id": "repo-a",
            "filesystem_scope": "target-only",
            "network_policy_digest": D,
            "credential_policy_digest": D,
            "writable_mounts": ("work", "out"),
            "resource_limits": {"cpu": 1, "memory_mb": 256},
            "probe_suite_digest": D,
            "probe_result": ProbeResult.ENFORCED,
            "expires_at": "2026-09-15T00:00:00Z",
        }
        values.update(changes)
        return IsolationAttestation(**values)

    def test_only_attested_backend_admits_untrusted_execution(self):
        require_attested(self.attestation(), now=BEFORE_EXPIRY)
        with self.assertRaises(IsolationError):
            require_attested(
                self.attestation(probe_result=ProbeResult.UNAVAILABLE, image_digest=None),
                now=BEFORE_EXPIRY
            )
        result = UnavailableIsolationBackend().execute([], attestation=self.attestation())
        self.assertEqual(result.error_code, "BLOCKED_ISOLATION")

    def test_registry_rejects_unpinned_enforced_backend(self):
        with TemporaryDirectory() as directory:
            registry = IsolationRegistry(f"{directory}/attestations.json")
            with self.assertRaises(IsolationError):
                registry.register(self.attestation(image_digest=None))
            registry.register(self.attestation())
            restored = registry.get("tenant-a", "repo-a", "oci.host")
            self.assertEqual(restored, self.attestation())

    def test_boolean_resource_limit_is_rejected(self):
        with self.assertRaises(IsolationError):
            self.attestation(resource_limits={"cpu": True})

    def test_malformed_expires_at_is_rejected(self):
        with self.assertRaises(IsolationError):
            self.attestation(expires_at="2026-09-15")
        with self.assertRaises(IsolationError):
            self.attestation(expires_at="not-a-date")

    def test_naive_expires_at_is_rejected(self):
        with self.assertRaises(IsolationError):
            self.attestation(expires_at="2026-09-15T00:00:00")

    def test_expires_at_with_offset_is_accepted(self):
        a = self.attestation(expires_at="2026-09-15T00:00:00+02:00")
        boundary = datetime(2026, 9, 14, 22, tzinfo=timezone.utc)
        require_attested(a, now=boundary - timedelta(microseconds=1))
        self.assertFalse(a.admits_untrusted(now=boundary))
        with self.assertRaises(IsolationError):
            require_attested(a, now=boundary)

    def test_expired_attestation_is_rejected(self):
        knownbeforeexpiry = datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
        expired = self.attestation(expires_at="2026-09-14T23:59:59Z")
        with self.assertRaises(IsolationError):
            require_attested(expired, now=knownbeforeexpiry)

    def test_expiry_equality_rejects_admission(self):
        expiry = datetime(2026, 9, 15, 12, 30, 0, tzinfo=timezone.utc)
        a = self.attestation(expires_at=expiry.isoformat())
        with self.assertRaises(IsolationError):
            require_attested(a, now=expiry)

    def test_valid_attestation_before_expiry_admits(self):
        knownbeforeexpiry = datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
        a = self.attestation(expires_at=(knownbeforeexpiry + timedelta(hours=1)).isoformat())
        require_attested(a, now=knownbeforeexpiry)

    def test_require_attested_with_naive_now_is_rejected(self):
        a = self.attestation()
        for invalid in (datetime(2026, 9, 15), "2026-09-14T00:00:00Z", True, 0):
            with self.subTest(invalid=invalid), self.assertRaises(IsolationError):
                require_attested(a, now=cast(Any, invalid))

    def test_same_object_is_rechecked_on_each_admission(self):
        a = self.attestation()
        original_digest = a.digest
        self.assertTrue(a.admits_untrusted(now=BEFORE_EXPIRY))
        require_attested(a, now=BEFORE_EXPIRY)
        self.assertFalse(a.admits_untrusted(now=BEFORE_EXPIRY + timedelta(days=1)))
        with self.assertRaises(IsolationError):
            require_attested(a, now=BEFORE_EXPIRY + timedelta(days=2))
        self.assertEqual(a.digest, original_digest)

    def test_default_clock_rechecks_expiry_without_rewriting_record(self):
        a = self.attestation()
        class Clock(datetime):
            observed = BEFORE_EXPIRY

            @classmethod
            def now(cls, tz=None):
                return cls.observed

        with patch("hive_mind_os.isolated_execution.datetime", Clock):
            Clock.observed = Clock(2026, 9, 14, tzinfo=timezone.utc)
            require_attested(a)
            self.assertTrue(a.admits_untrusted())
            Clock.observed = Clock(2026, 9, 15, tzinfo=timezone.utc)
            self.assertFalse(a.admits_untrusted())
            with self.assertRaises(IsolationError):
                require_attested(a)

    def test_unavailable_attestation_fails_closed(self):
        knownbeforeexpiry = datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc)
        unavailable = self.attestation(
            probe_result=ProbeResult.UNAVAILABLE,
            image_digest=None,
            expires_at="1970-01-01T00:00:00Z"
        )
        with self.assertRaises(IsolationError):
            require_attested(unavailable, now=knownbeforeexpiry)


if __name__ == "__main__":
    unittest.main()
