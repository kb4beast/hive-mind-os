from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from fixture_support import copy_autopilot_fixture

BIN = Path(__file__).resolve().parents[1] / "bin"
if str(BIN) not in sys.path:
    sys.path.insert(0, str(BIN))

import autopilot  # noqa: E402
import post_expiry_completion as post_expiry  # noqa: E402
from durable_controller import ClaimError, digest_json  # noqa: E402


class Optimizer370PostExpiryCompletionTests(unittest.TestCase):
    AUTHORITY_DIGEST = "sha256:9302862efd2da6d59e7eff8c2f830fb0172acf53736a932c08662297993befb2"
    SCHEMA_DIGEST = "sha256:df1cf230da72e6b4e924ed8c90f70324cc886578f7d1f578e51c2e02a11e18ac"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        source = Path(__file__).resolve().parents[1]
        copy_autopilot_fixture(source, self.root / ".autopilot")
        for relative in (
            "optimizer-370-post-expiry-authority.json",
            "optimizer-370-post-expiry-authority.schema.json",
            "optimizer-370-post-expiry-intended-receipt.json",
        ):
            shutil.copy2(source / relative, self.root / ".autopilot" / relative)
        control = self.root / ".autopilot" / "control-plane.json"
        value = json.loads(control.read_text(encoding="utf-8"))
        value["verify_git_objects"] = False
        control.write_text(json.dumps(value), encoding="utf-8")
        self.now = datetime(2026, 8, 11, 22, 10, tzinfo=UTC)
        self.plane = autopilot.ControlPlane(self.root, clock=lambda: self.now)
        self.common = self.root / "common"
        self.common.mkdir()
        self.plane._post_expiry_common_dir = lambda: self.common  # type: ignore[method-assign]
        self.plane._fsync_directory = lambda _path: None  # type: ignore[method-assign]
        self.old_constants = (
            post_expiry.AUTHORITY_DIGEST,
            post_expiry.AUTHORITY_SCHEMA_DIGEST,
            post_expiry.SEALED_CAPABILITY_COMMIT,
        )
        post_expiry.AUTHORITY_DIGEST = self.AUTHORITY_DIGEST
        post_expiry.AUTHORITY_SCHEMA_DIGEST = self.SCHEMA_DIGEST
        post_expiry.SEALED_CAPABILITY_COMMIT = post_expiry.ZERO_CAPABILITY

    def tearDown(self) -> None:
        (
            post_expiry.AUTHORITY_DIGEST,
            post_expiry.AUTHORITY_SCHEMA_DIGEST,
            post_expiry.SEALED_CAPABILITY_COMMIT,
        ) = self.old_constants
        self.temporary.cleanup()

    @property
    def authority_path(self) -> Path:
        return self.root / ".autopilot" / "optimizer-370-post-expiry-authority.json"

    @contextmanager
    def sealed_capability(self):
        authority = json.loads(self.authority_path.read_text(encoding="utf-8"))
        authority["capability_commit"] = "f" * 40
        self.authority_path.write_text(json.dumps(authority), encoding="utf-8")
        with mock.patch.multiple(
            post_expiry,
            AUTHORITY_DIGEST=digest_json(authority),
            SEALED_CAPABILITY_COMMIT="f" * 40,
        ):
            yield

    def test_static_documents_validate(self) -> None:
        self.assertEqual(self.plane.post_expiry_static_issues(), ())
        self.assertTrue(self.plane.validate_post_expiry_completion()["valid"])

    def test_every_top_level_authority_field_is_sealed(self) -> None:
        original_bytes = self.authority_path.read_bytes()
        original = json.loads(original_bytes)
        for key in original:
            with self.subTest(key=key):
                changed = copy.deepcopy(original)
                value = changed[key]
                if isinstance(value, dict):
                    value["foreign"] = True
                elif isinstance(value, list):
                    value.append("foreign")
                elif isinstance(value, bool):
                    changed[key] = not value
                elif isinstance(value, int):
                    changed[key] = value + 1
                else:
                    changed[key] = str(value) + "-foreign"
                self.authority_path.write_text(json.dumps(changed), encoding="utf-8")
                self.assertIn("post-expiry authority material was altered", self.plane.post_expiry_static_issues())
                self.authority_path.write_bytes(original_bytes)

    def test_intended_receipt_mutation_fails(self) -> None:
        path = self.root / ".autopilot" / "optimizer-370-post-expiry-intended-receipt.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["pr"] = 999
        path.write_text(json.dumps(value), encoding="utf-8")
        self.assertIn("post-expiry intended receipt was altered", self.plane.post_expiry_static_issues())

    def test_prepare_rejects_zero_capability(self) -> None:
        with self.assertRaisesRegex(ClaimError, "not yet sealed"):
            self.plane.prepare_post_expiry_completion(actor="codex:builder-379")
        self.assertFalse(self.plane._state_path("AUTHORIZED").exists())

    def test_sealed_prepare_is_canonical_o_excl_and_one_time(self) -> None:
        with self.sealed_capability():
            record = self.plane.prepare_post_expiry_completion(actor="codex:builder-379")
            path = self.plane._state_path("AUTHORIZED")
            self.assertEqual(path.read_bytes(), post_expiry._canonical_file_bytes(record))
            self.assertEqual(record["predecessor_digest"], post_expiry.AUTHORITY_DIGEST)
            with self.assertRaisesRegex(ClaimError, "one-time"):
                self.plane.prepare_post_expiry_completion(actor="codex:builder-379")

    def test_expiry_boundary_is_reported_without_transition(self) -> None:
        with self.sealed_capability():
            record = self.plane.prepare_post_expiry_completion(
                actor="codex:builder-379", lease_minutes=1
            )
            self.now += timedelta(minutes=1)
            status = self.plane.post_expiry_completion_status()
            self.assertEqual(status["state"], "AUTHORIZED")
            self.assertEqual(status["expired"], True)
            self.assertEqual(record["expires_at"], "2026-08-11T22:11:00Z")

    def test_lease_bounds_fail_before_any_state_write(self) -> None:
        with self.sealed_capability():
            for minutes in (0, 11):
                with self.subTest(minutes=minutes), self.assertRaisesRegex(ClaimError, "bounded maximum"):
                    self.plane.prepare_post_expiry_completion(
                        actor="codex:builder-379", lease_minutes=minutes
                    )
        self.assertFalse(self.plane._state_path("AUTHORIZED").exists())

    def test_no_activation_or_publication_surface_exists(self) -> None:
        for name in (
            "activate_post_expiry_completion",
            "publish_post_expiry_receipt",
            "integrate_post_expiry_release",
        ):
            self.assertFalse(hasattr(self.plane, name))
        action = autopilot.parser()._subparsers._group_actions[0]
        choices = set(action.choices)
        self.assertIn("optimizer-370-post-expiry-prepare", choices)
        self.assertFalse(any("post-expiry-activate" in item or "post-expiry-publish" in item for item in choices))


if __name__ == "__main__":
    unittest.main()
