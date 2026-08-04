from __future__ import annotations

import argparse
import asyncio
import io
import os
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from hive_mind_os import cli
from hive_mind_os.models import Role


class DeliverProviderConfigurationTests(unittest.TestCase):
    def test_deliver_help_exposes_non_secret_provider_overrides(self) -> None:
        help_text = cli.build_deliver_parser().format_help()
        for flag in ("--provider", "--base-url", "--model"):
            with self.subTest(flag=flag):
                self.assertIn(flag, help_text)
        self.assertNotIn("--api-key", help_text)

    def test_flags_override_environment_for_primary_and_curator(self) -> None:
        arguments = argparse.Namespace(
            provider="openai_compatible",
            base_url="https://flags.example/v1",
            model="flag-model",
        )
        environment = {
            "HIVE_MIND_MODEL_PROVIDER": "anthropic",
            "HIVE_MIND_MODEL_BASE_URL": "https://environment.example/v1",
            "HIVE_MIND_MODEL_MODEL": "environment-model",
            "HIVE_MIND_MODEL_PROVIDER__CURATOR": "anthropic",
            "HIVE_MIND_MODEL_BASE_URL__CURATOR": "https://curator.example/v1",
            "HIVE_MIND_MODEL_MODEL__CURATOR": "curator-model",
            "OPENAI_API_KEY": "test-key",
        }
        with patch.dict(os.environ, environment, clear=True):
            primary = cli._provider_from_arguments(arguments)
            curator = cli._provider_from_arguments(arguments, role=Role.CURATOR)
        for provider in (primary, curator):
            self.assertEqual(provider.config.base_url, "https://flags.example/v1")
            self.assertEqual(provider.config.model, "flag-model")

    def test_model_configuration_lists_each_missing_variable(self) -> None:
        arguments = argparse.Namespace(
            state_dir=None,
            backend="model",
            provider=None,
            base_url=None,
            model=None,
        )
        error = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), redirect_stderr(error):
            self.assertEqual(asyncio.run(cli._run_deliver(arguments)), 1)
        rendered = error.getvalue()
        self.assertIn("HIVE_MIND_MODEL_MODEL", rendered)
        self.assertIn("OPENAI_API_KEY", rendered)

    def test_experiment_run_fails_until_a_real_evaluation_surface_exists(self) -> None:
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(cli._run_experiment(argparse.Namespace()), 1)
        self.assertIn("evaluation surface not implemented", error.getvalue())


if __name__ == "__main__":
    unittest.main()
