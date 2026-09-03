from __future__ import annotations

import unittest
from dataclasses import replace
from hashlib import sha256

from hive_mind_os.resource_adapter import (
    ConservativeResourceAdapter,
    ResourceAdapterError,
    ResourceDescriptor,
    ResourceKind,
    ResourceSnapshot,
)


def _resource(
    *,
    kind: ResourceKind = ResourceKind.REPOSITORY_PATH,
    locator: str = "src/app.py",
    mutable: bool = False,
    version: str | None = None,
) -> ResourceDescriptor:
    return ResourceDescriptor(
        "subject-one",
        "resource-one",
        kind,
        locator,
        "text/plain",
        mutable,
        version,
        ("source:one",),
    )


class ResourceAdapterTests(unittest.TestCase):
    def test_repository_path_is_one_of_many_typed_resources(self) -> None:
        observed = {kind: _resource(kind=kind) for kind in ResourceKind}
        self.assertEqual(set(ResourceKind), set(observed))
        self.assertNotEqual(
            observed[ResourceKind.REPOSITORY_PATH].identity_digest,
            observed[ResourceKind.DATASET].identity_digest,
        )

    def test_observation_retains_digest_metadata_but_not_source_body(self) -> None:
        body = b"print('safe')\n"
        snapshot = ConservativeResourceAdapter().observe(
            _resource(),
            body,
            observed_at="2026-09-02T00:00:00Z",
            evidence_refs=("receipt:read",),
        )
        self.assertEqual("sha256:" + sha256(body).hexdigest(), snapshot.content_digest)
        self.assertEqual(len(body), snapshot.byte_length)
        self.assertFalse(hasattr(snapshot, "body"))

    def test_secret_and_oversized_content_fail_closed(self) -> None:
        adapter = ConservativeResourceAdapter(max_bytes=32)
        with self.assertRaises(ResourceAdapterError):
            adapter.observe(
                _resource(),
                b"api_key=abcdefghijklmnopqrstuvwxyz",
                observed_at="2026-09-02T00:00:00Z",
                evidence_refs=("receipt:read",),
            )
        with self.assertRaises(ResourceAdapterError):
            adapter.observe(
                _resource(),
                b"x" * 33,
                observed_at="2026-09-02T00:00:00Z",
                evidence_refs=("receipt:read",),
            )

    def test_unsafe_links_and_unversioned_mutable_resources_are_rejected(self) -> None:
        for locator in (
            "http://example.test/a",
            "../outside",
            "file:///secret",
            ".env?x",
            "dir/id_rsa#x",
            "src/app.py?download=1",
            "src/app.py#fragment",
        ):
            with self.subTest(locator=locator), self.assertRaises(ResourceAdapterError):
                _resource(locator=locator)
        with self.assertRaises(ResourceAdapterError):
            _resource(kind=ResourceKind.API, locator="https://example.test/api", mutable=True)
        resource = _resource(
            kind=ResourceKind.API,
            locator="https://example.test/api",
            mutable=True,
            version="etag:123",
        )
        self.assertEqual("etag:123", resource.version)

        for mutable in (0, 1, "", []):
            with self.subTest(mutable=mutable):
                with self.assertRaisesRegex(ResourceAdapterError, "strict boolean"):
                    _resource(mutable=mutable)  # type: ignore[arg-type]

    def test_snapshot_time_and_binary_flag_are_canonical(self) -> None:
        adapter = ConservativeResourceAdapter()
        for observed_at in (
            "not-a-time",
            "2026-09-02",
            "2026-09-02 00:00:00Z",
            "2026-09-02T00:00:00+00:00",
            "2026-02-30T00:00:00Z",
            "2026-09-02T00:00:00.1234567Z",
        ):
            with self.subTest(observed_at=observed_at):
                with self.assertRaisesRegex(ResourceAdapterError, "UTC RFC 3339"):
                    adapter.observe(
                        _resource(),
                        b"safe",
                        observed_at=observed_at,
                        evidence_refs=("receipt:read",),
                    )
        valid = adapter.observe(
            _resource(),
            b"safe",
            observed_at="2026-09-02T00:00:00.1Z",
            evidence_refs=("receipt:read",),
        )
        for binary in (0, 1, [], ""):
            with self.subTest(binary=binary):
                with self.assertRaisesRegex(ResourceAdapterError, "strict boolean"):
                    replace(valid, binary=binary)  # type: ignore[arg-type]

        with self.assertRaisesRegex(ResourceAdapterError, "strict boolean"):
            ResourceSnapshot(
                _resource(),
                "sha256:" + "0" * 64,
                0,
                "2026-09-02T00:00:00Z",
                ("receipt:read",),
                binary=None,  # type: ignore[arg-type]
            )

    def test_identity_collections_reject_mutable_lists(self) -> None:
        with self.assertRaisesRegex(ResourceAdapterError, "immutable tuple"):
            ResourceDescriptor(
                "subject-one",
                "resource-one",
                ResourceKind.ARTIFACT,
                "artifact.bin",
                "application/octet-stream",
                False,
                None,
                ["source:one"],  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(ResourceAdapterError, "immutable tuple"):
            ResourceSnapshot(
                _resource(),
                "sha256:" + "0" * 64,
                0,
                "2026-09-02T00:00:00Z",
                ["receipt:read"],  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
