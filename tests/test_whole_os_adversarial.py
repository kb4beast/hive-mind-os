import unittest

from hive_mind_os.whole_os_adversarial import Canary, CanaryScanner


class WholeOSAdversarialTests(unittest.TestCase):
    def test_split_and_encoded_canaries_are_detected(self):
        scanner = CanaryScanner((Canary("secret", b"alpha-bravo"),))
        self.assertIn("secret", scanner.scan({"a": b"alpha-", "b": b"bravo"}))
        self.assertIn("secret", scanner.scan({"encoded": b"YWxwaGEtYnJhdm8="}))

    def test_clean_export_is_admitted(self):
        CanaryScanner((Canary("secret", b"alpha-bravo"),)).require_clean(
            {"lesson.md": b"abstract retry guidance"}
        )


if __name__ == "__main__":
    unittest.main()
