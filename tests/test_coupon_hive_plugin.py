import copy
import hashlib
import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path


class CouponHivePluginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Path(__file__).resolve().parents[1]
        self.plugin = self.repository / "plugins" / "coupon-hive"
        self.skill = self.plugin / "skills" / "coupon-hive"
        self.plan = self.repository / "docs" / "plan" / "coupon-hive-2026-09-14"
        self.legacy = self.repository / "custom-gpts" / "coupon-hive"

    @staticmethod
    def read_json(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def load_watch_validator(self):
        path = self.skill / "scripts" / "validate_watch_spec.py"
        spec = importlib.util.spec_from_file_location("coupon_hive_watch_validator", path)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_portable_and_codex_manifests_are_exact_mirrors(self) -> None:
        portable = self.plugin / "plugin.json"
        codex = self.plugin / ".codex-plugin" / "plugin.json"
        self.assertEqual(portable.read_bytes(), codex.read_bytes())

        manifest = self.read_json(portable)
        self.assertEqual(manifest["name"], "coupon-hive")
        self.assertEqual(manifest["version"], "0.1.0")
        self.assertEqual(manifest["skills"], "./skills/")
        interface = manifest["interface"]
        self.assertEqual(interface["displayName"], "Coupon Hive")
        self.assertEqual(interface["category"], "Shopping")
        self.assertEqual(len(interface["defaultPrompt"]), 3)
        self.assertNotIn("ultimate coupon", json.dumps(manifest).lower())
        self.assertNotIn("guaranteed savings", json.dumps(manifest).lower())

    def test_manifest_paths_and_png_assets_are_real_and_transparent(self) -> None:
        manifest = self.read_json(self.plugin / "plugin.json")
        for field in ("composerIcon", "logo"):
            path = self.plugin / manifest["interface"][field]
            self.assertTrue(path.is_file(), path)
            data = path.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            self.assertIn(data[25], (4, 6), "PNG must have an alpha channel")

        skill_icon = self.skill / "assets" / "icon.png"
        legacy_icon = self.legacy / "icon.png"
        self.assertEqual(skill_icon.read_bytes(), legacy_icon.read_bytes())
        self.assertEqual(skill_icon.read_bytes(), (self.plugin / "assets" / "icon.png").read_bytes())
        self.assertEqual(
            hashlib.sha256(skill_icon.read_bytes()).hexdigest(),
            "2058ba0f3ef134e39f8a749bbca2f7c9e101c86f839f18041495f001be421371",
        )
        provenance = (self.plan / "ASSET_PROVENANCE.md").read_text(encoding="utf-8")
        self.assertIn("OpenAI built-in image generation", provenance)
        self.assertIn("Reference images: none", provenance)

    def test_skill_is_complete_and_routes_progressive_references(self) -> None:
        skill_text = (self.skill / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill_text.startswith("---\n"))
        frontmatter = re.match(r"^---\n(.*?)\n---", skill_text, re.DOTALL)
        self.assertIsNotNone(frontmatter)
        assert frontmatter is not None
        self.assertIn("name: coupon-hive", frontmatter.group(1))
        self.assertIn("coupon", frontmatter.group(1).lower())
        self.assertNotIn("[TODO:", skill_text)
        self.assertNotIn("Local developer", skill_text)

        required_references = {
            "interview-contract.md",
            "offer-verification.md",
            "safety-privacy.md",
            "scheduled-task-template.md",
            "lifecycle-spec.schema.json",
            "watch-spec.schema.json",
        }
        reference_root = self.skill / "references"
        self.assertEqual(
            {path.name for path in reference_root.iterdir() if path.is_file()},
            required_references,
        )
        for name in required_references:
            self.assertIn(name, skill_text)

        agent_text = (self.skill / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("$coupon-hive", agent_text)
        self.assertIn("./assets/icon.png", agent_text)
        self.assertIn('#F2B705', agent_text)

    def test_watch_schema_is_version_bound_and_fail_closed(self) -> None:
        schema = self.read_json(
            self.skill / "references" / "watch-spec.schema.json"
        )
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        self.assertEqual(schema["properties"]["skill_version"]["const"], "0.1.0")
        self.assertEqual(
            set(schema["required"]),
            {
                "schema_version",
                "skill_version",
                "confirmation",
                "task_binding",
                "host_payload",
                "query",
                "scope",
                "economics",
                "accepted_offer_types",
                "conditions",
                "sources",
                "schedule",
                "notification",
                "status",
            },
        )
        for property_name in (
            "task_binding",
            "host_payload",
            "query",
            "scope",
            "economics",
            "conditions",
            "sources",
            "schedule",
            "notification",
        ):
            self.assertFalse(
                schema["properties"][property_name]["additionalProperties"],
                property_name,
            )
        self.assertEqual(
            schema["properties"]["notification"]["properties"][
                "silent_when_unchanged"
            ]["const"],
            True,
        )
        self.assertEqual(schema["properties"]["status"]["const"], "confirmed")
        self.assertEqual(
            schema["properties"]["confirmation"]["properties"][
                "confirmed_by_user"
            ]["const"],
            True,
        )
        self.assertIn(
            "approved_spec_digest",
            schema["properties"]["confirmation"]["required"],
        )
        self.assertEqual(
            schema["properties"]["confirmation"]["properties"][
                "approved_spec_digest"
            ]["pattern"],
            "^sha256:[0-9a-f]{64}$",
        )
        self.assertEqual(
            set(schema["properties"]["task_binding"]["properties"]["action"]["enum"]),
            {"create", "update"},
        )
        host_payload = schema["properties"]["host_payload"]["properties"]
        self.assertEqual(
            host_payload["prompt_template_id"]["const"],
            "coupon-hive-recurring-v1",
        )
        self.assertEqual(
            set(host_payload["requested_lifecycle_actions"]["items"]["enum"]),
            {"pause", "resume"},
        )
        self.assertEqual(
            host_payload["recurring_prompt_sha256"]["pattern"],
            "^sha256:[0-9a-f]{64}$",
        )
        self.assertEqual(
            schema["properties"]["sources"]["properties"]["access_policy"]["const"],
            "host_public_web_only",
        )
        schedule = schema["properties"]["schedule"]["properties"]
        self.assertNotIn("rrule", schedule)
        self.assertEqual(schedule["minute"]["type"], ["integer", "null"])
        self.assertEqual(
            set(schedule["frequency"]["enum"]),
            {"hourly", "daily", "weekly", "monthly"},
        )
        self.assertRegex("America/Argentina/Buenos_Aires", schedule["timezone"]["pattern"])
        self.assertNotRegex("CET", schedule["timezone"]["pattern"])

    def test_watch_spec_semantic_validator_accepts_fixture_and_rejects_loopholes(self) -> None:
        validator = self.load_watch_validator()
        fixture = self.read_json(
            self.repository / "tests" / "fixtures" / "coupon_hive" / "valid_watch_spec.json"
        )
        self.assertEqual(validator.validate_watch_spec(fixture), [])

        mutations = {}

        unconfirmed = copy.deepcopy(fixture)
        unconfirmed["confirmation"]["confirmed_by_user"] = False
        mutations["unconfirmed"] = unconfirmed

        fake_timezone = copy.deepcopy(fixture)
        fake_timezone["schedule"]["timezone"] = "Mars/Olympus"
        mutations["fake timezone"] = fake_timezone

        merchant_overlap = copy.deepcopy(fixture)
        merchant_overlap["sources"]["allowed_merchants"] = ["https://www.example.com"]
        merchant_overlap["sources"]["blocked_merchants"] = ["example.com"]
        mutations["merchant overlap"] = merchant_overlap

        unsupported_trial = copy.deepcopy(fixture)
        unsupported_trial["conditions"]["trial"] = True
        mutations["subscription scope"] = unsupported_trial

        false_free = copy.deepcopy(fixture)
        false_free["economics"]["free_definition"] = "free_now_only"
        false_free["accepted_offer_types"] = ["free_now"]
        false_free["conditions"]["membership"] = True
        mutations["conditional free"] = false_free

        missing_threshold = copy.deepcopy(fixture)
        missing_threshold["notification"]["events"].append(
            "price_threshold_crossed"
        )
        mutations["missing threshold"] = missing_threshold

        duplicate_create = copy.deepcopy(fixture)
        duplicate_create["task_binding"]["existing_task_id"] = "task-existing"
        mutations["create with existing id"] = duplicate_create

        bad_daily = copy.deepcopy(fixture)
        bad_daily["schedule"]["local_time"] = "99:99"
        mutations["bad daily schedule"] = bad_daily

        boolean_version = copy.deepcopy(fixture)
        boolean_version["schema_version"] = True
        mutations["boolean schema version"] = boolean_version

        for label, candidate in mutations.items():
            with self.subTest(label=label):
                candidate["confirmation"]["approved_spec_digest"] = (
                    validator.approval_digest(candidate)
                )
                self.assertTrue(validator.validate_watch_spec(candidate))

        tampered_after_confirmation = copy.deepcopy(fixture)
        tampered_after_confirmation["query"]["description"] = "luxury laptop"
        tampered_after_confirmation["schedule"]["frequency"] = "hourly"
        tampered_after_confirmation["schedule"]["local_time"] = None
        tampered_after_confirmation["schedule"]["minute"] = 15
        errors = validator.validate_watch_spec(tampered_after_confirmation)
        self.assertIn(
            "$.confirmation.approved_spec_digest does not match the scheduled settings",
            errors,
        )

        tampered_summary = copy.deepcopy(fixture)
        tampered_summary["confirmation"]["watch_card_summary"] = (
            "A different Watch Card that the user did not approve."
        )
        self.assertIn(
            "$.confirmation.approved_spec_digest does not match the scheduled settings",
            validator.validate_watch_spec(tampered_summary),
        )

        candidate = copy.deepcopy(fixture)
        candidate["confirmation"] = {
            "watch_card_summary": fixture["confirmation"]["watch_card_summary"]
        }
        candidate.pop("status")
        pre_confirmation_digest = validator.approval_digest(candidate)
        self.assertEqual(
            pre_confirmation_digest,
            fixture["confirmation"]["approved_spec_digest"],
        )
        confirmed_transition = copy.deepcopy(candidate)
        confirmed_transition["confirmation"].update(
            {
                "confirmed_by_user": True,
                "confirmed_at": "2026-09-14T15:00:00Z",
                "approved_spec_digest": pre_confirmation_digest,
            }
        )
        confirmed_transition["status"] = "confirmed"
        self.assertEqual(
            validator.approval_digest(confirmed_transition),
            pre_confirmation_digest,
        )
        self.assertEqual(validator.validate_watch_spec(confirmed_transition), [])

    def test_watch_validator_handles_hostile_types_lengths_and_numbers_fail_closed(self) -> None:
        validator = self.load_watch_validator()
        fixture = self.read_json(
            self.repository / "tests" / "fixtures" / "coupon_hive" / "valid_watch_spec.json"
        )

        malformed_arrays = {
            "offer types": ("accepted_offer_types", None),
            "query conditions": ("query", "condition"),
            "weekdays": ("schedule", "weekdays"),
            "events": ("notification", "events"),
        }
        for label, (parent, child) in malformed_arrays.items():
            candidate = copy.deepcopy(fixture)
            if child is None:
                candidate[parent] = [{}]
            else:
                candidate[parent][child] = [{}]
            with self.subTest(label=label):
                self.assertTrue(validator.validate_watch_spec(candidate))

        for label, parent, field in (
            ("task action", "task_binding", "action"),
            ("host surface", "host_payload", "host_surface"),
            ("category", "query", "category"),
            ("location precision", "scope", "location_precision"),
            ("free definition", "economics", "free_definition"),
            ("frequency", "schedule", "frequency"),
        ):
            candidate = copy.deepcopy(fixture)
            candidate[parent][field] = {}
            with self.subTest(hostile_scalar=label):
                self.assertTrue(validator.validate_watch_spec(candidate))

        for unsafe_title in (
            "Coupon Hive — drill watch ",
            "Coupon Hive — drill\u2028watch",
            "Coupon Hive — drill\u200bwatch",
        ):
            candidate = copy.deepcopy(fixture)
            candidate["host_payload"]["task_title"] = unsafe_title
            candidate["confirmation"]["approved_spec_digest"] = (
                validator.approval_digest(candidate)
            )
            with self.subTest(unsafe_host_title=repr(unsafe_title)):
                self.assertTrue(validator.validate_watch_spec(candidate))

        hostile_timezone = copy.deepcopy(fixture)
        hostile_timezone["schedule"]["timezone"] = "/etc/passwd"
        self.assertTrue(validator.validate_watch_spec(hostile_timezone))

        noncanonical_timezone = copy.deepcopy(fixture)
        noncanonical_timezone["schedule"]["timezone"] = "CET"
        noncanonical_timezone["confirmation"]["approved_spec_digest"] = (
            validator.approval_digest(noncanonical_timezone)
        )
        self.assertTrue(validator.validate_watch_spec(noncanonical_timezone))

        malformed_merchant = copy.deepcopy(fixture)
        malformed_merchant["sources"]["allowed_merchants"] = ["[::"]
        malformed_merchant["confirmation"]["approved_spec_digest"] = (
            validator.approval_digest(malformed_merchant)
        )
        self.assertTrue(validator.validate_watch_spec(malformed_merchant))

        contradictory_minute = copy.deepcopy(fixture)
        contradictory_minute["schedule"]["minute"] = 0
        contradictory_minute["confirmation"]["approved_spec_digest"] = (
            validator.approval_digest(contradictory_minute)
        )
        self.assertTrue(validator.validate_watch_spec(contradictory_minute))

        past_end = copy.deepcopy(fixture)
        past_end["schedule"]["ends_at"] = "2020-01-01T00:00:00Z"
        past_end["confirmation"]["approved_spec_digest"] = (
            validator.approval_digest(past_end)
        )
        self.assertTrue(validator.validate_watch_spec(past_end))

        equal_quiet_hours = copy.deepcopy(fixture)
        equal_quiet_hours["schedule"]["quiet_hours"] = {
            "start": "22:00",
            "end": "22:00",
        }
        equal_quiet_hours["confirmation"]["approved_spec_digest"] = (
            validator.approval_digest(equal_quiet_hours)
        )
        self.assertTrue(validator.validate_watch_spec(equal_quiet_hours))

        zero_improvement = copy.deepcopy(fixture)
        zero_improvement["notification"]["events"].append(
            "price_threshold_crossed"
        )
        zero_improvement["notification"]["minimum_price_improvement"] = 0
        zero_improvement["confirmation"]["approved_spec_digest"] = (
            validator.approval_digest(zero_improvement)
        )
        self.assertTrue(validator.validate_watch_spec(zero_improvement))

        huge_price = copy.deepcopy(fixture)
        huge_price["economics"]["maximum_effective_price"] = 10**10000
        self.assertTrue(validator.validate_watch_spec(huge_price))

        for label, parent, field, value in (
            ("task id", "task_binding", "existing_task_id", "x" * 301),
            ("variant", "query", "variants", ["x" * 101]),
            ("locality", "scope", "locality", "x" * 121),
            (
                "eligibility",
                "conditions",
                "eligibility_assertions",
                ["x" * 101],
            ),
            ("merchant", "sources", "allowed_merchants", ["x" * 201]),
        ):
            candidate = copy.deepcopy(fixture)
            candidate[parent][field] = value
            if label == "task id":
                candidate["task_binding"]["action"] = "update"
            if label == "locality":
                candidate["scope"]["location_precision"] = "city"
            candidate["confirmation"]["approved_spec_digest"] = (
                validator.approval_digest(candidate)
            )
            with self.subTest(label=label):
                self.assertTrue(validator.validate_watch_spec(candidate))

        for value in (float("nan"), float("inf"), float("-inf")):
            candidate = copy.deepcopy(fixture)
            candidate["economics"]["maximum_effective_price"] = value
            with self.subTest(non_finite=value):
                self.assertTrue(validator.validate_watch_spec(candidate))

        for value in ("2026-09-14", "2026-09-14T15:00:00"):
            candidate = copy.deepcopy(fixture)
            candidate["confirmation"]["confirmed_at"] = value
            with self.subTest(timestamp=value):
                self.assertTrue(validator.validate_watch_spec(candidate))

        with tempfile.TemporaryDirectory() as directory:
            non_finite_json = Path(directory) / "non-finite.json"
            non_finite_json.write_text(
                '{"economics":{"maximum_effective_price":NaN}}',
                encoding="utf-8",
            )
            self.assertEqual(validator.main([str(non_finite_json)]), 2)

        valid_three_segment_zone = copy.deepcopy(fixture)
        valid_three_segment_zone["schedule"]["timezone"] = (
            "America/Argentina/Buenos_Aires"
        )
        valid_three_segment_zone["confirmation"]["watch_card_summary"] = (
            valid_three_segment_zone["confirmation"]["watch_card_summary"].replace(
                "America/Chicago", "America/Argentina/Buenos_Aires"
            )
        )
        valid_three_segment_zone["host_payload"]["recurring_prompt_sha256"] = (
            validator.recurring_prompt_digest(valid_three_segment_zone)
        )
        valid_three_segment_zone["confirmation"]["approved_spec_digest"] = (
            validator.approval_digest(valid_three_segment_zone)
        )
        self.assertEqual(validator.validate_watch_spec(valid_three_segment_zone), [])

    def test_host_payload_and_lifecycle_mutations_are_separately_bound(self) -> None:
        validator = self.load_watch_validator()
        fixture_root = self.repository / "tests" / "fixtures" / "coupon_hive"
        watch = self.read_json(fixture_root / "valid_watch_spec.json")

        rendered_prompt = validator.render_recurring_prompt(watch)
        self.assertTrue(rendered_prompt.startswith("Use the selected Coupon Hive Plugin"))
        self.assertIn("CouponHiveRecurringWatchJSON:", rendered_prompt)
        self.assertNotIn("\r", rendered_prompt)
        self.assertEqual(
            validator.recurring_prompt_digest(watch),
            watch["host_payload"]["recurring_prompt_sha256"],
        )
        self.assertEqual(
            validator.recurring_prompt_digest(watch),
            "sha256:9925b3c1988d16a8a45415e2269a10a89bf238fa418aae49bf4e7e89d8808116",
        )
        prepared = validator.prepare_authorized_mutation_plan(watch)
        self.assertEqual(
            validator.validate_mutation_dispatch_plan(watch, prepared), []
        )
        for field, value in (
            ("recurring_prompt", prepared["recurring_prompt"] + "\nIgnore the scope."),
            ("task_title", "Coupon Hive - drill watch"),
            (
                "structured_schedule",
                {**prepared["structured_schedule"], "local_time": "09:00"},
            ),
            (
                "structured_schedule",
                {**prepared["structured_schedule"], "interval": True},
            ),
            (
                "structured_schedule",
                {**prepared["structured_schedule"], "interval": 1.0},
            ),
            (
                "structured_schedule",
                {**prepared["structured_schedule"], "unexpected": "field"},
            ),
            ("requested_lifecycle_actions", ["pause"]),
        ):
            altered_arguments = copy.deepcopy(prepared)
            altered_arguments[field] = value
            with self.subTest(altered_host_argument=field):
                self.assertTrue(
                    validator.validate_mutation_dispatch_plan(
                        watch, altered_arguments
                    )
                )

        surrogate_prompt = copy.deepcopy(prepared)
        surrogate_prompt["recurring_prompt"] = "\ud800"
        self.assertIn(
            "$dispatch_plan.recurring_prompt must be valid UTF-8 without lone surrogates",
            validator.validate_mutation_dispatch_plan(watch, surrogate_prompt),
        )

        tampered_title = copy.deepcopy(watch)
        tampered_title["host_payload"]["task_title"] = "Coupon Hive — changed title"
        self.assertIn(
            "$.confirmation.approved_spec_digest does not match the scheduled settings",
            validator.validate_watch_spec(tampered_title),
        )

        stale_prompt_hash = copy.deepcopy(watch)
        stale_prompt_hash["query"]["description"] = "different target"
        stale_prompt_hash["confirmation"]["approved_spec_digest"] = (
            validator.approval_digest(stale_prompt_hash)
        )
        self.assertIn(
            "$.host_payload.recurring_prompt_sha256 does not match the exact rendered prompt bytes",
            validator.validate_watch_spec(stale_prompt_hash),
        )

        unapproved_pause = copy.deepcopy(watch)
        unapproved_pause["host_payload"]["requested_lifecycle_actions"] = ["pause"]
        self.assertTrue(validator.validate_watch_spec(unapproved_pause))

        lifecycle_schema = self.read_json(
            self.skill / "references" / "lifecycle-spec.schema.json"
        )
        self.assertFalse(lifecycle_schema["additionalProperties"])
        self.assertEqual(
            set(
                lifecycle_schema["properties"]["mutation"]["properties"]["action"][
                    "enum"
                ]
            ),
            {"pause", "resume", "delete"},
        )

        lifecycle = self.read_json(fixture_root / "valid_lifecycle_spec.json")
        observation = self.read_json(
            fixture_root / "valid_lifecycle_observation.json"
        )
        lifecycle_receipt = self.read_json(
            fixture_root / "valid_lifecycle_receipt.json"
        )
        self.assertEqual(validator.validate_lifecycle_spec(lifecycle), [])
        self.assertEqual(
            validator.validate_observed_lifecycle_target(lifecycle, observation), []
        )
        prepared_lifecycle = validator.prepare_authorized_lifecycle_plan(
            lifecycle, observation
        )
        self.assertEqual(
            validator.validate_lifecycle_dispatch_plan(
                lifecycle, observation, prepared_lifecycle
            ),
            [],
        )
        self.assertEqual(
            validator.validate_lifecycle_receipt(
                lifecycle, observation, lifecycle_receipt
            ),
            [],
        )
        wrong_lifecycle_arguments = copy.deepcopy(prepared_lifecycle)
        wrong_lifecycle_arguments["action"] = "delete"
        self.assertTrue(
            validator.validate_lifecycle_dispatch_plan(
                lifecycle, observation, wrong_lifecycle_arguments
            )
        )

        stale_state_arguments = copy.deepcopy(prepared_lifecycle)
        stale_state_arguments["observed_current_state"] = "paused"
        self.assertTrue(
            validator.validate_lifecycle_dispatch_plan(
                lifecycle, observation, stale_state_arguments
            )
        )

        self.assertTrue(
            validator.validate_observed_lifecycle_target(lifecycle, None)
        )
        for field, value in (
            ("host_surface", "codex_skill"),
            ("existing_task_id", "different-task"),
            ("task_title", "Coupon Hive — different watch"),
            ("observed_current_state", "paused"),
            ("observed_at", "2026-09-14T14:59:59Z"),
        ):
            stale_observation = copy.deepcopy(observation)
            stale_observation[field] = value
            with self.subTest(stale_observation=field):
                self.assertTrue(
                    validator.validate_observed_lifecycle_target(
                        lifecycle, stale_observation
                    )
                )

        for field, value in (
            ("status", "failed"),
            ("task_id", "different-task"),
            ("action", "delete"),
            ("final_state", "active"),
            ("received_at", "2026-09-14T15:00:59Z"),
        ):
            bad_receipt = copy.deepcopy(lifecycle_receipt)
            bad_receipt[field] = value
            with self.subTest(bad_lifecycle_receipt=field):
                self.assertTrue(
                    validator.validate_lifecycle_receipt(
                        lifecycle, observation, bad_receipt
                    )
                )

        tampered_lifecycle = copy.deepcopy(lifecycle)
        tampered_lifecycle["mutation"]["action"] = "delete"
        errors = validator.validate_lifecycle_spec(tampered_lifecycle)
        self.assertIn(
            "$.confirmation.approved_mutation_digest does not match the lifecycle mutation",
            errors,
        )
        self.assertIn(
            "$.mutation.expected_final_state does not match the requested action",
            errors,
        )

        for field in ("host_surface", "action", "expected_current_state"):
            hostile = copy.deepcopy(lifecycle)
            hostile["mutation"][field] = {}
            with self.subTest(hostile_lifecycle_field=field):
                self.assertTrue(validator.validate_lifecycle_spec(hostile))

        for field, value in (
            ("task_title", "Coupon Hive — household watch "),
            ("task_title", "Coupon Hive — household\u2028watch"),
            ("existing_task_id", "task\u200b-fixture-lifecycle"),
            ("expected_current_state", "paused"),
        ):
            hostile = copy.deepcopy(lifecycle)
            hostile["mutation"][field] = value
            hostile["confirmation"]["approved_mutation_digest"] = (
                validator.lifecycle_approval_digest(hostile)
            )
            with self.subTest(unsafe_lifecycle_field=field, value=repr(value)):
                self.assertTrue(validator.validate_lifecycle_spec(hostile))

    def test_free_and_evidence_taxonomies_are_consistent(self) -> None:
        skill_text = (self.skill / "SKILL.md").read_text(encoding="utf-8")
        verification = (
            self.skill / "references" / "offer-verification.md"
        ).read_text(encoding="utf-8")
        legacy = (self.legacy / "INSTRUCTIONS.md").read_text(encoding="utf-8")
        combined = "\n".join((skill_text, verification, legacy))
        for state in (
            "verified_current",
            "corroborated",
            "unverified_lead",
            "expired_or_ineligible",
            "quarantined",
        ):
            self.assertIn(state, combined)
        for classification in (
            "free_now",
            "free_with_purchase",
            "free_after_rebate",
            "free_trial",
            "bogo",
            "free_sample",
            "sweepstakes",
            "loyalty_or_account_required",
            "deposit_or_authorization_required",
            "unknown",
        ):
            self.assertIn(classification, combined)
        self.assertIn(
            "Only verified_current plus free_now",
            verification,
        )
        self.assertIn("aggregator-only code cannot be verified_current", verification)
        self.assertIn("unknown mandatory shipping or fee amount cannot be treated as zero", verification)
        self.assertIn("account creation, marketing consent, loyalty-point redemption", verification)

    def test_confirmation_receipt_and_quiet_run_boundaries_are_explicit(self) -> None:
        schedule = (
            self.skill / "references" / "scheduled-task-template.md"
        ).read_text(encoding="utf-8")
        skill_text = (self.skill / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "user's explicit confirmation",
            "successful receipt",
            "Stay quiet when nothing actionable changed",
            "No recurring task was created",
            "Scheduled Tasks are not supported inside a Custom GPT",
            "fail closed",
            "Use one WatchSpec per independently scheduled target",
            "never create a replacement as a shortcut",
            "remaining live state",
        ):
            self.assertIn(phrase, schedule)
        self.assertIn("$coupon-hive", schedule)
        self.assertIn("Coupon Hive Plugin in ChatGPT", schedule)
        self.assertIn("claims that a task exists without a host-generated receipt", skill_text)

    def test_prompt_injection_privacy_and_abuse_controls_are_present(self) -> None:
        safety = (
            self.skill / "references" / "safety-privacy.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "untrusted evidence",
            "confirmed WatchSpec",
            "full addresses",
            "payment card",
            "one-time codes",
            "government identifiers",
            "gift card",
            "brute-forcing codes",
            "access-control bypass",
            "publisher-operated server",
        ):
            self.assertIn(phrase, safety)

    def test_privacy_terms_support_and_store_material_are_complete_drafts(self) -> None:
        for name in ("PRIVACY.md", "TERMS.md", "SUPPORT.md"):
            path = self.plugin / name
            self.assertTrue(path.is_file(), path)
            text = path.read_text(encoding="utf-8")
            self.assertGreater(len(text), 500)
            self.assertNotIn("[TODO:", text)

        privacy = (self.plugin / "PRIVACY.md").read_text(encoding="utf-8")
        self.assertIn("zero days", privacy)
        self.assertIn("no Coupon Hive backend receives the data", privacy)
        listing = (self.plugin / "submission" / "listing.md").read_text(encoding="utf-8")
        self.assertIn("Publication blockers", listing)
        self.assertNotIn("ultimate coupon finder", listing.lower())
        self.assertNotIn("research products, services", listing.lower())
        release = (
            self.plugin / "submission" / "release-notes.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Known limitations", release)
        self.assertIn("Deferred", release)
        readme = (self.plugin / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("C:/Users/", readme)
        self.assertNotIn("C:\\Users\\", readme)

    def test_submission_has_exact_required_case_inventory(self) -> None:
        cases = self.read_json(self.plugin / "submission" / "test-cases.json")
        self.assertEqual(cases["plugin_version"], "0.1.0")
        self.assertEqual(len(cases["positive"]), 5)
        self.assertEqual(len(cases["negative"]), 4)
        identifiers = [
            case["id"]
            for group in ("positive", "negative")
            for case in cases[group]
        ]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        for case in cases["positive"]:
            self.assertTrue(case["user_prompt"].strip(), case["id"])
            self.assertGreaterEqual(
                len(case["expected_workflow_behavior"]), 4, case["id"]
            )
            self.assertTrue(case["expected_result_shape"], case["id"])
            self.assertTrue(case["required_fixture_data"], case["id"])
            self.assertTrue(case["portal_setup"].strip(), case["id"])
            self.assertNotIn("fixture", case["user_prompt"].lower())
        for case in cases["negative"]:
            self.assertTrue(case["user_prompt_or_scenario"].strip(), case["id"])
            self.assertGreaterEqual(len(case["expected_safe_behavior"]), 3, case["id"])
            self.assertTrue(case["why_not_act"].strip(), case["id"])
            self.assertTrue(case["required_fixture_data"], case["id"])
            self.assertTrue(case["portal_setup"].strip(), case["id"])
        fixtures = self.read_json(
            self.plugin / "submission" / "fixtures" / "evaluation-fixtures.json"
        )
        for identifier in identifiers:
            self.assertIn(identifier, fixtures)
        negative_text = json.dumps(cases["negative"]).lower()
        self.assertIn("prompt injection", negative_text)
        self.assertIn("hidden payment", negative_text)
        self.assertIn("unauthorized code", negative_text)
        self.assertIn("source disallows automated access", negative_text)

    def test_submission_watch_specs_are_complete_and_semantically_valid(self) -> None:
        validator = self.load_watch_validator()
        fixture_root = self.plugin / "submission" / "fixtures"
        names = {
            "pos-003-watch-spec.json",
            "pos-004-laptop-watch-spec.json",
            "pos-004-monitor-watch-spec.json",
            "pos-005-original-watch-spec.json",
            "pos-005-updated-watch-spec.json",
        }
        for name in names:
            with self.subTest(name=name):
                payload = self.read_json(fixture_root / name)
                self.assertEqual(validator.validate_watch_spec(payload), [])
                self.assertEqual(
                    payload["host_payload"]["recurring_prompt_sha256"],
                    validator.recurring_prompt_digest(payload),
                )

        fixtures = self.read_json(fixture_root / "evaluation-fixtures.json")
        self.assertEqual(
            fixtures["POS-004"]["clarified_schedules"]["refurbished laptop"],
            "weekly Monday at 09:00 America/New_York",
        )
        self.assertEqual(
            fixtures["POS-005"]["clarified_update_schedule"],
            "weekly Monday at 08:00 America/Chicago",
        )
        pos003 = self.read_json(fixture_root / "pos-003-watch-spec.json")
        self.assertEqual(pos003["notification"]["events"], ["new_verified_match"])
        self.assertIsNone(pos003["notification"]["minimum_price_improvement"])

        def assert_payload_summary_matches(spec: dict, summary: dict) -> None:
            for field in (
                "task_title",
                "host_surface",
                "prompt_template_id",
                "recurring_prompt_sha256",
                "requested_lifecycle_actions",
            ):
                self.assertEqual(summary[field], spec["host_payload"][field], field)
            self.assertEqual(summary["structured_schedule"], spec["schedule"])
            self.assertEqual(
                summary["approval_digest"],
                spec["confirmation"]["approved_spec_digest"],
            )
            dispatch_plan = validator.prepare_authorized_mutation_plan(spec)
            self.assertEqual(
                validator.validate_mutation_dispatch_plan(spec, dispatch_plan), []
            )

        assert_payload_summary_matches(
            pos003, fixtures["POS-003"]["confirmed_payload_summary"]
        )
        self.assertEqual(
            fixtures["POS-003"]["task_create_receipt"]["task_name"],
            pos003["host_payload"]["task_title"],
        )

        for target, spec_name in fixtures["POS-004"]["confirmed_watch_specs"].items():
            spec = self.read_json(fixture_root / spec_name)
            assert_payload_summary_matches(
                spec, fixtures["POS-004"]["confirmed_payload_summaries"][target]
            )
            receipt = next(
                item
                for item in fixtures["POS-004"]["host_outcomes"]
                if item["target"] == target
            )
            self.assertEqual(receipt["task_name"], spec["host_payload"]["task_title"])

        original = self.read_json(fixture_root / "pos-005-original-watch-spec.json")
        updated = self.read_json(fixture_root / "pos-005-updated-watch-spec.json")
        for field in (
            "query",
            "scope",
            "economics",
            "accepted_offer_types",
            "conditions",
            "sources",
            "notification",
        ):
            self.assertEqual(original[field], updated[field], field)
        for field in (
            "interval",
            "local_time",
            "minute",
            "day_of_month",
            "timezone",
            "quiet_hours",
            "ends_at",
            "maximum_runs",
        ):
            self.assertEqual(original["schedule"][field], updated["schedule"][field], field)
        self.assertEqual(updated["task_binding"]["action"], "update")
        self.assertEqual(
            updated["task_binding"]["existing_task_id"], "task-fixture-005"
        )
        self.assertEqual(
            original["host_payload"]["requested_lifecycle_actions"], []
        )
        self.assertEqual(
            updated["host_payload"]["requested_lifecycle_actions"], ["pause"]
        )
        assert_payload_summary_matches(
            updated, fixtures["POS-005"]["confirmed_payload_summary"]
        )
        self.assertEqual(
            fixtures["POS-005"]["confirmed_payload_summary"]["task_id"],
            updated["task_binding"]["existing_task_id"],
        )
        self.assertTrue(
            all(
                outcome["task_name"] == updated["host_payload"]["task_title"]
                for outcome in fixtures["POS-005"]["host_outcomes"]
            )
        )
        update_receipt = fixtures["POS-005"]["normalized_update_receipt"]
        self.assertEqual(
            validator.validate_compound_update_receipt(updated, update_receipt), []
        )
        compound_lifecycle_receipt = fixtures["POS-005"][
            "normalized_lifecycle_receipt"
        ]
        self.assertEqual(
            validator.validate_compound_lifecycle_receipt(
                updated, update_receipt, compound_lifecycle_receipt
            ),
            [],
        )
        for field, value in (
            ("status", "failed"),
            ("task_id", "different-task"),
            ("task_title", "Coupon Hive — different watch"),
            (
                "structured_schedule",
                {**updated["schedule"], "local_time": "09:00"},
            ),
        ):
            bad_receipt = copy.deepcopy(update_receipt)
            bad_receipt[field] = value
            with self.subTest(bad_compound_receipt=field):
                self.assertTrue(
                    validator.validate_compound_update_receipt(
                        updated, bad_receipt
                    )
                )
        for field, value in (
            ("status", "failed"),
            ("task_id", "different-task"),
            ("task_title", "Coupon Hive — different watch"),
            ("action", "resume"),
            ("final_state", "active"),
            ("received_at", "2026-09-14T15:01:59Z"),
        ):
            bad_receipt = copy.deepcopy(compound_lifecycle_receipt)
            bad_receipt[field] = value
            with self.subTest(bad_compound_lifecycle_receipt=field):
                self.assertTrue(
                    validator.validate_compound_lifecycle_receipt(
                        updated, update_receipt, bad_receipt
                    )
                )

        local_cases = self.read_json(
            self.plugin / "submission" / "local-adversarial-cases.json"
        )
        self.assertTrue(local_cases["not_for_portal"])
        self.assertEqual(
            {case["id"] for case in local_cases["cases"]},
            {"LOCAL-PARTIAL-001", "LOCAL-PARTIAL-COMPOUND-001"},
        )

        partial_compound = fixtures["LOCAL-PARTIAL-COMPOUND-001"]
        partial_spec = self.read_json(
            fixture_root / partial_compound["confirmed_watch_spec"]
        )
        partial_update = partial_compound["normalized_update_receipt"]
        partial_pause = partial_compound["normalized_lifecycle_failure"]
        self.assertEqual(
            validator.validate_compound_update_receipt(partial_spec, partial_update),
            [],
        )
        self.assertTrue(
            validator.validate_compound_lifecycle_receipt(
                partial_spec, partial_update, partial_pause
            )
        )
        self.assertEqual(partial_pause["status"], "failed")
        self.assertEqual(partial_pause["action"], "pause")
        self.assertEqual(partial_pause["final_state"], "active")
        self.assertEqual(
            partial_compound["expected_remaining_state"],
            {
                "task_id": "task-fixture-005",
                "task_title": "Coupon Hive — portal household watch",
                "schedule": "weekly Monday at 08:00 America/Chicago",
                "state": "active",
            },
        )
        required_response = "\n".join(partial_compound["required_response"])
        for required_phrase in (
            "update succeeded",
            "pause failed",
            "remains active",
            "Do not automatically retry",
            "fresh listing",
            "explicit confirmation",
        ):
            self.assertIn(required_phrase, required_response)

        lifecycle_case = fixtures["LOCAL-LIFECYCLE-001"]
        lifecycle_spec = self.read_json(
            fixture_root / lifecycle_case["confirmed_lifecycle_spec"]
        )
        lifecycle_observation = self.read_json(
            fixture_root / lifecycle_case["fresh_host_observation"]
        )
        lifecycle_receipt = self.read_json(
            fixture_root / lifecycle_case["host_receipt"]
        )
        self.assertEqual(validator.validate_lifecycle_spec(lifecycle_spec), [])
        self.assertEqual(
            validator.validate_observed_lifecycle_target(
                lifecycle_spec, lifecycle_observation
            ),
            [],
        )
        lifecycle_plan = validator.prepare_authorized_lifecycle_plan(
            lifecycle_spec, lifecycle_observation
        )
        self.assertEqual(
            validator.validate_lifecycle_dispatch_plan(
                lifecycle_spec, lifecycle_observation, lifecycle_plan
            ),
            [],
        )
        self.assertEqual(
            validator.validate_lifecycle_receipt(
                lifecycle_spec, lifecycle_observation, lifecycle_receipt
            ),
            [],
        )

    def test_legacy_gpt_is_ready_to_paste_but_cannot_claim_scheduling(self) -> None:
        builder = (self.legacy / "BUILDER.md").read_text(encoding="utf-8")
        instructions = (self.legacy / "INSTRUCTIONS.md").read_text(encoding="utf-8")
        knowledge = (self.legacy / "KNOWLEDGE.md").read_text(encoding="utf-8")
        self.assertIn("legacy Custom GPT configuration", builder)
        self.assertIn("Scheduled Tasks are not supported", builder)
        self.assertIn("no task has been created", instructions)
        self.assertIn("ready-to-paste prompt", instructions)
        self.assertIn("inert", instructions)
        self.assertIn("fresh explicit confirmation", instructions)
        self.assertIn("approval in the GPT does not transfer", builder)
        self.assertLessEqual(len(instructions), 8000)
        self.assertIn("Stable duplicate fingerprint", knowledge)
        self.assertNotIn("[TODO:", "\n".join((builder, instructions, knowledge)))

    def test_atomic_requirements_reference_preserved_sources(self) -> None:
        requirements = self.read_json(self.plan / "requirements.json")
        source_ledger = (self.plan / "SOURCES.md").read_text(encoding="utf-8")
        ids = [item["id"] for item in requirements["requirements"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 16)
        for requirement in requirements["requirements"]:
            self.assertIn(
                requirement["disposition"],
                {"adopt", "adapt", "defer", "reject", "quarantine"},
            )
            self.assertTrue(requirement["sources"], requirement["id"])
            for source_id in requirement["sources"]:
                self.assertIn(source_id, source_ledger, requirement["id"])
        self.assertIn("Open evidence obligations", source_ledger)

        claims = self.read_json(self.plan / "CLAIMS.json")["claims"]
        self.assertEqual(
            {claim["requirement"] for claim in claims},
            set(ids),
        )
        self.assertEqual(len(claims), len(ids))
        for claim in claims:
            self.assertIn(
                claim["disposition"],
                {"adopt", "adapt", "defer", "reject", "quarantine"},
            )
            for field in (
                "advocate_case",
                "cross_examination",
                "implementation",
                "acceptance",
                "outcome_metric",
                "rollback",
                "owner",
            ):
                self.assertTrue(claim[field], f"{claim['id']}:{field}")

        receipts = self.read_json(self.plan / "RETRIEVAL_RECEIPTS.json")
        self.assertFalse(receipts["raw_snapshots_retained"])
        self.assertEqual(
            {receipt["source_id"] for receipt in receipts["receipts"]},
            {f"SRC-CH-{number:03d}" for number in range(6, 16)},
        )
        self.assertIn("OBL-CH-007", source_ledger)

    def test_independent_evaluation_is_complete_without_claiming_live_execution(self) -> None:
        cases = self.read_json(self.plugin / "submission" / "test-cases.json")
        results = self.read_json(
            self.plugin / "submission" / "evaluation-results.json"
        )
        expected_ids = {
            case["id"]
            for group in ("positive", "negative")
            for case in cases[group]
        }
        self.assertEqual(
            {result["id"] for result in results["cases"]},
            expected_ids,
        )
        self.assertTrue(all(result["verdict"] == "pass" for result in results["cases"]))
        self.assertEqual(results["summary"]["fixture_cases_passed"], 9)
        self.assertEqual(
            results["summary"]["public_submission"],
            "quarantine_pending_live_and_external_receipts",
        )
        exclusions = "\n".join(results["explicit_exclusions"])
        self.assertIn("No live target ChatGPT model run", exclusions)
        self.assertIn("No ChatGPT Scheduled Task or Codex automation", exclusions)

    def test_court_record_preserves_roles_dissent_and_publication_quarantine(self) -> None:
        court = (self.plan / "COURT_RECORD.md").read_text(encoding="utf-8")
        for identity in (
            "/root/repo_explorer",
            "/root/product_architect",
            "/root/advocate",
            "/root/cross_examiner",
            "/root/authority_auditor",
            "/root/forward_curator",
            "/root/integrator",
            "/root/steward",
            "/root/curator_optimizer",
            "/root/expert_witness",
            "/root/release_judge",
        ):
            self.assertIn(identity, court)
        self.assertIn("Remaining dissent is not resolved by local tests", court)
        self.assertIn("quarantine | CLM-CH-011", court)
        self.assertIn("reject | CLM-CH-012", court)

    def test_product_architecture_and_rollback_preserve_truth_boundaries(self) -> None:
        architecture = (self.plan / "ARCHITECTURE.md").read_text(encoding="utf-8")
        threat_model = (self.plan / "THREAT_MODEL.md").read_text(encoding="utf-8")
        rollback = (self.plan / "ROLLBACK.md").read_text(encoding="utf-8")
        self.assertIn("no publisher-operated state", architecture.lower())
        self.assertIn("No schedule success is reported without a host receipt", architecture)
        self.assertIn("Merchant-page prompt injection", threat_model)
        self.assertIn("Unbounded or unauthorized search load", threat_model)
        self.assertIn("Plugin removal does not necessarily pause or delete tasks", rollback)
        self.assertIn("future remote service", architecture)


if __name__ == "__main__":
    unittest.main()
