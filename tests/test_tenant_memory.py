import unittest

from hive_mind_os.tenant_memory import (
    BoundaryError,
    BoundaryState,
    ScopedMemoryHandle,
    SubjectMemoryBoundary,
    SubjectNamespace,
)


class TenantMemoryTests(unittest.TestCase):
    def boundary(self, tenant):
        return SubjectMemoryBoundary(
            tenant,
            "same-name",
            f"private-{tenant}",
            f"cache-{tenant}",
            f"logs-{tenant}",
            "provider-policy",
            "managed-key-profile",
            "retention-policy",
            BoundaryState.ACTIVE,
        )

    def test_colliding_names_remain_subject_partitioned(self):
        first, second = self.boundary("a"), self.boundary("b")
        namespace = SubjectNamespace()
        namespace.put(first, "artifact", "private-a")
        handle = ScopedMemoryHandle(first.digest, "builder", "mission", ("private",))
        self.assertEqual(namespace.get(handle, first, "artifact"), "private-a")
        with self.assertRaises(BoundaryError):
            namespace.get(handle, second, "artifact")

    def test_revocation_immediately_removes_access(self):
        boundary = self.boundary("a")
        namespace = SubjectNamespace()
        namespace.put(boundary, "artifact", "private-a")
        handle = ScopedMemoryHandle(boundary.digest, "builder", "mission", ("private",))
        namespace.revoke(boundary)
        with self.assertRaises(BoundaryError):
            namespace.get(handle, boundary, "artifact")
        with self.assertRaises(BoundaryError):
            namespace.put(boundary, "other", "value")

    def test_legacy_data_is_never_inferred(self):
        with self.assertRaisesRegex(BoundaryError, "LEGACY_UNBOUND"):
            SubjectNamespace().migrate_legacy("repo-cache")


if __name__ == "__main__":
    unittest.main()
