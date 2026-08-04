from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from hive_mind_os import cli


class DemoCliTests(unittest.TestCase):
    def test_demo_repairs_the_fixture_and_prints_a_concise_honest_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary) / "receipt-bundle"
            stdout = io.StringIO()
            with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
                cli.main(("demo", "--output", str(output_dir)))

            self.assertEqual(raised.exception.code, 0)
            lines = stdout.getvalue().splitlines()
            self.assertLess(len(lines), 20)
            self.assertIn("Fixture regression repaired", lines[0])
            self.assertIn("Curator re-ran the sealed checks", lines[1])
            self.assertIn("does not inspect or repair arbitrary repositories", lines[-1])
            self.assertTrue((output_dir / "changes.patch").is_file())
            self.assertTrue((output_dir / "delivery.json").is_file())

    def test_deliver_names_the_fixture_only_backend(self) -> None:
        parser = cli.build_deliver_parser()
        args = parser.parse_args(
            (
                "--repository",
                "repository",
                "--objective",
                "objective",
            )
        )

        self.assertEqual(args.backend, "fixture-demo")
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit):
            parser.parse_args(
                (
                    "--repository",
                    "repository",
                    "--objective",
                    "objective",
                    "--backend",
                    "scripted",
                )
            )
        self.assertIn("invalid choice", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
