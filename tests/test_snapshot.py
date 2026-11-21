"""Reduced numbers for the example data must not change.

The snapshot uses fixed-seed synthetic inputs. Regenerate it only for an
intentional numeric update with tools/generate_synthetic_fixtures.py.
"""
import json
import math
import re
import unittest

from snapshot_support import OUTPUT, reduce_variants

# Max relative drift vs the Python 3.12 snapshot: 8.8e-11 on Python 3.10
# (numpy 2.2.6/scipy 1.15.3/pandas 2.3.3), 2.3e-11 on Python 3.14
# (numpy 2.5.5/scipy 1.18.1/pandas 3.1.1, also used on 3.12), worst in
# th_correction_covariance.
RTOL = 1e-9
ATOL = 1e-300
# Near-zero sensitivity drift: 1.3e-29 absolute on Python 3.10
# (numpy 2.2.6/scipy 1.15.3/pandas 2.3.3) vs Python 3.12
# (numpy 2.5.5/scipy 1.18.1/pandas 3.1.1). The smallest snapshot
# sensitivity magnitude above 1e-20 is 1.846e-18, over 1e6 times this floor.
SENSITIVITY_ATOL = 1e-24
SENSITIVITY_NAME = re.compile(r"d[A-Za-z][A-Za-z0-9]*_d[A-Za-z][A-Za-z0-9]*")


def _close(a, b, atol):
    if isinstance(a, list):
        return (isinstance(b, list) and len(a) == len(b)
                and all(_close(x, y, atol) for x, y in zip(a, b)))
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return math.isclose(a, b, rel_tol=RTOL, abs_tol=atol)


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
                        atol = SENSITIVITY_ATOL if SENSITIVITY_NAME.fullmatch(name) else ATOL
                        self.assertTrue(_close(value, got[name], atol),
                                        f"{name}: snapshot {value!r}, now {got[name]!r}")


if __name__ == "__main__":
    unittest.main()
