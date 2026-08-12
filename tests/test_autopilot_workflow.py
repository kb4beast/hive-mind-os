from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import new as hmac_new
from pathlib import Path
from unittest.mock import patch

from hive_mind_os.autopilot_workflow import (
    GENERIC_PROMPT_SOURCE,
    PortableAutopilotError,
    initialize_repository,
    inspect_repository,
    simple_prompt,
    trust_controller,
)


class PortableAutopilotWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.host_state = self.root.parent / f"{self.root.name}-host-state"
        self.environment = patch.dict(
            os.environ,
            {"XDG_STATE_HOME": str(self.host_state)},
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(lambda: __import__("shutil").rmtree(self.host_state, ignore_errors=True))
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# Other Repository\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://example.invalid/acme/widgets.git"],
            cwd=self.root,
            check=True,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _canonical_bytes(value: object) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    def _issue_controller_authorization(
        self,
        contract: dict[str, object],
        *,
        actor: str = "host:trust-pinner",
        issuer: str = "host:authority",
        reviewer: str = "curator:independent-fixture",
        evidence_inside_repository: bool = False,
    ) -> tuple[Path, Path, Path]:
        authority_root = self.host_state / "hive-mind-os" / "controller-trust-authority"
        trust_root = self.root.parent / f"{self.root.name}-trust"
        authority_root.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            authority_root.chmod(0o700)
        self.addCleanup(lambda: __import__("shutil").rmtree(trust_root, ignore_errors=True))
        key = b"fixture-host-owned-controller-trust-key-0123456789"
        key_path = authority_root / "controller-trust-authority.key"
        key_path.write_bytes(key)
        if os.name != "nt":
            key_path.chmod(0o600)
        if evidence_inside_repository:
            evidence = self.root / "review-evidence.json"
            evidence_uri = str(evidence)
        else:
            evidence = authority_root / "review-evidence.json"
            evidence_uri = evidence.name
        evidence.write_text('{"verdict":"safe","executed":false}\n', encoding="utf-8")
        now = datetime.now(UTC)
        authorization = {
            "grant": "PIN_CONTROLLER_TRUST",
            "repository_id": contract["repository_id"],
            "controller_source_commit": contract["controller_source_commit"],
            "controller_bundle_digest": contract["controller_bundle_digest"],
            "authorized_actor": actor,
            "issuer": issuer,
            "independent_reviewer": reviewer,
            "evidence": {
                "uri": evidence_uri,
                "sha256": "sha256:" + sha256(evidence.read_bytes()).hexdigest(),
            },
            "issued_at": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        }
        signed_material = {
            "schema_version": 1,
            "kind": "hive-mind-controller-trust-authorization-v1",
            "key_id": "sha256:" + sha256(key).hexdigest(),
            "authorization": authorization,
        }
        capability: dict[str, object] = {
            **signed_material,
            "signature": "sha256:"
            + hmac_new(key, self._canonical_bytes(signed_material), "sha256").hexdigest(),
        }
        capability["capability_id"] = "sha256:" + sha256(
            self._canonical_bytes(capability)
        ).hexdigest()
        capability_path = authority_root / "controller-trust-capability.json"
        capability_path.write_text(json.dumps(capability), encoding="utf-8")
        return authority_root, trust_root, capability_path

    def test_initialize_and_inspect_uninstalled_repository(self) -> None:
        result = initialize_repository(
            self.root,
            objective="Build a portable widget service",
            target_branch="release/widgets",
        )
        self.assertEqual(result["status"], "initialized")
        request = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(request["target_branch"], "release/widgets")
        self.assertEqual(request["source"]["sha256"], GENERIC_PROMPT_SOURCE["sha256"])
        self.assertEqual(request["source"]["license"], "unresolved-no-repository-license-declared")
        contract = inspect_repository(self.root, request="Take it from here")
        self.assertEqual(contract["intent"]["intent"], "BUILD_DAG")
        self.assertEqual(contract["tasks"][0]["transport"], "durable_user_owned_task")
        self.assertRegex(
            contract["tasks"][0]["title"],
            r"^Hive Mind DAG-BUILD-[0-9a-f]{12} \[[0-9a-f]{12}\]$",
        )
        self.assertNotIn("kb4beast/hive-mind-os", contract["tasks"][0]["prompt"])

    def test_initialize_fails_closed_instead_of_overwriting_request(self) -> None:
        first = initialize_repository(self.root, objective="First")
        repeated = initialize_repository(self.root, objective="First")
        self.assertEqual(first["request"]["request_id"], repeated["request"]["request_id"])
        self.assertEqual(repeated["status"], "already-initialized")
        (self.root / "README.md").write_text("# Changed\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "change"], cwd=self.root, check=True, capture_output=True)
        self.assertEqual(
            initialize_repository(self.root, objective="First")["status"],
            "already-initialized",
        )
        with self.assertRaises(PortableAutopilotError):
            initialize_repository(self.root, objective="Second")

    def test_protected_or_invalid_target_branch_is_rejected(self) -> None:
        with self.assertRaises(PortableAutopilotError):
            initialize_repository(self.root, target_branch="main")
        with self.assertRaises(PortableAutopilotError):
            initialize_repository(self.root, target_branch="Main")
        with self.assertRaises(PortableAutopilotError):
            initialize_repository(self.root, target_branch="REFS/HEADS/release/test")
        with self.assertRaises(PortableAutopilotError):
            initialize_repository(self.root, target_branch="bad branch")
        with self.assertRaises(PortableAutopilotError):
            initialize_repository(
                self.root,
                target_branch="production",
                protected_branches=("production",),
            )

    def test_remote_credentials_are_not_persisted(self) -> None:
        subprocess.run(["git", "remote", "remove", "origin"], cwd=self.root, check=True)
        subprocess.run(
            [
                "git",
                "remote",
                "add",
                "origin",
                "https://secret@example.invalid/acme/widgets.git?token=also-secret#private",
            ],
            cwd=self.root,
            check=True,
        )
        result = initialize_repository(self.root)
        request = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(
            request["repository_remote"],
            "https://example.invalid/acme/widgets.git",
        )
        self.assertNotIn("secret", json.dumps(request))

    def test_secret_like_operator_text_is_rejected_before_persistence(self) -> None:
        with self.assertRaises(PortableAutopilotError):
            initialize_repository(self.root, objective="Use api_key=sk-example-secret-123456")
        initialize_repository(self.root)
        with self.assertRaises(PortableAutopilotError):
            inspect_repository(self.root, request="continue with Bearer abcdefghijklmnop")

    def test_ssh_user_info_and_missing_origin_are_safe(self) -> None:
        subprocess.run(["git", "remote", "remove", "origin"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "ssh://secret@example.invalid/acme/widgets.git"],
            cwd=self.root,
            check=True,
        )
        result = initialize_repository(self.root)
        self.assertEqual(result["request"]["repository_remote"], "ssh://example.invalid/acme/widgets.git")
        self.temporary.cleanup()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Fixture"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# Local\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=self.root, check=True, capture_output=True)
        local = initialize_repository(self.root)
        self.assertIsNone(local["request"]["repository_remote"])

    def test_check_only_does_not_bootstrap_uninstalled_repository(self) -> None:
        initialize_repository(self.root)
        contract = inspect_repository(self.root, request="Check only; do not build or start anything")
        self.assertEqual(contract["intent"]["intent"], "CHECK")
        self.assertEqual(contract["tasks"], [])
        self.assertTrue(contract["bootstrap_required"])

    def test_explanation_language_does_not_bootstrap(self) -> None:
        initialize_repository(self.root)
        contract = inspect_repository(self.root, request="Explain how to finish the DAG")
        self.assertEqual(contract["intent"]["intent"], "CHECK")
        self.assertEqual(contract["tasks"], [])

    def test_review_and_how_question_language_does_not_bootstrap(self) -> None:
        initialize_repository(self.root)
        for request in ("How can I finish the DAG?", "Review how to start the next level"):
            with self.subTest(request=request):
                contract = inspect_repository(self.root, request=request)
                self.assertEqual(contract["intent"]["intent"], "CHECK")
                self.assertEqual(contract["tasks"], [])

    def test_persisted_request_cannot_redeclare_target_as_protected(self) -> None:
        result = initialize_repository(self.root, target_branch="release/widgets")
        path = Path(result["path"])
        request = json.loads(path.read_text(encoding="utf-8"))
        request["protected_branches"].append("release/*")
        material = dict(request)
        material.pop("request_id")
        request["request_id"] = "sha256:" + sha256(
            json.dumps(
                material,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        path.write_text(json.dumps(request), encoding="utf-8")
        with self.assertRaises(PortableAutopilotError):
            inspect_repository(self.root, request="continue")

    def test_repository_state_symlink_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as outside_name:
            managed = self.root / ".hive-mind"
            try:
                os.symlink(outside_name, managed, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")
            with self.assertRaises(PortableAutopilotError):
                initialize_repository(self.root)

    def test_simple_prompt_is_repository_neutral(self) -> None:
        prompt = simple_prompt()
        self.assertIn("build, start, continue, check, or finish", prompt)
        self.assertNotIn("kb4beast", prompt)

    def test_inspect_never_executes_target_repository_controller(self) -> None:
        controller = self.root / ".autopilot" / "bin" / "autopilot.py"
        controller.parent.mkdir(parents=True)
        escaped = self.root.parent / f"{self.root.name}-controller-escaped.txt"
        controller.write_text(
            "from pathlib import Path\n"
            f"Path({str(escaped)!r}).write_text('executed')\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "-f", ".autopilot/bin/autopilot.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "controller"], cwd=self.root, check=True, capture_output=True)
        contract = inspect_repository(self.root, request="check")
        self.assertEqual(contract["kind"], "hive-mind-portable-controller-review-required-v1")
        self.assertFalse(escaped.exists())
        (self.root / "README.md").write_text("# Product-only change\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "product"], cwd=self.root, check=True, capture_output=True)
        self.assertEqual(
            inspect_repository(self.root, request="check")["outcome"],
            "CONTROLLER_REVIEW_REQUIRED",
        )
        controller.write_text(controller.read_text(encoding="utf-8") + "# dirty\n", encoding="utf-8")
        with self.assertRaises(PortableAutopilotError):
            inspect_repository(self.root, request="check")

    def test_installed_controller_contract_requires_host_sandbox(self) -> None:
        controller = self.root / ".autopilot" / "bin" / "autopilot.py"
        controller.parent.mkdir(parents=True)
        controller.write_text("print('{}')\n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", ".autopilot/bin/autopilot.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "controller"], cwd=self.root, check=True, capture_output=True)
        review = inspect_repository(self.root, request="continue")
        _authority_root, trust_root, capability_path = self._issue_controller_authorization(
            dict(review)
        )
        trust_controller(
            self.root,
            actor="host:trust-pinner",
            authorization_capability=capability_path,
            trust_state_root=trust_root,
        )
        contract = inspect_repository(self.root, request="check")
        self.assertEqual(contract["outcome"], "CONTROLLER_REVIEW_REQUIRED")
        contract = inspect_repository(
            self.root,
            request="check",
            trust_state_root=trust_root,
        )
        self.assertTrue(contract["invocation"]["deny_outside_repository_filesystem"])
        self.assertIn("git", contract["invocation"]["allow_descendant_processes"])

    def test_controller_trust_rejects_self_review_and_arbitrary_actor(self) -> None:
        controller = self.root / ".autopilot" / "bin" / "autopilot.py"
        controller.parent.mkdir(parents=True)
        controller.write_text("print('{}')\n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", ".autopilot/bin/autopilot.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "controller"], cwd=self.root, check=True, capture_output=True)
        review = inspect_repository(self.root, request="continue")
        _authority_root, trust_root, capability_path = self._issue_controller_authorization(
            dict(review),
            reviewer="host:trust-pinner",
        )
        with self.assertRaisesRegex(PortableAutopilotError, "distinct authorized actor"):
            trust_controller(
                self.root,
                actor="host:trust-pinner",
                authorization_capability=capability_path,
                trust_state_root=trust_root,
            )
        _authority_root, trust_root, capability_path = self._issue_controller_authorization(
            dict(review),
            actor="host:authorized-pinner",
        )
        with self.assertRaisesRegex(PortableAutopilotError, "does not authorize this actor"):
            trust_controller(
                self.root,
                actor="attacker:self-appointed",
                authorization_capability=capability_path,
                trust_state_root=trust_root,
            )

    def test_controller_trust_revalidates_resolvable_digest_bound_evidence(self) -> None:
        controller = self.root / ".autopilot" / "bin" / "autopilot.py"
        controller.parent.mkdir(parents=True)
        controller.write_text("print('{}')\n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", ".autopilot/bin/autopilot.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "controller"], cwd=self.root, check=True, capture_output=True)
        review = inspect_repository(self.root, request="continue")
        authority_root, trust_root, capability_path = self._issue_controller_authorization(
            dict(review)
        )
        trust_controller(
            self.root,
            actor="host:trust-pinner",
            authorization_capability=capability_path,
            trust_state_root=trust_root,
        )
        (authority_root / "review-evidence.json").write_text("tampered\n", encoding="utf-8")
        contract = inspect_repository(
            self.root,
            request="continue",
            trust_state_root=trust_root,
        )
        self.assertEqual(contract["outcome"], "CONTROLLER_REVIEW_REQUIRED")
        self.assertIn("evidence digest", contract["blocker"])

    def test_controller_trust_rejects_forgery_and_stale_bundle(self) -> None:
        controller = self.root / ".autopilot" / "bin" / "autopilot.py"
        controller.parent.mkdir(parents=True)
        controller.write_text("print('{}')\n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", ".autopilot/bin/autopilot.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "controller"], cwd=self.root, check=True, capture_output=True)
        review = inspect_repository(self.root, request="continue")
        _authority_root, trust_root, capability_path = self._issue_controller_authorization(
            dict(review)
        )
        forged = json.loads(capability_path.read_text(encoding="utf-8"))
        forged["authorization"]["independent_reviewer"] = "curator:forged"
        material = dict(forged)
        material.pop("capability_id")
        forged["capability_id"] = "sha256:" + sha256(
            self._canonical_bytes(material)
        ).hexdigest()
        capability_path.write_text(json.dumps(forged), encoding="utf-8")
        with self.assertRaisesRegex(PortableAutopilotError, "signature is invalid"):
            trust_controller(
                self.root,
                actor="host:trust-pinner",
                authorization_capability=capability_path,
                trust_state_root=trust_root,
            )
        _authority_root, trust_root, capability_path = self._issue_controller_authorization(
            dict(review)
        )
        trust_controller(
            self.root,
            actor="host:trust-pinner",
            authorization_capability=capability_path,
            trust_state_root=trust_root,
        )
        controller.write_text("print({'changed': True})\n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", ".autopilot/bin/autopilot.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "change controller"], cwd=self.root, check=True, capture_output=True)
        contract = inspect_repository(
            self.root,
            request="continue",
            trust_state_root=trust_root,
        )
        self.assertEqual(contract["outcome"], "CONTROLLER_REVIEW_REQUIRED")
        self.assertIn("missing or stale", contract["blocker"])

    def test_controller_trust_rejects_repository_owned_evidence(self) -> None:
        controller = self.root / ".autopilot" / "bin" / "autopilot.py"
        controller.parent.mkdir(parents=True)
        controller.write_text("print('{}')\n", encoding="utf-8")
        subprocess.run(["git", "add", "-f", ".autopilot/bin/autopilot.py"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "controller"], cwd=self.root, check=True, capture_output=True)
        review = inspect_repository(self.root, request="continue")
        _authority_root, trust_root, capability_path = self._issue_controller_authorization(
            dict(review),
            evidence_inside_repository=True,
        )
        with self.assertRaisesRegex(PortableAutopilotError, "escapes the host authorization root"):
            trust_controller(
                self.root,
                actor="host:trust-pinner",
                authorization_capability=capability_path,
                trust_state_root=trust_root,
            )


if __name__ == "__main__":
    unittest.main()
