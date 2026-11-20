"""Reduced numbers for the example data must not change.

The snapshot uses fixed-seed synthetic inputs. Regenerate it only for an
intentional numeric update with tools/generate_synthetic_fixtures.py.
"""
import json
import math
import unittest

from snapshot_support import OUTPUT, reduce_variants

RTOL = 1e-12
ATOL = 1e-300


def _close(a, b):
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return math.isclose(a, b, rel_tol=RTOL, abs_tol=ATOL)


class SnapshotTests(unittest.TestCase):
    def test_example_reduction_matches_snapshot(self):
        expected = json.loads(OUTPUT.read_text())
        actual = reduce_variants()
        self.assertEqual(sorted(expected), sorted(actual))
        for variant, grains in expected.items():
            self.assertEqual(sorted(grains), sorted(actual[variant]), variant)
            for grain, numbers in grains.items():
                got = actual[variant][grain]
                missing = sorted(set(numbers) - set(got))
                self.assertFalse(missing, f"{variant}/{grain} lost attributes {missing}")
                for name, value in numbers.items():
                    with self.subTest(variant=variant, grain=grain, name=name):
                        self.assertTrue(_close(value, got[name]),
                                        f"{name}: snapshot {value!r}, now {got[name]!r}")


if __name__ == "__main__":
    unittest.main()
