import unittest

from tiny_pkg.maths import increment


class MathsTests(unittest.TestCase):
    def test_documented_example(self) -> None:
        self.assertEqual(increment(1), 2)


if __name__ == "__main__":
    unittest.main()
