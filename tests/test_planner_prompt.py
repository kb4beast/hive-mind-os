import hashlib
import unittest

from hive_mind_os.planner_prompt import planner_prompt, planner_prompt_artifact


class PlannerPromptTests(unittest.TestCase):
    def test_original_prompt_is_content_addressed_inert_and_generic(self) -> None:
        prompt = planner_prompt()
        artifact = planner_prompt_artifact()
        self.assertEqual("MIT", artifact["license"])
        self.assertEqual(len(prompt.encode("utf-8")), artifact["bytes"])
        self.assertEqual(
            "sha256:" + hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            artifact["sha256"],
        )
        self.assertFalse(artifact["execution_authorized"])
        self.assertIn("discover, design, build, validate", prompt)
        for forbidden in ("kb4beast", "GitHub", "release/hive-mind-autopilot", "BASELINE-000"):
            self.assertNotIn(forbidden, prompt)

    def test_prompt_requires_separation_blockers_and_no_commands(self) -> None:
        prompt = planner_prompt()
        self.assertIn("Separate builder, verifier, integrator, and judge", prompt)
        self.assertIn("typed blocker", prompt)
        self.assertIn("do not include commands", prompt)


if __name__ == "__main__":
    unittest.main()
