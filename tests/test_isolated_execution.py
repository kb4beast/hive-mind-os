import unittest
from tempfile import TemporaryDirectory

from hive_mind_os.isolated_execution import (
    IsolationAttestation,
    IsolationError,
    IsolationRegistry,
    ProbeResult,
    UnavailableIsolationBackend,
    require_attested,
)

D = "sha256:" + "a" * 64


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
        require_attested(self.attestation())
        with self.assertRaises(IsolationError):
            require_attested(
                self.attestation(probe_result=ProbeResult.UNAVAILABLE, image_digest=None)
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


if __name__ == "__main__":
    unittest.main()
